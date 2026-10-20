"""scripts.readme_stats dal-kesen testleri (LEED) — 3 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — gercek HTTP YOK; urllib.request.urlopen STUBLA.
readme_stats._fiyatlar + _bot_sayilari + _charge_shield.
"""
import io
import json
import os
import sys
from contextlib import contextmanager

import pytest


@contextmanager
def _readme_mod():
    """ORTAM: scripts dizini sys.path'e eklenir (module import yolu)."""
    sys.path.insert(0, "scripts")
    import readme_stats as RS
    sys.path.pop(0)
    yield RS


# G47: sester SDK PyPI-de ( sester==0.7.5, CI-de-kurulu);
# yalnizca-yerel-gelistirme-icin yedek-yol ( CI-de-YOK).
_SESTER = os.environ.get(
    "MESH_SESTER_ROOT", "/home/gokun/projects/01_unicorn/63-Sester")


@contextmanager
def _sester_yuklu():
    """ORTAM-OGRENDI: x402_servis importu icin Sester dizini sys.path'te
    OLMALIDIR + 3 env setdefault (UNPUMP_TREASURY_EOA / ANSWRANK_MAINNET_PAY_TO
    / ANSWRANK_SELLER_SECRET) — _fiyatlar kendi setdefault'unu yapar ama
    sys.path'yi disaridan hazirlamak gerekir.

    G47: sester+unpump-CI-de-YOKSA-tum-fiyat-testleri-skip'lenir
    ( kod-sabitleri kardes-repodan-geliyor, ornatilmadan-test-edilemez).
    """
    if not os.path.isdir(_SESTER):
        pytest.skip(
            "sester-kardes-repo bu-checkout-ta-YOK; MESH_SESTER_ROOT-ile-"
            "kok-verilir ( G47)")
    sys.path.insert(0, _SESTER)
    for k, v in [("UNPUMP_TREASURY_EOA",
                  "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5"),
                 ("ANSWRANK_MAINNET_PAY_TO",
                  "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5"),
                 ("ANSWRANK_SELLER_SECRET", "readme-stats-read-only")]:
        os.environ.setdefault(k, v)
    try:
        yield
    finally:
        if _SESTER in sys.path:
            sys.path.remove(_SESTER)


@contextmanager
def _stub_urlopen(payload, RS):
    """Saf-in-memory healthz stubu — gercek ag YOK."""
    ctx = io.StringIO(json.dumps(payload))
    ctx.__enter__ = lambda self: self
    ctx.__exit__ = lambda self, *a: False
    import urllib.request as _ureq
    orig = _ureq.urlopen
    _ureq.urlopen = lambda url, timeout=None: ctx
    try:
        yield
    finally:
        _ureq.urlopen = orig


def _fiyatlar_urlopen(payload):
    """_fiyatlar'i stublanmis urlopen + Sester env ile cagirir."""
    with _readme_mod() as RS, _stub_urlopen(payload, RS), _sester_yuklu():
        return RS._fiyatlar()


# == _fiyatlar — healthz dallari ==============================================================

def test_fiyatlar_healthz_tam():
    out = _fiyatlar_urlopen({
        "prices": {"audit": "0.05", "citations": "0.10", "fix": "0.20"},
        "daily_quota": 42,
        "ledger_chain_valid": True,
    })
    assert out["audit"] == "0.05"
    assert out["citations"] == "0.10"
    assert out["fix"] == "0.20"
    assert out["daily_quota"] == 42
    assert out["ledger_chain_valid"] is True


def test_fiyatlar_healthz_bos_payload():
    """ORTAM: bos healthz -> fiyatlar dict'i bosalir; kod dallari yine eklenir."""
    out = _fiyatlar_urlopen({})
    assert out.get("audit") is None
    assert out.get("daily_quota") is None
    assert out.get("ledger_chain_valid") is None


def test_fiyatlar_healthz_prices_eksik():
    out = _fiyatlar_urlopen({"daily_quota": 7, "ledger_chain_valid": False})
    assert out["daily_quota"] == 7
    assert out["ledger_chain_valid"] is False


