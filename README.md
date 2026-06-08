ex-uol
=============

Extracts invoices, contacts, products, accounting records and more from
[UOL Účetnictví](https://www.uol.cz/) (a Czech cloud accounting/ERP system) via its REST API.

**Table of Contents:**

[TOC]

Functionality Notes
===================

You select one object (endpoint) per configuration row. The extractor supports all of UOL's list
endpoints; each object becomes one Storage table, and nested line items (e.g. invoice `items`, contact
`addresses`, receivable `payments`) are split into linked child tables. Loads can be full or
incremental (for endpoints that expose a date filter).

Prerequisites
=============

1. A UOL account with the **REST API** permission enabled.
2. An **API token** generated in UOL under *Settings → API tokens* (`/api_tokens`).
3. Your **customer ID** (the subdomain assigned by UOL) for production/sandbox.

Authentication is HTTP Basic — your UOL login **email** as the username and the **API token** as the
password.

Features
========

| **Feature**             | **Description**                                                        |
|-------------------------|------------------------------------------------------------------------|
| Generic UI Form         | Dynamic UI form for easy configuration.                                |
| Row-Based Configuration | One configuration row per object/endpoint.                             |
| Incremental Loading     | Per-endpoint date filtering with a `last_run` watermark (upsert on PK).|
| Child Tables            | Nested arrays exploded into linked child tables.                       |
| Test Connection         | Validates credentials before running.                                  |

Supported Endpoints
===================

All UOL list endpoints, including: sales invoices/orders, retails, purchase invoices/orders, contacts
(+ addresses) and contact bank accounts, products, product categories, price lists, bank accounts and
movements, demands for payment, companies, departments, contracts, petty cashes and cash income/
disbursements, accounting records, receivables, internal documents, uploaded documents, document
templates, currencies, countries, predefined texts, and payment rules.

If you need additional endpoints, please submit your request to
[ideas.keboola.com](https://ideas.keboola.com/).

Configuration
=============

Connection (configuration)
---------------------------
- **Server** — `production` or `sandbox`.
- **Customer ID** — your UOL customer ID (subdomain).
- **Email** — UOL login email (Basic-auth username).
- **API Token** — UOL API token (stored encrypted).

Object (configuration row)
--------------------------
- **Object / Endpoint** — the UOL resource to extract.
- **Load Type** — `full_load` (default) or `incremental_load`.
- **Date Field** — (incremental) which `*_from` date filter to use; only some endpoints offer one.
- **Date From** — (incremental) `last_run` (continue from the last run), a relative value such as
  `yesterday` or `5 days ago`, or a fixed `YYYY-MM-DD` date.

Output
======

One table per object, named after the endpoint, with the resource's primary key set. Nested arrays
become child tables named `<endpoint>_<array>` with a foreign-key column to the parent and an
`_item_index`. Incremental rows are upserted on the primary key.

Development
-----------

To customize the local data folder path, replace the `CUSTOM_FOLDER` placeholder with your desired path in the `docker-compose.yml` file:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    volumes:
      - ./:/code
      - ./CUSTOM_FOLDER:/data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Clone this repository, initialize the workspace, and run the component using the following
commands:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
git clone  component-ex-uol
cd component-ex-uol
docker-compose build
docker-compose run --rm dev
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run the test suite and perform lint checks using this command:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
docker-compose run --rm test
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Integration
===========

For details about deployment and integration with Keboola, refer to the
[deployment section of the developer
documentation](https://developers.keboola.com/extend/component/deployment/).
