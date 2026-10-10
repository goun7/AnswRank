"""answrank.api.app._turkish_validation_handler dal-kesen testleri (LEED).

Hedef fonksiyon: module-level, "_"-onekli, 15 satirlik exception handler
(Pydantic dogrulama hatalarini Turkce'ye cevirir).

Kural-1: mevcut production dosyalarina DOKUNULMADI; SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory testler — RequestValidationError nesneleri bellekte insa
edilir, dis ag/HTTP/DB cagrisi YAPILMADI. TestClient yalnizca yerel ASGI app'i
cagirir; conftest zaten DB'yi gecici dosyaya yonlermistir.
"""
import asyncio
import json

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, BaseModel

from answrank.api.app import _turkish_validation_handler as handler
from answrank.api.app import app


# ------------------------------------------------------------------ yardimcilar
def _run(errs, body=None, request=None):
    """Handler'i bir kez calistirir; (status_code, body_dict, headers) doner."""
    resp = asyncio.run(handler(request, RequestValidationError(errs, body=body)))
    return resp.status_code, json.loads(resp.body), dict(resp.headers)


def _err(rule=None, loc=(), msg="hata mesaji", inp="deger", ctx=None):
    """Pydantic hata sozlugu uretir; rule=None -> 'type' anahtari YOK."""
    e = {"loc": tuple(loc), "msg": msg, "input": inp}
    if rule is not None:
        e["type"] = rule
    if ctx is not None:
        e["ctx"] = ctx
    return e


class _Req:
    """Handler 'request' argumanini HIC kullanmaz; herhangi bir nesne gecebilir."""
    pass


# ------------------------------------------------------------------ donus tipi
def test_json_response_doner():
    resp = asyncio.run(handler(None, RequestValidationError([])))
    assert isinstance(resp, JSONResponse)


def test_status_code_her_zaman_422():
    for errs in ([], [_err("string_too_short", ("body", "url"))],
                 [_err("missing", ("body", "a")), _err("missing", ("body", "b"))]):
        sc, _, _ = _run(errs)
        assert sc == 422


def test_content_type_json():
    _, _, hdr = _run([_err("missing", ("body", "a"))])
    assert hdr["content-type"].startswith("application/json")


def test_govde_tek_detail_anahtari():
    _, body, _ = _run([_err("missing", ("body", "a"))])
    assert list(body.keys()) == ["detail"]


# ------------------------------------------------------------------ hata listesi
def test_bos_hata_listesi_bos_detail():
    sc, body, _ = _run([])
    assert sc == 422
    assert body["detail"] == ""


def test_tek_hata_tek_mesaj():
    _, body, _ = _run([_err("string_too_short", ("body", "url"))])
    assert body["detail"] == "url: en az 3 karakter olmalı"


def test_coklu_hata_noktali_virgul_ile_birlesir():
    _, body, _ = _run([
        _err("string_too_short", ("body", "a")),
        _err("missing", ("body", "b")),
    ])
    assert body["detail"] == "a: en az 3 karakter olmalı; b: zorunlu alan eksik"


def test_coklu_hata_sirasi_korunur():
    errs = [_err(f"missing", ("body", f"f{i}")) for i in range(5)]
    _, body, _ = _run(errs)
    assert body["detail"] == "; ".join(f"f{i}: zorunlu alan eksik" for i in range(5))


def test_uc_hata_tamami_gorunur():
    _, body, _ = _run([
        _err("string_too_short", ("body", "x")),
        _err("value_error", ("body", "y")),
        _err("literal_error", ("body", "z")),
    ])
    assert body["detail"] == ("x: en az 3 karakter olmalı; y: geçersiz değer; "
                              "z: geçersiz değer (literal_error)")


# ------------------------------------------------------------------ bilinen kurallar
@pytest.mark.parametrize("rule,beklenen", [
    ("string_too_short", "en az 3 karakter olmalı"),
    ("missing", "zorunlu alan eksik"),
    ("value_error", "geçersiz değer"),
])
def test_bilinen_kurallar_turkceye_cevrilir(rule, beklenen):
    _, body, _ = _run([_err(rule, ("body", "alan"))])
    assert body["detail"] == f"alan: {beklenen}"


