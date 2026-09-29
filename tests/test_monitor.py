"""E1 — GEO İzleme aboneliği testleri (D-16.09-M karar 4).

Anayasa: izleme bir ÖLÇÜM makinesidir; delta ancak iki gerçek koşu arasında
hesaplanır. Koşu yoksa digest "ÖLÇÜLEMEDİ" der, ilk koşu varsa "İLK ÖLÇÜM —
delta henüz hesaplanamaz" der. Fiyat config'den türemesiz üretilmez.
"""

import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

import pytest

from answrank.config import settings
from answrank.db import Database
from answrank.economics import EconomicsEngine, PricingTier
from answrank.monitor.service import MonitorService


@pytest.fixture
def db(tmp_path):
    return Database(db_path=str(tmp_path / "mon.db"))


@pytest.fixture
def svc(db):
    return MonitorService(db=db)


def _measured(score=61.0, sov=12.5, audit_id="audit_x1", cit_id=7):
    async def ex(domain, sector, brand):
        return {"status": "MEASURED", "score_base": score, "sov_pct": sov,
                "audit_id": audit_id, "citation_run_id": cit_id, "note": ""}
    return ex


def _unauditable():
    async def ex(domain, sector, brand):
        return {"status": "UNAUDITABLE", "score_base": None, "sov_pct": None,
                "audit_id": None, "citation_run_id": None, "note": "DOĞRULANAMADI"}
    return ex


# ------------------------------------------------------------------- CRUD/kadans

def test_monitor_add_and_list(svc):
    mid = svc.add(domain="klinik.example", brand="Örnek Klinik", sector="dental")
    rows = {m["id"]: m for m in svc.list()}
    assert mid in rows
    assert rows[mid]["cadence_days"] == 30 and rows[mid]["active"] == 1
    assert rows[mid]["contract_id"] is None


def test_run_due_only_due_monitors(svc):
    now = datetime(2026, 9, 16, 12, 0)
    # next_due_at hizmetin 'now' parametresinden gelir (duvar saati bağımlılığı = zaman tuzağı)
    svc.add(domain="a.example", brand="A", sector="general", now=now - timedelta(days=1))
    m2 = svc.add(domain="b.example", brand="B", sector="general", now=now)
    # m2'nin sırası henüz gelmedi: next_due'u ileri al
    svc.db.postpone_next_due(m2, now + timedelta(days=9), now_iso=now.isoformat())
    called = []

    async def spy(domain, sector, brand):
        called.append(domain)
        return {"status": "MEASURED", "score_base": 50.0, "sov_pct": 5.0,
                "audit_id": None, "citation_run_id": None, "note": ""}
    asyncio.run(svc.run_due(executor=spy, now=now))
    assert called == ["a.example"]


def test_monitor_run_persists_measured_and_unauditable(svc):
    m = svc.add(domain="c.example", brand="C", sector="dental")
    asyncio.run(svc.run_one(m, executor=_measured(), now=datetime(2026, 9, 16)))
    runs = svc.db.monitor_runs(m)
    assert runs[-1]["status"] == "MEASURED" and runs[-1]["score_base"] == 61.0
    m2 = svc.add(domain="d.example", brand="D", sector="dental")
    asyncio.run(svc.run_one(m2, executor=_unauditable(), now=datetime(2026, 9, 16)))
    r2 = svc.db.monitor_runs(m2)[-1]
    assert r2["status"] == "UNAUDITABLE" and r2["score_base"] is None


# ---------------------------------------------------------------------- digest

def test_digest_first_run_is_baseline_not_delta(svc):
    m = svc.add(domain="e.example", brand="E", sector="general")
    asyncio.run(svc.run_one(m, executor=_measured(), now=datetime(2026, 9, 16)))
    d = svc.digest(m)
    assert d["status"] == "İLK ÖLÇÜM" and d["delta_base"] is None
    assert "delta henüz" in d["text"] and "ÖLÇÜLEMEDİ" not in d["text"]


