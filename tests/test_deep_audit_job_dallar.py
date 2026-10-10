"""api.submit_deep_audit_job dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-3: engine/db/job_manager stub — gercek ag YAPILMADI.
"""
import asyncio
import json
import sys
import types

import pytest
from fastapi.testclient import TestClient

from answrank.api import app as answ_app


class _DeepRes:
    base_audit = {"url": "u"}

    def model_dump(self):
        return {"base_audit": {"url": "u"}, "ok": True}


class _Base:
    pass


class _Job:
    def __init__(self, jid):
        self.id = jid


class _JM:
    submitted = []
    progress = []
    job_id = "JOB1"
    raises = None

    async def submit(self, kind, work):
        _JM.submitted.append((kind, work))
        if _JM.raises:
            raise _JM.raises
        job = _Job(_JM.job_id)
        _JM.work_ran = await work(job)
        return _JM.job_id

    def report_progress(self, job, frac, msg):
        _JM.progress.append((job.id, frac, msg))


class _Engine:
    kwargs = None
    raises = None

    async def audit_url_deep(self, **kw):
        _Engine.kwargs = kw
        if _Engine.raises:
            raise _Engine.raises
        return _DeepRes()


class _DB:
    saved = []
    raises = None

    async def save_audit(self, base):
        _DB.saved.append(base)
        if _DB.raises:
            raise _DB.raises


@pytest.fixture
def client(monkeypatch):
    _JM.submitted = []
    _JM.progress = []
    _JM.job_id = "JOB1"
    _JM.raises = None
    _JM.work_ran = None
    _Engine.kwargs = None
    _Engine.raises = None
    _DB.saved = []
    _DB.raises = None
    monkeypatch.setattr(answ_app, "job_manager", _JM())
    monkeypatch.setattr(answ_app, "engine", _Engine())
    monkeypatch.setattr(answ_app, "db", _DB())
    return TestClient(answ_app.app)


def _post(client, **kw):
    body = {"url": "https://x.example"}
    body.update(kw)
    return client.post("/api/jobs/deep-audit", content=json.dumps(body),
                       headers={"Content-Type": "application/json"})


# -- temel ---------------------------------------------------------------------------------

def test_status_200(client):
    assert _post(client).status_code == 200


def test_returns_json(client):
    assert _post(client).json().get("job_id") == "JOB1"


def test_status_url(client):
    out = _post(client).json()
    assert out["status_url"] == "/api/jobs/JOB1"


def test_stream_url(client):
    out = _post(client).json()
    assert out["stream_url"] == "/api/jobs/JOB1/stream"


def test_three_keys(client):
    assert set(_post(client).json()) == {
        "job_id", "status_url", "stream_url"}


def test_urls_derived_from_job_id(client):
    _JM.job_id = "ABC99"
    out = _post(client).json()
    assert out["job_id"] == "ABC99"
    assert out["status_url"] == "/api/jobs/ABC99"


def test_custom_job_id_in_urls(client):
    _JM.job_id = "z"
    out = _post(client).json()
    assert "/api/jobs/z" in out["status_url"]


# -- submit ---------------------------------------------------------------------------------

def test_submit_kind_deep_audit(client):
    _post(client)
    assert _JM.submitted[0][0] == "deep-audit"


def test_submit_work_callable(client):
    _post(client)
    assert callable(_JM.submitted[0][1])


def test_job_id_returned(client):
    _JM.job_id = "Q"
    assert _post(client).json()["job_id"] == "Q"


# -- work() icerigi ---------------------------------------------------------------------------------

def test_work_returns_model_dump(client):
    _post(client)
    assert _JM.work_ran == {"base_audit": {"url": "u"}, "ok": True}


def test_progress_005_first(client):
    _post(client)
    assert _JM.progress[0] == ("JOB1", 0.05, "Fetching page + auxiliary assets")


def test_progress_085_persisting(client):
    _post(client)
    assert (0.85, "Persisting audit") in [(f, m) for _, f, m in _JM.progress]


def test_progress_095_finalizing(client):
    _post(client)
    assert (0.95, "Finalizing") in [(f, m) for _, f, m in _JM.progress]


def test_progress_three_steps(client):
    _post(client)
    assert len(_JM.progress) == 3


def test_engine_kwargs_passed(client):
    _post(client)
    kw = _Engine.kwargs
    assert kw["url"] == "https://x.example"
    assert kw["sector"] == "general"


def test_engine_brand_passed(client):
    _post(client, brand_name="Acme")
    assert _Engine.kwargs["brand_name"] == "Acme"


def test_engine_flags_default_true(client):
    _post(client)
    kw = _Engine.kwargs
    assert kw["probe_waf"] is True
    assert kw["check_adversarial"] is True
    assert kw["check_grounding"] is True
    assert kw["check_rag"] is True


def test_engine_flags_off(client):
    _post(client, probe_waf=False, check_rag=False)
    kw = _Engine.kwargs
    assert kw["probe_waf"] is False
    assert kw["check_rag"] is False
    assert kw["check_adversarial"] is True


def test_custom_sector(client):
    _post(client, sector="dental")
    assert _Engine.kwargs["sector"] == "dental"


def test_db_save_called(client):
    _post(client)
    assert len(_DB.saved) == 1


def test_db_save_before_095(client):
    _post(client)
    order = [f for _, f, _ in _JM.progress]
    assert order == [0.05, 0.85, 0.95]


# -- hata ---------------------------------------------------------------------------------

def test_engine_error_propagates(client):
    _Engine.raises = RuntimeError("ag hatasi")
    with pytest.raises(RuntimeError):
        _post(client)


def test_db_error_propagates(client):
    _DB.raises = ValueError("db yok")
    with pytest.raises(ValueError):
        _post(client)


def test_submit_error_propagates(client):
    _JM.raises = OSError("kuyruk dolu")
    with pytest.raises(OSError):
        _post(client)


def test_submit_error_no_progress(client):
    _JM.raises = OSError("kuyruk dolu")
    with pytest.raises(OSError):
        _post(client)
    assert _JM.progress == []


# -- validation ---------------------------------------------------------------------------------

def test_missing_url_422(client):
    r = client.post("/api/jobs/deep-audit",
                    content=json.dumps({}),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_url_only_ok(client):
    r = client.post("/api/jobs/deep-audit",
                    content=json.dumps({"url": "https://y"}),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 200


def test_bad_type_flag_422(client):
    r = client.post("/api/jobs/deep-audit",
                    content=json.dumps({"url": "u", "probe_waf": "evet"}),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(client):
    a = _post(client).json()
    b = _post(client).json()
    assert a == b


def test_new_job_id_each_submit(client):
    ids = []
    for i, jid in enumerate(["A", "B"]):
        _JM.job_id = jid
        ids.append(_post(client).json()["job_id"])
    assert ids == ["A", "B"]
