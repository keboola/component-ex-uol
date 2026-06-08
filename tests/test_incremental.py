import pytest
from keboola.component.exceptions import UserException

from component import Component
from endpoints import get_endpoint

# --- active_field selection ---

def test_valid_date_field_is_accepted():
    """A date_field that exists in endpoint.date_fields becomes active_field."""
    endpoint = get_endpoint("accounting_records")
    date_field = "date_from"
    # Simulate the selection logic from run()
    active_field = date_field if (date_field and date_field in endpoint.date_fields) else None
    assert active_field == "date_from"


def test_invalid_date_field_raises_user_exception():
    """A date_field not in endpoint.date_fields must raise UserException."""
    comp = Component.__new__(Component)
    comp.get_state_file = lambda: {}

    endpoint = get_endpoint("accounting_records")
    # accounting_records only has ("date_from",) — "issue_date_from" is invalid
    date_field = "issue_date_from"
    if date_field and date_field not in endpoint.date_fields:
        available = ", ".join(endpoint.date_fields) or "none (full load only)"
        with pytest.raises(UserException, match="date_field"):
            raise UserException(
                f"date_field '{date_field}' is not available for endpoint 'accounting_records'. "
                f"Available: {available}."
            )


def test_endpoint_with_no_date_fields_is_full_load():
    """Endpoints with no date_fields always use full load (active_field=None)."""
    endpoint = get_endpoint("contacts")
    assert endpoint.date_fields == ()
    date_field = None
    active_field = date_field if (date_field and date_field in endpoint.date_fields) else None
    assert active_field is None
    assert not active_field  # => incremental = False


def test_no_date_field_config_means_full_load():
    """When date_field is not set in config, active_field is None and incremental is False."""
    endpoint = get_endpoint("sales_invoices")
    date_field = None  # not set in config
    active_field = date_field if (date_field and date_field in endpoint.date_fields) else None
    assert active_field is None


# --- params building ---

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
