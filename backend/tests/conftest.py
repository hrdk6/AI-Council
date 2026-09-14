import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Must run before any `app` module is imported: config is read at import time, and
# load_dotenv never overrides variables that are already set. This keeps tests away
# from the developer's real history database and production settings in backend/.env.
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="ai-council-tests-"))
os.environ["DATABASE_PATH"] = str(_TEST_DATA_DIR / "test.db")
os.environ["ENVIRONMENT"] = "test"
os.environ["API_KEY"] = ""

import pytest


@pytest.fixture(autouse=True)
def clear_config_cache():
    """Clear config cache and shared model cooldowns between tests."""
    from app.config import get_config
    from app.routing import MODEL_HEALTH
    get_config.cache_clear()
    MODEL_HEALTH.reset()
    yield
    MODEL_HEALTH.reset()
    get_config.cache_clear()
