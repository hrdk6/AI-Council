"""Tests for backend configuration."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_config_loads():
    from app.config import CHAIRMAN, DECISION_ARCHITECT, EXPERT_LIBRARY, cfg
    
    assert cfg is not None
    assert isinstance(EXPERT_LIBRARY, dict)
    assert len(EXPERT_LIBRARY) == 4
    assert "operator" in EXPERT_LIBRARY
    assert "analyst" in EXPERT_LIBRARY
    assert "risk" in EXPERT_LIBRARY
    assert "researcher" in EXPERT_LIBRARY
    
    assert DECISION_ARCHITECT.provider
    assert DECISION_ARCHITECT.model
    assert DECISION_ARCHITECT.max_tokens > 0
    assert DECISION_ARCHITECT.timeout > 0
    
    assert CHAIRMAN.provider
    assert CHAIRMAN.model
    assert CHAIRMAN.max_tokens > 0
    assert CHAIRMAN.timeout > 0


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("EXPERT_OPERATOR_MODEL", "test-model")
    monkeypatch.setenv("EXPERT_OPERATOR_MAX_TOKENS", "500")
    
    # Need to clear the lru_cache
    from app.config import get_config
    get_config.cache_clear()
    
    # Re-import to get fresh config
    import importlib

    import app.config
    importlib.reload(app.config)
    from app.config import cfg
    
    assert cfg.expert_operator_model == "test-model"
    assert cfg.expert_operator_max_tokens == 500
    
    get_config.cache_clear()