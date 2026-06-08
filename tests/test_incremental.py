from src.component import Component
from src.configuration import Configuration
from src.endpoints import get_endpoint


def _cfg(**over):
    p = {
        "base_url": "https://x/api", "email": "e@x.cz", "#api_token": "t",
        "endpoint": "accounting_records",
    }
    p.update(over)
    return Configuration(**p)


def test_build_params_uses_incremental_param():
    ep = get_endpoint("accounting_records")  # inc date_from
    assert Component._build_params(ep, "2026-01-01T00:00:00+00:00") == {
        "date_from": "2026-01-01T00:00:00+00:00"
    }


def test_build_params_empty_without_since():
    ep = get_endpoint("accounting_records")
    assert Component._build_params(ep, None) == {}


def test_full_load_uses_date_from_not_state():
    comp = Component.__new__(Component)
    ep = get_endpoint("accounting_records")
    cfg = _cfg(load_type="full_load", date_from="2025-01-01")
    assert comp._resolve_since(cfg, ep) == "2025-01-01"


def test_incremental_prefers_state_watermark():
    comp = Component.__new__(Component)
    comp.get_state_file = lambda: {"last_run": "2026-05-01T00:00:00+00:00"}
    ep = get_endpoint("accounting_records")
    cfg = _cfg(load_type="incremental_load", date_from="2020-01-01")
    assert comp._resolve_since(cfg, ep) == "2026-05-01T00:00:00+00:00"


def test_child_pk_shape():
    ep = get_endpoint("sales_invoices")  # pk gid
    assert Component._child_pk(ep) == ["sales_invoices_gid", "_item_index"]
