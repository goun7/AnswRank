"""api.register_lead_inquiry_api dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-3: SwarmOrchestrator stub — gercek ag YAPILMADI.
"""
import json
import re

import pytest
from fastapi.testclient import TestClient

from answrank.api import app as answ_app
from answrank.agents import swarm as swarm_mod


class _Cand:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _Scout:
    qualified = []

    def qualify(self, cand):
        _Scout.qualified.append(cand)
        return cand


class _Orch:
    seed_kwargs = None
    persisted = []
    raises = None

    def __init__(self):
        self.scout = _Scout()

    def seed_target(self, **kw):
        _Orch.seed_kwargs = kw
        if _Orch.raises:
            raise _Orch.raises
        return _Cand(**kw)

    def persist_candidate(self, cand):
        _Orch.persisted.append(cand)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(swarm_mod, "SwarmOrchestrator", _Orch)
    _Orch.seed_kwargs = None
    _Orch.persisted = []
    _Orch.raises = None
    _Scout.qualified = []
    return TestClient(answ_app.app)


def _body(**kw):
    b = {"brand_name": "Acme", "domain": "acme.example",
         "email_or_phone": "x@example.com"}
    b.update(kw)
    return json.dumps(b)


def _post(client, **kw):
    return client.post("/api/inquiry", content=_body(**kw),
                       headers={"Content-Type": "application/json"})


# -- temel ---------------------------------------------------------------------------------

def test_status_200(client):
    assert _post(client).status_code == 200


def test_status_success(client):
    assert _post(client).json()["status"] == "success"


def test_returns_json(client):
    assert isinstance(_post(client).json(), dict)


def test_six_keys(client):
    assert set(_post(client).json()) == {
        "status", "reservation_code", "brand_name", "domain",
        "city", "country", "message"}


def test_message_english(client):
    assert _post(client).json()["message"] == (
        "Territory reservation request received and "
        "priority audit queued.")


# -- echo ---------------------------------------------------------------------------------

def test_brand_echoed(client):
    assert _post(client).json()["brand_name"] == "Acme"


def test_domain_echoed(client):
    assert _post(client).json()["domain"] == "acme.example"


def test_default_city(client):
    assert _post(client).json()["city"] == "İstanbul"


def test_default_country(client):
    assert _post(client).json()["country"] == "TR"


def test_custom_city(client):
    assert _post(client, city="İzmir").json()["city"] == "İzmir"


def test_custom_country(client):
    assert _post(client, country="DE").json()["country"] == "DE"


def test_custom_sector(client):
    _post(client, sector="legal")
    assert _Orch.seed_kwargs["sector"] == "legal"


def test_default_sector(client):
    _post(client)
    assert _Orch.seed_kwargs["sector"] == "dental"


# -- reservation_code ---------------------------------------------------------------------------------

def test_code_prefix(client):
    assert _post(client).json()["reservation_code"].startswith("ANSW-LK-")


def test_code_length(client):
    code = _post(client).json()["reservation_code"]
    assert len(code) == len("ANSW-LK-") + 4


def test_code_hex_upper(client):
    code = _post(client).json()["reservation_code"]
    suffix = code[len("ANSW-LK-"):]
    assert re.fullmatch(r"[0-9A-F]{4}", suffix)


def test_code_unique_per_call(client):
    a = _post(client).json()["reservation_code"]
    b = _post(client).json()["reservation_code"]
    assert a != b


def test_code_depends_on_domain(client):
    a = _post(client).json()["reservation_code"]
    b = _post(client, domain="other.example").json()[
        "reservation_code"]
    assert a != b


# -- orch cagrilari ---------------------------------------------------------------------------------

def test_seed_target_called(client):
    _post(client)
    assert _Orch.seed_kwargs is not None


def test_seed_target_brand(client):
    _post(client)
    assert _Orch.seed_kwargs["brand_name"] == "Acme"


def test_seed_target_domain(client):
    _post(client)
    assert _Orch.seed_kwargs["domain"] == "acme.example"


def test_seed_target_five_kwargs(client):
    _post(client)
    assert len(_Orch.seed_kwargs) == 5


def test_scout_qualify_called(client):
    _post(client)
    assert len(_Scout.qualified) == 1


def test_scout_qualify_receives_candidate(client):
    _post(client)
    assert _Scout.qualified[0].brand_name == "Acme"


def test_persist_candidate_called(client):
    _post(client)
    assert len(_Orch.persisted) == 1


def test_persisted_has_domain(client):
    _post(client)
    assert _Orch.persisted[0].domain == "acme.example"


def test_seed_before_persist(client):
    _post(client)
    assert _Orch.seed_kwargs is not None
    assert len(_Orch.persisted) == 1


# -- hata ---------------------------------------------------------------------------------

def test_orch_error_500(client):
    _Orch.raises = RuntimeError("swarm hatasi")
    with pytest.raises(RuntimeError):
        _post(client)


def test_orch_error_no_persist(client):
    _Orch.raises = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        _post(client)
    assert _Orch.persisted == []


# -- validation ---------------------------------------------------------------------------------

def test_missing_brand_422(client):
    r = client.post("/api/inquiry",
                    content=json.dumps({"domain": "d",
                                        "email_or_phone": "e"}),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_missing_domain_422(client):
    r = client.post("/api/inquiry",
                    content=json.dumps({"brand_name": "b",
                                        "email_or_phone": "e"}),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_missing_contact_422(client):
    r = client.post("/api/inquiry",
                    content=json.dumps({"brand_name": "b",
                                        "domain": "d"}),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_notes_optional_ok(client):
    r = _post(client, notes="acil")
    assert r.status_code == 200


def test_bad_type_422(client):
    r = client.post("/api/inquiry",
                    content=json.dumps({"brand_name": 1,
                                        "domain": "d",
                                        "email_or_phone": "e"}),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


# -- unicode ---------------------------------------------------------------------------------

def test_turkish_chars_preserved(client):
    r = _post(client, city="Şanlıurfa")
    assert r.json()["city"] == "Şanlıurfa"


def test_brand_unicode(client):
    r = _post(client, brand_name="TürkMarka")
    assert r.json()["brand_name"] == "TürkMarka"


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable_structure(client):
    a = _post(client).json()
    b = _post(client).json()
    assert a["status"] == b["status"] == "success"
    assert a["message"] == b["message"]