def test_digest_two_runs_real_delta(svc):
    m = svc.add(domain="f.example", brand="F", sector="general")
    asyncio.run(svc.run_one(m, executor=_measured(score=40.0, sov=3.0, cit_id=1), now=datetime(2026, 9, 1)))
    asyncio.run(svc.run_one(m, executor=_measured(score=52.0, sov=9.0, cit_id=2), now=datetime(2026, 9, 30)))
    d = svc.digest(m)
    assert d["status"] == "İZLENİYOR" and d["delta_base"] == pytest.approx(12.0)
    assert d["delta_sov"] == pytest.approx(6.0)
    assert "+12" in d["text"] or "12" in d["text"]


def test_digest_no_runs_unmeasured(svc):
    m = svc.add(domain="g.example", brand="G", sector="general")
    d = svc.digest(m)
    assert d["status"] == "ÖLÇÜLEMEDİ"
    assert "uydur" in d["text"] or "ölçüm yok" in d["text"]


def test_digest_after_unauditable_keeps_last_measured(svc):
    m = svc.add(domain="h.example", brand="H", sector="general")
    asyncio.run(svc.run_one(m, executor=_measured(score=40.0, cit_id=1), now=datetime(2026, 9, 1)))
    asyncio.run(svc.run_one(m, executor=_measured(score=52.0, cit_id=2), now=datetime(2026, 9, 20)))
    asyncio.run(svc.run_one(m, executor=_unauditable(), now=datetime(2026, 10, 1)))
    d = svc.digest(m)
    assert d["delta_base"] == pytest.approx(12.0)
    assert "Son koşu ÖLÇÜLEMEDİ" in d["text"]


# ------------------------------------------------------------------ fiyat/sözleşme

def test_monitor_price_and_tier_single_source():
    assert settings.monitor_monthly_price_try == 2500.0
    pkg = EconomicsEngine.PACKAGES[PricingTier.GEO_MONITOR]
    assert pkg.price_try == settings.monitor_monthly_price_try
    assert pkg.billing_type == "monthly"
    assert any("Madde-7" in f or "izleme" in f.lower() for f in pkg.features)


def test_contract_guarantee_binds_monitoring():
    from answrank.legal.contract_generator import ContractGenerator, ContractMetadata
    from answrank.legal.contract_generator import ClientLegalDetails
    client = ClientLegalDetails(
        client_name="Örnek AŞ", company_title="Örnek Sağlık AŞ", tax_number="1234567890",
        tax_office="Kadıköy", address="İstanbul", authorized_person="A. Yılmaz",
        email="a@ornek.example", phone="+90 555 000 00 00", domain="ornek.example", sector="dental")
    doc = ContractGenerator.generate_contract(
        client, ContractMetadata(contract_number="SZ-2026-001",
                                service_tier=PricingTier.MONTHLY_RETAINER,
                                monthly_fee_try=6000.0, start_date="2026-09-16"))
    low = doc.contract_text.lower()
    assert "izlem" in low and "kurulamaz" in low  # TR İ→i̇ combining tuzağı: "izlem" parçası her iki yazımda da eşleşir
    assert "7.5" in doc.contract_text                     # eski istisna bendi kaymadı
    bare = ContractGenerator.generate_madde_7_clause()
    assert "+12 net puan" in bare and "+25" not in bare   # çıplak çağrışık satılan bandı render eder


def test_db_path_bound_per_instance(tmp_path):
    d1 = Database(db_path=str(tmp_path / "a.db"))
    assert d1.db_path.endswith("a.db")


