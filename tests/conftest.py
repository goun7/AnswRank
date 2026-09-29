"""Shared pytest fixtures for the AnswRank test suite.

Isolation contract:
- No test may ever read or write the development/production database.
- At conftest import time (before any test module or FastAPI app singleton
  is loaded) ``settings.db_path`` is redirected to a throwaway session file.
  This neutralizes module-level ``Database()`` singletons such as the one in
  ``answrank.api.app``.
- Additionally, every test gets its own fresh SQLite file via monkeypatched
  ``settings.db_path`` so per-test state (territory locks, swarm candidates)
  cannot leak into later tests.
- The auxiliary asset cache (robots/llms/sitemap TTL cache) is flushed
  between tests so cross-test cache hits cannot mask or fake behavior.
"""

import tempfile

import pytest

from answrank.audit.cache import asset_cache
from answrank.config import settings

# Session-level redirect: anything constructed at import/collection time
# (module singletons) lands in a temp file, never in the repo's answrank.db.
_SESSION_DB_DIR = tempfile.mkdtemp(prefix="answrank-test-session-")
settings.db_path = _SESSION_DB_DIR + "/session.db"


@pytest.fixture(autouse=True)
def isolated_db_path(tmp_path, monkeypatch):
    """Point settings.db_path at a fresh temp file for every single test."""
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test-answrank.db"))


@pytest.fixture(autouse=True)
def flush_asset_cache():
    """Start each test with an empty asset cache (deterministic fetch behavior)."""
    asset_cache.invalidate()
    yield
    asset_cache.invalidate()
