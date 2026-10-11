"""answrank.api.app dal-kesen testleri (LEED) — _monitor_service + 3 endpoint.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — TestClient (loopback FastAPI), sqlite tmp;
MonitorService modul-nitelik stub. _monitor_service + create_monitor +
list_monitors + digest endpoint'leri.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from answrank.api import app as app_mod
from answrank.api.app import app
from answrank.monitor.service import MonitorService


@pytest.fixture
def client(tmp_path, monkeypatch):
    """ORTAM: settings.db_path -> tmp VE app.db module-global'i yeniden baglanir
    (import aninda gercek repo DB'sine baglanirdi — Kural-4)."""
    from answrank.config import settings
    p = str(tmp_path / "api.db")
    monkeypatch.setattr(settings, "db_path", p)
    from answrank.db import Database
    monkeypatch.setattr(app_mod, "db", Database())
    return TestClient(app)


def _monitors(p):
    with sqlite3.connect(p) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM monitors")]


# == _monitor_service fabrikasi =================================================================

def test_monitor_service_instance_doner():
    """ORTAM: _monitor_service() bir MonitorService instance dondurur."""
    s = app_mod._monitor_service()
    assert isinstance(s, MonitorService)


def test_monitor_service_modul_db_baglanir(monkeypatch):
    """ORTAM: module-level 'db' globalini kullanir — duyunca yayilir."""
    from answrank.db import Database
    d = Database()
    monkeypatch.setattr(app_mod, "db", d)
    assert app_mod._monitor_service().db is d


def test_monitor_service_her_cagrida_yeni(monkeypatch):
    """ORTAM: CACHE YOK — her cagri yeni instance uretir (stateless factory)."""
    a = app_mod._monitor_service()
    b = app_mod._monitor_service()
    assert a is not b


def test_monitor_service_db_none_singleton(monkeypatch):
    """ORTAM: app.db None ise MonitorService(db=None) -> Database() singleton."""
    monkeypatch.setattr(app_mod, "db", None)
    s = app_mod._monitor_service()
    assert s.db is not None


def test_monitor_service_db_degisince_yayilir(monkeypatch):
    from answrank.db import Database
    d1, d2 = Database(), Database()
    monkeypatch.setattr(app_mod, "db", d1)
    assert app_mod._monitor_service().db is d1
    monkeypatch.setattr(app_mod, "db", d2)
    assert app_mod._monitor_service().db is d2


# == POST /api/monitors (create_monitor) =========================================================

def test_create_monitor_basarili(client):
    r = client.post("/api/monitors", json={"domain": "a.example",
                                           "brand": "Marka"})
    assert r.status_code == 200
    v = r.json()
    assert v["monitor_id"].startswith("mon_")
    assert v["domain"] == "a.example"
    assert v["sector"] == "general"
    assert "İzleme kaydı açıldı" in v["message"]


def test_create_monitor_db_yazar(client, tmp_path):
    p = str(tmp_path / "api.db")
    client.post("/api/monitors", json={"domain": "b.example",
                                       "brand": "Marka B"})
    rows = _monitors(p)
    assert len(rows) == 1
    assert rows[0]["domain"] == "b.example"
    assert rows[0]["brand"] == "Marka B"
    assert rows[0]["sector"] == "general"


def test_create_monitor_sektor_verilince(client, tmp_path):
    client.post("/api/monitors", json={"domain": "c.example",
                                       "brand": "Marka", "sector": "dental"})
    assert _monitors(str(tmp_path / "api.db"))[0]["sector"] == "dental"


def test_create_monitor_cadence_kaydedilir(client, tmp_path):
    client.post("/api/monitors", json={"domain": "d.example", "brand": "Marka",
                                       "cadence_days": 45})
    assert _monitors(str(tmp_path / "api.db"))[0]["cadence_days"] == 45


def test_create_monitor_contract_id_none(client, tmp_path):
    r = client.post("/api/monitors", json={"domain": "e.example",
                                           "brand": "Marka"})
    assert _monitors(str(tmp_path / "api.db"))[0]["contract_id"] is None


def test_create_monitor_contract_id_verilince(client, tmp_path):
    client.post("/api/monitors", json={"domain": "f.example",
                                       "brand": "Marka", "contract_id": "C-9"})
    assert _monitors(str(tmp_path / "api.db"))[0]["contract_id"] == "C-9"


@pytest.mark.parametrize("domain", ["ab", ""])
def test_create_monitor_kisa_domain_422(client, domain):
    """ORTAM: domain min_length=3 -> 422 (Turkce handler)."""
    r = client.post("/api/monitors", json={"domain": domain, "brand": "Marka"})
    assert r.status_code == 422


@pytest.mark.parametrize("brand", ["x", ""])
def test_create_monitor_kisa_brand_422(client, brand):
    r = client.post("/api/monitors", json={"domain": "abc.example",
                                           "brand": brand})
    assert r.status_code == 422


def test_create_monitor_gectersiz_sektor_422_turkce(client):
    """ORTAM-OGRENDI: sektor banka disinda -> 422 + Turkce handler mesaji
    ('sector: geçersiz değer'); pydantic value_error handler tarafindan
    genel-Turkce karsiligina donusturulur."""
    r = client.post("/api/monitors", json={"domain": "g.example",
                                           "brand": "Marka",
                                           "sector": "yok-sektor"})
    assert r.status_code == 422
    assert r.json() == {"detail": "sector: geçersiz değer"}


def test_create_monitor_gecerli_sektor_bankasi(client):
    """ORTAM: bankadaki sektorlerin hepsi gecerli."""
    for s in ["accounting", "aesthetic", "dental", "general"]:
        r = client.post("/api/monitors", json={"domain": f"{s}.example",
                                               "brand": "Marka",
                                               "sector": s})
        assert r.status_code == 200


def test_create_monitor_cadence_sinir_disi_422(client):
    """ORTAM: cadence_days ge=1, le=90 — 0 ve 91 reddedilir."""
    assert client.post("/api/monitors",
                       json={"domain": "h.example", "brand": "Marka",
                             "cadence_days": 0}).status_code == 422
    assert client.post("/api/monitors",
                       json={"domain": "h.example", "brand": "Marka",
                             "cadence_days": 91}).status_code == 422


@pytest.mark.parametrize("cadence", [1, 90])
def test_create_monitor_cadence_sinir_gecerli(client, cadence):
    r = client.post("/api/monitors", json={"domain": "i.example", "brand": "Marka",
                                           "cadence_days": cadence})
    assert r.status_code == 200


def test_create_monitor_domain_eksik_422(client):
    assert client.post("/api/monitors",
                       json={"brand": "Marka"}).status_code == 422


def test_create_monitor_monitor_id_benzersiz(client):
    a = client.post("/api/monitors", json={"domain": "a.example",
                                           "brand": "Marka"}).json()["monitor_id"]
    b = client.post("/api/monitors", json={"domain": "a.example",
                                           "brand": "Marka"}).json()["monitor_id"]
    assert a != b


def test_create_monitor_unicode_domain(client):
    r = client.post("/api/monitors", json={"domain": "i̇ğ.example",
                                           "brand": "İşletme"})
    assert r.status_code == 200
    assert r.json()["domain"] == "i̇ğ.example"


def test_create_monitor_stub_monitor_service(monkeypatch):
    """ORTAM: MonitorService modul-niteligi STUBLA (from-import runtime okur)
    — endpoint _monitor_service fabrikasini kullanir."""
    cagrilan = {"add": 0}

    class _S:
        def __init__(self, db=None):
            self.db = db

        def add(self, **kw):
            cagrilan["add"] += 1
            cagrilan.update(kw)
            return "mon_stub"

        def list(self):
            return []

    import answrank.monitor.service as mod
    monkeypatch.setattr(mod, "MonitorService", _S)
    c = TestClient(app)
    r = c.post("/api/monitors", json={"domain": "s.example", "brand": "Marka"})
    assert r.status_code == 200
    assert r.json()["monitor_id"] == "mon_stub"
    assert cagrilan["add"] == 1
    assert cagrilan["domain"] == "s.example"
    assert cagrilan["brand"] == "Marka"


# == GET /api/monitors (list) =====================================================================

def test_list_monitors_bos(client):
    r = client.get("/api/monitors")
    assert r.status_code == 200
    assert r.json() == {"monitors": []}


def test_list_monitors_dolu(client):
    client.post("/api/monitors", json={"domain": "a.example", "brand": "Marka A"})
    r = client.get("/api/monitors")
    assert len(r.json()["monitors"]) == 1


def test_list_monitors_iki_kayit(client):
    client.post("/api/monitors", json={"domain": "a.example", "brand": "Marka A"})
    client.post("/api/monitors", json={"domain": "b.example", "brand": "Marka B"})
    assert len(client.get("/api/monitors").json()["monitors"]) == 2


def test_list_monitors_stub_list(monkeypatch):
    """ORTAM: GET /api/monitors _monitor_service().list() dondurur."""
    class _S:
        def __init__(self, db=None):
            pass

        def list(self):
            return [{"id": "mon_x", "domain": "z.example"}]

    import answrank.monitor.service as mod
    monkeypatch.setattr(mod, "MonitorService", _S)
    r = TestClient(app).get("/api/monitors")
    assert r.json()["monitors"] == [{"id": "mon_x", "domain": "z.example"}]


# == GET /api/monitors/{id}/digest ===============================================================

def test_digest_basarili(monkeypatch):
    """ORTAM: digest MonitorService.digest sonucunu JSON olarak dondurur."""
    class _S:
        def __init__(self, db=None):
            pass

        def digest(self, mid):
            return {"monitor_id": mid, "status": "İZLENİYOR", "runs": []}

    import answrank.monitor.service as mod
    monkeypatch.setattr(mod, "MonitorService", _S)
    r = TestClient(app).get("/api/monitors/mon_abc/digest")
    assert r.status_code == 200
    assert r.json()["status"] == "İZLENİYOR"


def test_digest_monitor_yok_404(monkeypatch):
    """ORTAM-OGRENDI: MonitorService.digest KeyError -> 404 (uydurma kayit yok)."""
    class _S:
        def __init__(self, db=None):
            pass

        def digest(self, mid):
            raise KeyError(f"monitor {mid} yok — uydurma kayıt işlenmez")

    import answrank.monitor.service as mod
    monkeypatch.setattr(mod, "MonitorService", _S)
    r = TestClient(app).get("/api/monitors/mon_yok/digest")
    assert r.status_code == 404


def test_digest_gerçek_db(client):
    """ORTAM: gerçek tmp sqlite akışı — aç, digest, 404."""
    mid = client.post("/api/monitors",
                      json={"domain": "a.example", "brand": "Marka A"}).json()["monitor_id"]
    r = client.get(f"/api/monitors/{mid}/digest")
    assert r.status_code == 200
    assert r.json()["monitor_id"] == mid
    r2 = client.get("/api/monitors/mon_yok/digest")
    assert r2.status_code == 404
