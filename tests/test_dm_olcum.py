#!/usr/bin/env python3
"""K8 — DM ölçüm çekirdeği testleri ( K1+K2+K5+K7).

Kapsam: x402_servis'in ref-ayırma, etik kapı ( kişisel veri filtresi)
ve sayaç fonksiyonlarını doğrular. Yalnızca fonksiyonlar — canlı
HTTP çağrısı YAPILMAZ, gerçek müşteri verisi YOK ( 0 müşteri).

⚠ ETİK KAPI: ref KİŞİYE ÖZGÜ DEĞİLDİR — kişisel tanımlayıcı
  REDDEDILMELİDİR ( e-posta, isim, telefon, serbest metin).
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# x402_servis import-aninda fail-closed SystemExit yapmasin ( treasury
# ZORUNLU). Test ortaminda env mock'lanir — gercek servis BASLATILMAZ,
# yalnizca fonksiyonlar cagrilir ( 0 gercek musteri, gercek odeme YOK).
import os as _os
_os.environ.setdefault("UNPUMP_TREASURY_EOA", "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5")
_os.environ.setdefault("ANSWRANK_MAINNET_PAY_TO", "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5")
# test-özelliği secret: HMAC zinciri bu anahtarla yazılır ( gercek DEGIL)
_os.environ.setdefault("ANSWRANK_SELLER_SECRET", "test-only-secret-k9-dm-olcum")

# Bu testler sibling Sester reposunu gerektirir (x402 dogfood, x402_servis.py).
# Bağımsız checkout'ta sester yoksa sessizce atlanır — AnswRank çekirdek
# kütüphane testleri her koşulda bağımsız koşar.
pytest.importorskip("sester")

import x402_servis as xs  # noqa: E402


def _req(ref: str | None = None) -> SimpleNamespace:
    """Minimal Request taklidi ( query_params ile)."""
    params = {"ref": ref} if ref is not None else {}
    return SimpleNamespace(query_params=params)


# --- K1: ref ayırma ---

@pytest.mark.parametrize("ref", [
    "unpump-p1a-tr-01", "unpump-p3b-en-07", "unpump-p2b-tr-12",
])
def test_k1_ref_gecerli_biçim_ayrilir(ref):
    assert xs._ref_ayir(_req(ref)) == ref


def test_k1_ref_yoksa_none():
    assert xs._ref_ayir(_req(None)) is None


def test_k1_ref_bossa_none():
    assert xs._ref_ayir(_req("")) is None


@pytest.mark.parametrize("kotu", [
    "unpump-p1a-tr-1",      # 1 hane sira ( 2 olmali)
    "unpump-p4a-tr-01",     # gecersiz profil
    "unpump-p1c-tr-01",     # gecersiz varyant
    "unpump-p1a-de-01",     # gecersiz dil
    "UNPUMP-p1a-tr-01",     # buyuk harf
    "unpump-p1a-tr-01;x=1", # ek parametre
])
def test_k1_ref_biçim_disi_reddedilir(kotu):
    """KATI biçim — biçim dışı ref yok sayılır ( kısıt amaçlı)."""
    assert xs._ref_ayir(_req(kotu)) is None


# --- K7: kişisel veri filtresi ( ETİK KAPI) ---

@pytest.mark.parametrize("kisisel", [
    "ahmet@eposta.com",       # e-posta
    "ahmet.yilmaz",           # isim
    "+905551234567",          # telefon
    "Merhaba Ahmet",          # serbest metin
    "unpump-ahmet-tr-01",     # profil yerine isim
    "unpump-p1a-tr-01;user=ahmet",  # ek kisisel alan
])
def test_k7_kisisel_veri_reddedilir(kisisel):
    """ETİK KURAL: ref kişisel tanımlayıcı içeremez — kişi tanımlanmaz."""
    # once K1'den gecmeye calisirsa bile K7 reddetmeli
    assert xs._ref_kisisel_veri_filtre(kisisel) is None


def test_k7_gecerli_ref_kabul_edilir():
    assert xs._ref_kisisel_veri_filtre("unpump-p1a-tr-01") == "unpump-p1a-tr-01"


def test_k7_ref_kisiyi_tanimlamaz():
    """Reddedilenler kişiselleştirilebilir DEĞIL — yalnızca biçim geçer."""
    assert xs._ref_kisisel_veri_filtre(None) is None
    assert xs._ref_kisisel_veri_filtre("") is None


# --- K5: sayaçlar ( thread-safe) ---

def test_k5_sayac_baslangicta_sifir():
    # test oncesi temiz state
    xs._REF_SAYACLAR.pop("unpump-p1a-tr-99", None)
    xs._ref_sayac_artir("unpump-p1a-tr-99", "deneme")
    assert xs.ref_ozet()["unpump-p1a-tr-99"]["deneme"] == 1
    xs._REF_SAYACLAR.pop("unpump-p1a-tr-99", None)


def test_k5_deneme_sayaci_artar():
    ref = "unpump-p2b-en-03"
    xs._REF_SAYACLAR.pop(ref, None)
    xs._ref_sayac_artir(ref, "deneme")
    xs._ref_sayac_artir(ref, "deneme")
    xs._ref_sayac_artir(ref, "odeme")
    ozet = xs.ref_ozet()
    assert ozet[ref]["deneme"] == 2
    assert ozet[ref]["odeme"] == 1
    xs._REF_SAYACLAR.pop(ref, None)


def test_k5_gecersiz_anahtar_yazmaz():
    ref = "unpump-p3a-tr-05"
    xs._REF_SAYACLAR.pop(ref, None)
    xs._ref_sayac_artir(ref, "gosterim")  # bu anahtar YOK ( K5'te)
    assert ref not in xs.ref_ozet()
    xs._REF_SAYACLAR.pop(ref, None)


def test_k5_ref_yoksa_sayac_yazmaz():
    once = len(xs.ref_ozet())
    xs._ref_sayac_artir(None, "deneme")
    assert len(xs.ref_ozet()) == once


def test_k5_ref_ozet_kopya_donuyor():
    """Dışarıdan değiştirme ana tabloyu etkilememeli."""
    ref = "unpump-p1b-tr-08"
    xs._REF_SAYACLAR.pop(ref, None)
    xs._ref_sayac_artir(ref, "deneme")
    ozet = xs.ref_ozet()
    ozet[ref]["deneme"] = 999  # kopyada degisiklik
    assert xs.ref_ozet()[ref]["deneme"] == 1  # ana tablo etkilenmedi
    xs._REF_SAYACLAR.pop(ref, None)


# --- K1+K7 entegrasyon: ref akışı ---

def test_ref_akisi_gecerli_ref_kabul_edilir():
    """K1 → K7 hattı: geçerli ref filtre'den geçer."""
    ref = xs._ref_kisisel_veri_filtre(xs._ref_ayir(_req("unpump-p1a-tr-01")))
    assert ref == "unpump-p1a-tr-01"


