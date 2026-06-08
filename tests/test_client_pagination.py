import responses

from src.client import UolClient

BASE = "https://test.demo.uol.cz/api"


def _page(items, next_url):
    meta = {"pagination": {}}
    if next_url:
        meta["pagination"]["next"] = next_url
    return {"_meta": meta, "items": items}


@responses.activate
def test_iter_records_follows_next_until_absent():
    responses.add(
        responses.GET, f"{BASE}/v1/contacts",
        json=_page([{"contact_id": "a"}], f"{BASE}/v1/contacts?page=2&per_page=250"), status=200,
    )
    responses.add(
        responses.GET, f"{BASE}/v1/contacts",
        json=_page([{"contact_id": "b"}], None), status=200,
    )
    client = UolClient(BASE, "e@x.cz", "t")
    out = list(client.iter_records("v1/contacts"))
    assert [r["contact_id"] for r in out] == ["a", "b"]


@responses.activate
def test_iter_records_stops_on_empty_items():
    responses.add(responses.GET, f"{BASE}/v1/products", json=_page([], None), status=200)
    client = UolClient(BASE, "e@x.cz", "t")
    assert list(client.iter_records("v1/products")) == []


@responses.activate
def test_iter_records_passes_extra_params():
    responses.add(responses.GET, f"{BASE}/v1/accounting_records", json=_page([], None), status=200)
    client = UolClient(BASE, "e@x.cz", "t")
    list(client.iter_records("v1/accounting_records", params={"date_from": "2026-01-01"}))
    qs = responses.calls[0].request.url
    assert "date_from=2026-01-01" in qs
    assert "per_page=250" in qs