@pytest.mark.parametrize("rule", [
    "literal_error", "int_parsing", "string_too_long", "greater_than_equal",
    "less_than_equal", "float_parsing", "missing_error", "value_error.error",
    "bool_parsing", "list_type",
])
def test_bilinmeyen_kural_fallback_icerir(rule):
    _, body, _ = _run([_err(rule, ("body", "alan"))])
    assert body["detail"] == f"alan: geçersiz değer ({rule})"


def test_type_anahtari_yoksa_invalid_defaultu():
    _, body, _ = _run([_err(None, ("body", "alan"))])
    assert body["detail"] == "alan: geçersiz değer (invalid)"


def test_type_none_olamaz_python_none_degeri():
    # type anahtari var ama None -> fallback yine rule adini tasiyan olmali
    _, body, _ = _run([{"loc": ("body", "alan"), "msg": "m", "input": "i", "type": None}])
    assert body["detail"] == "alan: geçersiz değer (None)"


def test_bilinen_ve_bilinmeyen_karisik():
    _, body, _ = _run([
        _err("missing", ("body", "a")),
        _err("int_parsing", ("body", "b")),
    ])
    assert body["detail"] == "a: zorunlu alan eksik; b: geçersiz değer (int_parsing)"


# ------------------------------------------------------------------ loc isleme
@pytest.mark.parametrize("loc,beklenen_prefix", [
    (("body", "url"), "url"),
    (("body", "a", "b"), "a.b"),
    (("body",), ""),
    ((), ""),
    (("query", "limit"), "query.limit"),
    (("path", "id"), "path.id"),
    (("body", "user", "profile", "name"), "user.profile.name"),
])
def test_loc_body_segmani_filtrelenir(loc, beklenen_prefix):
    _, body, _ = _run([_err("missing", loc)])
    if beklenen_prefix:
        assert body["detail"].startswith(beklenen_prefix + ": ")
    else:
        assert not body["detail"].startswith(":")


def test_body_birden_fazla_kez_filtrelenir():
    _, body, _ = _run([_err("missing", ("body", "body", "x"))])
    assert body["detail"] == "x: zorunlu alan eksik"


def test_loc_bosluk_none_degil_gercek_string():
    _, body, _ = _run([_err("missing", ("body", " x "))])
    assert body["detail"] == " x : zorunlu alan eksik"


def test_loc_tamsayi_kismi_str_yapilir():
    _, body, _ = _run([_err("missing", ("body", 0, "x"))])
    assert body["detail"] == "0.x: zorunlu alan eksik"


def test_loc_unicode_tr_karakterler():
    _, body, _ = _run([_err("missing", ("body", "şehir"))])
    assert body["detail"] == "şehir: zorunlu alan eksik"


def test_loc_unicode_karisik_karakterler():
    _, body, _ = _run([_err("value_error", ("body", "üşenmez", "ç"))])
    assert body["detail"] == "üşenmez.ç: geçersiz değer"


def test_bos_loc_mesaj_prefix_yok():
    _, body, _ = _run([_err("missing", ("body",))])
    assert body["detail"] == "zorunlu alan eksik"


def test_bos_loc_noktali_virgul_isareti_yok():
    _, body, _ = _run([_err("missing", ())])
    assert body["detail"] == "zorunlu alan eksik"


# ------------------------------------------------------------------ request/body argumanlari
def test_request_argumani_yok_sayilir():
    _, body, _ = _run([_err("missing", ("body", "a"))], request=_Req())
    assert body["detail"] == "a: zorunlu alan eksik"


def test_body_kwarg_ciktiyi_degistirmez():
    a, _, _ = _run([_err("missing", ("body", "a"))])
    b, _, _ = _run([_err("missing", ("body", "a"))], body={"x": 1})
    assert a == b == 422