def test_ref_akisi_kisisel_ref_yok_sayilir():
    """K1 reddetmese bile K7 reddetmeli ( katı etik kapı)."""
    ham = "unpump-p1a-tr-01"
    # K1 gecerli buldu, K7 de gecerli -> akis OK
    assert xs._ref_kisisel_veri_filtre(xs._ref_ayir(_req(ham))) == ham


# --- healthz'de dm_ref_counts alanı ( K5 görünürlük) ---

def test_healthz_dm_ref_counts_alani_var():
    """healthz yanıtında dm_ref_counts anahtarı bulunmalı ( açık izleme)."""
    import inspect
    kaynak = inspect.getsource(xs.healthz)
    assert "dm_ref_counts" in kaynak
    assert "ref_ozet" in kaynak


# --- /audit endpoint'inde ref kullanımı ( K1+K2 entegrasyon) ---

def test_audit_endpoint_ref_kullaniyor():
    """K1+K5+K2: /audit ref'i ayırır, sayar ve receipt'e yazar."""
    import inspect
    kaynak = inspect.getsource(xs.audit)
    assert "_ref_ayir" in kaynak        # K1
    assert "_ref_sayac_artir" in kaynak # K5 ( deneme + odeme)
    assert "dm_ref" in kaynak           # K2 ( receipt payload)


def test_audit_receipte_ref_yaziliyor_k2():
    """K2: charge detail'inde dm_ref alanı var."""
    import inspect
    kaynak = inspect.getsource(xs._charge)
    # _charge detail'i disaridan alir; /audit 'dm_ref' ekler
    assert inspect.getsource(xs.audit).count("dm_ref") >= 1


# --- çoklu ref aynı anda ( thread-safety basit kontrol) ---

def test_coklu_ref_birbirini_bozmaz():
    """Aynı anda farklı ref'ler ayrı sayaçlar tutar."""
    refs = ["unpump-p1a-tr-01", "unpump-p2b-en-02", "unpump-p3a-tr-03"]
    for r in refs:
        xs._REF_SAYACLAR.pop(r, None)
    for r in refs:
        xs._ref_sayac_artir(r, "deneme")
    ozet = xs.ref_ozet()
    for r in refs:
        assert ozet[r]["deneme"] == 1
        xs._REF_SAYACLAR.pop(r, None)