@pytest.mark.parametrize("payload", [
    None, "<html>500</html>", "{invalid json", "",
])
def test_fiyatlar_healthz_gersiz_payload_kod_dallari_yine_gecer(payload):
    """ORTAM-OGRENDI: healthz parse hatasi yutulur — KOD sabitleri her zaman
    gecer (ikincil kaynak); healthz anahtarlari YOK olur."""
    if payload is None:
        out = _fiyatlar_ag_hatasi()
    else:
        out = _fiyatlar_urlopen_raw(payload)
    assert "audit_kod" in out
    assert "ledger_chain_valid" not in out


def _fiyatlar_urlopen_raw(raw):
    import urllib.request as _ureq
    with _readme_mod() as RS, _sester_yuklu():
        orig = _ureq.urlopen
        ctx = io.StringIO(raw)
        ctx.__enter__ = lambda self: self
        ctx.__exit__ = lambda self, *a: False
        _ureq.urlopen = lambda url, timeout=None: ctx
        try:
            return RS._fiyatlar()
        finally:
            _ureq.urlopen = orig


def _fiyatlar_ag_hatasi():
    """ORTAM: urlopen exception -> healthz dallari hic eklenmez."""
    import urllib.request as _ureq
    with _readme_mod() as RS, _sester_yuklu():
        orig = _ureq.urlopen
        _ureq.urlopen = lambda url, timeout=None: (_ for _ in ()).throw(
            ConnectionError("refused"))
        try:
            return RS._fiyatlar()
        finally:
            _ureq.urlopen = orig


def test_fiyatlar_ag_hatasi_kod_dallari_var():
    out = _fiyatlar_ag_hatasi()
    assert out["audit_kod"].startswith("$")
    assert out["citations_kod"].startswith("$")
    assert out["fix_kod"].startswith("$")
    assert out["daily_quota_kod"].startswith("$")


def test_fiyatlar_kod_sabitleri_gercek_deger():
    """ORTAM-OGRENDI: x402_servis sabitleri — import dogrulandi:
    PRICE_AUDIT=0.05, PRICE_CITATIONS=1.2, PRICE_FIX=0.2, DAILY_QUOTA=10.0
    (f-string float format: '$1.2' / '$0.2' / '$10.0' — Kural-5 quirk)."""
    out = _fiyatlar_ag_hatasi()
    assert out["audit_kod"] == "$0.05"
    assert out["citations_kod"] == "$1.2"
    assert out["fix_kod"] == "$0.2"
    assert out["daily_quota_kod"] == "$10.0"


def test_fiyatlar_healthz_ve_kod_birlikte():
    """ORTAM: her iki kaynak da gecerse hepsi ayni dict'te toplanir."""
    out = _fiyatlar_urlopen({
        "prices": {"audit": "0.05"},
        "daily_quota": 10,
        "ledger_chain_valid": True,
    })
    assert out["audit"] == "0.05"
    assert out["audit_kod"] == "$0.05"
    assert out["daily_quota"] == 10
    assert out["daily_quota_kod"] == "$10.0"


def test_fiyatlar_urllib_timeout_kullanilir():
    """ORTAM: urlopen timeout=8 ile cagrilir (saglik kontrolu)."""
    import urllib.request as _ureq
    with _readme_mod() as RS:
        gorulen = {}
        orig = _ureq.urlopen
        ctx = io.StringIO("{}")
        ctx.__enter__ = lambda self: self
        ctx.__exit__ = lambda self, *a: False
        _ureq.urlopen = lambda url, timeout=None: gorulen.setdefault(
            "timeout", timeout) and ctx
        try:
            RS._fiyatlar()
        finally:
            _ureq.urlopen = orig
        assert gorulen["timeout"] == 8


def test_fiyatlar_healthz_url_sabiti():
    with _readme_mod() as RS:
        assert RS._HEALTHZ_URL == "http://127.0.0.1:8007/healthz"


