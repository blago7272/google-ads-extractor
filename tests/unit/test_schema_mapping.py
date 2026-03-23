from __future__ import annotations

import os
import unittest
from unittest import mock

from orchestration.schema_mapping import resolve_schema_name


class SchemaMappingTest(unittest.TestCase):
    def test_stage_schema_is_suffixed(self) -> None:
        self.assertEqual(resolve_schema_name("gads_reporting_mart", "stage"), "gads_reporting_mart_stage")

    def test_prod_schema_is_unchanged(self) -> None:
        self.assertEqual(resolve_schema_name("gads_reporting_mart", "prod"), "gads_reporting_mart")

    def test_dev_schema_uses_owner_suffix(self) -> None:
        with mock.patch.dict(os.environ, {"DBT_DEV_SCHEMA_OWNER": "Alice.Test"}, clear=False):
            self.assertEqual(
                resolve_schema_name("gads_reporting_mart", "dev"),
                "gads_reporting_mart_dev_alice_test",
            )


if __name__ == "__main__":
    unittest.main()
