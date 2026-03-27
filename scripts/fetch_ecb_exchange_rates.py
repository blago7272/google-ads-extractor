#!/usr/bin/env python3
"""Fetch daily EUR exchange rates from the ECB and update cfg_exchange_rates.csv.

Usage:
    # Fetch latest rates (last 90 days)
    python scripts/fetch_ecb_exchange_rates.py

    # Backfill a specific date range
    python scripts/fetch_ecb_exchange_rates.py --start-date 2024-01-01 --end-date 2024-12-31

    # Fetch specific currencies only
    python scripts/fetch_ecb_exchange_rates.py --currencies USD,GBP,CAD

    # Dry run (print without writing)
    python scripts/fetch_ecb_exchange_rates.py --dry-run

Source: ECB Statistical Data Warehouse (SDMX 2.1 REST API)
Endpoint: https://data-api.ecb.europa.eu/service/data/EXR/D.{currencies}.EUR.SP00.A
No authentication required.
"""

from __future__ import annotations

import argparse
import csv
import io
import ssl
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ECB_BASE_URL = "https://data-api.ecb.europa.eu/service/data/EXR"

# Currencies to fetch by default. Add new currencies here as clients are onboarded.
DEFAULT_CURRENCIES = ["USD", "GBP", "CAD", "BGN", "PLN", "CZK", "RON", "TRY", "CHF"]

# Pegged currencies are maintained as static rows and are never overwritten by
# ECB data. The ECB does publish BGN rates, but the fixed peg is more accurate.
PEGGED_CURRENCIES = {
    "BGN": {
        "eur_exchange_rate": 1.0 / 1.95583,
        "rate_source": "fixed_peg",
        "notes": "Fixed at 1 EUR = 1.95583 BGN",
    },
}

SEED_PATH = Path(__file__).resolve().parent.parent / "seeds" / "cfg_exchange_rates.csv"
SEED_COLUMNS = ["currency", "valid_from", "eur_exchange_rate", "rate_source", "notes"]


