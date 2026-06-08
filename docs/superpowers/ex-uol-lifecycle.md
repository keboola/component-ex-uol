# keboola.ex-uol — New Component Build Lifecycle

> **For agents (read this first):** This file is the **durable, cross-session source of truth** for
> building this new component. `TodoWrite` resets every session; this file does not. Whenever you
> start work on this component — in any skill, in any session — open this file, find the phase you
> own, and act on it.
>
> **The loop for every phase:**
> 1. Read this file; find your phase and the phase(s) before it. Earlier phases are dependencies —
>    if one isn't ticked, resolve it (or surface the blocker) before starting yours.
> 2. Do the phase's work.
> 3. Dispatch the **phase verifier** (see *Verification contract* below) as a fresh subagent.
> 4. **Only tick `- [x]` when the verifier returns ✅ with real evidence** — never on your own
>    say-so. Paste the evidence line under the phase.
> 5. Commit this file (`git add` + commit) so the next session sees the new state.
>
> Mirror the still-open phases into `TodoWrite` for the live in-session checklist, but treat *this
> file* as authoritative.

**Component:** `keboola.ex-uol`  ·  **Type:** `extractor`
**Created:** `2026-06-08`
**Spec:** `docs/superpowers/specs/2026-06-08-ex-uol-design.md`
**Plan:** `docs/superpowers/plans/2026-06-08-ex-uol.md` (created in Phase 3)

---

## Verification contract

A phase is "done" only when it's confirmed against **real evidence** by a check that is independent of
the work itself.

**Preferred — dispatch a fresh subagent** (the `Task`/`Agent` tool) so the verifier has a clean context
and no implementer bias. **If subagent dispatch isn't available to you**, run the verification yourself
as a *separate, deliberate pass*: re-derive every piece of evidence from scratch (run the commands,
read the files, query the platform) and do **not** lean on your own earlier claims about what you did.
Either way, give the verifier the phase's **Definition of done** and this instruction:

> Verify ONLY whether this phase is genuinely complete, by gathering **real evidence** — run the
> commands, read the actual files, query the platform/portal/git as needed. Do **not** fix or change
> anything; you are a checker, not an implementer. Return either:
> - `✅ DONE` followed by the concrete evidence you observed (command output, file paths, job IDs,
>   tag names — the specifics), or
> - `❌ NOT DONE` followed by exactly what is missing or failing.
>
> If you cannot confirm a requirement with evidence, default to `❌ NOT DONE`. "Should be fine" is not
> evidence.

If the verifier returns ❌, the box stays unticked — fix the gap and re-verify. This mirrors the
superpowers principle: *evidence before assertions, always.*

---

## Phases

Later phases generally depend on earlier ones, so work top-down. Where two adjacent phases are
genuinely independent (Phase 6 portal value-setup and Phase 7 cf-dev smoke-test don't depend on each
other — both only need Phases 1–5), either order is fine.

### Phase 1 — Scaffold + bootstrap release · owner: `component-get-started` (verified here by `component-plan-new`)
- [x] complete

**Definition of done:**
- Repo pushed to `origin` under the correct org; initial commit on `main`.
- Per-repo portal creds set for the **target vendor**: `KBC_DEVELOPERPORTAL_USERNAME` (variable) +
  `KBC_DEVELOPERPORTAL_PASSWORD` (secret).
- Dev Portal **app created** (via `kbagent dev-portal create`) — the release pipeline needs a target.
- `0.0.1` tag exists and its `push.yml` run **built and pushed the image** (run is green).

> Note: `get-started` runs *before* this tracker exists. `component-plan-new` creates this file and
> runs the Phase 1 verifier retroactively to confirm the scaffold actually landed before planning.

**Evidence:** ✅ Verified 2026-06-08. Repo on `origin/keboola/component-ex-uol`, `main`, initial commit
`6f401c4`. `KBC_DEVELOPERPORTAL_USERNAME` (variable) + `KBC_DEVELOPERPORTAL_PASSWORD` (secret) both set.
Dev Portal app `keboola.ex-uol` exists (type extractor). Release `0.0.1` tag present; push.yml run
`27125422167` completed **success** (2m33s), image digest `sha256:5711ee47…ad9ac1` pushed to ECR.

### Phase 2 — Research the source/target system · owner: `component-plan-new`
- [x] complete

**Definition of done:** a research summary settles API style(s), auth method(s) and which the vendor
recommends, pagination, rate limits, incremental/cursor support — plus a **feasibility & provisioning
verdict** (sandbox availability, headless-auth vs admin-only setup). Blockers surfaced to the user.

