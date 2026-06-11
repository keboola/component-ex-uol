"""ex-uol — UOL Účetnictví extractor."""

from __future__ import annotations

import csv
import json
import logging
import re
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
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

# Maximum non-null samples retained per column for type inference.
# Keeping a bounded sample is sufficient to determine the base type while
# avoiding unbounded memory growth on large datasets.
_TYPE_SAMPLE_LIMIT = 1_000


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
    type_samples: dict[str, list[Any]],
    primary_key: list[str],
) -> dict[str, ColumnDefinition]:
    """Build a typed schema dict mapping column name → ColumnDefinition.

    ``type_samples`` maps column name to a bounded list of non-null values
    accumulated during the streaming pass — no full row set required.
    """
    schema: dict[str, ColumnDefinition] = {}
    for col in columns:
        vals = type_samples.get(col, [])
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


class _SpillState:
    """Accumulates streaming state during pass 1 (disk spill).

    Attributes
    ----------
    spill_path:
        Path to the NDJSON temp file written during pass 1.
    columns:
        Ordered list of all discovered column names (union across all rows).
    type_samples:
        Per-column bounded list of non-null values used for type inference.
        At most _TYPE_SAMPLE_LIMIT entries are retained per column.
    row_count:
        Total number of rows written to the spill file.
    """

    def __init__(self, spill_path: str) -> None:
        self.spill_path = spill_path
        self.columns: list[str] = []
        self._col_set: set[str] = set()
        self.type_samples: dict[str, list[Any]] = defaultdict(list)
        self.row_count: int = 0

    def observe_column(self, col: str) -> None:
        if col not in self._col_set:
            self._col_set.add(col)
            self.columns.append(col)

    def observe_value(self, col: str, value: Any) -> None:
        if value is not None and len(self.type_samples[col]) < _TYPE_SAMPLE_LIMIT:
            self.type_samples[col].append(value)


def _stream_to_spill(
    client: UolClient,
    endpoint: Endpoint,
    params: dict[str, Any],
    primary_key: list[str],
    known_columns: tuple[str, ...],
    spill_path: str,
) -> _SpillState:
    """Pass 1 — stream API records to a NDJSON spill file.

    Simultaneously:
    - Seeds column order: PK first, then known_columns, then discovered keys.
    - Accumulates bounded type-inference samples (no full row set in memory).
    - Writes each flattened row as one JSON line to *spill_path*.

    Peak memory is O(columns * _TYPE_SAMPLE_LIMIT) + one row at a time.
    """
    state = _SpillState(spill_path)

    # Seed ordering: PK columns first, then known static columns.
    for col in primary_key:
        state.observe_column(col)
    for col in known_columns:
        state.observe_column(col)

    with open(spill_path, "w", encoding="utf-8") as fh:
        for record in client.iter_records(endpoint.path, params=params):
            row = flatten_record(record)
            for col, value in row.items():
                state.observe_column(col)
                state.observe_value(col, value)
            fh.write(json.dumps(row, ensure_ascii=False))
            fh.write("\n")
            state.row_count += 1

    return state


def _write_csv_from_spill(
    spill_path: str,
    columns: list[str],
    out_path: str,
) -> None:
    """Pass 2 — read the NDJSON spill file and write the final CSV.

    Processes one row at a time so peak memory is O(one row).
    """
    with (
        open(spill_path, encoding="utf-8") as spill_fh,
        open(out_path, "w", encoding="utf-8", newline="") as csv_fh,
    ):
        writer = csv.DictWriter(csv_fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for line in spill_fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            writer.writerow(row)


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

        self._write_table(
            endpoint.name,
            endpoint.primary_key,
            incremental,
            endpoint.columns,
            cfg.columns,
            params,
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
        primary_key: list[str],
        incremental: bool,
        known_columns: tuple[str, ...] = (),
        selected_columns: list[str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Two-pass disk-spill write.

        Pass 1: stream API records to a temp NDJSON file; collect column union
                and bounded type-inference samples.
        Pass 2: read the spill file row-by-row and write the final CSV with the
                complete header (known only after pass 1 finishes).

        Peak memory is O(columns * _TYPE_SAMPLE_LIMIT) + one row at a time —
        the full table is never held in RAM.
        """
        # Guard: if there is no primary key, force full-overwrite (incremental upsert requires a PK)
        if not primary_key:
            incremental = False

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".ndjson",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            spill_path = tmp.name

        try:
            # --- Pass 1: stream → spill ---
            state = _stream_to_spill(
                self._client,
                self._get_endpoint_by_name(name),
                params or {},
                primary_key,
                known_columns,
                spill_path,
            )

            columns = state.columns
            if selected_columns:
                keep = set(selected_columns) | set(primary_key)
                columns = [c for c in columns if c in keep]

            schema = _build_schema(columns, state.type_samples, primary_key)
            table = self.create_out_table_definition(
                f"{name}.csv",
                schema=schema,
                primary_key=primary_key,
                incremental=incremental,
                has_header=True,
            )

            # --- Pass 2: spill → CSV ---
            _write_csv_from_spill(spill_path, columns, table.full_path)

            self.write_manifest(table)
            LOGGER.info("Wrote %d rows to %s", state.row_count, name)

        finally:
            # Always remove the temp file, even on error.
            try:
                Path(spill_path).unlink(missing_ok=True)
            except OSError:
                pass

    def _get_endpoint_by_name(self, name: str) -> Endpoint:
        """Return the Endpoint for *name*; raises UserException if not found."""
        try:
            return get_endpoint(name)
        except KeyError:
            raise UserException(f"Unknown endpoint '{name}'. Valid endpoints: {', '.join(endpoint_names())}.") from None

    @staticmethod
    def _collect_columns(
        rows: list[dict[str, Any]], primary_key: list[str], known_columns: tuple[str, ...] = ()
    ) -> list[str]:
        """Return ordered column list from an in-memory row set.

        Retained for unit tests and backward-compatibility; the run() path now
        uses _stream_to_spill which builds the same ordering incrementally.
        """
        ordered: list[str] = list(primary_key)
        for col in known_columns:
            if col not in ordered:
                ordered.append(col)
        seen = set(ordered)
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
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
