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
- The x402 payment environment is isolated per test: some x402 modules set
  ``ANSWRANK_SELLER_SECRET`` at module import time (``x402_servis.py``
  requires it) and never clear it; without per-test isolation that leak
  would silently flip the MCP/API payment gate into paid mode for every
  later test.
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


# x402 odeeme ortam degiskenleri (AnswRank <-> Sester mesh code bond).
# Bazi x402 test modulleri, x402_servis.py'nin import-aninda zorunlu
# kildigi secret'i MODUL SEVIYESINDE os.environ.setdefault ile yazar ve
# geri almaz. Bu lekelenme o testlerden sonra calisan MCP/API sunucularini
# yanlislikla 'odemeli' modda acar (SesterPaymentGate env'den yapilanir).
# Bu fixture lekeyi her testten once temizler; degeri gercekten isteyen
# testler kendi monkeypatch.setenv'ini zaten kullanir (sablon boyle).
_X402_ENV_KEYS = (
    "ANSWRANK_SELLER_SECRET",        # odemeli modun anahtari (lekenin kaynagi)
    "ANSWRANK_TEST", "UNPUMP_TEST",  # sim/mainnet mod secimi
    "ANSWRANK_PAY_TO", "ANSWRANK_RECEIPTS_DB",
    "ANSWRANK_PRICE_AUDIT", "ANSWRANK_PRICE_CITATIONS", "ANSWRANK_PRICE_FIX",
)


@pytest.fixture(autouse=True)
def isolated_x402_env(monkeypatch):
    """x402 odeme env'ini test bazinda izole eder -- bir testin sizdirdigi
    secret diger testlerin odeeme kapisini acamaz."""
    for key in _X402_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