def test_run_one_unknown_monitor_and_executor_crash(svc):
    with pytest.raises(KeyError):
        asyncio.run(svc.run_one("mon_yok", executor=_measured()))
    with pytest.raises(KeyError):
        svc.digest("mon_yok")
    m = svc.add(domain="crash.example", brand="C", sector="general")

    async def boom(domain, sector, brand):
        raise OSError("network down")
    asyncio.run(svc.run_one(m, executor=boom, now=datetime(2026, 9, 16)))
    r = svc.db.monitor_runs(m)[-1]
    assert r["status"] == "UNAUDITABLE" and "DOĞRULANAMADI" in r["note"]
    d = svc.digest(m)
    assert d["status"] == "ÖLÇÜLEMEDİ" and "uydur" in d["text"]


def test_live_executor_unauditable_and_measured(svc, monkeypatch):
    from types import SimpleNamespace
    from answrank.audit.engine import AuditEngine
    from answrank.audit.crawler import CrawlData
    from answrank.monitor import service as ms

    dead = AuditEngine().audit_crawl_data(CrawlData(
        url="https://x.test", domain="x.test", html_content="", status_code=0,
        headers={}, is_https=True, fetch_warnings=["DOĞRULANAMADI: test"]))
    ok = AuditEngine().audit_crawl_data(CrawlData(
        url="https://a.example", domain="a.example", html_content="<title>A</title><p>x</p>",
        status_code=200, headers={}, is_https=True))
    with patch.object(AuditEngine, "audit_url", new=AsyncMock(return_value=dead)):
        res = asyncio.run(ms.live_executor("x.test", "dental", "X"))
    assert res["status"] == "UNAUDITABLE"

    from answrank.citations.runner import MultiLLMCitationRunner
    fake_run = SimpleNamespace(run_id="cit_r1", citation_rate_percentage=8.0)
    with patch.object(AuditEngine, "audit_url", new=AsyncMock(return_value=ok)), \
         patch.object(MultiLLMCitationRunner, "run_citations", new=AsyncMock(return_value=fake_run)), \
         patch("answrank.db.Database.save_audit", new=AsyncMock()), \
         patch("answrank.db.Database.save_citations", new=AsyncMock()):
        res = asyncio.run(ms.live_executor("a.example", "dental", "A"))
    assert res["status"] == "MEASURED" and res["citation_run_id"] == "cit_r1" and res["sov_pct"] == 8.0


# ------------------------------------------------------------- CLI yüzeyi (E1b)

def _run_cli(argv, monkeypatch, capsys, db_path):
    import sys
    monkeypatch.setenv("ANSWRANK_DB_PATH", db_path)
    from answrank.config import settings
    monkeypatch.setattr(settings, "db_path", db_path)
    monkeypatch.setattr(sys, "argv", ["answrank"] + argv)
    from answrank.cli import main
    main()
    return " ".join(capsys.readouterr().out.split())


def test_cli_monitor_add_run_digest(tmp_path, monkeypatch, capsys):
    dbp = str(tmp_path / "cli.db")
    out = _run_cli(["monitor", "add", "--domain", "klinik.example", "--brand", "Klinik",
                    "--sector", "dental"], monkeypatch, capsys, dbp)
    assert "mon_" in out and "klinik.example" in out
    mid = [t for t in out.split() if t.startswith("mon_")][0]
    empty = _run_cli(["monitor", "digest", mid], monkeypatch, capsys, dbp)
    assert "ölçümlü koşu yok" in empty and "uydur" in empty
    fake = _measured(score=44.0, sov=2.0, cit_id="c1")
    monkeypatch.setattr("answrank.monitor.service.live_executor", fake)
    run_out = _run_cli(["monitor", "run"], monkeypatch, capsys, dbp)
    assert "MEASURED" in run_out or "ölçüldü" in run_out
    d2 = _run_cli(["monitor", "digest", mid], monkeypatch, capsys, dbp)
    assert "İLK ÖLÇÜM" in d2 and "delta henüz" in d2


def test_cli_monitor_rejects_unbanked_sector(tmp_path, monkeypatch, capsys):
    import sys
    monkeypatch.setattr(sys, "argv", ["answrank", "monitor", "add", "--domain", "x.example",
                                      "--brand", "X", "--sector", "veterinary"])
    from answrank.cli import main
    with pytest.raises(SystemExit):
        main()
    err = capsys.readouterr().err
    assert "invalid choice" in err


