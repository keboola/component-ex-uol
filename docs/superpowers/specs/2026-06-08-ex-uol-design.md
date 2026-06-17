# ex-uol — Design Spec

> Type: extractor
> Component ID: keboola.ex-uol
> Status: draft
> Date: 2026-06-08

## 1. Overview & source system

`keboola.ex-uol` extracts data from **UOL Účetnictví**, a Czech cloud accounting/ERP system, via its
REST API. It reads accounting objects (invoices, contacts, products, bank movements, accounting
records, …) into Keboola Storage tables, one object per config row, with optional incremental loading.

- **Source system:** UOL Účetnictví REST API — Swagger UI at https://api.uol.cz/, OpenAPI spec at
  https://api.uol.cz/openapi.yaml.
- **Primary use case:** sync a UOL accounting tenant into Keboola for reporting, reconciliation, and
  downstream analytics (e.g. receivables ageing, sales/purchase analysis, bank movement matching).

## 2. Keboola mapping

- **Source objects → output tables.** Each UOL list endpoint (`/v1/<resource>`) maps to one output
  table named after the resource (e.g. `contacts.csv`, `sales_invoices.csv`). Nested line-item arrays
  (e.g. an invoice's `items[]`) are exploded into a **child table** `<resource>_items.csv` linked to
  the parent by a foreign-key column (`<resource>_id`). See §4.
- **Config rows, one row per object.** ~30 independent endpoints → **config rows** (Keboola
  convention): each row selects one endpoint, can be enabled/scheduled/run/retried independently, and
  gets its **own per-row `state.json`** watermark (root state is unused when rows exist). Rows execute
  **sequentially in `rowsSortOrder` by default**; row-level parallelism is opt-in (`parallelism` > 1)
  and safe here since each row writes a distinct table and owns its state — we don't enable it by
  default. Connection/auth lives at **config level**; endpoint selection + load options live at
  **row level**.
- **Incremental strategy — user-driven `date_field` + `date_from` (revised after checklist review).**
  The API has no universal `modified-since`, and only **6 endpoints** expose any date filter at all
  (`sales_invoices`, `sales_orders`, `purchase_invoices`, `accounting_records`, `receivables`,
  `uploaded_documents`); the other 23 are **full-load only** by API design. Critically, the available
  filters mix true update cursors (`updated_at_from`, `created_at_from`, `last_payment_time_from`) with
  **business-document dates** (`issue_date_from`, `due_date_from`, `date_from`, …) — so the component
  must **not** hardcode one cursor and stuff wall-clock-now into it (that silently drops backdated /
  late-entered / same-date-edited records). Instead the registry stores, per endpoint, the **full list
  of available `*_from` params**, and the user controls incrementality with two row fields:
  - **`date_field`** — which `*_from` param to filter on, chosen from a dropdown populated by the
    `listDateFields` sync action (reads the registry for the selected endpoint). Empty / no available
    fields → **full load**, no date filter.
  - **`date_from`** — the lower-bound value, accepting: **`last_run`** (use the `state.json` watermark),
    relative phrases (**`yesterday`**, **`5 days ago`**, …), or a **hardcoded ISO date**. Parsed with
    `dateparser`. `last_run` with no stored watermark → first run is unfiltered (full history), then the
    watermark takes over.
  - **Watermark:** `run_started_at` (UTC) captured **before** fetch, persisted as `last_run` **after** a
    successful write, only when a `date_field` is active. Output mapping is incremental (PK upsert) when
    a `date_field` is set; full-overwrite otherwise. (`load_type` is **replaced** by this `date_field` +
    `date_from` model.)
- **Secrets.** The API token is a `#`-prefixed key (`#api_token`) so the platform encrypts it.
- **Sync actions.** `test-connection` (calls `/v1/ping`) validates credentials in the UI. The endpoint
  picker is a **static enum dropdown** in the row schema, not a sync action — UOL's endpoint catalog is
  fixed and known at build time (the API does not enumerate its own resources), so an enum is the
  correct fit rather than a live list call.
- **Output tables: native types + explicit PK.** CF default for a new component is **authoritative
  native types**: emit a `schema` manifest (`data_type.base.type`) with an explicit primary key, and
  flip the Dev Portal `dataTypeSupport` property to `authoritative` (a **Phase 6** task — until flipped,
  the platform silently downgrades to legacy hints). Because the ~30 endpoints have heterogeneous,
  dynamically-discovered columns, v1 declares columns dynamically from the response with base type
  **STRING** (numbers/dates preserved as text — safe, lossless, and reviewer-acceptable for a
  dynamic-schema extractor) while still setting the **explicit PK** from the registry. The
  python-component lib auto-detects `KBC_DATA_TYPE_SUPPORT` (absent → legacy), so the code emits the
  right manifest format for either mode.
- **Output bucket / table naming.** Table names are the resource names; the component does **not**
  hard-code a destination bucket (a hard-coded destination is silently overridden if `default_bucket`
  is on). Whether to enable `default_bucket` (→ `in.c-keboola.ex-uol-{configId}`) is a **Phase 6**
  Dev Portal decision; default is off, letting standard output-mapping behaviour place tables.
- **Primary keys are resource-specific** — declared per endpoint in the registry (`<resource>_id` /
  `gid`, e.g. contacts use `contact_id`), not a universal `id`.

## 3. Authentication & connection

- **Auth method:** HTTP **Basic** — email as username, API token as password
  (`Authorization: Basic base64(email:token)`). Chosen because it is the only scheme the API offers and
  it authenticates **headlessly** (no OAuth redirect, no admin app registration).
- **Connection method:** REST/JSON over HTTPS. `Accept: application/json`, UTF-8.
- **Provisioning (headless, customer self-service):**
  1. In UOL, the user opens **Settings → API tokens** (`/api_tokens`) and mints a token.
  2. The user account must have the **"REST API" permission** enabled.
  3. The user supplies their login email + the token to the component config.
  No platform-admin or vendor-side app registration is required.
- **Blockers / access:** None. A publicly testable **demo instance** exists at
  `https://test.demo.uol.cz/api` with **published, verified demo credentials** in the OpenAPI spec
  (`api.uol.cz/openapi.yaml`, under "Where to start"): demo email + demo token. Confirmed working — a
  live `GET /v1/ping` returns 200 and `GET /v1/contacts` returns real data. These credentials drive VCR
  cassette recording directly (the implementer pulls them from the spec at record time; not stored in
  this repo, and still sanitized from cassettes per §7).

## 4. Data model & endpoints

- **Scope: all list (collection) GET endpoints**, selectable per row via the endpoint dropdown.
  Catalogued in the client registry (resource path · primary key · incremental param · child arrays):
  - **Sales:** `sales_invoices`, `sales_orders`, `retails`
  - **Purchases:** `purchase_invoices`, `purchase_orders`
  - **Contacts:** `contacts`, `contact_bank_accounts`
  - **Products:** `products`, `product_categories`, `price_lists`
  - **Banking:** `my_bank_accounts`, `bank_balances`, `bank_movements`, `bank_movement_items`,
    `demands_for_payment`
  - **Company:** `my_companies`, `departments`, `contracts`
  - **Cash:** `petty_cashes`, `petty_cash_incomes`, `petty_cash_disburstments`
  - **Accounting:** `accounting_records`, `receivables`, `internal_documents`
  - **Documents:** `uploaded_documents`, `document_templates`
  - **Reference:** `currencies`, `countries`, `predefined_texts`, `payment_rules`
- **Response envelope (verified against the demo instance):** the list body is
  `{ "_meta": { "pagination": { "first", "last", "next" } }, "items": [ … ] }` — records live under
  **`items`**, and each item also carries its own `_meta.href`. The client reads `items` and follows
  `_meta.pagination.next`.
- **Primary keys are resource-specific** (verified: contacts use `contact_id` = e.g. `"adrian_stanek"`,
  not `id`; other resources use `<resource>_id` or `gid`). The registry declares each resource's PK —
  there is no universal `id` field.
- **Pagination:** `page` (from 1) + `per_page` (component uses max **250**). Follow
  `_meta.pagination.next` until absent (fallback: increment `page` until an empty `items`).
- **Rate limits:** general **30 req / 10 s**; `/v1/receivables` **10 req / 10 s**. The client
  self-throttles to stay under the per-resource limit and, on **HTTP 429**, backs off (honour
  `Retry-After`, default 30 s) and retries.
- **Bulk/async export:** none — all reads are synchronous paginated GETs.
- **Nested data → child tables (chosen strategy).** Nested arrays are common and not limited to
  invoice/order `items[]` — verified that `contacts` carry `addresses[]`, and records also embed nested
  *objects* (`creator`, `modifier`, `contract`). Per the endpoint registry, declared nested **arrays**
  are exploded into `<resource>_<array>.csv` (e.g. `sales_invoices_items.csv`, `contacts_addresses.csv`)
  with a `<resource>_id` foreign key + the child's own PK where present. Scalar fields stay on the
  parent row; nested **objects** and any *non-declared* array are serialized to JSON-string columns to
  avoid data loss. This keeps the parent relational and query-friendly while preserving fidelity.

## 5. Configuration & schema

> **Handoff:** the actual `configSchema.json` / `configRowSchema.json` is built by
> **`component-build-ui`** — this section describes the fields, not the JSON.

- **Config-level (`configSchema.json`):**
  - `base_url` (string, required) — full API base URL including `/api`, e.g.
    `https://test.demo.uol.cz/api` or `https://{customerId}.ucetnictvi.uol.cz/api`. (User pastes the
    full URL — chosen over a type+customerId pair for flexibility across demo/sandbox/production.)
  - `email` (string, required) — UOL login email (Basic-auth username).
  - `#api_token` (string, **secret**, required) — UOL API token (Basic-auth password).
  - Sync action: **test-connection** button.
- **Row-level (`configRowSchema.json`):**
  - `endpoint` (string, required) — **enum dropdown** of the registry resources (§4).
  - `date_field` (string, optional) — which `*_from` API filter to use; a dropdown populated by the
    **`listDateFields`** sync action (returns the selected endpoint's available date filters from the
    registry, empty for the 23 full-load-only endpoints). Empty → full load.
  - `date_from` (string, optional) — lower-bound value: **`last_run`** (use `state.json` watermark),
    a relative phrase (**`yesterday`**, **`5 days ago`**), or a hardcoded **ISO date**. Parsed with
    `dateparser`. Only applied when `date_field` is set. `last_run` with no stored watermark → unfiltered
    first run.
- **Defaults:** `date_field` empty (full load) unless the user opts into incremental; `per_page` fixed
  at 250 internally (not user-exposed). `load_type` is removed (superseded by `date_field` + `date_from`).

## 6. Code architecture

- **`src/endpoints.py`** — the **endpoint registry**: an immutable list/dict of `Endpoint` records
  (`path`, `primary_key`, `incremental_param` or `None`, `child_arrays`). Single source of truth for
  scope, PKs, incremental capability, and child-table splitting.
- **`src/client.py`** — `UolClient`: `__init__(base_url, email, token)`; `ping()` for test-connection;
  `iter_records(endpoint, params)` generator that handles Basic auth, pagination (`_meta.next`),
  self-throttling, and 429/5xx retry+backoff (`requests` + `urllib3 Retry`/manual backoff).
- **`src/configuration.py`** — Pydantic models: a connection-only `ConnectionConfig`
  (`base_url`, `email`, `#api_token`) used by the `test_connection` sync action (must NOT require
  row-level fields), and the full `Configuration` (adds `endpoint`, `date_field`, `date_from`) used by
  `run()`. A `resolve_since(date_from, state)` helper parses `last_run`/relative/ISO via `dateparser`.
  Validated early.
- **`src/component.py`** — `Component(ComponentBase)`: `run()` is a thin orchestrator —
  `_get_config` → build client → resolve `since` from `state.json` (if incremental + supported) →
  `_fetch` records → `_write_parent_and_children` (parent table + exploded child tables, **`schema`
  manifests** with explicit PK + incremental flag) → advance `state.json` watermark on success. Sync
  action `test_connection`. Any scratch/temp work uses **`/tmp`**, never `/data/out/tables/` (every
  file there is uploaded as a table). Reads `KBC_DATA_TYPE_SUPPORT` via the SDK to pick manifest format.
- **Error handling:** `UserException` (exit 1) for bad config, auth failure (401/403), not-found (404),
  **network/transport errors** (`requests.RequestException` — connection/DNS/timeout/SSL),
  **any other 4xx** (e.g. 400/422 bad filter), **non-JSON 200 bodies**, and **exhausted 429/5xx
  retries**. None of these may escape as a raw exception (which would be exit 2 / "internal error").
  Unexpected/programming errors still bubble up as exit 2. 429/5xx are retried with backoff first.
- **Logging:** `run()` emits INFO progress — selected endpoint + resolved `since`, record/row counts per
  table, and watermark advance — never logging the token, headers, or full response bodies.
- **Key dependencies:** `keboola.component` (core SDK), `requests` (HTTP), `pydantic` (config),
  `dateparser` (relative `date_from` parsing). No vendor SDK (the only one, Ruby `pina`, is archived).

## 7. Testing

- **Fixture shape (platform reality):** the component always receives a **single merged** `config.json`
  with `parameters` at the root (the platform merges root + row before the run), and state is
  **row-scoped** — one `state.json` per test case. Fixtures reflect this; no root/row split to replicate.
- **Datadir tests (`tests/`):**
  - Happy path — a simple resource (`contacts`) → one parent table, correct PK/schema.
  - Child-table path — `sales_invoices` with `items[]` → parent + `sales_invoices_items.csv` with FK.
  - Incremental — seeded `state.json` watermark → only `*_from`-filtered records fetched; watermark
    advances after write; output manifest has `incremental=true` + PK.
  - Full load — `load_type=full_load` ignores state.
  - Empty result — endpoint returns zero rows → empty table, no crash.
  - Auth failure — 401 / error `0002` → `UserException`, **exit 1**.
- **VCR strategy:** record real interactions against the **demo** instance (`test.demo.uol.cz`) for a
  representative set (a paginated list, a child-array resource, a 429-then-success, an empty list).
  **Sanitizers:** strip the `Authorization` header, and scrub the demo email + token (the values from
  the OpenAPI spec) from request/response bodies and query strings (`VCR_SANITIZERS`). Cassettes
  committed; credentials never in fixtures (even though these are demo-only).
- **Sync action tests:** `test-connection` success (200 `/v1/ping`) and failure (401) paths.
- **Seed payloads:** the OpenAPI spec's example responses (and a live demo capture once a token is
  available) seed the first cassettes.

