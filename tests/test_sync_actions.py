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
