"""ex-uol — UOL Účetnictví extractor."""

from __future__ import annotations

import csv
import logging
from datetime import UTC, datetime

from keboola.component.base import ComponentBase, sync_action
from keboola.component.dao import BaseType, ColumnDefinition
from keboola.component.exceptions import UserException
from keboola.component.sync_actions import SelectElement, ValidationResult
from keboola.vcr import DefaultSanitizer

from src.client import UolClient
from src.configuration import Configuration
from src.endpoints import endpoint_names, get_endpoint
from src.flatten import flatten_record

STATE_LAST_RUN = "last_run"

# VCR sanitizers: DefaultSanitizer strips the Authorization header (which
# carries the Basic-auth email:token credential) from every recorded cassette.
# The demo email and token do not appear in UOL response bodies or query
# strings — they are only ever sent as a Basic-auth header — so no additional
# TokenSanitizer is required.
VCR_SANITIZERS = [
    DefaultSanitizer(),
]


class Component(ComponentBase):
    def run(self):
        cfg = self._get_config()
        try:
            endpoint = get_endpoint(cfg.endpoint)
        except KeyError:
            raise UserException(
                f"Unknown endpoint '{cfg.endpoint}'. Valid endpoints: {', '.join(endpoint_names())}."
            ) from None
        client = UolClient(cfg.base_url, cfg.email, cfg.api_token)

        run_started_at = datetime.now(UTC)
        since = self._resolve_since(cfg, endpoint)
        params = self._build_params(endpoint, since)

        parent_rows: list[dict] = []
        child_rows: dict[str, list[dict]] = {}
        for record in client.iter_records(endpoint.path, params=params):
            parent, children = flatten_record(record, endpoint)
            parent_rows.append(parent)
            for table, rows in children.items():
                child_rows.setdefault(table, []).extend(rows)

        self._write_table(endpoint.name, parent_rows, endpoint.primary_key, cfg.incremental)
        for table, rows in child_rows.items():
            self._write_table(table, rows, self._child_pk(endpoint), cfg.incremental)

        if cfg.incremental and endpoint.incremental_param:
            self.write_state_file({STATE_LAST_RUN: run_started_at.isoformat()})

    def _get_config(self) -> Configuration:
        try:
            return Configuration(**self.configuration.parameters)
        except Exception as exc:  # noqa: BLE001
            raise UserException(f"Invalid configuration: {exc}") from exc

    def _resolve_since(self, cfg: Configuration, endpoint) -> str | None:
        if not (cfg.incremental and endpoint.incremental_param):
            return cfg.date_from if not cfg.incremental else None
        state = self.get_state_file() or {}
        return state.get(STATE_LAST_RUN) or cfg.date_from

    @staticmethod
    def _build_params(endpoint, since: str | None) -> dict:
        if since and endpoint.incremental_param:
            return {endpoint.incremental_param: since}
        return {}

    @staticmethod
    def _child_pk(endpoint) -> list[str]:
        if not endpoint.primary_key:
            return []
        return [f"{endpoint.name}_{endpoint.primary_key[0]}", "_item_index"]

    def _write_table(self, name: str, rows: list[dict], primary_key: list[str], incremental: bool):
        columns = self._collect_columns(rows, primary_key)
        table = self.create_out_table_definition(
            f"{name}.csv",
            schema={c: ColumnDefinition(data_types=BaseType.string()) for c in columns},
            primary_key=primary_key,
            incremental=incremental,
        )
        with open(table.full_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        self.write_manifest(table)

    @staticmethod
    def _collect_columns(rows: list[dict], primary_key: list[str]) -> list[str]:
        ordered: list[str] = list(primary_key)
        for row in rows:
            for key in row:
                if key not in ordered:
                    ordered.append(key)
        return ordered

    @sync_action("testConnection")
    def test_connection(self) -> ValidationResult:
        cfg = self._get_config()
        client = UolClient(cfg.base_url, cfg.email, cfg.api_token)
        if not client.ping():
            raise UserException("Could not authenticate against UOL (/v1/ping failed).")
        return ValidationResult("Connection established.")

    @sync_action("listEndpoints")
    def list_endpoints(self):
        return [SelectElement(value=n, label=n) for n in endpoint_names()]


if __name__ == "__main__":
    try:
        Component().execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:  # noqa: BLE001
        logging.exception(exc)
        exit(2)
