import pytest
from pydantic import ValidationError
from src.configuration import Configuration, LoadType


def _params(**over):
    base = {
        "base_url": "https://test.demo.uol.cz/api",
        "email": "demo@example.com",
        "#api_token": "secret",
        "endpoint": "contacts",
    }
    base.update(over)
    return base


def test_defaults_to_incremental():
    cfg = Configuration(**_params())
    assert cfg.load_type == LoadType.incremental_load
    assert cfg.incremental is True
    assert cfg.date_from is None


def test_reads_secret_alias():
    cfg = Configuration(**_params())
    assert cfg.api_token == "secret"


def test_full_load_flag():
    cfg = Configuration(**_params(load_type="full_load"))
    assert cfg.incremental is False


def test_missing_required_field_raises():
    p = _params()
    del p["base_url"]
    with pytest.raises(ValidationError):
        Configuration(**p)
