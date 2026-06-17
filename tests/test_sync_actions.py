from unittest.mock import MagicMock, patch

from component import Component
from endpoints import endpoint_names


def _patch_configuration(comp, parameters=None, action="run"):
    mock_cfg = MagicMock()
    mock_cfg.action = action
    mock_cfg.parameters = parameters or {}
    return patch.object(type(comp), "configuration", new_callable=lambda: property(lambda self: mock_cfg))


def test_list_endpoints_returns_all_names():
    comp = Component.__new__(Component)
    with _patch_configuration(comp):
        elements = comp.list_endpoints()

    values = [e.value for e in elements]
    assert values == endpoint_names()
    assert "sales_invoices" in values


def test_list_endpoints_labels_are_humanized():
    comp = Component.__new__(Component)
    with _patch_configuration(comp):
        elements = comp.list_endpoints()

    label_map = {e.value: e.label for e in elements}
    assert label_map["sales_invoices"] == "Sales Invoices"
    assert label_map["accounting_records"] == "Accounting Records"
    assert label_map["purchase_invoices"] == "Purchase Invoices"
    assert label_map["uploaded_documents"] == "Uploaded Documents"


def test_list_endpoints_value_stays_raw():
    comp = Component.__new__(Component)
    with _patch_configuration(comp):
        elements = comp.list_endpoints()

    values = [e.value for e in elements]
    # values must be raw snake_case names, not humanized
    assert "sales_invoices" in values
    assert "Sales Invoices" not in values


def test_list_date_fields_sales_invoices():
    comp = Component.__new__(Component)
    with _patch_configuration(comp, parameters={"endpoint": "sales_invoices"}):
        elements = comp.list_date_fields()

    values = [e.value for e in elements]
    assert values == ["tax_payment_date_from", "issue_date_from", "due_date_from"]
    assert len(elements) == 3


def test_list_date_fields_contacts_returns_empty():
    comp = Component.__new__(Component)
    with _patch_configuration(comp, parameters={"endpoint": "contacts"}):
        elements = comp.list_date_fields()

    assert elements == []


def test_list_date_fields_unknown_endpoint_returns_empty():
    comp = Component.__new__(Component)
    with _patch_configuration(comp, parameters={"endpoint": "does_not_exist"}):
        elements = comp.list_date_fields()

    assert elements == []


def test_list_date_fields_no_endpoint_returns_empty():
    comp = Component.__new__(Component)
    with _patch_configuration(comp, parameters={}):
        elements = comp.list_date_fields()

    assert elements == []