# --------------------------------------------------------------- API (E1b)

def test_api_monitor_surface_roundtrip(tmp_path, monkeypatch):
    from answrank.db import Database
    from answrank.api import app as appmod
    db = Database(db_path=str(tmp_path / "api.db"))
    monkeypatch.setattr(appmod, "db", db)
    from fastapi.testclient import TestClient
    from answrank.api.app import app
    client = TestClient(app)
    r = client.post("/api/monitors", json={"domain": "api-klinik.example",
                                           "brand": "API Klinik", "sector": "dental"})
    assert r.status_code == 200
    mid = r.json()["monitor_id"]
    bad = client.post("/api/monitors", json={"domain": "x.example", "brand": "X",
                                             "sector": "veterinary"})
    assert bad.status_code == 422
    lst = client.get("/api/monitors").json()
    assert any(m["id"] == mid for m in lst["monitors"])
    monkeypatch.setattr("answrank.monitor.service.live_executor", _measured(score=51.0, sov=4.0))
    runr = client.post(f"/api/monitors/{mid}/run")
    assert runr.status_code == 200 and runr.json()["status"] == "MEASURED"
    dig = client.get(f"/api/monitors/{mid}/digest").json()
    assert dig["status"] == "İLK ÖLÇÜM" and dig["delta_base"] is None
    missing = client.get("/api/monitors/mon_yok/digest")
    assert missing.status_code == 404 and "uydurma" in missing.json()["detail"]


def test_documented_route_count_now_47():
    from answrank.api.app import app
    from fastapi.routing import APIRoute
    api_routes = [r for r in app.routes if isinstance(r, APIRoute)]
    paths = app.openapi()["paths"]
    # E1'den itibaren: /api/monitors POST+GET aynı path'i paylaşır → handler 47, path 46.
    assert len(api_routes) == 52 and len(paths) == 51  # E11: /api/payments/channels
    paths = app.openapi()["paths"]
    for p in ("/api/monitors", "/api/monitors/{monitor_id}/run", "/api/monitors/{monitor_id}/digest", "/api/monitors/{monitor_id}/fulfillment", "/api/queue", "/api/queue/{item_id}/decision", "/api/leads"):
        assert p in paths


def test_cli_monitor_list_run_exhaustions_and_unauditable(tmp_path, monkeypatch, capsys):
    dbp = str(tmp_path / "cli2.db")
    empty = _run_cli(["monitor", "list"], monkeypatch, capsys, dbp)
    assert "Kayıtlı izleme yok" in empty
    _run_cli(["monitor", "add", "--domain", "listk.example", "--brand", "L",
             "--sector", "general"], monkeypatch, capsys, dbp)
    listing = _run_cli(["monitor", "list"], monkeypatch, capsys, dbp)
    assert "listk.example" in listing and "cadence=30g" in listing

    async def crash(domain, sector, brand):
        raise OSError("down")
    monkeypatch.setattr("answrank.monitor.service.live_executor", crash)
    run1 = _run_cli(["monitor", "run"], monkeypatch, capsys, dbp)
    assert "UNAUDITABLE" in run1 and "sayı uydurulmaz" in run1
    run2 = _run_cli(["monitor", "run"], monkeypatch, capsys, dbp)
    assert "Vadesi gelmiş izleme yok" in run2
    bad = _run_cli(["monitor", "digest", "mon_yok"], monkeypatch, capsys, dbp)
    assert "bulunamadı" in bad


