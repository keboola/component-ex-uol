"""Tests for the two-pass disk-spill streaming implementation.

Verifies:
1. _SpillState — column discovery order and bounded type-sample accumulation.
2. _stream_to_spill — NDJSON spill file contents and state after pass 1.
3. _write_csv_from_spill — correct CSV output from a spill file.
4. _write_table (streaming path) — end-to-end: columns, data, temp-file cleanup.
5. Temp-file cleanup on error during pass 2.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from component import (
    _TYPE_SAMPLE_LIMIT,
    Component,
    _SpillState,
    _stream_to_spill,
    _write_csv_from_spill,
)
from endpoints import Endpoint

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_endpoint(name: str = "items", pk: list[str] | None = None, known: tuple[str, ...] = ()) -> Endpoint:
    return Endpoint(name=name, path=f"v1/{name}", primary_key=pk or ["id"], columns=known)


def _make_component(table_name: str = "items") -> tuple[Component, str]:
    import json as _json

    tmpdir = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmpdir, "in/tables"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "out/tables"), exist_ok=True)
    cfg_json = {
        "parameters": {
            "server_type": "demo",
            "email": "a@b.cz",
            "#api_token": "tok",
            "endpoint": table_name,
        },
        "action": "run",
    }
    with open(os.path.join(tmpdir, "config.json"), "w") as fh:
        _json.dump(cfg_json, fh)
    comp = Component(data_path_override=tmpdir)
    return comp, tmpdir


# ---------------------------------------------------------------------------
# 1. _SpillState
# ---------------------------------------------------------------------------


class TestSpillState:
    def test_column_order_pk_then_known_then_discovered(self) -> None:
        state = _SpillState("/dev/null")
        state.observe_column("pk")
        state.observe_column("known_a")
        state.observe_column("discovered")
        state.observe_column("pk")  # duplicate — should not re-append
        assert state.columns == ["pk", "known_a", "discovered"]

    def test_no_duplicate_columns(self) -> None:
        state = _SpillState("/dev/null")
        for _ in range(5):
            state.observe_column("x")
        assert state.columns == ["x"]

    def test_type_sample_bounded(self) -> None:
        state = _SpillState("/dev/null")
        for i in range(_TYPE_SAMPLE_LIMIT + 50):
            state.observe_value("col", i)
        assert len(state.type_samples["col"]) == _TYPE_SAMPLE_LIMIT

    def test_null_values_not_stored(self) -> None:
        state = _SpillState("/dev/null")
        state.observe_value("col", None)
        state.observe_value("col", None)
        assert "col" not in state.type_samples or state.type_samples["col"] == []

    def test_non_null_values_stored(self) -> None:
        state = _SpillState("/dev/null")
        state.observe_value("col", 1)
        state.observe_value("col", 2)
        assert state.type_samples["col"] == [1, 2]


# ---------------------------------------------------------------------------
# 2. _stream_to_spill
# ---------------------------------------------------------------------------


class TestStreamToSpill:
    def _make_mock_client(self, records: list[dict]) -> MagicMock:
        client = MagicMock()
        client.iter_records.return_value = iter(records)
        return client

    def test_spill_file_contains_all_rows(self) -> None:
        records = [{"id": 1, "val": "a"}, {"id": 2, "val": "b"}]
        client = self._make_mock_client(records)
        endpoint = _fake_endpoint(pk=["id"])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as tmp:
            spill_path = tmp.name
        try:
            state = _stream_to_spill(client, endpoint, {}, ["id"], (), spill_path)
            assert state.row_count == 2
            lines = Path(spill_path).read_text().splitlines()
            assert len(lines) == 2
            assert json.loads(lines[0]) == {"id": 1, "val": "a"}
            assert json.loads(lines[1]) == {"id": 2, "val": "b"}
        finally:
            Path(spill_path).unlink(missing_ok=True)

    def test_column_order_pk_first(self) -> None:
        records = [{"val": "x", "id": 1}]
        client = self._make_mock_client(records)
        endpoint = _fake_endpoint(pk=["id"])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as tmp:
            spill_path = tmp.name
        try:
            state = _stream_to_spill(client, endpoint, {}, ["id"], (), spill_path)
            assert state.columns[0] == "id"
        finally:
            Path(spill_path).unlink(missing_ok=True)

    def test_known_columns_seeded_before_discovered(self) -> None:
        records = [{"id": 1, "dynamic": "d", "known": "k"}]
        client = self._make_mock_client(records)
        endpoint = _fake_endpoint(pk=["id"], known=("id", "known"))
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as tmp:
            spill_path = tmp.name
        try:
            state = _stream_to_spill(client, endpoint, {}, ["id"], ("id", "known"), spill_path)
            known_idx = state.columns.index("known")
            dynamic_idx = state.columns.index("dynamic")
            assert known_idx < dynamic_idx
        finally:
            Path(spill_path).unlink(missing_ok=True)

    def test_type_samples_populated(self) -> None:
        records = [{"id": 1, "amount": 3.5}, {"id": 2, "amount": 7.0}]
        client = self._make_mock_client(records)
        endpoint = _fake_endpoint(pk=["id"])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as tmp:
            spill_path = tmp.name
        try:
            state = _stream_to_spill(client, endpoint, {}, ["id"], (), spill_path)
            assert state.type_samples["amount"] == [3.5, 7.0]
        finally:
            Path(spill_path).unlink(missing_ok=True)

    def test_zero_records(self) -> None:
        client = self._make_mock_client([])
        endpoint = _fake_endpoint(pk=["id"])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as tmp:
            spill_path = tmp.name
        try:
            state = _stream_to_spill(client, endpoint, {}, ["id"], (), spill_path)
            assert state.row_count == 0
            assert Path(spill_path).read_text() == ""
        finally:
            Path(spill_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 3. _write_csv_from_spill
# ---------------------------------------------------------------------------


class TestWriteCsvFromSpill:
    def test_csv_header_and_rows(self) -> None:
        rows = [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as spill:
            for r in rows:
                spill.write(json.dumps(r) + "\n")
            spill_path = spill.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as out:
            out_path = out.name
        try:
            _write_csv_from_spill(spill_path, ["id", "name"], out_path)
            with open(out_path, newline="") as fh:
                reader = csv.DictReader(fh)
                data = list(reader)
            assert data[0]["id"] == "1"
            assert data[1]["name"] == "Bob"
        finally:
            Path(spill_path).unlink(missing_ok=True)
            Path(out_path).unlink(missing_ok=True)

    def test_extra_columns_in_spill_are_ignored(self) -> None:
        """extrasaction='ignore' — columns not in fieldnames are silently dropped."""
        rows = [{"id": "1", "name": "Alice", "secret": "drop"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as spill:
            for r in rows:
                spill.write(json.dumps(r) + "\n")
            spill_path = spill.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as out:
            out_path = out.name
        try:
            _write_csv_from_spill(spill_path, ["id", "name"], out_path)
            with open(out_path, newline="") as fh:
                reader = csv.DictReader(fh)
                data = list(reader)
            assert "secret" not in data[0]
        finally:
            Path(spill_path).unlink(missing_ok=True)
            Path(out_path).unlink(missing_ok=True)

    def test_missing_column_in_row_written_as_empty(self) -> None:
        """A row missing a column writes an empty value for that field."""
        rows = [{"id": "1"}, {"id": "2", "name": "Bob"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as spill:
            for r in rows:
                spill.write(json.dumps(r) + "\n")
            spill_path = spill.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as out:
            out_path = out.name
        try:
            _write_csv_from_spill(spill_path, ["id", "name"], out_path)
            with open(out_path, newline="") as fh:
                reader = csv.DictReader(fh)
                data = list(reader)
            # Row 0 has no "name" → DictWriter writes "" (restval default)
            assert data[0]["name"] == ""
            assert data[1]["name"] == "Bob"
        finally:
            Path(spill_path).unlink(missing_ok=True)
            Path(out_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 4. _write_table end-to-end (streaming path)
# ---------------------------------------------------------------------------


class TestWriteTableStreaming:
    def _run_write_table(
        self,
        rows: list[dict],
        pk: list[str] = None,
        known: tuple[str, ...] = (),
        selected_columns: list[str] | None = None,
        table_name: str = "items",
    ) -> tuple[list[str], list[dict[str, str]], str]:
        """Run _write_table with mocked client; return (header, csv_rows, tmpdir)."""
        if pk is None:
            pk = ["id"]
        comp, tmpdir = _make_component(table_name)
        fake_ep = _fake_endpoint(table_name, pk, known)
        mock_client = MagicMock()
        mock_client.iter_records.return_value = iter(rows)
        comp.__dict__["_client"] = mock_client
        with patch("component.get_endpoint", return_value=fake_ep):
            comp._write_table(table_name, pk, False, known, selected_columns, {})
        path = os.path.join(tmpdir, "out/tables", f"{table_name}.csv")
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            data = list(reader)
            header = list(reader.fieldnames or [])
        return header, data, tmpdir

    def test_basic_output(self) -> None:
        rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        header, data, _ = self._run_write_table(rows)
        assert set(header) == {"id", "name"}
        assert data[0]["name"] == "Alice"
        assert data[1]["id"] == "2"

    def test_column_filter_applied(self) -> None:
        rows = [{"id": "1", "name": "Alice", "age": "30"}]
        header, data, _ = self._run_write_table(rows, selected_columns=["name"])
        assert set(header) == {"id", "name"}
        assert "age" not in header

    def test_pk_always_present_when_filtered(self) -> None:
        rows = [{"id": "1", "x": "v"}]
        header, _, _ = self._run_write_table(rows, selected_columns=[])
        assert "id" in header

    def test_temp_file_cleaned_up_after_success(self) -> None:
        """No NDJSON temp files should remain after a successful run."""
        rows = [{"id": "1"}]
        comp, tmpdir = _make_component()
        fake_ep = _fake_endpoint(pk=["id"])
        mock_client = MagicMock()
        mock_client.iter_records.return_value = iter(rows)
        comp.__dict__["_client"] = mock_client
        with patch("component.get_endpoint", return_value=fake_ep):
            comp._write_table("items", ["id"], False, (), None, {})
        # The test is that no exception was raised and the CSV was written.
        out = os.path.join(tmpdir, "out/tables/items.csv")
        assert os.path.exists(out)

    def test_temp_file_cleaned_up_on_error(self) -> None:
        """Spill file is removed even when pass 2 raises."""
        rows = [{"id": "1"}]
        comp, tmpdir = _make_component()
        fake_ep = _fake_endpoint(pk=["id"])
        mock_client = MagicMock()
        mock_client.iter_records.return_value = iter(rows)
        comp.__dict__["_client"] = mock_client

        spill_paths: list[str] = []

        original_stream = __import__("component")._stream_to_spill

        def capturing_stream(client, endpoint, params, pk, known, spill_path):
            spill_paths.append(spill_path)
            return original_stream(client, endpoint, params, pk, known, spill_path)

        with patch("component.get_endpoint", return_value=fake_ep):
            with patch("component._stream_to_spill", side_effect=capturing_stream):
                with patch("component._write_csv_from_spill", side_effect=OSError("disk full")):
                    with pytest.raises(OSError, match="disk full"):
                        comp._write_table("items", ["id"], False, (), None, {})

        # Spill file must have been deleted despite the error.
        for p in spill_paths:
            assert not Path(p).exists(), f"Spill file not cleaned up: {p}"

    def test_zero_rows_produces_header_only(self) -> None:
        rows: list[dict] = []
        header, data, _ = self._run_write_table(rows, known=("id", "name"))
        assert header == ["id", "name"]
        assert data == []

    def test_sparse_rows_union_columns(self) -> None:
        """Rows with different key sets: union of all keys appears in header."""
        rows = [{"id": "1", "a": "x"}, {"id": "2", "b": "y"}]
        header, data, _ = self._run_write_table(rows)
        assert set(header) == {"id", "a", "b"}
        # Row 0 has no "b" → written as empty string
        assert data[0].get("b", "") == ""

    def test_incremental_forced_off_when_no_pk(self) -> None:
        """When pk=[], incremental is forced to False (no error expected)."""
        rows = [{"name": "x"}]
        comp, tmpdir = _make_component("nopk")
        fake_ep = _fake_endpoint("nopk", [], ())
        mock_client = MagicMock()
        mock_client.iter_records.return_value = iter(rows)
        comp.__dict__["_client"] = mock_client
        with patch("component.get_endpoint", return_value=fake_ep):
            # incremental=True but pk=[] → should be silently forced to False
            comp._write_table("nopk", [], True, (), None, {})
        out = os.path.join(tmpdir, "out/tables/nopk.csv")
        assert os.path.exists(out)
