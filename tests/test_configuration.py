import pytest
from keboola.component.exceptions import UserException
from pydantic import ValidationError

from configuration import Configuration, ConnectionConfig, resolve_since


def _conn_params(**over):
    base = {
        "base_url": "https://test.demo.uol.cz/api",
        "email": "demo@example.com",
        "#api_token": "secret",
    }
    base.update(over)
    return base


def _full_params(**over):
    base = _conn_params()
    base["endpoint"] = "contacts"
    base.update(over)
    return base


# --- ConnectionConfig ---

def test_connection_config_parses_connection_fields():
    conn = ConnectionConfig(**_conn_params())
    assert conn.base_url == "https://test.demo.uol.cz/api"
    assert conn.email == "demo@example.com"
    assert conn.api_token == "secret"


def test_connection_config_ignores_row_fields():
    # extra="ignore" means row-level fields don't cause an error
    conn = ConnectionConfig(**_full_params(date_field="issue_date_from"))
    assert conn.api_token == "secret"


def test_connection_config_missing_required_raises():
    p = _conn_params()
    del p["base_url"]
    with pytest.raises(ValidationError):
        ConnectionConfig(**p)


# --- Configuration ---

def test_configuration_parses_full_params():
    cfg = Configuration(**_full_params())
    assert cfg.endpoint == "contacts"
    assert cfg.date_field is None
    assert cfg.date_from is None


def test_configuration_reads_secret_alias():
    cfg = Configuration(**_full_params())
    assert cfg.api_token == "secret"


def test_configuration_with_date_field_and_date_from():
    cfg = Configuration(**_full_params(date_field="issue_date_from", date_from="last_run"))
    assert cfg.date_field == "issue_date_from"
    assert cfg.date_from == "last_run"


def test_configuration_missing_required_field_raises():
    p = _full_params()
    del p["base_url"]
    with pytest.raises(ValidationError):
        Configuration(**p)


# --- resolve_since ---

def test_resolve_since_last_run_with_watermark():
    state = {"last_run": "2026-05-01T00:00:00+00:00"}
    result = resolve_since("last_run", state)
    assert result == "2026-05-01T00:00:00+00:00"


def test_resolve_since_last_run_empty_state():
    result = resolve_since("last_run", {})
    assert result is None


def test_resolve_since_none_returns_watermark():
    state = {"last_run": "2026-03-01T00:00:00+00:00"}
    result = resolve_since(None, state)
    assert result == "2026-03-01T00:00:00+00:00"


def test_resolve_since_none_empty_state():
    result = resolve_since(None, {})
    assert result is None


def test_resolve_since_empty_string_returns_watermark():
    state = {"last_run": "2026-04-01T00:00:00+00:00"}
    result = resolve_since("", state)
    assert result == "2026-04-01T00:00:00+00:00"


def test_resolve_since_relative_yesterday():
    result = resolve_since("yesterday", {})
    assert result is not None
    assert isinstance(result, str)
    # Should be a parseable ISO string
    assert "T" in result or "-" in result


def test_resolve_since_relative_5_days_ago():
    result = resolve_since("5 days ago", {})
    assert result is not None
    assert isinstance(result, str)


def test_resolve_since_absolute_iso_date():
    result = resolve_since("2026-01-15", {})
    assert result is not None
    assert "2026-01-15" in result


def test_resolve_since_garbage_raises():
    with pytest.raises(UserException, match="Could not parse date_from"):
        resolve_since("not a date xyz !!!", {})
