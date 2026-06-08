"""Split a UOL record into a flat parent row plus child rows for nested arrays.

- Declared `child_arrays` become child tables `<endpoint>_<array>`, each row
  carrying a FK column `<endpoint>_<first-pk>` and an `_item_index`.
- Nested objects and any *non-declared* arrays are serialized to JSON strings
  on the parent (lossless).
- The `_meta` envelope key is dropped.
"""

from __future__ import annotations

import json

from src.endpoints import Endpoint


def _fk_column(ep: Endpoint) -> str | None:
    return f"{ep.name}_{ep.primary_key[0]}" if ep.primary_key else None


def flatten_record(record: dict, ep: Endpoint) -> tuple[dict, dict[str, list[dict]]]:
    parent: dict = {}
    children: dict[str, list[dict]] = {}
    fk_col = _fk_column(ep)
    fk_val = record.get(ep.primary_key[0]) if ep.primary_key else None

    for key, value in record.items():
        if key == "_meta":
            continue
        if key in ep.child_arrays and isinstance(value, list):
            table = f"{ep.name}_{key}"
            rows = []
            for idx, item in enumerate(value):
                row = dict(item) if isinstance(item, dict) else {"value": item}
                row.pop("_meta", None)
                if fk_col is not None:
                    row[fk_col] = fk_val
                row["_item_index"] = idx
                rows.append(row)
            children[table] = rows
        elif isinstance(value, (dict, list)):
            parent[key] = json.dumps(value, ensure_ascii=False)
        else:
            parent[key] = value
    return parent, children
