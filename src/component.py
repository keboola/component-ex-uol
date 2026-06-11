"""ex-uol — UOL Účetnictví extractor."""

from __future__ import annotations

import csv
import logging
import re
from datetime import UTC, datetime
from functools import cached_property
from typing import Any

from keboola.component.base import ComponentBase, sync_action
from keboola.component.dao import BaseType, ColumnDefinition
from keboola.component.exceptions import UserException
from keboola.component.sync_actions import SelectElement, ValidationResult
from keboola.vcr import DefaultSanitizer

from client import UolClient
from configuration import Configuration, ConnectionConfig, LoadType, resolve_since
from endpoints import Endpoint, endpoint_names, get_endpoint
from flatten import flatten_record

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type-inference helpers
# ---------------------------------------------------------------------------

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def _infer_base_type(values: list[Any]) -> BaseType:
    """Infer a Keboola BaseType from a column's non-null Python values.

    Rules (conservative — STRING fallback on any ambiguity):
    - bool checked BEFORE int because bool is a subclass of int.
    - String-encoded numbers (e.g. "3.0") stay STRING — UOL quotes some
      numeric fields and importing them as NUMERIC would risk type errors.
    - JSON-array strings won't match the date/timestamp regex → STRING.
    - Empty list → STRING (no evidence to infer from).
    """
    if not values:
        return BaseType.string()
    if all(isinstance(v, bool) for v in values):
        return BaseType.boolean()
    # Exclude booleans from numeric checks (bool is subclass of int).
    non_bool = [v for v in values if not isinstance(v, bool)]
    if non_bool and len(non_bool) == len(values):
        if all(isinstance(v, int) for v in non_bool):
            return BaseType.integer()
        if all(isinstance(v, (int, float)) for v in non_bool):
            return BaseType.numeric()
    # Date / timestamp heuristic on pure-string columns.
    if all(isinstance(v, str) for v in values):
        if all(_ISO_DATE_RE.match(v) for v in values):
            return BaseType.date()
        if all(_ISO_DATETIME_RE.match(v) for v in values):
            return BaseType.timestamp()
    return BaseType.string()


def _build_schema(
    columns: list[str],
    rows: list[dict[str, Any]],
    primary_key: list[str],
) -> dict[str, ColumnDefinition]:
    """Build a typed schema dict mapping column name → ColumnDefinition."""
    schema: dict[str, ColumnDefinition] = {}
    for col in columns:
        vals = [row[col] for row in rows if row.get(col) is not None]
        base_type = _infer_base_type(vals)
        is_pk = col in primary_key
        schema[col] = ColumnDefinition(
            data_types=base_type,
            primary_key=is_pk,
            nullable=not is_pk,
        )
    return schema


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
        raise UserException("Incremental load requires a Date Field; choose one or switch to full load.")

    if cfg.date_field not in endpoint.date_fields:
        available = ", ".join(endpoint.date_fields) or "none (full load only)"
        raise UserException(
            f"date_field '{cfg.date_field}' is not available for endpoint '{cfg.endpoint}'. Available: {available}."
        )

    return cfg.date_field


def _fetch_records(client: UolClient, endpoint: Endpoint, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch all records from the API and return flat parent rows."""
    parent_rows: list[dict[str, Any]] = []
    for record in client.iter_records(endpoint.path, params=params):
        parent_rows.append(flatten_record(record))
    return parent_rows


class Component(ComponentBase):
    @cached_property
    def _connection_config(self) -> ConnectionConfig:
        """Validated connection-only config, shared by run() and sync actions."""
        try:
            return ConnectionConfig(**self.configuration.parameters)
        except Exception as exc:
            raise UserException(f"Invalid configuration: {exc}") from exc

    @cached_property
    def _client(self) -> UolClient:
        """Build the API client once per invocation from the connection config."""
        conn = self._connection_config
        return UolClient(conn.base_url, conn.email, conn.api_token)

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

        run_started_at = datetime.now(UTC)
        since = resolve_since(cfg.date_from, self.get_state_file() or {}) if incremental else None
        params = {active_field: since} if (active_field and since) else {}

        LOGGER.info("Extracting %s (date_field=%s, since=%s)", endpoint.name, active_field, since)

        parent_rows = _fetch_records(self._client, endpoint, params)

        LOGGER.info("Fetched %d %s records", len(parent_rows), endpoint.name)

        self._write_table(
            endpoint.name,
            parent_rows,
            endpoint.primary_key,
            incremental,
            endpoint.columns,
            cfg.columns,
        )

        if incremental:
            self.write_state_file({STATE_LAST_RUN: run_started_at.isoformat()})
            LOGGER.info("Saved incremental watermark last_run=%s", run_started_at.isoformat())

    def _get_config(self) -> Configuration:
        try:
            return Configuration(**self.configuration.parameters)
        except Exception as exc:
            raise UserException(f"Invalid configuration: {exc}") from exc

    def _write_table(
        self,
        name: str,
        rows: list[dict[str, Any]],
        primary_key: list[str],
        incremental: bool,
        known_columns: tuple[str, ...] = (),
        selected_columns: list[str] | None = None,
    ) -> None:
        # Guard: if there is no primary key, force full-overwrite (incremental upsert requires a PK)
        if not primary_key:
            incremental = False
        columns = self._collect_columns(rows, primary_key, known_columns)
        if selected_columns:
            # Restrict output to the user's selection, but always keep the primary key
            # (required for the table key and incremental upsert). Order is preserved.
            keep = set(selected_columns) | set(primary_key)
            columns = [c for c in columns if c in keep]
        schema = _build_schema(columns, rows, primary_key)
        table = self.create_out_table_definition(
            f"{name}.csv",
            schema=schema,
            primary_key=primary_key,
            incremental=incremental,
            has_header=True,
        )
        # Write the header row and set has_header=true in the manifest: Storage skips
        # the header line and applies the schema's column types. The header is kept for
        # easier debugging of the produced CSVs.
        with open(table.full_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        self.write_manifest(table)
        LOGGER.info("Wrote %d rows to %s", len(rows), name)

    @staticmethod
    def _collect_columns(
        rows: list[dict[str, Any]], primary_key: list[str], known_columns: tuple[str, ...] = ()
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
        if not self._client.ping():
            raise UserException("Could not authenticate against UOL (/v1/ping failed).")
        return ValidationResult("Connection established.")

    @sync_action("listEndpoints")
    def list_endpoints(self) -> list[SelectElement]:
        return [SelectElement(value=n, label=n.replace("_", " ").title()) for n in endpoint_names()]

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

    @sync_action("listColumns")
    def list_columns(self) -> list[SelectElement]:
        endpoint_name = self.configuration.parameters.get("endpoint")
        if not endpoint_name:
            return []
        try:
            endpoint = get_endpoint(endpoint_name)
        except KeyError:
            return []

        # Start from the curated static registry (curated order, available for some endpoints).
        names: list[str] = list(endpoint.columns)

        # Augment with a live 1-record sample so endpoints without a static registry are
        # covered and the listed names match the exact flattened output columns. A sync
        # action must never hard-fail the UI, so any error here is swallowed — but logged
        # at debug level so a bad token / unreachable API is still diagnosable.
        try:
            sample = self._client.sample_record(endpoint.path)
            if sample:
                for col in flatten_record(sample):
                    if col not in names:
                        names.append(col)
        except Exception as exc:
            LOGGER.debug("listColumns: could not sample %s, returning registry columns only: %s", endpoint.path, exc)

        return [SelectElement(value=c, label=c) for c in names]


if __name__ == "__main__":
    try:
        Component().execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