def fetch_ecb_rates(
    currencies: list[str],
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, str]]:
    """Fetch daily exchange rates from the ECB SDMX API.

    Returns a list of dicts with keys matching SEED_COLUMNS.
    The ECB rate is "1 EUR = X foreign currency", so eur_exchange_rate = 1/X
    (i.e., how many EUR per 1 unit of foreign currency).
    """
    # Exclude pegged currencies from the API call
    api_currencies = [c for c in currencies if c not in PEGGED_CURRENCIES and c != "EUR"]
    if not api_currencies:
        return []

    currency_key = "+".join(api_currencies)
    url = f"{ECB_BASE_URL}/D.{currency_key}.EUR.SP00.A"

    params = []
    if start_date:
        params.append(f"startPeriod={start_date.isoformat()}")
    if end_date:
        params.append(f"endPeriod={end_date.isoformat()}")
    params.append("format=csvdata")

    if params:
        url += "?" + "&".join(params)

    print(f"Fetching: {url}")

    request = Request(url, headers={"Accept": "text/csv"})
    try:
        with urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        print(f"ECB API error: HTTP {exc.code} — {exc.reason}", file=sys.stderr)
        sys.exit(1)
    except URLError as exc:
        # Retry with default certifi/system certs if SSL fails (common on macOS)
        if "CERTIFICATE_VERIFY_FAILED" in str(exc.reason):
            print("SSL verification failed, retrying with certifi fallback...")
            try:
                import certifi
                ctx = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                ctx = ssl.create_default_context()
            try:
                with urlopen(request, timeout=60, context=ctx) as response:
                    raw = response.read().decode("utf-8")
            except (HTTPError, URLError) as retry_exc:
                print(f"Retry failed: {retry_exc}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"Network error: {exc.reason}", file=sys.stderr)
            sys.exit(1)

    reader = csv.DictReader(io.StringIO(raw))

    results: list[dict[str, str]] = []
    for row in reader:
        currency = row.get("CURRENCY")
        obs_date = row.get("TIME_PERIOD")
        obs_value = row.get("OBS_VALUE")

        if not currency or not obs_date or not obs_value:
            continue

        try:
            ecb_rate = float(obs_value)
        except ValueError:
            continue

        if ecb_rate <= 0:
            continue

        # ECB publishes "1 EUR = X foreign". We store "1 foreign = X EUR".
        eur_exchange_rate = 1.0 / ecb_rate

        results.append({
            "currency": currency,
            "valid_from": obs_date,
            "eur_exchange_rate": str(eur_exchange_rate),
            "rate_source": "ecb_daily",
            "notes": f"ECB reference rate: 1 EUR = {ecb_rate} {currency}",
        })

    print(f"Fetched {len(results)} rate observations for {len(api_currencies)} currencies.")
    return results


def load_existing_seed(path: Path) -> list[dict[str, str]]:
    """Load the existing seed CSV."""
    if not path.exists():
        return []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def merge_rates(
    existing: list[dict[str, str]],
    new_rates: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Merge new rates into existing, deduplicating by (currency, valid_from).

    Pegged currencies are preserved and never overwritten. The EUR base row is
    always preserved.
    """
    # Index existing rows by (currency, valid_from)
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in existing:
        key = (row["currency"], row["valid_from"])
        by_key[key] = row

    # Add or update with new rates, but never overwrite pegged or base rows
    for row in new_rates:
        currency = row["currency"]
        if currency in PEGGED_CURRENCIES or currency == "EUR":
            continue
        key = (currency, row["valid_from"])
        by_key[key] = row

    # Sort: EUR first, then pegged, then alphabetical by currency, then by date
    def sort_key(row: dict[str, str]) -> tuple[int, str, str]:
        currency = row["currency"]
        if currency == "EUR":
            return (0, currency, row["valid_from"])
        if currency in PEGGED_CURRENCIES:
            return (1, currency, row["valid_from"])
        return (2, currency, row["valid_from"])

    return sorted(by_key.values(), key=sort_key)


def write_seed(path: Path, rows: list[dict[str, str]]) -> None:
    """Write the merged rates to the seed CSV."""
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SEED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch ECB exchange rates and update cfg_exchange_rates.csv"
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Start date for backfill (YYYY-MM-DD). Default: last 90 days.",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="End date for backfill (YYYY-MM-DD). Default: today.",
    )
    parser.add_argument(
        "--currencies",
        type=lambda s: [c.strip().upper() for c in s.split(",")],
        default=DEFAULT_CURRENCIES,
        help=f"Comma-separated currencies. Default: {','.join(DEFAULT_CURRENCIES)}",
    )
    parser.add_argument(
        "--seed-path",
        type=Path,
        default=SEED_PATH,
        help=f"Path to the seed CSV. Default: {SEED_PATH}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print fetched rates without writing to the seed file.",
    )
    args = parser.parse_args()

    new_rates = fetch_ecb_rates(
        currencies=args.currencies,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    if args.dry_run:
        print("\n--- Dry run: fetched rates ---")
        for row in new_rates[:20]:
            print(f"  {row['currency']}  {row['valid_from']}  {row['eur_exchange_rate']}")
        if len(new_rates) > 20:
            print(f"  ... and {len(new_rates) - 20} more")
        return

    existing = load_existing_seed(args.seed_path)
    merged = merge_rates(existing, new_rates)
    write_seed(args.seed_path, merged)

    # Summary
    currencies_in_seed = sorted(set(r["currency"] for r in merged))
    date_range = [r["valid_from"] for r in merged if r["currency"] != "EUR" and r["currency"] not in PEGGED_CURRENCIES]
    if date_range:
        print(f"Date range: {min(date_range)} to {max(date_range)}")
    print(f"Currencies: {', '.join(currencies_in_seed)}")


if __name__ == "__main__":
    main()