**Evidence:** ✅ Verified 2026-06-08 (spec commit `4d25724`, §1–4). UOL Účetnictví REST/JSON API;
auth = HTTP **Basic** (email + token, headless, customer self-service); pagination `page`+`per_page`
(max 250) via `_meta.pagination.next` (verified live); rate limits 30 req/10s general, 10 req/10s
receivables, 429+backoff; incremental is **per-endpoint** (registry declares cursor param, e.g.
`issue_date_from`, `updated_at_from`, or None). **Provisioning verdict: GREEN** — public demo instance
`test.demo.uol.cz`, demo creds published in the OpenAPI spec, live `/v1/ping` → 200; no admin-only
blocker. All ~30 endpoints' PKs/child-arrays captured from real demo responses.

### Phase 3 — Spec + implementation plan · owner: `component-plan-new`
- [x] complete

**Definition of done:** `docs/superpowers/specs/...-design.md` committed (full scope: source system,
Keboola mapping, auth/provisioning, data model, config/schema, code architecture, datadir + VCR
tests, cf-dev deployment, risks) with **no placeholders/TODOs**, AND a superpowers plan committed at
`docs/superpowers/plans/...md`. User approved the spec. The **grounding reconciliation gate** ran:
the evidence below contains a per-reference reconciliation list covering each behaviour-relevant
`keboola-context` file (`[reference] → correct | corrected: …`), and every `corrected:` item is
reflected in the committed spec.

**Evidence:** ✅ Verified 2026-06-08. Spec committed `4d25724`, plan `docs/superpowers/plans/2026-06-08-ex-uol.md`
committed; both placeholder-free; user approved the spec. **Grounding reconciliation list** (keboola-context):
- `architecture-conventions.md` → correct (config rows, `#` secrets, sync actions, client/`run()` split applied).
- `config-rows.md` → **corrected:** dropped "rows run in parallel" → rows are **sequential by default**, parallelism opt-in; per-row `state.json` (root state unused). (spec §2)
- `incremental-state.md` → correct (watermark captured before fetch, persisted after success; PK upsert).
- `native-data-types.md` → **corrected:** vague "where supported" → emit `schema` manifest + explicit PK, dynamic STRING columns, flip Dev Portal `dataTypeSupport=authoritative` in Phase 6. (spec §2, §8)
- `output-mapping.md` → **corrected:** added `/tmp` scratch rule (everything in `/data/out/tables` is uploaded); incremental+PK=upsert confirmed. (spec §6)
- `default-bucket.md` → **corrected:** no hard-coded destination (silently overridden if default_bucket on); default_bucket left a Phase 6 decision. (spec §2)
- `encryption.md` → correct (`#api_token` → `KBC::ProjectSecure`).
- `exit-codes.md` → correct (UserException=1, unexpected=2).
- `environment-variables.md` → correct (no `forward_token`; SDK auto-detects `KBC_DATA_TYPE_SUPPORT`; merged config.json + row-scoped state noted in spec §7).
- `telemetry.md` → N/A (about querying telemetry, not building an extractor) — deliberately skipped.

### Phase 4 — Implement on `initial-implementation` branch · owner: `component-develop`
- [x] complete

> **How this gets executed:** the superpowers plan (Phase 3) is worked task-by-task via
> `superpowers:subagent-driven-development`, with implementation tasks dispatched to `component-develop`
> (schema/UI → `component-build-ui`). This box gates the *milestone* — tick it on the verifier's ✅,
> not when the plan's last task is checked off.

**Definition of done:** branch `initial-implementation` exists; component logic implemented per the
plan; `run()` is a clean orchestrator with logic in private methods; `ruff check` clean. Fine-grained
step tracking lives in the superpowers plan file — this box tracks the phase as a whole.

**Evidence:** ✅ Verified 2026-06-08 by fresh subagent. Branch `initial-implementation` exists. Source
(396 lines): `src/endpoints.py` (71), `src/configuration.py` (34), `src/client.py` (106),
`src/flatten.py` (54), `src/component.py` (131). `run()` (component.py:33) is a thin orchestrator
delegating to `_get_config`/`_resolve_since`/`_build_params`/`_write_table`/`_child_pk` +
`get_endpoint`/`flatten_record`. `ruff check src/ tests/` → All checks passed. Built task-by-task via
subagent-driven-development with per-task spec+quality review; plan Tasks 1–12 all complete.

