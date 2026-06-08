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
  convention): each row selects one endpoint, can be enabled/scheduled/run/retried independently, gets
  its own `state.json` watermark, and rows run in parallel. Connection/auth lives at **config level**;
  endpoint selection + load options live at **row level**.
- **Incremental strategy.** Endpoint-dependent (the API has no universal `modified-since`). The client
  carries a per-endpoint registry declaring whether the endpoint supports a date/updated cursor and
  which query param drives it. Where supported, the row defaults to incremental: persist a `last_run`
  ISO-UTC watermark in `state.json`, pass it as the endpoint's `*_from` filter, set incremental output
  mapping with the resource primary key (upsert). Where unsupported, full load every run (stated in
  the registry). Watermark is captured **before** fetch and persisted **after** a successful write.
- **Secrets.** The API token is a `#`-prefixed key (`#api_token`) so the platform encrypts it.
- **Sync actions.** `test-connection` (calls `/v1/ping`) validates credentials in the UI. The endpoint
  picker is a **static enum dropdown** in the row schema, not a sync action — UOL's endpoint catalog is
  fixed and known at build time (the API does not enumerate its own resources), so an enum is the
  correct fit rather than a live list call.
- **Output bucket / table naming.** Default-bucket behaviour (no hard-coded bucket); table names are
  the resource names. Primary keys come from the endpoint registry (`id`, or `gid` for resources that
  use it).

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
  - `load_type` (enum, default `incremental_load`) — `full_load` | `incremental_load`. Honoured only
    when the selected endpoint supports an incremental cursor; otherwise full load regardless (the UI
    note states this).
  - `date_from` (string, optional) — ISO date seed for the **first** incremental run / lower bound of a
    full window; ignored once a `state.json` watermark exists.
- **Defaults:** `load_type=incremental_load`; `per_page` fixed at 250 internally (not user-exposed).

## 6. Code architecture

- **`src/endpoints.py`** — the **endpoint registry**: an immutable list/dict of `Endpoint` records
  (`path`, `primary_key`, `incremental_param` or `None`, `child_arrays`). Single source of truth for
  scope, PKs, incremental capability, and child-table splitting.
- **`src/client.py`** — `UolClient`: `__init__(base_url, email, token)`; `ping()` for test-connection;
  `iter_records(endpoint, params)` generator that handles Basic auth, pagination (`_meta.next`),
  self-throttling, and 429/5xx retry+backoff (`requests` + `urllib3 Retry`/manual backoff).
- **`src/configuration.py`** — Pydantic models: `Configuration` (`base_url`, `email`, `pswd_api_token`)
  and `RowConfiguration` (`endpoint`, `load_type`, `date_from`), with a `LoadType` StrEnum and a
  computed `incremental` property. Validated early.
- **`src/component.py`** — `Component(ComponentBase)`: `run()` is a thin orchestrator —
  `_get_config` → build client → resolve `since` from `state.json` (if incremental + supported) →
  `_fetch` records → `_write_parent_and_children` (parent table + exploded child tables, manifests with
  PK + incremental flag) → advance `state.json` watermark on success. Sync action `test_connection`.
- **Error handling:** `UserException` (exit 1) for bad config (missing/invalid `base_url`/email/token),
  auth failure (401/`0001`,`0002`), invalid customer (`0003`), and not-found (`0004`); unexpected
  errors bubble up as exit 2. 429 is handled by retry, not surfaced as an error unless retries exhaust.
- **Key dependencies:** `keboola.component` (core SDK), `requests` (HTTP), `pydantic` (config),
  `urllib3 Retry` (backoff). No vendor SDK (the only one, Ruby `pina`, is archived and irrelevant).

## 7. Testing

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
