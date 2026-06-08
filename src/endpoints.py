"""Registry of UOL Účetnictví list endpoints.

Single source of truth: each Endpoint declares its API path, primary key,
the incremental cursor query-param (or None for full-load-only endpoints),
and any nested array fields to explode into child tables.

PKs, child arrays and incremental params were verified against the live demo
instance (test.demo.uol.cz) and the OpenAPI spec (api.uol.cz/openapi.yaml).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    name: str
    path: str
    primary_key: list[str]
    incremental_param: str | None = None
    child_arrays: tuple[str, ...] = ()


def _ep(name, pk, *, inc=None, children=()):
    return Endpoint(
        name=name, path=f"v1/{name}", primary_key=pk, incremental_param=inc, child_arrays=children
    )


_ALL = [
    _ep("sales_invoices", ["gid"], inc="issue_date_from", children=("items",)),
    _ep("sales_orders", ["order_id"], inc="updated_at_from", children=("items",)),
    _ep("retails", ["retail_id"], children=("items",)),
    _ep("purchase_invoices", ["gid"], inc="received_date_from", children=("items",)),
    _ep("purchase_orders", ["order_id"], children=("items",)),
    _ep("contacts", ["contact_id"], children=("addresses",)),
    _ep("contact_bank_accounts", ["bank_account_id"]),
    _ep("products", ["product_id"]),
    _ep("product_categories", ["type_id"]),
    _ep("price_lists", ["price_list_id"], children=("items",)),
    _ep("my_bank_accounts", ["bank_account_id"]),
    _ep("bank_movements", ["gid"], children=("items",)),
    _ep("bank_movement_items", []),
    _ep("demands_for_payment", ["reminder_id"], children=("items",)),
    _ep("my_companies", ["my_company_id"]),
    _ep("departments", ["department_id"]),
    _ep("contracts", ["contract_id"]),
    _ep("petty_cashes", ["petty_cash_id"]),
    _ep("petty_cash_incomes", ["gid"], children=("items",)),
    _ep("petty_cash_disburstments", ["gid"], children=("items",)),
    _ep("accounting_records", ["gid"], inc="date_from"),
    _ep("receivables", ["invoice_id"], inc="last_payment_time_from", children=("payments",)),
    _ep("internal_documents", ["number"], children=("items",)),
    _ep("uploaded_documents", ["id"], inc="created_at_from"),
    _ep("document_templates", ["id"]),
    _ep("currencies", ["currency_id"]),
    _ep("countries", ["country_id"]),
    _ep("predefined_texts", ["predefined_text_id"]),
    _ep("payment_rules", ["gid"]),
]

ENDPOINTS: dict[str, Endpoint] = {e.name: e for e in _ALL}


def get_endpoint(name: str) -> Endpoint:
    return ENDPOINTS[name]


def endpoint_names() -> list[str]:
    return sorted(ENDPOINTS)
