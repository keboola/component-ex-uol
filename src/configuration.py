"""Validated configuration for ex-uol.

The platform merges root config + the active config row into a single
`parameters` object, so this one model holds both connection-level and
row-level fields (see keboola-context config-rows behaviour).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field


class LoadType(StrEnum):
    full_load = "full_load"
    incremental_load = "incremental_load"


class Configuration(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    base_url: str
    email: str
    api_token: str = Field(alias="#api_token")

    endpoint: str
    load_type: LoadType = LoadType.incremental_load
    date_from: str | None = None

    @computed_field
    @property
    def incremental(self) -> bool:
        return self.load_type == LoadType.incremental_load
