import json

from endpoints import get_endpoint
from flatten import flatten_record


def test_scalars_passthrough():
    ep = get_endpoint("products")
    result = flatten_record({"product_id": "p1", "name": "X", "price": 9.99}, ep)
    assert result == {"product_id": "p1", "name": "X", "price": 9.99}


def test_meta_dropped_at_top_level():
    ep = get_endpoint("products")
    result = flatten_record({"product_id": "p1", "_meta": {"href": "h"}}, ep)
    assert "_meta" not in result
    assert result == {"product_id": "p1"}


def test_nested_object_flattened():
    ep = get_endpoint("contacts")
    result = flatten_record({"contact_id": "acme", "creator": {"user_id": "x"}}, ep)
    assert result["creator_user_id"] == "x"
    assert "creator" not in result


def test_deep_nesting_flattened():
    ep = get_endpoint("products")
    result = flatten_record({"a": {"b": {"c": 1}}}, ep)
    assert result == {"a_b_c": 1}


def test_nested_object_meta_dropped():
    ep = get_endpoint("contacts")
    rec = {
        "contact_id": "acme",
        "creator": {"user_id": "u1", "_meta": {"href": "h"}},
        "_meta": {"href": "x"},
    }
    result = flatten_record(rec, ep)
    assert result["creator_user_id"] == "u1"
    assert "creator__meta" not in result
    assert "_meta" not in result


def test_array_becomes_json_column():
    ep = get_endpoint("contacts")
    rec = {"contact_id": "acme", "bank_accounts": [{"x": 1}, {"x": 2}]}
    result = flatten_record(rec, ep)
    assert "bank_accounts" in result
    parsed = json.loads(result["bank_accounts"])
    assert parsed == [{"x": 1}, {"x": 2}]


def test_array_meta_stripped_from_json_column():
    ep = get_endpoint("sales_invoices")
    rec = {"gid": "g1", "items": [{"x": 1, "_meta": {"href": "h"}}, {"x": 2}]}
    result = flatten_record(rec, ep)
    parsed = json.loads(result["items"])
    assert parsed == [{"x": 1}, {"x": 2}]


def test_array_nested_meta_stripped_recursively():
    ep = get_endpoint("contacts")
    rec = {
        "contact_id": "c",
        "bank_accounts": [{"id": 1, "_meta": {"href": "h"}, "sub": {"_meta": {}, "v": 2}}],
    }
    result = flatten_record(rec, ep)
    parsed = json.loads(result["bank_accounts"])
    assert "_meta" not in parsed[0]
    assert parsed[0]["sub"] == {"v": 2}


def test_returns_flat_dict_not_tuple():
    ep = get_endpoint("products")
    result = flatten_record({"product_id": "p1"}, ep)
    assert isinstance(result, dict)


def test_full_contacts_record_shape():
    ep = get_endpoint("contacts")
    rec = {
        "contact_id": "c",
        "creator": {"user_id": "u", "_meta": {"href": "h"}},
        "bank_accounts": [{"x": 1, "_meta": {}}],
        "_meta": {"href": "x"},
    }
    result = flatten_record(rec, ep)
    assert result["contact_id"] == "c"
    assert result["creator_user_id"] == "u"
    assert "_meta" not in result
    parsed = json.loads(result["bank_accounts"])
    assert parsed == [{"x": 1}]
