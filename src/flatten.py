"""Flatten a UOL record into a single flat row for Storage output.

- Nested objects are flattened recursively into `<parent>_<child>` scalar columns.
- Variable-length arrays are kept as a single JSON-string column (cleaned of the
  API `_meta` envelope).
- The `_meta` key is dropped at every level.
"""

from __future__ import annotations

import json
from typing import Any


def _strip_meta(value: Any) -> Any:
    """Recursively drop `_meta` keys from dicts/lists (used for array JSON columns)."""
    if isinstance(value, dict):
        return {k: _strip_meta(v) for k, v in value.items() if k != "_meta"}
    if isinstance(value, list):
        return [_strip_meta(v) for v in value]
    return value


def _flatten_into(prefix: str, value: Any, out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "_meta":
                continue
            _flatten_into(f"{prefix}_{k}" if prefix else k, v, out)
    elif isinstance(value, list):
        out[prefix] = json.dumps(_strip_meta(value), ensure_ascii=False)
    else:
        out[prefix] = value


def flatten_record(record: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in record.items():
        if key == "_meta":
            continue
        _flatten_into(key, value, out)
    return out