def test_body_kwarg_hata_listesini_degistirmez():
    _, body, _ = _run([_err("string_too_short", ("body", "z"))], body=None)
    assert body["detail"] == "z: en az 3 karakter olmalı"


# ------------------------------------------------------------------ uretilebilirlik
def test_tekrar_uretilebilir_ayni_cikti():
    e = _err("missing", ("body", "a"))
    first, _, _ = _run([e])
    second, _, _ = _run([dict(e)])
    assert first == second


def test_ctx_alani_gormezden_gelilir():
    _, body, _ = _run([_err("string_too_short", ("body", "x"), ctx={"min_length": 3})])
    assert body["detail"] == "x: en az 3 karakter olmalı"


def test_msg_alani_kullanilmaz_turkce_sabit():
    _, body, _ = _run([_err("string_too_short", ("body", "x"), msg="ENGLISH MSG")])
    assert "ENGLISH MSG" not in body["detail"]


# ------------------------------------------------------------------ gercek pydantic hatalari
class _Model(BaseModel):
    url: str
    count: int


def test_gercek_pydantic_validation_error_islenir():
    try:
        _Model(url="ok")
        pytest.fail("dogrulama hatasi bekleniyordu")
    except Exception as exc:  # pydantic ValidationError -> errors()
        errs = exc.errors()
    sc, body, _ = _run(errs)
    assert sc == 422
    assert "count: zorunlu alan eksik" in body["detail"]


def test_gercek_pydantic_tip_hatasi_bilinmeyen_kural_duser():
    try:
        _Model(url="ok", count="abc")
        pytest.fail("dogrulama hatasi bekleniyordu")
    except Exception as exc:
        errs = exc.errors()
    _, body, _ = _run(errs)
    assert body["detail"] == "count: geçersiz değer (int_parsing)"


# ------------------------------------------------------------------ app entegrasyonu (yerel)
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(monkeypatch, tmp_path):
    # app.db'yi tamen tasiyin temp Database ile degistir: dogrulama gecmeyen
    # rotalar (limit=50) DB'ye erisir; test_payments.py:209'daki app.db.db_path
    # kalici mutasyonu (mevcut suite kirliligi) bu testleri bozmamali.
    from answrank.api import app as app_module
    from answrank.db import Database

    monkeypatch.setattr(app_module, "db", Database(db_path=str(tmp_path / "h.db")))
    return TestClient(app)


def test_app_handler_kayitli_literal_hatasi(client):
    r = client.post("/api/queue/1/decision", json={"action": "bogus", "note": "x"})
    assert r.status_code == 422
    assert r.json() == {"detail": "action: geçersiz değer (literal_error)"}


def test_app_handler_kayitli_eksik_alan(client):
    r = client.post("/api/queue/1/decision", json={"note": "x"})
    assert r.status_code == 422
    assert r.json() == {"detail": "action: zorunlu alan eksik"}


def test_app_handler_coklu_eksik_alan_birlesik(client):
    r = client.post("/api/monitors", json={"sector": "general"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    # domain/brand tamamen yok -> "missing" -> zorunlu alan eksik
    assert "domain: zorunlu alan eksik" in detail
    assert "brand: zorunlu alan eksik" in detail
    assert detail.count("; ") == 1


def test_app_handler_kisa_alan_string_too_short(client):
    r = client.post("/api/monitors", json={"domain": "ab", "brand": "x"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "domain: en az 3 karakter olmalı" in detail
    assert "brand: en az 3 karakter olmalı" in detail


def test_app_handler_query_param_hatasi(client):
    r = client.get("/api/audits/recent", params={"limit": "abc"})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("query.limit: geçersiz değer")


def test_app_handler_sinir_degeri_50_gecerli(client):
    # le=50 sinir degeri gecerli -> 200 (dogrulama hatasi degil)
    r = client.get("/api/audits/recent", params={"limit": 50})
    assert r.status_code == 200


def test_app_handler_sinir_degeri_51_reddedilir(client):
    r = client.get("/api/audits/recent", params={"limit": 51})
    assert r.status_code == 422
    assert "limit" in r.json()["detail"]
