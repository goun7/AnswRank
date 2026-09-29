from answrank.finance.tax_ledger import TaxLedger, TaxRegime
from answrank.agents.swarm import SwarmOrchestrator

def test_tax_ledger_foreign_export_service():
    ledger = TaxLedger(custom_rates={"GBP": 46.0, "TRY": 1.0})

    # UK Client invoice for GBP 1,500
    rec = ledger.record_invoice(
        client_brand="Harley Dental",
        country="UK",
        currency="GBP",
        amount=1500.0,
    )

    assert rec.regime == TaxRegime.EXPORT_SERVICE
    assert rec.vat_rate_pct == 0.0
    assert rec.vat_amount_try == 0.0
    assert rec.amount_try == 69000.0  # 1500 * 46
    # 11257 sayili CBK (2026): ihracat kazanç indirimi %100 -> exempt = amount_try
    assert rec.exempt_income_try == rec.amount_try
    assert rec.taxable_base_try == 0.0
    assert "KVK Madde 10/1-ğ" in rec.statutory_legal_note
    assert "KDV Kanunu Madde 11/1-a" in rec.statutory_legal_note

def test_tax_ledger_domestic_service():
    ledger = TaxLedger()

    # TR Client invoice for TRY 6,000
    rec = ledger.record_invoice(
        client_brand="DentGroup Istanbul",
        country="TR",
        currency="TRY",
        amount=6000.0,
    )

    assert rec.regime == TaxRegime.DOMESTIC_SERVICE
    assert rec.vat_rate_pct == 20.0
    assert rec.vat_amount_try == 1200.0
    assert rec.gross_total_try == 7200.0
    assert rec.exempt_income_try == 0.0
    assert rec.taxable_base_try == 6000.0

def test_fiscal_summary_cpa_report():
    orch = SwarmOrchestrator()

    # Add 1 domestic and 1 foreign client
    cand_tr = orch.seed_target("TR Clinic", "trclinic.com", country="TR", currency="TRY")
    orch.fulfillment.generate_contract(cand_tr)

    cand_uk = orch.seed_target("UK Clinic", "ukclinic.co.uk", country="UK", currency="GBP")
    orch.fulfillment.generate_contract(cand_uk)

    report = orch.get_fiscal_report()
    assert report.total_invoices_count == 2
    assert report.export_invoices_count == 1
    assert report.domestic_invoices_count == 1
    assert report.total_exempt_income_kvk10g_try > 0
    assert report.effective_tax_shield_pct > 0


# ── Persistence & FX-source integrity (added to kill the "empty on every restart" bug) ──

def test_invoices_persist_and_reload(tmp_path, monkeypatch):
    """A fresh TaxLedger must rehydrate invoices written by a previous instance,
    so the fiscal ledger and its invoice numbering survive process restarts."""
    from answrank.config import settings
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "ledger.db"))

    first = TaxLedger(custom_rates={"GBP": 46.0, "TRY": 1.0})
    assert len(first.records) == 0  # fresh store -> no history
    first.record_invoice("Clinic A", "UK", "GBP", 1000.0)
    first.record_invoice("Clinic B", "TR", "TRY", 5000.0)
    assert first.last_persist_error is None
    assert [r.invoice_id for r in first.records] == ["UNPUMP-INV-0001", "UNPUMP-INV-0002"]

    reloaded = TaxLedger(custom_rates={"GBP": 46.0, "TRY": 1.0})
    assert len(reloaded.records) == 2
    assert reloaded.records[0].client_brand == "Clinic A"
    assert reloaded.records[0].amount_try == 46000.0
    # Numbering continues from persisted history, so no invoice_id collision:
    third = reloaded.record_invoice("Clinic C", "TR", "TRY", 100.0)
    assert third.invoice_id == "UNPUMP-INV-0003"


def test_reload_is_silent_when_store_unavailable(tmp_path, monkeypatch):
    """load_persisted must never crash the ledger on a missing/broken DB."""
    from answrank.config import settings
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "nested" / "missing.db"))
    led = TaxLedger()  # parent dir does not exist -> load path guarded
    assert led.records == []


