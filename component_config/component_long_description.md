The UOL Účetnictví extractor pulls data from the [UOL Účetnictví](https://www.uol.cz/) cloud
accounting/ERP system into Keboola Storage via its REST API.

## What it extracts

You select one object (endpoint) per configuration row. The extractor supports all of UOL's list
endpoints, including:

- **Sales** — sales invoices, sales orders, retails
- **Purchases** — purchase invoices, purchase orders
- **Contacts** — contacts (with addresses), contact bank accounts
- **Products & pricing** — products, product categories, price lists
- **Banking** — bank accounts, bank movements, demands for payment
- **Cash** — petty cashes, cash incomes and disbursements
- **Accounting** — accounting records, receivables, internal documents
- **Documents & reference data** — uploaded documents, document templates, currencies, countries,
  predefined texts, payment rules, departments, companies, contracts

Each object becomes one Storage table; nested line items (e.g. invoice `items`, contact `addresses`,
receivable `payments`) are split into linked child tables.

## Load types

- **Full load** (default) — re-reads the whole object on every run.
- **Incremental load** — for endpoints that expose a date filter, choose the date field and a
  starting point. The starting point accepts `last_run` (continue from the previous run's watermark),
  a relative value such as `yesterday` or `5 days ago`, or a fixed `YYYY-MM-DD` date. Rows are
  upserted on their primary key.

## Authentication

HTTP Basic authentication using your UOL login **email** and an **API token** generated in UOL under
*Settings → API tokens*. The account must have the **REST API** permission enabled.

## Notes & limitations

- Incremental filtering is only available on the endpoints that expose a date filter; all other
  objects are full-load only.
- The API is rate limited (≈30 requests / 10 s); the extractor throttles and retries automatically.
