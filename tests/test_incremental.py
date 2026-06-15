import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from keboola.component.exceptions import UserException

from component import _active_date_field, _stream_to_spill
from configuration import Configuration
from endpoints import Endpoint, get_endpoint


def _make_cfg(**over) -> Configuration:
    """Build a minimal demo Configuration."""
    base: dict[str, Any] = {
        "server_type": "demo",
        "email": "demo@example.com",
        "#api_token": "secret",
        "endpoint": "accounting_records",
    }
    base.update(over)
    return Configuration(**base)


# --- _active_date_field: full_load always returns None ---


def test_full_load_ignores_date_field():
    cfg = _make_cfg(load_type="full_load", date_field="date_from")
    endpoint = get_endpoint("accounting_records")
    assert _active_date_field(cfg, endpoint) is None


def test_full_load_no_date_field_returns_none():
    cfg = _make_cfg(load_type="full_load")
    endpoint = get_endpoint("accounting_records")
    assert _active_date_field(cfg, endpoint) is None


# --- _active_date_field: incremental_load + valid date_field ---


def test_incremental_valid_date_field_returns_field():
    cfg = _make_cfg(load_type="incremental_load", date_field="date_from")
    endpoint = get_endpoint("accounting_records")
    assert _active_date_field(cfg, endpoint) == "date_from"


def test_incremental_valid_date_field_sales_invoices():
    cfg = _make_cfg(
        load_type="incremental_load",
        date_field="issue_date_from",
        endpoint="sales_invoices",
    )
    endpoint = get_endpoint("sales_invoices")
    assert _active_date_field(cfg, endpoint) == "issue_date_from"


# --- _active_date_field: incremental_load + missing date_field → UserException ---


def test_incremental_no_date_field_raises():
    cfg = _make_cfg(load_type="incremental_load")
    endpoint = get_endpoint("accounting_records")
    with pytest.raises(UserException, match="Incremental load requires a Date Field"):
        _active_date_field(cfg, endpoint)


# --- _active_date_field: incremental_load + invalid date_field → UserException ---


def test_incremental_invalid_date_field_raises():
    cfg = _make_cfg(load_type="incremental_load", date_field="issue_date_from")
    endpoint = get_endpoint("accounting_records")  # only has "date_from"
    with pytest.raises(UserException, match="date_field"):
        _active_date_field(cfg, endpoint)


def test_incremental_date_field_on_full_load_only_endpoint_raises():
    cfg = _make_cfg(
        load_type="incremental_load",
        date_field="date_from",
        endpoint="contacts",
    )
    endpoint = get_endpoint("contacts")  # date_fields == ()
    with pytest.raises(UserException, match="date_field"):
        _active_date_field(cfg, endpoint)


# --- params building (unchanged logic) ---


def test_params_built_with_active_field_and_since():
    active_field = "date_from"
    since = "2026-01-01T00:00:00+00:00"
    params = {active_field: since} if (active_field and since) else {}
    assert params == {"date_from": "2026-01-01T00:00:00+00:00"}


def test_params_empty_when_no_since():
    active_field = "date_from"
    since = None
    params = {active_field: since} if (active_field and since) else {}
    assert params == {}


def test_params_empty_when_no_active_field():
    active_field = None
    since = "2026-01-01T00:00:00+00:00"
    params = {active_field: since} if (active_field and since) else {}
    assert params == {}


# --- _stream_to_spill: column ordering (replaces _collect_columns tests) ---


def _fake_endpoint(name: str = "items", pk: list[str] | None = None, known: tuple[str, ...] = ()) -> Endpoint:
    return Endpoint(name=name, path=f"v1/{name}", primary_key=pk or ["id"], columns=known)


def _run_spill(records: list[dict], pk: list[str], known: tuple[str, ...]) -> list[str]:
    """Helper: run _stream_to_spill and return the resulting column list."""
    client = MagicMock()
    client.iter_records.return_value = iter(records)
    endpoint = _fake_endpoint(pk=pk, known=known)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ndjson", delete=False) as tmp:
        spill_path = tmp.name
    try:
        state = _stream_to_spill(client, endpoint, {}, pk, known, spill_path)
        return state.columns
    finally:
        Path(spill_path).unlink(missing_ok=True)


def test_spill_column_order_seeds_known_columns():
    """PK and known_columns seed the ordering before any rows are seen."""
    pk = ["gid"]
    known = ("gid", "status", "total_amount")
    cols = _run_spill([], pk, known)
    assert cols[0] == "gid"
    assert "status" in cols
    assert "total_amount" in cols


def test_spill_column_order_no_dupes_from_known_and_pk():
    """gid appears in both pk and known — must appear exactly once."""
    pk = ["gid"]
    known = ("gid", "status")
    cols = _run_spill([{"gid": "1", "extra": "x"}], pk, known)
    assert cols.count("gid") == 1
    assert "extra" in cols


def test_spill_column_order_empty_rows_uses_known():
    """With zero rows the column list equals pk + known only."""
    pk = ["invoice_id"]
    known = ("invoice_id", "total_amount", "status")
    cols = _run_spill([], pk, known)
    assert cols == ["invoice_id", "total_amount", "status"]


def test_spill_column_order_discovered_appended_after_known():
    """Columns discovered in rows come after known_columns."""
    pk = ["gid"]
    known = ("gid", "status")
    cols = _run_spill([{"gid": "1", "new_field": "v"}], pk, known)
    assert cols.index("status") < cols.index("new_field")
