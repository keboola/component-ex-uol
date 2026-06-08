"""Validated configuration for ex-uol.

The platform merges root config + the active config row into a single
`parameters` object, so Configuration holds both connection-level and
row-level fields (see keboola-context config-rows behaviour).

ConnectionConfig holds only connection fields and is used by sync actions
(e.g. testConnection) that must not require row-level fields.
"""

from __future__ import annotations

from enum import StrEnum

import dateparser
from keboola.component.exceptions import UserException
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ServerType(StrEnum):
    production = "production"
    sandbox = "sandbox"
    demo = "demo"


class LoadType(StrEnum):
    full_load = "full_load"
    incremental_load = "incremental_load"


class ConnectionConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    server_type: ServerType = ServerType.production
    customer_id: str | None = None
    email: str
    api_token: str = Field(alias="#api_token")

    @model_validator(mode="after")
    def _check_customer_id(self) -> ConnectionConfig:
        if self.server_type != ServerType.demo and not (self.customer_id or "").strip():
            raise ValueError("customer_id is required for sandbox/production servers.")
        return self

    @property
    def base_url(self) -> str:
        if self.server_type == ServerType.demo:
            return "https://test.demo.uol.cz/api"
        if self.server_type == ServerType.sandbox:
            return f"https://{self.customer_id}.sandbox.uol.cz/api"
        return f"https://{self.customer_id}.ucetnictvi.uol.cz/api"


class Configuration(ConnectionConfig):
    endpoint: str
    load_type: LoadType = LoadType.full_load
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
