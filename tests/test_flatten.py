import json
from src.endpoints import get_endpoint
from src.flatten import flatten_record


def test_scalar_and_nested_object_become_parent_columns():
    ep = get_endpoint("contacts")  # pk contact_id, child_arrays ("addresses",)
    rec = {
        "contact_id": "acme",
        "name": "Acme",
        "creator": {"user_id": "u1"},
        "addresses": [{"address_id": "hq"}],
        "_meta": {"href": "x"},
    }
    parent, children = flatten_record(rec, ep)
    assert parent["contact_id"] == "acme"
    assert parent["name"] == "Acme"
    assert json.loads(parent["creator"]) == {"user_id": "u1"}
    assert "_meta" not in parent
    assert "addresses" not in parent


def test_child_rows_get_fk_and_item_index():
    ep = get_endpoint("contacts")
    rec = {"contact_id": "acme", "addresses": [{"address_id": "hq"}, {"address_id": "wh"}]}
    _parent, children = flatten_record(rec, ep)
    rows = children["contacts_addresses"]
    assert rows[0]["contacts_contact_id"] == "acme"
    assert rows[0]["_item_index"] == 0
    assert rows[1]["_item_index"] == 1
    assert rows[1]["address_id"] == "wh"


def test_no_children_for_endpoint_without_arrays():
    ep = get_endpoint("products")  # no child_arrays
    parent, children = flatten_record({"product_id": "p1", "name": "X"}, ep)
    assert children == {}
    assert parent == {"product_id": "p1", "name": "X"}


def test_endpoint_without_pk_still_flattens():
    ep = get_endpoint("bank_movement_items")  # pk []
    parent, children = flatten_record({"number": "1", "amount": 5}, ep)
    assert parent == {"number": "1", "amount": 5}
    assert children == {}
