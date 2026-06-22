# Design: `probe` sync action for ex-uol

**Date:** 2026-06-22
**Status:** Approved

## Goal

Add a fast, read-only **`probe`** sync action that lets an AI agent (KAI, or any
agent configuring this extractor) peek into the UOL end system and get real data
back quickly — without committing to a full `run`. All operator/agent-facing
instructions for the action live in the configuration schema, mirroring the
`keboola.ex-google-drive` `probe` convention.

## Behavior — dual mode

A single `@sync_action("probe")` method on `Component`, with the mode decided by
whether `endpoint` is present in the merged `parameters`:

- **Catalog mode** (no `endpoint`): returns the endpoint registry — every
  endpoint's `name`, `primary_key`, `date_fields`, `columns`. No HTTP call.
  This is what an agent hits first (typically from the root config) to discover
  what UOL exposes.
- **Sample mode** (`endpoint` set): resolves the endpoint via
  `_get_endpoint_by_name`, uses the cached `self._client` (which validates the
  connection config), fetches up to `probe_limit` real records from page 1,
  flattens them via `flatten_record`, and returns the endpoint's `primary_key`,
  `date_fields`, `columns` (registry ∪ discovered), `sample_count`, and the
  `sample` rows.

The action returns a plain JSON-serializable `dict`. `keboola.component`'s
`process_sync_action_result` serializes a `dict` directly via `json.dumps` and
does **not** inject `status`, so the returned dict includes `"status": "success"`
explicitly.

`probe_limit` defaults to **5** and is hard-capped at **20** to keep the
sync-action stdout payload small. It is read directly from `parameters` (no
Pydantic model change; `run()` ignores it).

### Response shapes

Catalog mode (no `endpoint`):

```json
{
  "status": "success",
  "endpoints": [
    {
      "name": "sales_invoices",
      "primary_key": ["gid"],
      "date_fields": ["tax_payment_date_from", "issue_date_from", "due_date_from"],
      "columns": ["accounting_address_address_id", "..."]
    }
  ]
}
```

Sample mode (`endpoint` set):

```json
{
  "status": "success",
  "endpoint": "sales_invoices",
  "primary_key": ["gid"],
  "date_fields": ["tax_payment_date_from", "issue_date_from", "due_date_from"],
  "columns": ["gid", "buyer_name", "..."],
  "sample_count": 5,
  "sample": [{ "gid": 123, "buyer_name": "..." }]
}
```

## Components touched

1. **`src/component.py`** — new `probe` sync action + `_probe_limit()` clamp
   helper. Reuses the existing cached `self._client` and the
   `_get_endpoint_by_name` helper. The only new behavior; `run()` and the other
   sync actions are untouched.
2. **`src/client.py`** — add `sample_records(path, limit)`: one GET with
   `per_page=limit`, returns up to `limit` items. `sample_record` now delegates
   to it (`sample_records(path, 1)`), leaving `listColumns` unchanged.
3. **`component_config/configRowSchema.json`** — add two elements after `columns`:
   - `probe_limit` — integer, default 5, min 1, max 20, title "Probe sample size".
     Its `description` carries the full agent-facing instructions: what the probe
     does, the two response shapes, rules for agents (keep samples small,
     read-only, start with catalog mode at root), how to map a probe result back
     into a row config (`endpoint` → which object, `date_fields` →
     `date_field` + `load_type`, `columns` → `columns`), error cases, and related
     actions (`listEndpoints` / `listColumns` / `testConnection` / `run`).
   - `run_probe` — `"type": "button"`, `"format": "sync-action"`,
     `options.async.action": "probe"`, label "Run Probe (sample data)".

   The button lives in the row schema (best for humans configuring a row, where
   `endpoint` is already selected → probe runs in sample mode). The action itself
   is callable by name from any context, so KAI can invoke it at the root with
   explicit parameters; with no `endpoint` it returns the catalog.

## Errors

- Unknown `endpoint` → `UserException` listing the valid endpoint names (via
  `_get_endpoint_by_name`).
- Missing / invalid credentials → the existing `ConnectionConfig` / `UolClient`
  `UserException` surfaces unchanged through `self._client`.
- Catalog mode never touches the API, so it cannot fail on connectivity.

## Tests (VCR functional + unit)

- `tests/functional/<n>_probe_catalog` — no `endpoint` → expected
  `sync_action_result.json` is the catalog (no cassette HTTP interaction).
- `tests/functional/<n>_probe_sample_sales_invoices` — `endpoint=sales_invoices`,
  `probe_limit=5` → cassette for `GET /v1/sales_invoices?per_page=5`, expected
  result is the sample payload.
- A unit assertion for catalog mode in `tests/test_sync_actions.py`.

## Scope guardrails

No change to `run()`, no change to existing sync actions, no Pydantic model
change. One new component method (+ a small helper), one new client method, two
schema elements, two functional tests + one unit assertion. No documentation-file
changes.
