"""Tests for the value-based type-inference helpers in component.py."""

from __future__ import annotations

import os
import sys
import unittest

# Ensure src/ is importable when running from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from keboola.component.dao import BaseType  # noqa: E402

from component import _build_schema, _infer_base_type  # noqa: E402


class TestInferBaseType(unittest.TestCase):
    # ------------------------------------------------------------------ #
    # Numeric types                                                        #
    # ------------------------------------------------------------------ #

    def test_integers(self) -> None:
        assert _infer_base_type([1, 2, 3]) == BaseType.integer()

    def test_mixed_int_and_float_is_numeric(self) -> None:
        assert _infer_base_type([1, 2.5]) == BaseType.numeric()

    def test_all_floats_is_numeric(self) -> None:
        assert _infer_base_type([1.0, 2.0]) == BaseType.numeric()

    # ------------------------------------------------------------------ #
    # Boolean                                                              #
    # ------------------------------------------------------------------ #

    def test_booleans(self) -> None:
        # bool is a subclass of int — must be detected as BOOLEAN, not INTEGER
        assert _infer_base_type([True, False]) == BaseType.boolean()

    def test_bool_not_confused_with_int(self) -> None:
        # A mix of bool and int is not all-bool and not all-non-bool-int
        # (non_bool contains only the ints but mixed with bools the check
        # len(non_bool)==len(values) fails) → STRING fallback
        assert _infer_base_type([True, 1]) == BaseType.string()

    # ------------------------------------------------------------------ #
    # Date / timestamp                                                     #
    # ------------------------------------------------------------------ #

    def test_iso_dates(self) -> None:
        assert _infer_base_type(["2026-01-15", "2026-02-01"]) == BaseType.date()

    def test_iso_datetime_with_tz(self) -> None:
        assert _infer_base_type(["2025-10-17T12:24:20.776+02:00"]) == BaseType.timestamp()

    def test_iso_datetime_space_separator(self) -> None:
        assert _infer_base_type(["2025-10-17 12:24:20"]) == BaseType.timestamp()

    # ------------------------------------------------------------------ #
    # STRING fallback cases                                                #
    # ------------------------------------------------------------------ #

    def test_string_encoded_numbers_stay_string(self) -> None:
        # UOL quotes some numeric fields; importing as NUMERIC would risk errors
        assert _infer_base_type(["3.0", "4.0"]) == BaseType.string()

    def test_mixed_strings_stay_string(self) -> None:
        assert _infer_base_type(["abc", "2026-01-15"]) == BaseType.string()

    def test_empty_values_returns_string(self) -> None:
        assert _infer_base_type([]) == BaseType.string()

    def test_json_array_string_stays_string(self) -> None:
        assert _infer_base_type(['[{"x":1}]']) == BaseType.string()

    def test_plain_string_stays_string(self) -> None:
        assert _infer_base_type(["hello", "world"]) == BaseType.string()


class TestBuildSchema(unittest.TestCase):
    """Integration-level test: _build_schema produces the right ColumnDefinition types."""

    SAMPLE_ROW = {
        "amount": 3630.0,
        "hidden": False,
        "issue_date": "2026-01-15",
        "created_at": "2025-10-17T12:24:20+02:00",
        "name": "x",
        "items": '[{"id":1}]',
    }

    def test_schema_types_for_sample_row(self) -> None:
        columns = list(self.SAMPLE_ROW.keys())
        rows = [self.SAMPLE_ROW]
        schema = _build_schema(columns, rows, primary_key=[])

        assert schema["amount"].data_types == BaseType.numeric(), "amount should be NUMERIC"
        assert schema["hidden"].data_types == BaseType.boolean(), "hidden should be BOOLEAN"
        assert schema["issue_date"].data_types == BaseType.date(), "issue_date should be DATE"
        assert schema["created_at"].data_types == BaseType.timestamp(), "created_at should be TIMESTAMP"
        assert schema["name"].data_types == BaseType.string(), "name should be STRING"
        assert schema["items"].data_types == BaseType.string(), "items (JSON array) should be STRING"

    def test_primary_key_columns_not_nullable(self) -> None:
        columns = ["id", "name"]
        rows = [{"id": 1, "name": "foo"}]
        schema = _build_schema(columns, rows, primary_key=["id"])

        assert schema["id"].primary_key is True
        assert schema["id"].nullable is False
        assert schema["name"].primary_key is False
        assert schema["name"].nullable is True

    def test_empty_rows_all_string(self) -> None:
        columns = ["a", "b"]
        schema = _build_schema(columns, rows=[], primary_key=[])
        assert schema["a"].data_types == BaseType.string()
        assert schema["b"].data_types == BaseType.string()

    def test_null_values_skipped_infer_remaining(self) -> None:
        # Column 'x' has one null row and one integer row → should infer INTEGER
        rows = [{"x": None}, {"x": 5}]
        schema = _build_schema(["x"], rows, primary_key=[])
        assert schema["x"].data_types == BaseType.integer()


if __name__ == "__main__":
    unittest.main()
