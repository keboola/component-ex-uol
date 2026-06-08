import pytest

from endpoints import ENDPOINTS, endpoint_names, get_endpoint


def test_registry_has_29_endpoints():
    assert len(ENDPOINTS) == 29


def test_known_endpoint_shapes():
    inv = get_endpoint("sales_invoices")
    assert inv.path == "v1/sales_invoices"
    assert inv.primary_key == ["gid"]
    assert inv.child_arrays == ("items",)
    assert inv.date_fields == ("tax_payment_date_from", "issue_date_from", "due_date_from")

    contacts = get_endpoint("contacts")
    assert contacts.primary_key == ["contact_id"]
    assert contacts.child_arrays == ("addresses",)
    assert contacts.date_fields == ()


def test_endpoint_names_sorted_and_complete():
    names = endpoint_names()
    assert "receivables" in names
    assert "bank_balances" not in names
    assert names == sorted(names)


def test_unknown_endpoint_raises():
    with pytest.raises(KeyError):
        get_endpoint("does_not_exist")


# --- columns field ---

def test_sales_invoices_columns_non_empty():
    ep = get_endpoint("sales_invoices")
    assert len(ep.columns) > 0
    assert "gid" in ep.columns


def test_sales_orders_columns_non_empty():
    ep = get_endpoint("sales_orders")
    assert len(ep.columns) > 0
    assert "order_id" in ep.columns


def test_purchase_invoices_columns_non_empty():
    ep = get_endpoint("purchase_invoices")
    assert len(ep.columns) > 0
    assert "gid" in ep.columns


def test_accounting_records_columns_non_empty():
    ep = get_endpoint("accounting_records")
    assert len(ep.columns) > 0
    assert "gid" in ep.columns


def test_receivables_columns_non_empty():
    ep = get_endpoint("receivables")
    assert len(ep.columns) > 0
    assert "invoice_id" in ep.columns


def test_uploaded_documents_columns_non_empty():
    ep = get_endpoint("uploaded_documents")
    assert len(ep.columns) > 0
    assert "id" in ep.columns


def test_contacts_columns_empty():
    """Full-load-only endpoints have no pre-declared columns."""
    ep = get_endpoint("contacts")
    assert ep.columns == ()


def test_retails_columns_empty():
    ep = get_endpoint("retails")
    assert ep.columns == ()
