"""answrank.api.app.queue_decide dal-kesen testleri (LEED).

Hedef fonksiyon: module-level, 12 satirlik kuyruk karar route handler'i
(POST /api/queue/{item_id}/decision).

Kural-1: mevcut production dosyalarina DOKUNULMADI; SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory testler — ApprovalQueue STUBLANDI (monkeypatch) ve
gercek entegrasyon testleri app'in gecici (conftest) DB singleton'i uzerinde
calisir; dis ag/HTTP cagrisi YAPILMADI.
"""
import asyncio
import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from answrank.api.app import QueueDecision
from answrank.api.app import db as app_db
from answrank.api.app import queue_decide
from answrank.queue import ApprovalQueue


# ------------------------------------------------------------------ stub altyapi
class _QueueStub:
    """ApprovalQueue.replace: decide() cagrisini kaydeder; sonuc/hatayi oynar."""

    last = None
    ret = None
    exc = None
    db_received = None
    calls = 0

    @classmethod
    def reset(cls, ret=None, exc=None):
        cls.last = None
        cls.ret = {"id": 7, "status": "APPROVED", "decision_note": ""} if ret is None else ret
        cls.exc = exc
        cls.calls = 0

    def __init__(self, db=None):
        _QueueStub.db_received = db

    def decide(self, item_id, approve, note=""):
        _QueueStub.last = {"item_id": item_id, "approve": approve, "note": note}
        _QueueStub.calls += 1
        if _QueueStub.exc is not None:
            raise _QueueStub.exc
        return _QueueStub.ret


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr("answrank.queue.ApprovalQueue", _QueueStub)
    _QueueStub.reset()
    return _QueueStub


@pytest.fixture
def real_q(monkeypatch, tmp_path):
    """Gercek ApprovalQueue + app DB'si. app.db'yi tamen tasiyin bir temp
    Database ile degistirir: (a) conftest'in session DB'sinde durum sizdirmesi,
    (b) test_payments.py:209'deki app.db.db_path kalici mutasyonu (mevcut
    kirlilik) bu testleri etkilemesin diye."""
    from answrank.api import app as app_module
    from answrank.db import Database

    db = Database(db_path=str(tmp_path / "qd.db"))
    monkeypatch.setattr(app_module, "db", db)
    return ApprovalQueue(db=db)


def _decide(item_id=1, action="approve", note=None):
    req = QueueDecision(action=action) if note is None else QueueDecision(action=action, note=note)
    return asyncio.run(queue_decide(item_id, req))


# ------------------------------------------------------------------ action dal'lari
def test_approve_approve_true_gecirir(stub):
    _decide(action="approve")
    assert stub.last["approve"] is True


def test_reject_approve_false_gecirir(stub):
    _decide(action="reject")
    assert stub.last["approve"] is False


@pytest.mark.parametrize("action,beklenen", [("approve", True), ("reject", False)])
def test_action_eslemesi(stub, action, beklenen):
    _decide(action=action)
    assert stub.last["approve"] is beklenen


def test_action_degeri_route_icinde_karsilastirilir(stub):
    # req.action == "approve" karsilastirmasi: reject != "approve"
    _decide(action="reject")
    assert stub.last["approve"] is False


# ------------------------------------------------------------------ item_id dal'lari
@pytest.mark.parametrize("item_id", [1, 2, 42, 0, 999999, -1])
def test_item_id_oldurulmeden_gecer(stub, item_id):
    _decide(item_id=item_id)
    assert stub.last["item_id"] == item_id


def test_item_id_tamsayi_tipinde(stub):
    _decide(item_id=5)
    assert isinstance(stub.last["item_id"], int)


# ------------------------------------------------------------------ note dal'lari
def test_note_default_bos_string(stub):
    _decide()
    assert stub.last["note"] == ""


def test_note_ozel_gecer(stub):
    _decide(note="butce onaylandi")
    assert stub.last["note"] == "butce onaylandi"


def test_note_unicode_gecer(stub):
    _decide(note="Diş Kliniği onaylandı — ğğ")
    assert stub.last["note"] == "Diş Kliniği onaylandı — ğğ"


def test_note_uzun_gecer(stub):
    uzun = "x" * 500
    _decide(note=uzun)
    assert stub.last["note"] == uzun


def test_note_bos_string_explicit(stub):
    _decide(note="")
    assert stub.last["note"] == ""


def test_note_model_varsayilani_bos():
    req = QueueDecision(action="approve")
    assert req.note == ""


# ------------------------------------------------------------------ donus degeri
def test_basarili_donus_dict_donar(stub):
    out = _decide()
    assert out == {"id": 7, "status": "APPROVED", "decision_note": ""}


def test_basarili_donus_sozluk_tipi(stub):
    assert isinstance(_decide(), dict)


def test_donulen_deger_kuyruktan_gecer(stub):
    stub.ret = {"id": 99, "status": "REJECTED", "decision_note": "hayir"}
    assert _decide(action="reject") == stub.ret


def test_db_singleton_enjekte_edilir(stub):
    _decide()
    assert stub.db_received is app_db


# ------------------------------------------------------------------ hata eslemeleri
def test_key_error_404_donar(stub):
    stub.exc = KeyError("yok")
    with pytest.raises(HTTPException) as ei:
        _decide()
    assert ei.value.status_code == 404
    assert ei.value.detail == "Kuyruk maddesi yok — uydurma karar işlenmez."


def test_value_error_409_donar(stub):
    stub.exc = ValueError("zaten kararli")
    with pytest.raises(HTTPException) as ei:
        _decide()
    assert ei.value.status_code == 409
    assert ei.value.detail == "Bu maddeye karar zaten verilmiş — çift karar yok."


