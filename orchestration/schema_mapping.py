from __future__ import annotations

import os


def dev_schema_owner() -> str:
    owner = os.getenv("DBT_DEV_SCHEMA_OWNER", os.getenv("USER", "local"))
    return owner.lower().replace(" ", "_").replace("-", "_").replace(".", "_")


def resolve_schema_name(base_schema: str, target_name: str) -> str:
    if target_name == "prod":
        return base_schema
    if target_name == "stage":
        return base_schema if base_schema.endswith("_stage") else f"{base_schema}_stage"
    if target_name == "dev":
        return base_schema if "_dev_" in base_schema else f"{base_schema}_dev_{dev_schema_owner()}"
    return f"{base_schema}_{target_name}"
