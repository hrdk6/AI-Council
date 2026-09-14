"""Tests for backend configuration."""

import pytest
from pydantic import ValidationError

from app.config import (
    CHAIRMAN,
    DECISION_ARCHITECT,
    EXPERT_LIBRARY,
    AppConfig,
    cfg,
    get_config,
    providers_in_use,
)


def test_config_loads():
    assert cfg is not None
    assert set(EXPERT_LIBRARY) == {"operator", "analyst", "risk", "researcher"}

    for role in (DECISION_ARCHITECT, CHAIRMAN):
        assert role.provider
        assert role.model
        assert role.max_tokens > 0
        assert role.timeout > 0


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("EXPERT_OPERATOR_MODEL", "test-model")
    monkeypatch.setenv("EXPERT_OPERATOR_MAX_TOKENS", "512")
    get_config.cache_clear()

    config = get_config()
    assert config.expert_operator_model == "test-model"
    assert config.expert_operator_max_tokens == 512


def test_blank_env_values_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "")
    get_config.cache_clear()
    assert get_config().rate_limit_requests == 10


def test_comma_separated_values_are_parsed():
    config = AppConfig.model_validate({
        "allowed_origins": "http://a.test, http://b.test",
        "anchor_experts": "risk,analyst",
        "groq_fallback_chain": "model-a,model-b",
    })
    assert config.allowed_origins == ["http://a.test", "http://b.test"]
    assert config.anchor_experts == ("risk", "analyst")
    assert config.groq_fallback_chain == ("model-a", "model-b")


def test_backup_models_parsed_and_validated():
    config = AppConfig.model_validate({"backup_models": "gemini:gemini-2.5-flash, openrouter:meta-llama/llama-3.3-70b:free"})
    assert config.backup_models == ("gemini:gemini-2.5-flash", "openrouter:meta-llama/llama-3.3-70b:free")
    with pytest.raises(ValidationError, match="BACKUP_MODELS"):
        AppConfig.model_validate({"backup_models": "gemini-2.5-flash"})
    with pytest.raises(ValidationError, match="BACKUP_MODELS"):
        AppConfig.model_validate({"backup_models": "anthropic:claude"})


def test_default_chain_has_several_groq_backups():
    assert len(AppConfig().groq_fallback_chain) >= 4


def test_invalid_numbers_raise_clear_errors():
    with pytest.raises(ValidationError, match="rate_limit_requests"):
        AppConfig.model_validate({"rate_limit_requests": "lots"})


def test_unknown_expert_keys_rejected():
    with pytest.raises(ValidationError, match="Unknown expert keys"):
        AppConfig.model_validate({"default_council_keys": "operator,wizard"})


def test_min_council_size_cannot_exceed_max():
    with pytest.raises(ValidationError, match="MIN_COUNCIL_SIZE"):
        AppConfig.model_validate({"min_council_size": 5, "max_council_size": 2})


def test_production_requires_api_key():
    with pytest.raises(ValidationError, match="API_KEY must be set"):
        AppConfig.model_validate({"environment": "production"})
    assert AppConfig.model_validate({"environment": "production", "api_key": "secret"}).is_production


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError, match="ALLOWED_ORIGINS"):
        AppConfig.model_validate({"environment": "production", "api_key": "k", "allowed_origins": "*"})


def test_providers_in_use_reflects_roles():
    assert providers_in_use() == sorted({role.provider for role in [*EXPERT_LIBRARY.values(), CHAIRMAN]})
