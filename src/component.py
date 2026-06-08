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

from client import UolClient
from configuration import Configuration, ConnectionConfig, LoadType, resolve_since
from endpoints import Endpoint, endpoint_names, get_endpoint
from flatten import flatten_record

STATE_LAST_RUN = "last_run"

# VCR sanitizers: DefaultSanitizer strips the Authorization header (which
# carries the Basic-auth email:token credential) from every recorded cassette.
# The demo email and token do not appear in UOL response bodies or query
# strings — they are only ever sent as a Basic-auth header — so no additional
# TokenSanitizer is required.
VCR_SANITIZERS = [
    DefaultSanitizer(),
]


def _active_date_field(cfg: Configuration, endpoint: Endpoint) -> str | None:
    """Determine the active date filter field based on load_type and config.

    Returns the active date field name, or None for a full load.

    Raises UserException if incremental_load is requested but:
    - no date_field is configured, or
    - the configured date_field is not valid for the endpoint.
    """
    if cfg.load_type == LoadType.full_load:
        return None

    # incremental_load path
    if not cfg.date_field:
        raise UserException(
            "Incremental load requires a Date Field; choose one or switch to full load."
        )

    if cfg.date_field not in endpoint.date_fields:
        available = ", ".join(endpoint.date_fields) or "none (full load only)"
        raise UserException(
            f"date_field '{cfg.date_field}' is not available for endpoint '{cfg.endpoint}'. "
            f"Available: {available}."
        )

    return cfg.date_field


def _fetch_records(client: UolClient, endpoint: Endpoint, params: dict) -> list[dict]:
    """Fetch all records from the API and return flat parent rows."""
    parent_rows: list[dict] = []
    for record in client.iter_records(endpoint.path, params=params):
        parent_rows.append(flatten_record(record, endpoint))
    return parent_rows


class Component(ComponentBase):
    def run(self) -> None:
        cfg = self._get_config()
        try:
            endpoint = get_endpoint(cfg.endpoint)
        except KeyError:
            raise UserException(
                f"Unknown endpoint '{cfg.endpoint}'. Valid endpoints: {', '.join(endpoint_names())}."
            ) from None

        active_field = _active_date_field(cfg, endpoint)
        incremental = active_field is not None

        client = UolClient(cfg.base_url, cfg.email, cfg.api_token)

        run_started_at = datetime.now(UTC)
        since = resolve_since(cfg.date_from, self.get_state_file() or {}) if incremental else None
        params = {active_field: since} if (active_field and since) else {}

        logging.info("Extracting %s (date_field=%s, since=%s)", endpoint.name, active_field, since)

        parent_rows = _fetch_records(client, endpoint, params)

        logging.info("Fetched %d %s records", len(parent_rows), endpoint.name)

        self._write_table(endpoint.name, parent_rows, endpoint.primary_key, incremental, endpoint.columns)

        if incremental:
            self.write_state_file({STATE_LAST_RUN: run_started_at.isoformat()})
            logging.info("Saved incremental watermark last_run=%s", run_started_at.isoformat())

    def _get_config(self) -> Configuration:
        try:
            return Configuration(**self.configuration.parameters)
        except Exception as exc:  # noqa: BLE001
            raise UserException(f"Invalid configuration: {exc}") from exc

    def _write_table(
        self,
        name: str,
        rows: list[dict],
        primary_key: list[str],
        incremental: bool,
        known_columns: tuple[str, ...] = (),
    ) -> None:
        # Guard: if there is no primary key, force full-overwrite (incremental upsert requires a PK)
        if not primary_key:
            incremental = False
        columns = self._collect_columns(rows, primary_key, known_columns)
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
        logging.info("Wrote %d rows to %s", len(rows), name)

    @staticmethod
    def _collect_columns(
        rows: list[dict], primary_key: list[str], known_columns: tuple[str, ...] = ()
    ) -> list[str]:
        ordered: list[str] = list(primary_key)
        for col in known_columns:
            if col not in ordered:
                ordered.append(col)
        for row in rows:
            for key in row:
                if key not in ordered:
                    ordered.append(key)
        return ordered

    @sync_action("testConnection")
    def test_connection(self) -> ValidationResult:
        try:
            conn = ConnectionConfig(**self.configuration.parameters)
        except Exception as exc:  # noqa: BLE001
            raise UserException(f"Invalid configuration: {exc}") from exc
        client = UolClient(conn.base_url, conn.email, conn.api_token)
        if not client.ping():
            raise UserException("Could not authenticate against UOL (/v1/ping failed).")
        return ValidationResult("Connection established.")

    @sync_action("listEndpoints")
    def list_endpoints(self) -> list[SelectElement]:
        return [
            SelectElement(value=n, label=n.replace("_", " ").title())
            for n in endpoint_names()
        ]

    @sync_action("listDateFields")
    def list_date_fields(self) -> list[SelectElement]:
        endpoint_name = self.configuration.parameters.get("endpoint")
        if not endpoint_name:
            return []
        try:
            endpoint = get_endpoint(endpoint_name)
        except KeyError:
            return []
        return [SelectElement(value=f, label=f) for f in endpoint.date_fields]


if __name__ == "__main__":
    try:
        Component().execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:  # noqa: BLE001
        logging.exception(exc)
        exit(2)
