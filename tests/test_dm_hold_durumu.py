#!/usr/bin/env python3
"""dm_hold doğruluk testleri — GERÇEK outbox durumundan türetme.

Kapsam: /olcum ve /olcum/rapor'daki dm_hold alanının hardcoded
DEĞİL, gerçek outbox durumundan ( DRAFT e-posta var + sent=0)
türetildiğini doğrular.

⚠ K4 GÖNDERİM YOK: bu testler outbox'a YAZMAZ/SİLMEZ — yalnızca
  dm_hold fonksiyonunu GEÇİCİ test dizinleri ile sınar ( gerçek
  outbox'a dokunulmaz).
"""
from __future__ import annotations

import os as _os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_os.environ.setdefault("UNPUMP_TREASURY_EOA", "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5")
_os.environ.setdefault("ANSWRANK_MAINNET_PAY_TO", "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5")
_os.environ.setdefault("ANSWRANK_SELLER_SECRET", "test-only-secret-dmhold")

# Bu testler sibling Sester reposunu gerektirir (x402 dogfood, x402_servis.py).
# Bağımsız checkout'ta sester yoksa sessizce atlanır — AnswRank çekirdek
# kütüphane testleri her koşulda bağımsız koşar.
pytest.importorskip("sester")

import x402_servis as xs  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_client = TestClient(xs.app)
_GERCEK_OUTBOX = xs._OUTBOX_DIZIN  # gerçek yolu hatirla ( test sonunda geri al)


@pytest.fixture(autouse=True)
def _temiz_sayaclar():
    xs._REF_SAYACLAR.clear()
    xs._OLCUM_IP.clear()
    yield
    xs._REF_SAYACLAR.clear()
    xs._OLCUM_IP.clear()
    xs._OUTBOX_DIZIN = _GERCEK_OUTBOX  # gercek outbox'a geri don


@pytest.fixture
def gecici_outbox(tmp_path, monkeypatch):
    """Geçici outbox ( gerçek outbox'a DOKUNMADAN)."""
    d = tmp_path / "outbox_test"
    d.mkdir()
    monkeypatch.setattr(xs, "_OUTBOX_DIZIN", d)
    return d


# --- _dm_hold_durumu: GERÇEK outbox ---

def test_dm_hold_gercek_outboxtan_true():
    """GERÇEK outbox: 15 DRAFT + sent=0 → dm_hold TRUE."""
    # gercek outbox'u sına ( degisiklik YAPMADAN — sadece okuma)
    xs._OUTBOX_DIZIN = _GERCEK_OUTBOX
    assert xs._dm_hold_durumu() is True


# --- _dm_hold_durumu: senaryolar ---

def test_dm_hold_draft_var_sent_yok_true(gecici_outbox):
    """DRAFT e-posta var + sent isareti YOK → HOLD true."""
    (gecici_outbox / "dm_01.eml").write_text(
        "To: info@ornek.com\nSubject: test\n\nMerhaba", encoding="utf-8")
    assert xs._dm_hold_durumu() is True


def test_dm_hold_outbox_bos_false(gecici_outbox):
    """Outbox boş ( DRAFT yok) → HOLD false ( kalkti)."""
    assert xs._dm_hold_durumu() is False


def test_dm_hold_sent_isareti_var_false(gecici_outbox):
    """En az bir e-posta GONDERILMIS ( sent isareti) → HOLD false."""
    (gecici_outbox / "dm_01.eml").write_text(
        "To: info@ornek.com\nSubject: test\n\nMerhaba", encoding="utf-8")
    (gecici_outbox / "dm_02.eml").write_text(
        "To: info@ornek.com\nSubject: test\n\nMerhaba\nStatus: Sent\n",
        encoding="utf-8")
    assert xs._dm_hold_durumu() is False


def test_dm_hold_delivered_isareti_false(gecici_outbox):
    (gecici_outbox / "dm_01.eml").write_text(
        "To: info@ornek.com\nSubject: t\n\nX-Delivered: yes\n",
        encoding="utf-8")
    assert xs._dm_hold_durumu() is False


def test_dm_hold_gonderildi_isareti_false(gecici_outbox):
    (gecici_outbox / "dm_01.eml").write_text(
        "To: info@ornek.com\nSubject: t\n\nGONDERILDI: 2026-09-28\n",
        encoding="utf-8")
    assert xs._dm_hold_durumu() is False