## 8. Deployment & validation (cf-dev project)

- Build an image from the `initial-implementation` branch (CI on branch push).
- Via **kbagent**, create a config in **cf-dev**: `base_url=https://test.demo.uol.cz/api`, demo
  `email` + `#api_token`, with a few rows (`contacts`, `sales_invoices`, `accounting_records`).
- Override the config's **image tag** to the `initial-implementation` build and run a job.
- **Success looks like:** job `success`; output tables `out.c-….contacts`, `…sales_invoices` (+
  `…sales_invoices_items`), `…accounting_records` populated with non-zero rows; resolved image tag
  matches the branch build (not a stale stable release).
- **Phase 6 portal coupling:** the native-types decision (§2) requires flipping the Dev Portal
  `dataTypeSupport` property to `authoritative` (`kbagent dev-portal patch … --property dataTypeSupport
  --value authoritative`, dry-run then TTY-confirm) so the `schema` manifests aren't downgraded —
  done in the Phase 6 portal setup, *after* the bootstrap release.

## 9. Open risks & blockers

1. **Demo API token for VCR** — ✅ **RESOLVED.** Published in the OpenAPI spec (`api.uol.cz/openapi.yaml`)
   and verified working (live `/v1/ping` → 200). No blocker. (Token value lives in the spec, not in
   this repo.)
2. **Incremental coverage is uneven** (low) — only some endpoints expose a date cursor, and the param
   name differs per endpoint (`updated_at_from`, `created_at_from`, `issue_date_from`, `date_from`).
   The registry must encode the correct param per endpoint; endpoints with no cursor are full-load.
3. **Heterogeneous response shapes across ~30 endpoints** (low/medium) — child-array fields and PKs
   vary; the registry is the mitigation, but each endpoint's shape should be confirmed against the
   OpenAPI spec when added. v1 verifies the high-value endpoints end-to-end; the long tail relies on the
   generic parent/child + JSON-fallback handling.
