from unittest.mock import MagicMock, patch

from src.component import Component
from src.endpoints import endpoint_names


def test_list_endpoints_returns_all_names():
    comp = Component.__new__(Component)
    # The @sync_action decorator reads self.configuration.action before
    # calling the underlying function.  configuration is a read-only property
    # on the base class, so we patch it at class level.
    # action="run" makes the decorator return the result directly without
    # writing JSON to stdout.
    mock_cfg = MagicMock()
    mock_cfg.action = "run"
    with patch.object(type(comp), "configuration", new_callable=lambda: property(lambda self: mock_cfg)):
        elements = comp.list_endpoints()

    values = [e.value for e in elements]
    assert values == endpoint_names()
    assert "sales_invoices" in values