def test_dm_hold_outbox_yok_false(tmp_path, monkeypatch):
    """Outbox dizini hiç yok → HOLD false."""
    monkeypatch.setattr(xs, "_OUTBOX_DIZIN", tmp_path / "yok_outbox")
    assert xs._dm_hold_durumu() is False


# --- /olcum endpoint'inde dm_hold GERÇEK durumdan ---

def test_olcum_dm_hold_alani_var():
    r = _client.get("/olcum")
    assert r.status_code == 200
    assert "dm_hold" in r.json()


def test_olcum_dm_hold_true_gercek_outbox():
    """GERÇEK outbox ile /olcum → dm_hold: true ( hardcoded DEGIL)."""
    xs._OUTBOX_DIZIN = _GERCEK_OUTBOX
    r = _client.get("/olcum")
    assert r.json()["dm_hold"] is True


# --- /olcum/rapor: 0-veri + dm_hold=true ---

def test_rapor_sifir_veri_dm_hold_true():
    """0 veri + GERÇEK outbox → 'Henuz gonderim yok' + HOLD aktif."""
    xs._REF_SAYACLAR.clear()
    xs._OUTBOX_DIZIN = _GERCEK_OUTBOX
    r = _client.get("/olcum/rapor")
    v = r.json()
    assert v["dm_hold"] is True
    assert "Henüz gönderim yok" in v["rapor"]
    assert "DM HOLD" in v["rapor"]


# --- /olcum/rapor: test verisi + dm_hold=true → DÜRÜST not ZORUNLU ---

def test_rapor_test_verisi_hold_aktif_uyari(gecici_outbox):
    """HOLD aktifken olusan veri TEST verisidir — uyarı ZORUNLU."""
    (gecici_outbox / "dm_01.eml").write_text(
        "To: info@ornek.com\nSubject: t\n\nMerhaba", encoding="utf-8")
    xs._ref_sayac_artir("unpump-p1a-tr-01", "deneme")  # sandbox/test verisi
    r = _client.get("/olcum/rapor")
    v = r.json()
    assert v["dm_hold"] is True
    assert "TEST verisidir" in v["rapor"]
    assert "GERÇEK" in v["rapor"].upper()
    assert "HOLD" in v["rapor"]


def test_rapor_test_verisi_sayac_dogru(gecici_outbox):
    (gecici_outbox / "dm_01.eml").write_text(
        "To: info@ornek.com\nSubject: t\n\nMerhaba", encoding="utf-8")
    xs._ref_sayac_artir("unpump-p1a-tr-01", "deneme")
    xs._ref_sayac_artir("unpump-p1a-tr-01", "odeme")
    r = _client.get("/olcum/rapor")
    sonuc = r.json()["varyantlar"]
    saas = next(k for k in sonuc if "SaaS" in k)
    assert sonuc[saas]["A"]["deneme"] == 1
    assert sonuc[saas]["A"]["odeme"] == 1


# --- /olcum/rapor: HOLD kalkti ( outbox bos) ---

def test_rapor_hold_kalkti_outbox_bos(gecici_outbox):
    """Outbox boş + veri var → dm_hold false, test-notu YOK."""
    xs._ref_sayac_artir("unpump-p1a-tr-01", "deneme")
    r = _client.get("/olcum/rapor")
    v = r.json()
    assert v["dm_hold"] is False
    assert "TEST verisidir" not in v["rapor"]


def test_rapor_hold_kalkti_sifir_veri_notu(gecici_outbox):
    """HOLD kalkti ama veri yok → dürüst not farklı."""
    r = _client.get("/olcum/rapor")
    v = r.json()
    assert v["dm_hold"] is False
    assert "Henüz gönderim yok" in v["rapor"]
    assert "kalktı" in v["rapor"] or "kalkti" in v["rapor"]


# --- hardcoded DEĞİL: outbox değişince rapor değişir ---

def test_dm_hold_dinamik_outbox_degisince(gecici_outbox):
    """Aynı çağrı outbox değişince farklı sonuç vermeli ( dinamik)."""
    assert xs._dm_hold_durumu() is False  # bos
    (gecici_outbox / "dm_01.eml").write_text("To: a@b.c\n\nx", encoding="utf-8")
    assert xs._dm_hold_durumu() is True   # draft geldi
    (gecici_outbox / "dm_01.eml").write_text(
        "To: a@b.c\n\nx\nStatus: Sent\n", encoding="utf-8")
    assert xs._dm_hold_durumu() is False  # gonderildi
