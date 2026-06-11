"""Tests for the column-filter feature.

Covers:
a) Configuration.columns field.
b) Component._write_table column filtering (via streaming path).
c) UolClient.sample_record.
d) Component.list_columns sync action.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import responses

from client import UolClient
from component import Component
from configuration import Configuration
from endpoints import Endpoint

BASE = "https://test.demo.uol.cz/api"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _full_params(**over) -> dict:
    base: dict = {
        "server_type": "demo",
        "email": "demo@example.com",
        "#api_token": "secret",
        "endpoint": "contacts",
    }
    base.update(over)
    return base


def _make_component(parameters: dict | None = None) -> tuple[Component, str]:
    """Return (Component, tmpdir) wired to a fresh temp data directory."""
    tmpdir = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmpdir, "in/tables"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "out/tables"), exist_ok=True)
    cfg_json = {"parameters": parameters or {}, "action": "run"}
    with open(os.path.join(tmpdir, "config.json"), "w") as fh:
        json.dump(cfg_json, fh)
    comp = Component(data_path_override=tmpdir)
    return comp, tmpdir


def _patch_configuration(comp: Component, parameters: dict | None = None):
    mock_cfg = MagicMock()
    mock_cfg.action = "run"
    mock_cfg.parameters = parameters or {}
    return patch.object(type(comp), "configuration", new_callable=lambda: property(lambda self: mock_cfg))


def _read_csv(tmpdir: str, table_name: str) -> tuple[list[str], list[dict]]:
    """Return (header, rows) from the written output CSV."""
    path = os.path.join(tmpdir, "out/tables", f"{table_name}.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    return fieldnames, rows


def _fake_endpoint(name: str = "out", pk: list[str] | None = None, known: tuple[str, ...] = ()) -> Endpoint:
    """Build a minimal Endpoint fixture for unit tests."""
    return Endpoint(name=name, path=f"v1/{name}", primary_key=pk or ["id"], columns=known)


def _write_and_read(
    selected_columns: list[str] | None,
    rows: list[dict],
    pk: tuple[str, ...] = ("id",),
    known: tuple[str, ...] = (),
    table_name: str = "out",
) -> tuple[list[str], list[dict]]:
    """Exercise _write_table via the streaming path with a mocked client.

    The client's iter_records is patched to yield the raw rows directly
    (flatten_record is a no-op when the row is already flat).
    """
    comp, tmpdir = _make_component()
    fake_ep = _fake_endpoint(table_name, list(pk), known)
    mock_client = MagicMock()
    mock_client.iter_records.return_value = iter(rows)
    # Wire the cached_property so _write_table picks up our mock client.
    comp.__dict__["_client"] = mock_client

    with patch("component.get_endpoint", return_value=fake_ep):
        comp._write_table(
            table_name,
            list(pk),
            False,
            known,
            selected_columns,
            {},
        )

    path = os.path.join(tmpdir, "out/tables", f"{table_name}.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        data = list(reader)
        header = list(reader.fieldnames or [])
    return header, data


# ---------------------------------------------------------------------------
# a) Configuration.columns
# ---------------------------------------------------------------------------


def test_configuration_columns_defaults_to_empty_list():
    cfg = Configuration(**_full_params())
    assert cfg.columns == []


def test_configuration_columns_accepts_list():
    cfg = Configuration(**_full_params(columns=["name", "email"]))
    assert cfg.columns == ["name", "email"]


def test_configuration_columns_single_item():
    cfg = Configuration(**_full_params(columns=["status"]))
    assert cfg.columns == ["status"]


# ---------------------------------------------------------------------------
# b) _write_table column filtering (streaming path)
# ---------------------------------------------------------------------------


def test_write_table_filter_restricts_columns():
    rows = [{"id": "1", "name": "Alice", "age": "30", "city": "Prague"}]
    header, data = _write_and_read(["name", "city"], rows)
    assert set(header) == {"id", "name", "city"}
    assert "age" not in header


def test_write_table_filter_pk_always_present():
    """PK column must appear even when not in selected_columns."""
    rows = [{"id": "1", "name": "Alice", "age": "30"}]
    header, data = _write_and_read(["name"], rows)
    assert "id" in header
    assert "name" in header
    assert "age" not in header


def test_write_table_filter_column_order_from_collect():
    """Column order is PK first, then known, then discovered; filter preserves that."""
    rows = [{"id": "1", "b": "2", "c": "3", "a": "4"}]
    known = ("id", "b", "c", "a")
    comp, tmpdir = _make_component()
    fake_ep = _fake_endpoint("out", ["id"], known)
    mock_client = MagicMock()
    mock_client.iter_records.return_value = iter(rows)
    comp.__dict__["_client"] = mock_client

    with patch("component.get_endpoint", return_value=fake_ep):
        comp._write_table("out", ["id"], False, known, ["b", "a"], {})

    path = os.path.join(tmpdir, "out/tables/out.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        first_line = fh.readline().rstrip("\r\n")
    cols = first_line.split(",")
    # id (PK) must be first; then b before a (known order)
    assert cols[0] == "id"
    assert cols.index("b") < cols.index("a")
    assert "c" not in cols


def test_write_table_no_filter_writes_all_columns():
    rows = [{"id": "1", "name": "Alice", "age": "30"}]
    header, _ = _write_and_read(None, rows)
    assert set(header) == {"id", "name", "age"}


def test_write_table_empty_filter_writes_all_columns():
    rows = [{"id": "1", "name": "Alice", "age": "30"}]
    header, _ = _write_and_read([], rows)
    assert set(header) == {"id", "name", "age"}


def test_write_table_csv_data_matches_filter():
    rows = [{"id": "1", "name": "Alice", "age": "30"}]
    _, data = _write_and_read(["name"], rows)
    assert data[0]["name"] == "Alice"
    assert data[0]["id"] == "1"
    assert "age" not in data[0]


# ---------------------------------------------------------------------------
# c) UolClient.sample_record
# ---------------------------------------------------------------------------


@responses.activate
def test_sample_record_returns_first_item():
    responses.add(
        responses.GET,
        f"{BASE}/v1/contacts",
        json={"items": [{"contact_id": "abc", "name": "Test"}]},
        status=200,
    )
    client = UolClient(BASE, "e@x.cz", "t")
    result = client.sample_record("v1/contacts")
    assert result == {"contact_id": "abc", "name": "Test"}


@responses.activate
def test_sample_record_returns_none_on_empty_items():
    responses.add(
        responses.GET,
        f"{BASE}/v1/contacts",
        json={"items": []},
        status=200,
    )
    client = UolClient(BASE, "e@x.cz", "t")
    result = client.sample_record("v1/contacts")
    assert result is None


@responses.activate
def test_sample_record_uses_per_page_1():
    responses.add(
        responses.GET,
        f"{BASE}/v1/contacts",
        json={"items": []},
        status=200,
    )
    client = UolClient(BASE, "e@x.cz", "t")
    client.sample_record("v1/contacts")
    qs = responses.calls[0].request.url or ""
    assert "per_page=1" in qs
    assert "page=1" in qs


# ---------------------------------------------------------------------------
# d) list_columns sync action
# ---------------------------------------------------------------------------


def test_list_columns_returns_registry_columns():
    """An endpoint with a static registry returns those columns."""
    comp = Component.__new__(Component)
    with _patch_configuration(
        comp,
        parameters={
            "server_type": "demo",
            "email": "demo@example.com",
            "#api_token": "secret",
            "endpoint": "uploaded_documents",
        },
    ):
        with patch("component.UolClient") as MockClient:
            # sample_record returns None → no augmentation
            MockClient.return_value.sample_record.return_value = None
            elements = comp.list_columns()

    values = [e.value for e in elements]
    assert "id" in values
    assert "state" in values
    assert "created_at" in values
    # Value and label are equal
    assert all(e.value == e.label for e in elements)


def test_list_columns_merges_live_sample_columns():
    """Extra keys from the live sample are appended after registry columns."""
    comp = Component.__new__(Component)
    with _patch_configuration(
        comp,
        parameters={
            "server_type": "demo",
            "email": "demo@example.com",
            "#api_token": "secret",
            "endpoint": "contacts",  # no static registry columns
        },
    ):
        with patch("component.UolClient") as MockClient:
            MockClient.return_value.sample_record.return_value = {
                "contact_id": "1",
                "email": "a@b.com",
                "extra_field": "x",
            }
            elements = comp.list_columns()

    values = [e.value for e in elements]
    assert "contact_id" in values
    assert "email" in values
    assert "extra_field" in values


def test_list_columns_no_endpoint_returns_empty():
    comp = Component.__new__(Component)
    with _patch_configuration(comp, parameters={}):
        elements = comp.list_columns()
    assert elements == []


def test_list_columns_unknown_endpoint_returns_empty():
    comp = Component.__new__(Component)
    with _patch_configuration(comp, parameters={"endpoint": "does_not_exist"}):
        elements = comp.list_columns()
    assert elements == []


def test_list_columns_does_not_raise_on_client_error():
    """Any live-sample exception is swallowed; at least registry columns are returned."""
    comp = Component.__new__(Component)
    with _patch_configuration(
        comp,
        parameters={
            "server_type": "demo",
            "email": "demo@example.com",
            "#api_token": "secret",
            "endpoint": "uploaded_documents",
        },
    ):
        with patch("component.UolClient") as MockClient:
            MockClient.return_value.sample_record.side_effect = RuntimeError("network error")
            elements = comp.list_columns()

    # Should not raise; should still return the registry columns
    values = [e.value for e in elements]
    assert "id" in values
    assert "state" in values


def test_list_columns_does_not_raise_on_connection_config_error():
    """Even if ConnectionConfig construction fails, list_columns swallows the error."""
    comp = Component.__new__(Component)
    # Missing required fields → ConnectionConfig would fail
    with _patch_configuration(comp, parameters={"endpoint": "uploaded_documents"}):
        # Should not raise; returns at least registry columns (or [] if construction fails before that)
        try:
            elements = comp.list_columns()
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"list_columns raised unexpectedly: {exc}") from exc
    # Result is a list (possibly empty or with registry items)
    assert isinstance(elements, list)