def test_key_error_baska_hata_degildir(stub):
    # KeyError -> 404; ValueError -> 409; KeyError asla 409 uretmez
    stub.exc = KeyError()
    with pytest.raises(HTTPException) as ei:
        _decide()
    assert ei.value.status_code == 404
    assert ei.value.status_code != 409


def test_baska_exception_yayilir(stub):
    stub.exc = RuntimeError("DB ulasilamaz")
    with pytest.raises(RuntimeError, match="DB ulasilamaz"):
        _decide()


def test_type_error_yayilir(stub):
    stub.exc = TypeError("tip hatasi")
    with pytest.raises(TypeError):
        _decide()


def test_hata_durumunda_donus_yok(stub):
    stub.exc = KeyError()
    with pytest.raises(HTTPException):
        _decide()
    assert stub.calls == 1


# ------------------------------------------------------------------ model dogrulama
def test_queue_decision_gecersiz_action_reddedilir():
    with pytest.raises(ValidationError):
        QueueDecision(action="bogus")


def test_queue_decision_action_zorunlu():
    with pytest.raises(ValidationError):
        QueueDecision()


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_queue_decision_gecerli_actionlar(action):
    assert QueueDecision(action=action).action == action


def test_queue_decision_note_str_tipi():
    with pytest.raises(ValidationError):
        QueueDecision(action="approve", note=12345)


# ------------------------------------------------------------------ coroutine
def test_fonksiyon_coroutine():
    assert asyncio.iscoroutinefunction(queue_decide)


def test_tek_cagista_tek_decide(stub):
    _decide()
    _decide()
    assert stub.calls == 2


# ------------------------------------------------------------------ GERCEK kuyruk
def _add_pending(real_q, kind="FREE_CYCLE", summary="test madde", ref_id=None):
    ref = ref_id if ref_id is not None else f"ref-{uuid.uuid4()}"
    assert real_q.add(kind=kind, ref_id=ref, summary=summary) is True
    row = next(it for it in real_q.pending() if it["ref_id"] == ref)
    return row["id"]


def test_real_approve_status_approved(real_q):
    iid = _add_pending(real_q)
    out = _decide(item_id=iid, action="approve")
    assert out["status"] == "APPROVED"


def test_real_reject_status_rejected(real_q):
    iid = _add_pending(real_q)
    out = _decide(item_id=iid, action="reject")
    assert out["status"] == "REJECTED"


def test_real_note_islenir(real_q):
    iid = _add_pending(real_q)
    out = _decide(item_id=iid, action="approve", note="bütçe onaylandı ğğ")
    assert out["decision_note"] == "bütçe onaylandı ğğ"


def test_real_karar_sonrasi_pending_dusulur(real_q):
    iid = _add_pending(real_q)
    _decide(item_id=iid, action="approve")
    assert all(it["id"] != iid for it in real_q.pending())


def test_real_db_durumu_guncellenir(real_q):
    iid = _add_pending(real_q)
    _decide(item_id=iid, action="reject")
    with real_q.db._get_connection() as conn:
        row = conn.execute("SELECT status FROM approval_queue WHERE id=?", (iid,)).fetchone()
    assert row["status"] == "REJECTED"


def test_real_olmayan_id_404(real_q):
    with pytest.raises(HTTPException) as ei:
        _decide(item_id=999999, action="approve")
    assert ei.value.status_code == 404


def test_real_negatif_id_404(real_q):
    with pytest.raises(HTTPException) as ei:
        _decide(item_id=-1, action="approve")
    assert ei.value.status_code == 404


def test_real_cift_karar_409(real_q):
    iid = _add_pending(real_q)
    _decide(item_id=iid, action="approve")
    with pytest.raises(HTTPException) as ei:
        _decide(item_id=iid, action="reject")
    assert ei.value.status_code == 409


def test_real_karar_detaylari_tasir(real_q):
    iid = _add_pending(real_q, summary="Madde 7.3: delta +5")
    out = _decide(item_id=iid, action="approve")
    assert out["id"] == iid
    assert out["summary"] == "Madde 7.3: delta +5"
    assert out["decided_at"] is not None


def test_real_dm_evidence_run_id_kanal_yoksa_none(real_q):
    # DM turu: gecerlilik kosusu yoksa kanit kimligi baglanamaz (fail-closed)
    iid = _add_pending(real_q, kind="DM", ref_id=f"dm-yok-{uuid.uuid4()}")
    out = _decide(item_id=iid, action="approve")
    assert out["evidence_run_id"] is None


def test_real_dm_gecersiz_kanitta_fail_closed(real_q):
    # citations tablosunda SATIR var ama gecerli degil -> yine None
    ref = f"dm-gecersiz-{uuid.uuid4()}"
    iid = _add_pending(real_q, kind="DM", ref_id=ref)
    with real_q.db._get_connection() as conn:
        conn.execute(
            "INSERT INTO citations (id, run_id, brand_name, domain, sector, city,"
            " total_runs, citations_found, citation_rate, raw_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("cid-1", "run-1", "B", ref, "dental", "İstanbul", 1, 0, 0.0,
             '{"is_fully_live": false}'),
        )
        conn.commit()
    out = _decide(item_id=iid, action="approve")
    assert out["evidence_run_id"] is None


def test_real_free_cycle_evidence_run_id_none(real_q):
    # DM disindaki turlerde kanit baglama yogunlugu yok
    iid = _add_pending(real_q, kind="FREE_CYCLE")
    out = _decide(item_id=iid, action="approve")
    assert out["evidence_run_id"] is None


def test_real_iki_farkli_madde_bagimsiz(real_q):
    a = _add_pending(real_q)
    b = _add_pending(real_q)
    assert _decide(item_id=a, action="approve")["status"] == "APPROVED"
    assert _decide(item_id=b, action="reject")["status"] == "REJECTED"
