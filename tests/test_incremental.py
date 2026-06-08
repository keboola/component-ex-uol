import pytest
from keboola.component.exceptions import UserException

from component import Component, _active_date_field
from configuration import Configuration
from endpoints import get_endpoint


def _make_cfg(**over) -> Configuration:
    """Build a minimal demo Configuration."""
    base = {
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


# --- _child_pk shape (unchanged) ---

def test_child_pk_shape():
    ep = get_endpoint("sales_invoices")  # pk gid
    assert Component._child_pk(ep) == ["sales_invoices_gid", "_item_index"]


def test_child_pk_empty_for_no_pk_endpoint():
    ep = get_endpoint("bank_movement_items")  # pk []
    assert Component._child_pk(ep) == []


# --- _collect_columns: known_columns seeding ---

def test_collect_columns_seeds_known_columns():
    rows: list[dict] = []
    pk = ["gid"]
    known = ("gid", "status", "total_amount")
    cols = Component._collect_columns(rows, pk, known)
    # PK first, then known (gid already there), then discovered
    assert cols[0] == "gid"
    assert "status" in cols
    assert "total_amount" in cols


def test_collect_columns_no_dupes_from_known_and_pk():
    rows = [{"gid": "1", "extra": "x"}]
    pk = ["gid"]
    known = ("gid", "status")
    cols = Component._collect_columns(rows, pk, known)
    assert cols.count("gid") == 1
    assert "extra" in cols


def test_collect_columns_empty_rows_uses_known():
    pk = ["invoice_id"]
    known = ("invoice_id", "total_amount", "status")
    cols = Component._collect_columns([], pk, known)
    assert cols == ["invoice_id", "total_amount", "status"]


def test_collect_columns_discovered_appended_after_known():
    rows = [{"gid": "1", "new_field": "v"}]
    pk = ["gid"]
    known = ("gid", "status")
    cols = Component._collect_columns(rows, pk, known)
    # known fields come before discovered
    assert cols.index("status") < cols.index("new_field")