def test_fx_source_labels():
    assert TaxLedger(custom_rates={"USD": 30.0}).fx_source == "custom"
    assert TaxLedger().fx_source == "static_default"
    led = TaxLedger(custom_rates={"GBP": 46.0, "TRY": 1.0})
    rec = led.record_invoice("X", "UK", "GBP", 10.0)
    assert rec.fx_source == "custom"
    # An explicit per-call rate overrides ledger rates and is labeled "explicit"
    rec2 = led.record_invoice("Y", "US", "USD", 10.0, exchange_rate=32.5)
    assert rec2.fx_source == "explicit"
    assert rec2.exchange_rate_tcmb == 32.5
    # A rate of exactly 0 must be honored, not silently replaced by the fallback
    # (guards the old `rate = exchange_rate or default` falsy bug).
    rec3 = led.record_invoice("Z", "US", "USD", 10.0, exchange_rate=0.0)
    assert rec3.exchange_rate_tcmb == 0.0
    assert rec3.fx_source == "explicit"


def test_env_fx_override_is_labeled(monkeypatch):
    monkeypatch.delenv("ANSWRANK_FX_LIVE", raising=False)
    monkeypatch.setenv("ANSWRANK_FX_RATES", '{"GBP": 51.25, "USD": 40.5}')
    rates, source = TaxLedger._resolve_rates()
    assert source == "env"
    assert rates["GBP"] == 51.25
    assert rates["USD"] == 40.5
    assert rates["TRY"] == 1.0  # unknown currencies keep safe defaults
    led = TaxLedger(load_persisted=False)
    assert led.fx_source == "env"
    assert led.record_invoice("E", "UK", "GBP", 100.0).fx_source == "env"


def test_malformed_env_falls_back_to_static(monkeypatch):
    monkeypatch.delenv("ANSWRANK_FX_LIVE", raising=False)
    monkeypatch.setenv("ANSWRANK_FX_RATES", "not-json")
    rates, source = TaxLedger._resolve_rates()
    assert source == "static_default"
    assert rates["GBP"] == TaxLedger.DEFAULT_EXCHANGE_RATES["GBP"]


def test_live_fx_disabled_offline_by_default(monkeypatch):
    """Without ANSWRANK_FX_LIVE=1 the ledger never attempts a network fetch,
    keeping the suite hermetic."""
    monkeypatch.delenv("ANSWRANK_FX_RATES", raising=False)
    monkeypatch.delenv("ANSWRANK_FX_LIVE", raising=False)

    def boom():
        raise AssertionError("network fetch attempted while ANSWRANK_FX_LIVE unset")

    monkeypatch.setattr(TaxLedger, "_fetch_live_fx", staticmethod(boom))
    rates, source = TaxLedger._resolve_rates()
    assert source == "static_default"


# ── Live FX fetch (opt-in via ANSWRANK_FX_LIVE), caching and failure fallback ──

class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload, self._status = payload, status

    def raise_for_status(self):
        if self._status >= 400:
            raise RuntimeError(f"HTTP {self._status}")

    def json(self):
        return self._payload


def test_live_fx_fetch_caches_and_falls_back(monkeypatch):
    import httpx
    TaxLedger._LIVE_FX_CACHE = None
    calls = {"n": 0}

    def fake_get(url, timeout=None):
        calls["n"] += 1
        assert "open.er-api.com" in url
        # USD base: TRY=36.0 per USD; GBP costs 0.75 USD -> 48.0 TRY/GBP
        return _FakeResp({"rates": {"USD": 1.0, "TRY": 36.0, "GBP": 0.75, "EUR": 0.9, "JPY": 150.0}})

    monkeypatch.setattr(httpx, "get", fake_get)
    rates = TaxLedger._fetch_live_fx()
    assert rates is not None
    assert rates["TRY"] == 1.0
    assert rates["GBP"] == 48.0   # 36.0 / 0.75
    assert rates["USD"] == 36.0   # 36.0 / 1.0
    assert rates["EUR"] == 40.0   # 36.0 / 0.9
    assert "JPY" not in rates     # only settlement currencies kept

    # Second call must be served from cache (no new HTTP call)...
    assert TaxLedger._fetch_live_fx()["GBP"] == 48.0
    assert calls["n"] == 1

    # ...and with the env flag set, resolution adopts the live source label.
    monkeypatch.delenv("ANSWRANK_FX_RATES", raising=False)
    monkeypatch.setenv("ANSWRANK_FX_LIVE", "1")
    rates2, source2 = TaxLedger._resolve_rates()
    assert source2 == "live:open.er-api.com"
    assert rates2["GBP"] == 48.0
    TaxLedger._LIVE_FX_CACHE = None