def test_fiyatlar_kod_sabitleri_istisna_yutulur(monkeypatch, capsys):
    """ORTAM-OGRENDI: x402_servis import hatasi -> stderr uyari + BOS fiyatlar
    (fail-soft). Kural-4: gercek healthz sunucusu da stub'lanir (ag YOK);
    sester hem sys.path'ten hem sys.modules onbelleginden cikarilmalidir."""
    with _readme_mod() as RS:
        import urllib.request as _ureq
        monkeypatch.setattr(_ureq, "urlopen",
                            lambda url, timeout=None: (_ for _ in ()).throw(
                                ConnectionError("stub")))
        monkeypatch.delitem(sys.modules, "x402_servis", raising=False)
        monkeypatch.delitem(sys.modules, "sester", raising=False)
        # ORTAM-OGRENDI: sys.modules[name]=None -> import ImportError verir
        # (full-suitete baska testler x402_servis'i onceden import edebilir)
        monkeypatch.setitem(sys.modules, "x402_servis", None)
        monkeypatch.setattr("sys.path", [p for p in sys.path if p != _SESTER])
        out = RS._fiyatlar()
    assert out == {}
    assert "kod sabitleri alınamadı" in capsys.readouterr().err


def test_fiyatlar_dict_donuş_tipi():
    assert isinstance(_fiyatlar_urlopen({}), dict)


# == _bot_sayilari ============================================================================

def test_bot_sayilari_alanlar():
    with _readme_mod() as RS:
        b = RS._bot_sayilari()
    assert "ai_bots_total" in b
    assert "tier_arama" in b
    assert "tier_egitim" in b
    assert "tier_kullanici_ajani" in b
    assert "tier_summary" in b
    assert "waf_probe_botlari" in b


def test_bot_sayilari_pozitif_tamsayi():
    with _readme_mod() as RS:
        b = RS._bot_sayilari()
    assert isinstance(b["ai_bots_total"], int) and b["ai_bots_total"] > 0
    assert isinstance(b["tier_arama"], int) and b["tier_arama"] >= 0
    assert isinstance(b["waf_probe_botlari"], int) and b["waf_probe_botlari"] > 0


def test_bot_sayilari_tier_toplam_tutarli():
    """ORTAM: tier'larin TOPLAMI ai_bots_total ile tutarli olmali."""
    with _readme_mod() as RS:
        b = RS._bot_sayilari()
    toplam = b["tier_arama"] + b["tier_egitim"] + b["tier_kullanici_ajani"]
    assert toplam == b["ai_bots_total"]


def test_bot_sayilari_summary_str():
    """ORTAM-OGRENDI: tier_summary bir STRING'dir (dict degil) —
    '39 AI botu (11 arama + 14 egitim + 14 kullanici-ajani)' formatinda."""
    with _readme_mod() as RS:
        b = RS._bot_sayilari()
    assert isinstance(b["tier_summary"], str)
    assert "AI botu" in b["tier_summary"]
    assert "arama" in b["tier_summary"] and "eğitim" in b["tier_summary"]


def test_bot_sayilari_istisna_bos_dict(monkeypatch, capsys):
    """ORTAM-OGRENDI: import hatasi -> stderr uyari + {} (fail-soft)."""
    with _readme_mod() as RS:
        import builtins
        orig_import = builtins.__import__
        builtins.__import__ = (lambda name, *a, **k: orig_import(name, *a, **k)
                               if name != "answrank.config"
                               else (_ for _ in ()).throw(ImportError("stub")))
        try:
            out = RS._bot_sayilari()
        finally:
            builtins.__import__ = orig_import
        assert out == {}
        assert "bot sayıları alınamadı" in capsys.readouterr().err


# == _charge_shield ===========================================================================

def test_charge_shield_alanlar():
    with _readme_mod() as RS:
        c = RS._charge_shield()
    assert c["servis"] == "ChargeShield"
    assert c["hizmet"] == "ters-ibraz savunması"
    assert c["fiyat"] == "$0.25/ibraz"
    assert "uyari" in c


def test_charge_shield_answrank_ayri_servis_vurgusu():
    """ORTAM-OGRENDI: ChargeShield AnswRank /audit'ten FARKLIdir —
    fiyat tablosu karisikligi onlenir."""
    with _readme_mod() as RS:
        c = RS._charge_shield()
    assert "FARKLI" in c["uyari"]
    assert "$0.05" in c["uyari"]
    assert "DEĞİL" in c["uyari"]


def test_charge_shield_fiyat_auditten_farkli():
    with _readme_mod() as RS:
        c = RS._charge_shield()
    assert c["fiyat"] != "$0.05/ibraz"