### Phase 5 — Local VCR tests + cassettes · owner: `component-test`
- [x] complete

**Definition of done:** datadir/unit/VCR tests present; the **full `pytest` suite runs green** (paste
the `N passed` line, not "should pass"); cassettes recorded and **verifiably sanitized** — grep every
cassette for secret patterns (the values from `secrets.json`, common keys like `token`/`password`/
`authorization`/`api_key`, and the configured `VCR_SANITIZERS` targets) and paste a clean result.

**Evidence:** ✅ Verified 2026-06-08 by fresh subagent. Full suite **green: `37 passed in 0.56s`**
(28 unit + 9 functional). Unit tests: registry, config, client (auth/pagination/throttle/429-exhaustion),
flatten, incremental helpers, sync actions. VCR functional cases (7 cassettes at
`tests/functional/0{1..7}_*/source/data/cassettes/requests.json`): testConnection, listEndpoints,
full_load contacts (+addresses child), sales_invoices (+items child), currencies (no-child),
auth_failure (401→UserException exit 1), **incremental accounting_records** (date_from applied,
manifest `incremental:true`, 103 rows). Sanitization sweep over whole `tests/` for the demo token,
demo email, and `Authorization: Basic <b64>` → **clean (no matches)** via `DefaultSanitizer`.

> **Re-verified 2026-06-08 after the post-audit redesign:** suite now **`94 passed`**. VCR coverage
> regenerated (never hand-edited) to **all 29 registry endpoints** (cases 07–35) + special cases 01–06
> (testConnection, listEndpoints, listDateFields with/without fields, auth_failure, incremental).
> Multi-page pagination now exercised by real cassettes (accounting_records 11 pages, purchase_invoices
> 3, countries 2). Leak sweep across all 35 cassettes → clean; configs use DUMMY placeholders; secrets.json
> gitignored.

### Phase 6 — Full Developer Portal value setup · owner: `component-dev-portal`
- [ ] complete

**Definition of done — MUST happen *after* the `0.0.1` release:** configSchema (and row schema if
config rows), sync actions, and the portal-owned properties (descriptions, UI options, etc.) are live
in the portal, confirmed via a fresh `kbagent dev-portal` GET.

> **Ordering, do not get this wrong:** the `0.0.1` release's CI-sync writes portal values from the
> repo. If you set portal values *before* that release, the release **overwrites** them. The bootstrap
> release already happened in Phase 1, so this manual value setup is safe here — but if any further
> release is cut afterwards, re-confirm the synced-vs-portal-owned property boundary.

**Evidence:** _

### Phase 7 — Deploy + smoke-test in cf-dev (image-tag override) · owner: `component-test` (tier 4)
- [ ] complete

**Definition of done:** an image built from the `initial-implementation` branch exists in the
platform; a config created in the **cf-dev** project (via kbagent) with the **image tag overridden**
to that branch build; a real job run **succeeded** end-to-end. Evidence must include the job ID, its
`success` status, **and the resolved image tag the job actually ran** — confirm it matches the
`initial-implementation` build, not a stale stable release (a green job against the wrong image is a
false pass).

**Evidence:** _

### Phase 8 — Final CF-standards review · owner: `component-checklist-review`
- [x] complete

**Definition of done:** `component-checklist-review` run over the full implementation; no open **blocking**
(critical/important) findings; component aligns with Component Factory standards.

> **If you cut a release after Phase 6** (e.g. promoting the reviewed component to a stable version),
> the CI property-sync runs again and overwrites the `[script]` portal properties from the repo —
> **re-run the Phase 6 verifier afterward** to confirm the portal-owned values survived. Phase 6 is
> only protected from the *bootstrap* `0.0.1` release automatically.

**Evidence:** ✅ Done 2026-06-08. Full 11-agent `component-checklist-review` run; surfaced 4 blocking
findings (Test Connection always failed due to full-config validation; incremental watermark used
wall-clock-now against business-date filters → silent record loss; network errors + non-auth 4xx
escaped as exit 2) plus importants. **All fixed** across passes A–D + cleanup: testConnection uses
connection-only `ConnectionConfig`; incremental redesigned to user-driven `date_field`+`date_from`
(`last_run`/relative/ISO via dateparser); client converts transport/4xx/non-JSON/exhausted-retry to
`UserException`; INFO logging added; empty-PK incremental guard; freezegun → dev deps. A fresh
re-audit of all four previously-blocking dimensions returned **no remaining blocking findings**; suite
`94 passed`, `ruff` clean. Remaining items are nice-to-haves only.