def test_api_run_monitor_404_and_500(tmp_path, monkeypatch):
    from answrank.db import Database
    from answrank.api import app as appmod
    monkeypatch.setattr(appmod, "db", Database(db_path=str(tmp_path / "a2.db")))
    from fastapi.testclient import TestClient
    from answrank.api.app import app
    client = TestClient(app)
    assert client.post("/api/monitors/mon_yok/run").status_code == 404
    r = client.post("/api/monitors", json={"domain": "x5.example", "brand": "X5"})
    mid = r.json()["monitor_id"]
    from answrank.monitor import service as _ms
    async def boom(domain, sector, brand):
        raise RuntimeError("kuyrukta gizli iç hata")
    # run_one executor hatasını YUTUP UNAUDITABLE yazar; 500 yolu için db yazımını patlat:
    with patch.object(_ms.MonitorService, "run_one", new=AsyncMock(side_effect=RuntimeError("db exploded"))):
        resp = client.post(f"/api/monitors/{mid}/run")
    assert resp.status_code == 500 and "iç hata" in resp.json()["detail"] and "exploded" not in resp.json()["detail"]


def test_landing_monitor_tile_price_single_source():
    from answrank.config import settings
    tpl = open("answrank/api/templates/landing.html", encoding="utf-8").read()
    price = f"{settings.monitor_monthly_price_try:,.0f}"
    assert tpl.count("monitor_line") >= 5  # markup + TR/UK/US/DE sözlükleri
    assert f"₺{price}/ay" in tpl and f"₺{price}/mo" in tpl and f"₺{price.replace(',', '.')}/Monat" in tpl


# ------------------------------------------------- E6: Madde-7.3 fulfillment motoru

def _two_runs(svc, mid, first=40.0, second=52.0):
    for s in (first, second):
        asyncio.run(svc.run_one(mid, executor=_measured(score=s, sov=1.0),
                                now=datetime(2026, 9, 16 if s == first else 20)))
        # kadans: ikinci koşu vade beklemeden executor direkt çağrısı
    return svc


def test_fulfillment_requires_contract_link(svc):
    from answrank.monitor.fulfillment import FulfillmentEvaluator
    m = svc.add(domain="sozlesmesiz.example", brand="S", sector="general")
    ev = FulfillmentEvaluator(db=svc.db).evaluate(m)
    assert ev["kind"] == "NO_LINK" and "hüküm kurulamaz" in ev["reason"].lower()


def test_fulfillment_insufficient_measurement_no_fabrication(svc):
    from answrank.monitor.fulfillment import FulfillmentEvaluator
    m = svc.add(domain="tek.example", brand="T", sector="general", contract_id="SZ-1")
    asyncio.run(svc.run_one(m, executor=_measured(), now=datetime(2026, 9, 16)))
    ev = FulfillmentEvaluator(db=svc.db).evaluate(m)
    assert ev["kind"] == "INSUFFICIENT" and "ÖLÇÜM YETERSİZ" in ev["reason"]
    assert ev["delta"] is None


def test_fulfillment_triggered_and_satisfied(svc):
    from answrank.monitor.fulfillment import FulfillmentEvaluator
    ev0 = FulfillmentEvaluator(db=svc.db)
    m = svc.add(domain="delta.example", brand="D", sector="general", contract_id="SZ-2")
    _two_runs(svc, m, 40.0, 45.0)  # +5 < +12 → 7.3 tetiklenir
    ev = ev0.evaluate(m)
    assert ev["kind"] == "TRIGGERED" and ev["delta"] == pytest.approx(5.0)
    assert "HİÇBİR EK ÜCRET" in ev["reason"] and "FREE-CYCLE" in ev["free_cycle_id"]
    m2 = svc.add(domain="buyuk.example", brand="B", sector="general", contract_id="SZ-3")
    _two_runs(svc, m2, 40.0, 55.0)  # +15 ≥ +12 → karşlandı
    ev2 = ev0.evaluate(m2)
    assert ev2["kind"] == "SATISFIED" and ev2["delta"] == pytest.approx(15.0)
    rows = ev0.list_events()
    assert {r["kind"] for r in rows} == {"TRIGGERED", "SATISFIED"}


