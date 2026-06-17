### Connection

Set these once on the configuration:

- **API Base URL** — the full UOL API base URL including `/api`, e.g.
  `https://test.demo.uol.cz/api` or `https://{customerId}.ucetnictvi.uol.cz/api`.
- **Email** — your UOL login email (used as the Basic-auth username).
- **API Token** — a token from UOL *Settings → API tokens*. The account needs the **REST API**
  permission. Stored encrypted.

Use **Test Connection** to verify the credentials.

### Objects (rows)

Add one row per object you want to extract:

- **Object / Endpoint** — the UOL resource to extract (e.g. `sales_invoices`, `contacts`).
- **Date Field** — optional. For endpoints that support it, the date filter to use for incremental
  loads (e.g. `updated_at_from`, `issue_date_from`). Leave empty for a full load.
- **Date From** — optional. The incremental lower bound: `last_run` (continue from the last run),
  a relative value like `yesterday` or `5 days ago`, or a fixed `YYYY-MM-DD` date. Applies only when
  a Date Field is set.
