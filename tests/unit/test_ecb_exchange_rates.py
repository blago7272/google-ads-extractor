"""Tests for the ECB exchange rate fetcher script."""

from __future__ import annotations

import csv
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the module under test
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.fetch_ecb_exchange_rates import (
    PEGGED_CURRENCIES,
    SEED_COLUMNS,
    load_existing_seed,
    merge_rates,
    write_seed,
)


# ---------------------------------------------------------------------------
# merge_rates
# ---------------------------------------------------------------------------


def _row(currency: str, valid_from: str, rate: str, source: str = "ecb_daily") -> dict[str, str]:
    return {
        "currency": currency,
        "valid_from": valid_from,
        "eur_exchange_rate": rate,
        "rate_source": source,
        "notes": f"test {currency}",
    }


def test_merge_preserves_eur_base():
    existing = [_row("EUR", "1900-01-01", "1.0", "base_currency")]
    new = [_row("EUR", "2026-03-01", "0.99", "ecb_daily")]
    merged = merge_rates(existing, new)
    eur_rows = [r for r in merged if r["currency"] == "EUR"]
    assert len(eur_rows) == 1
    assert eur_rows[0]["eur_exchange_rate"] == "1.0"


def test_merge_preserves_pegged_currencies():
    existing = [
        _row("EUR", "1900-01-01", "1.0", "base_currency"),
        _row("BGN", "1900-01-01", "0.511", "fixed_peg"),
    ]
    new = [_row("BGN", "2026-03-01", "0.510", "ecb_daily")]
    merged = merge_rates(existing, new)
    bgn_rows = [r for r in merged if r["currency"] == "BGN"]
    assert len(bgn_rows) == 1
    assert bgn_rows[0]["rate_source"] == "fixed_peg"


def test_merge_adds_new_currency():
    existing = [_row("EUR", "1900-01-01", "1.0", "base_currency")]
    new = [
        _row("USD", "2026-03-01", "0.92"),
        _row("USD", "2026-03-02", "0.93"),
    ]
    merged = merge_rates(existing, new)
    usd_rows = [r for r in merged if r["currency"] == "USD"]
    assert len(usd_rows) == 2


def test_merge_deduplicates():
    existing = [
        _row("EUR", "1900-01-01", "1.0", "base_currency"),
        _row("USD", "2026-03-01", "0.92"),
    ]
    new = [_row("USD", "2026-03-01", "0.925")]
    merged = merge_rates(existing, new)
    usd_rows = [r for r in merged if r["currency"] == "USD"]
    assert len(usd_rows) == 1
    assert usd_rows[0]["eur_exchange_rate"] == "0.925"


def test_merge_sort_order():
    existing = [_row("EUR", "1900-01-01", "1.0", "base_currency")]
    new = [
        _row("GBP", "2026-03-01", "1.17"),
        _row("USD", "2026-03-01", "0.92"),
        _row("CAD", "2026-03-01", "0.63"),
    ]
    merged = merge_rates(existing, new)
    currencies = [r["currency"] for r in merged]
    # EUR first, then pegged (none here besides existing BGN), then alphabetical
    assert currencies == ["EUR", "CAD", "GBP", "USD"]


# ---------------------------------------------------------------------------
# write_seed / load_existing_seed round-trip
# ---------------------------------------------------------------------------


def test_write_and_load_roundtrip():
    rows = [
        _row("EUR", "1900-01-01", "1.0", "base_currency"),
        _row("USD", "2026-03-01", "0.92"),
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        path = Path(f.name)

    write_seed(path, rows)
    loaded = load_existing_seed(path)

    assert len(loaded) == 2
    assert loaded[0]["currency"] == "EUR"
    assert loaded[1]["currency"] == "USD"

    path.unlink()


def test_load_nonexistent_file():
    result = load_existing_seed(Path("/nonexistent/path.csv"))
    assert result == []


# ---------------------------------------------------------------------------
# Multi-currency support
# ---------------------------------------------------------------------------


def test_handles_many_currencies():
    existing = [
        _row("EUR", "1900-01-01", "1.0", "base_currency"),
        _row("BGN", "1900-01-01", "0.511", "fixed_peg"),
    ]
    new = [
        _row("USD", "2026-03-01", "0.92"),
        _row("GBP", "2026-03-01", "1.17"),
        _row("CAD", "2026-03-01", "0.63"),
        _row("PLN", "2026-03-01", "0.23"),
        _row("CZK", "2026-03-01", "0.04"),
        _row("RON", "2026-03-01", "0.20"),
        _row("TRY", "2026-03-01", "0.026"),
        _row("CHF", "2026-03-01", "1.06"),
    ]
    merged = merge_rates(existing, new)
    currencies = set(r["currency"] for r in merged)
    assert currencies == {"EUR", "BGN", "USD", "GBP", "CAD", "PLN", "CZK", "RON", "TRY", "CHF"}
