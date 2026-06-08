"""Validated configuration for ex-uol.

The platform merges root config + the active config row into a single
`parameters` object, so Configuration holds both connection-level and
row-level fields (see keboola-context config-rows behaviour).

ConnectionConfig holds only connection fields and is used by sync actions
(e.g. testConnection) that must not require row-level fields.
"""

from __future__ import annotations

import dateparser
from keboola.component.exceptions import UserException
from pydantic import BaseModel, ConfigDict, Field


class ConnectionConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    base_url: str
    email: str
    api_token: str = Field(alias="#api_token")


class Configuration(ConnectionConfig):
    endpoint: str
    date_field: str | None = None
    date_from: str | None = None


def resolve_since(date_from: str | None, state: dict) -> str | None:
    """Resolve the lower-bound 'since' value for incremental filtering.

    - None/empty or 'last_run' (case-insensitive) -> the stored state watermark
      (None if no watermark yet -> unfiltered first run).
    - Otherwise parse as a relative ('yesterday', '5 days ago') or absolute (ISO)
      date via dateparser; return an ISO-8601 string. Unparseable -> UserException.
    """
    if date_from is None:
        return state.get("last_run")

    stripped = date_from.strip().lower().replace("_", " ")
    if stripped in ("", "last run"):
        return state.get("last_run")

    parsed = dateparser.parse(date_from, settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True})
    if parsed is None:
        raise UserException(
            f"Could not parse date_from '{date_from}'. "
            "Use 'last_run', a relative phrase like '5 days ago', or an ISO date."
        )
    return parsed.isoformat()
