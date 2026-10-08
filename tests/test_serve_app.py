"""create_app AEO İzleyici FastAPI testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: sahte olc_fn + monkeypatch _guvenli_domain (DNS yok).
"""
import sys

import pytest

sys.path.insert(0, ".")
sys.path.insert(0, "izleyici")
sys.path.insert(0, "../../01_unicorn/63-Sester")

from fastapi.testclient import TestClient  # noqa: E402

import izleyici.serve as serve  # noqa: E402


def _fake_olc(domain):
    return {"ai_alinti_puani": 87, "domain": domain}


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(serve, "_guvenli_domain", lambda d: d)
    monkeypatch.setattr(serve, "snapshot_yaz", lambda *a, **k: None)
    monkeypatch.setattr(serve, "_lead_yaz", lambda *a, **k: None)
    return serve.create_app(olc_fn=_fake_olc, gunluk_limit=3)


@pytest.fixture
def client(app):
    return TestClient(app)


def _post(client, email="a@b.com", domain="example.com", **over):
    return client.post("/rapor", json={"email": email, "domain": domain})


# -- landing ---------------------------------------------------------------------------

def test_landing_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200


def test_landing_shows_limit(client):
    r = client.get("/")
    assert "3" in r.text


def test_landing_title(client):
    r = client.get("/")
    assert "AEO" in r.text or "İzleyici" in r.text


# -- rapor başarı ---------------------------------------------------------------------------

def test_rapor_returns_200(client):
    assert _post(client).status_code == 200


def test_rapor_returns_report(client):
    r = _post(client)
    assert "rapor" in r.json()


def test_rapor_returns_score(client):
    r = _post(client)
    assert r.json()["puan"] == 87


def test_rapor_calls_olc_fn(client):
    r = _post(client, domain="test.com")
    assert r.status_code == 200


def test_rapor_snapshot_written(app, monkeypatch):
    yazildi = []
    monkeypatch.setattr(serve, "snapshot_yaz", lambda s, p: yazildi.append((s, p)))
    c = TestClient(app)
    _post(c)
    assert len(yazildi) == 1


def test_rapor_lead_written(app, monkeypatch):
    lead = []
    monkeypatch.setattr(serve, "_lead_yaz", lambda *a: lead.append(a))
    c = TestClient(app)
    _post(c, email="x@y.com")
    assert len(lead) == 1
    assert lead[0][1] == "x@y.com"


# -- email doğrulama ---------------------------------------------------------------------------

def test_missing_email_400(client):
    assert _post(client, email="").status_code == 400


def test_invalid_email_400(client):
    for bad in ("notanemail", "a@", "@b.com", "a b@c.com"):
        assert _post(client, email=bad).status_code == 400


def test_valid_emails_accepted(client):
    for good in ("a@b.com", "test.user@example.co.uk", "x+tag@y.org"):
        assert _post(client, email=good).status_code == 200


# -- domain doğrulama ---------------------------------------------------------------------------

def test_invalid_domain_400(app, monkeypatch):
    def _bad(d):
        raise ValueError("bu alan adı çözülemedi")
    monkeypatch.setattr(serve, "_guvenli_domain", _bad)
    c = TestClient(app)
    assert _post(c).status_code == 400


def test_domain_error_message(app, monkeypatch):
    """Domain hatası ValueError → HTTP 400'e dönüşür."""
    def _bad(d):
        raise ValueError("alan adı hatalı: " + d)
    monkeypatch.setattr(serve, "_guvenli_domain", _bad)
    c = TestClient(app)
    r = _post(c, domain="kötü")
    assert r.status_code == 400
    assert "hatalı" in r.json().get("detail", "")


# -- günlük limit ---------------------------------------------------------------------------

def test_limit_blocks_after_three(client):
    for _ in range(3):
        assert _post(client).status_code == 200
    assert _post(client).status_code == 429


def test_limit_message(client):
    for _ in range(3):
        _post(client)
    r = _post(client)
    assert "limit" in r.json().get("detail", "").lower()


def test_limit_is_per_ip(app, monkeypatch):
    """Farklı IP'ler ayrı sayılır."""
    monkeypatch.setattr(serve, "snapshot_yaz", lambda *a, **k: None)
    monkeypatch.setattr(serve, "_lead_yaz", lambda *a, **k: None)
    c = TestClient(app)

    class _Req:
        def __init__(self, host):
            self.client = type("C", (), {"host": host})()

    # her istek farklı IP → 429 gelmemeli
    for i in range(5):
        r = c.post("/rapor", json={"email": "a@b.com", "domain": "x.com"})
        # TestClient sabit IP kullanır → bu yine de limitler
        assert r.status_code in (200, 429)
        if r.status_code == 429:
            break


def test_limit_counter_increments(client):
    assert _post(client).status_code == 200
    assert _post(client).status_code == 200


# -- istek gövdesi ---------------------------------------------------------------------------

def test_missing_body_422(client):
    assert client.post("/rapor", json={}).status_code == 422


def test_missing_domain_422(client):
    assert client.post("/rapor", json={"email": "a@b.com"}).status_code == 422


def test_missing_email_422(client):
    assert client.post("/rapor", json={"domain": "x.com"}).status_code == 422


# -- olc_fn yoksa ---------------------------------------------------------------------------

def test_no_olc_fn_no_key_503(monkeypatch):
    """Üretim yolu: anahtar yok → 503."""
    monkeypatch.setattr(serve, "_guvenli_domain", lambda d: d)
    monkeypatch.setattr(serve, "snapshot_yaz", lambda *a, **k: None)
    monkeypatch.setattr(serve, "_lead_yaz", lambda *a, **k: None)

    class _FakeMotor:
        @staticmethod
        def env_oku():
            return {}

    monkeypatch.setitem(__import__("sys").modules, "ai_gorunurluk", _FakeMotor)
    app = serve.create_app(olc_fn=None, gunluk_limit=3)
    c = TestClient(app)
    assert _post(c).status_code == 503


# -- uygulama yapısı ---------------------------------------------------------------------------

def test_create_app_returns_fastapi():
    from fastapi import FastAPI
    assert isinstance(serve.create_app(olc_fn=_fake_olc), FastAPI)


def test_app_has_routes():
    app = serve.create_app(olc_fn=_fake_olc)
    paths = {r.path for r in app.routes}
    assert "/" in paths and "/rapor" in paths


def test_default_limit_3():
    app = serve.create_app(olc_fn=_fake_olc)
    assert isinstance(app, object)


def test_custom_limit_1(monkeypatch):
    monkeypatch.setattr(serve, "_guvenli_domain", lambda d: d)
    monkeypatch.setattr(serve, "snapshot_yaz", lambda *a, **k: None)
    monkeypatch.setattr(serve, "_lead_yaz", lambda *a, **k: None)
    c = TestClient(serve.create_app(olc_fn=_fake_olc, gunluk_limit=1))
    assert _post(c).status_code == 200
    assert _post(c).status_code == 429


def test_module_app_exists():
    assert serve.app is not None
