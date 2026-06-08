import pytest

from src.endpoints import ENDPOINTS, endpoint_names, get_endpoint


def test_registry_has_29_endpoints():
    assert len(ENDPOINTS) == 29


def test_known_endpoint_shapes():
    inv = get_endpoint("sales_invoices")
    assert inv.path == "v1/sales_invoices"
    assert inv.primary_key == ["gid"]
    assert inv.child_arrays == ("items",)
    assert inv.incremental_param == "issue_date_from"

    contacts = get_endpoint("contacts")
    assert contacts.primary_key == ["contact_id"]
    assert contacts.child_arrays == ("addresses",)
    assert contacts.incremental_param is None


def test_endpoint_names_sorted_and_complete():
    names = endpoint_names()
    assert "receivables" in names
    assert "bank_balances" not in names
    assert names == sorted(names)


def test_unknown_endpoint_raises():
    with pytest.raises(KeyError):
        get_endpoint("does_not_exist")