def test_fulfillment_cli_and_api(svc, tmp_path, monkeypatch, capsys):
    import sys
    m = svc.add(domain="api.example", brand="A", sector="general", contract_id="SZ-9")
    _two_runs(svc, m, 50.0, 58.0)  # +8 → tetik
    from answrank.config import settings
    monkeypatch.setattr(settings, "db_path", str(svc.db.db_path))
    monkeypatch.setattr(sys, "argv", ["answrank", "monitor", "fulfillment", m])
    from answrank.cli import main
    main()
    out = " ".join(capsys.readouterr().out.split())
    assert "TRIGGERED" in out and "8" in out
    from answrank.db import Database
    from answrank.api import app as appmod
    monkeypatch.setattr(appmod, "db", Database(db_path=str(svc.db.db_path)))
    from fastapi.testclient import TestClient
    from answrank.api.app import app
    r = TestClient(app).get(f"/api/monitors/{m}/fulfillment")
    assert r.status_code == 200 and r.json()["kind"] == "TRIGGERED"
    assert TestClient(app).get("/api/monitors/mon_yok/fulfillment").status_code == 404


def test_fulfillment_event_filter_and_all(svc):
    from answrank.monitor.fulfillment import FulfillmentEvaluator
    ev = FulfillmentEvaluator(db=svc.db)
    m1 = svc.add(domain="f1.example", brand="F1", sector="general", contract_id="SZ-F1")
    m2 = svc.add(domain="f2.example", brand="F2", sector="general")  # NO_LINK — persist yok
    _two_runs(svc, m1, 40.0, 60.0)
    ev.evaluate(m1)
    rows = ev.list_events()
    assert [r["monitor_id"] for r in ev.list_events(m1)] == [m1]
    assert all(r["kind"] == "SATISFIED" for r in rows)
    out = ev.evaluate_all()
    kinds = {r["monitor_id"]: r["kind"] for r in out}
    assert kinds[m1] == "SATISFIED" and kinds[m2] == "NO_LINK"


def test_fulfillment_cli_all_and_missing(tmp_path, monkeypatch, capsys):
    import sys
    from answrank.db import Database
    from answrank.monitor.service import MonitorService
    from answrank.monitor.fulfillment import FulfillmentEvaluator
    from answrank.config import settings
    db = Database(db_path=str(tmp_path / "fa.db"))
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "fa.db"))
    monkeypatch.setattr(sys, "argv", ["answrank", "monitor", "add", "--domain", "ca.example",
                                      "--brand", "CA", "--contract", "SZ-CA"])
    from answrank.cli import main
    main()
    mid = [t for t in " ".join(capsys.readouterr().out.split()).split() if t.startswith("mon_")][0]
    svc = MonitorService(db=db)
    for sc in (50.0, 54.0):
        asyncio.run(svc.run_one(mid, executor=_measured(score=sc),
                                now=datetime(2026, 9, 16 if sc == 50.0 else 18)))
    FulfillmentEvaluator(db=svc.db).evaluate("mon_yok") if False else None
    monkeypatch.setattr(sys, "argv", ["answrank", "monitor", "fulfillment", "mon_yok"])
    main()
    assert "İzleme kaydı yok" in " ".join(capsys.readouterr().out.split())
    monkeypatch.setattr(sys, "argv", ["answrank", "monitor", "fulfillment"])
    main()
    out = " ".join(capsys.readouterr().out.split())
    assert "TRIGGERED" in out  # --all: id verilmemiş → tümü


def test_fulfillment_evaluate_all_skips_vanished(svc, monkeypatch):
    from answrank.monitor import fulfillment as fmod
    m = svc.add(domain="vanish.example", brand="V", sector="general", contract_id="SZ-V")
    ev = fmod.FulfillmentEvaluator(db=svc.db)
    real = ev.evaluate
    def flaky(mid, now=None):
        if mid == m:
            raise KeyError("yarış: kayıt buharlaştı")
        return real(mid, now=now)
    monkeypatch.setattr(ev, "evaluate", flaky)
    assert ev.evaluate_all() == []