def test_live_fetch_error_returns_none_and_static_fallback(monkeypatch):
    import httpx
    TaxLedger._LIVE_FX_CACHE = None

    def boom_get(url, timeout=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(httpx, "get", boom_get)
    monkeypatch.delenv("ANSWRANK_FX_RATES", raising=False)
    monkeypatch.setenv("ANSWRANK_FX_LIVE", "1")
    assert TaxLedger._fetch_live_fx() is None
    rates, source = TaxLedger._resolve_rates()
    assert source == "static_default"
    assert rates == TaxLedger.DEFAULT_EXCHANGE_RATES
    TaxLedger._LIVE_FX_CACHE = None


def test_live_fetch_http_status_error(monkeypatch):
    import httpx
    TaxLedger._LIVE_FX_CACHE = None
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: _FakeResp({}, status=503))
    assert TaxLedger._fetch_live_fx() is None
    TaxLedger._LIVE_FX_CACHE = None


def test_live_fetch_malformed_payload(monkeypatch):
    import httpx
    TaxLedger._LIVE_FX_CACHE = None
    # Missing TRY key entirely -> conversion cannot anchor -> treated as failure.
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: _FakeResp({"rates": {"GBP": 0.75}}))
    assert TaxLedger._fetch_live_fx() is None
    TaxLedger._LIVE_FX_CACHE = None


def test_env_override_beats_live(monkeypatch):
    """A human-set ANSWRANK_FX_RATES is the explicit operator intent and must
    take precedence even when live fetching is enabled."""
    monkeypatch.setenv("ANSWRANK_FX_LIVE", "1")
    monkeypatch.setenv("ANSWRANK_FX_RATES", '{"USD": 41.0}')
    rates, source = TaxLedger._resolve_rates()
    assert source == "env"
    assert rates["USD"] == 41.0


def test_malformed_persisted_row_is_skipped(tmp_path, monkeypatch):
    """A garbage legacy DB row (e.g. unknown regime) must not poison the ledger;
    valid neighbours still load."""
    from answrank.config import settings
    from answrank.db import Database
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "mixed.db"))
    db = Database()
    good = {
        "invoice_id": "UNPUMP-INV-0001", "client_brand": "Good Clinic", "client_country": "GB",
        "regime": "EXPORT_SERVICE", "currency": "GBP", "amount_foreign": 100.0,
        "exchange_rate": 46.0, "fx_source": "custom", "amount_try": 4600.0,
        "vat_rate_pct": 0.0, "vat_amount_try": 0.0, "gross_total_try": 4600.0,
        "exempt_income_try": 3680.0, "taxable_base_try": 920.0,
        "legal_note": "x", "created_at": "2026-09-01",
    }
    db.save_tax_invoice_sync(good)
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO tax_invoices (invoice_id, client_brand, client_country, regime,"
            " currency, amount_foreign, exchange_rate, fx_source, amount_try, vat_rate_pct,"
            " vat_amount_try, gross_total_try, exempt_income_try, taxable_base_try,"
            " legal_note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("ANSW-BAD-0001", "Ghost", "GB", "NOT_A_REGIME", "GBP", 1.0, 1.0, "x",
             1.0, 0.0, 0.0, 1.0, 0.0, 1.0, "x", "2026-09-01"),
        )
        conn.commit()
    led = TaxLedger(custom_rates={"GBP": 46.0, "TRY": 1.0})
    assert [r.invoice_id for r in led.records] == ["UNPUMP-INV-0001"]
    assert led.records[0].client_brand == "Good Clinic"


def test_persist_failure_captured_not_raised(tmp_path, monkeypatch):
    """Mirror-write failures must not abort invoicing but stay visible on the
    ledger (and clear again on the next successful write)."""
    from answrank.config import settings
    from answrank.db import Database
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "fail.db"))
    led = TaxLedger(custom_rates={"GBP": 46.0, "TRY": 1.0})

    def explode(self, inv):
        raise OSError("disk on fire")

    monkeypatch.setattr(Database, "save_tax_invoice_sync", explode)
    rec = led.record_invoice("Clinic X", "UK", "GBP", 100.0)  # must NOT raise
    assert rec.amount_try == 4600.0
    assert led.last_persist_error and "disk on fire" in led.last_persist_error

    monkeypatch.undo()  # restore real Database
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "fail.db"))
    led.record_invoice("Clinic Y", "UK", "GBP", 100.0)
    assert led.last_persist_error is None


