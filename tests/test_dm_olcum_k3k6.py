#!/usr/bin/env python3
"""K3+K6 — /olcum read-only endpoint ve A/B rapor testleri.

Kapsam: /olcum ( rate-limit ile) ve /olcum/rapor ( A/B karsilastirma +
0-veri dürüst çikti). TestClient ile canli HTTP çağrısı YAPILIR ama
hepsi YERELDIR — gerçek müşteri verisi YOK ( 0 müşteri, 0 ödeme).

⚠ ETİK ( K7): raporda kişisel tanımlayıcı YOK — yalnızca
  'unpump-p<1-3><a-b>-<tr|en>-<NN>' kimlikleri.
"""
from __future__ import annotations

import os as _os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# x402_servis import-aninda fail-closed SystemExit yapmasin ( env mock)
_os.environ.setdefault("UNPUMP_TREASURY_EOA", "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5")
_os.environ.setdefault("ANSWRANK_MAINNET_PAY_TO", "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5")
_os.environ.setdefault("ANSWRANK_SELLER_SECRET", "test-only-secret-k3-k6-olcum")

# Bu testler sibling Sester reposunu gerektirir (x402 dogfood, x402_servis.py).
# Bağımsız checkout'ta sester yoksa sessizce atlanır — AnswRank çekirdek
# kütüphane testleri her koşulda bağımsız koşar.
pytest.importorskip("sester")

import x402_servis as xs  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_client = TestClient(xs.app)


# --- yardimci: test oncesi sayac temizle ---

@pytest.fixture(autouse=True)
def _temiz_ref_sayaclari():
    xs._REF_SAYACLAR.clear()
    xs._OLCUM_IP.clear()
    yield
    xs._REF_SAYACLAR.clear()
    xs._OLCUM_IP.clear()


# --- K3: /olcum read-only ---

def test_k3_olcum_endpoint_200_ve_ref_counts():
    """K3: /olcum read-only döner — ödeme GEREKMEZ ( 402 DEĞİL)."""
    r = _client.get("/olcum")
    assert r.status_code == 200
    v = r.json()
    assert v["status"] == "ok"
    assert "dm_ref_counts" in v


def test_k3_olcum_402_degil_odeme_istemez():
    """Kritik: /olcum ödeme gerektirmez — X-Payment olmadan 200."""
    r = _client.get("/olcum", headers={})  # X-Payment YOK
    assert r.status_code == 200
    assert r.status_code != 402


def test_k3_olcum_ref_gosterir():
    xs._ref_sayac_artir("unpump-p1a-tr-01", "deneme")
    r = _client.get("/olcum")
    assert r.json()["dm_ref_counts"]["unpump-p1a-tr-01"]["deneme"] == 1


def test_k3_rate_limit_429_ardisik_istekte():
    """K3 güvenlik: ayni IP'den saniyede 1 istek — 2. istek 429."""
    r1 = _client.get("/olcum")
    assert r1.status_code == 200
    r2 = _client.get("/olcum")  # hemen 2. istek
    assert r2.status_code == 429
    assert "rate-limit" in r2.json().get("detail", "").lower()


def test_k3_olcum_kisisiz_aciklama_var():
    """K7 uyum: yanıtta kişisel tanımlayıcı YOK."""
    r = _client.get("/olcum")
    govde = r.text
    assert "kisisiz" in govde or "açık izleme" in govde


# --- K6: /olcum/rapor A/B karsilastirma ---

def test_k6_rapor_sifir_veri_dürüst_cikti():
    """K6 ZORUNLU: 0 veri olduğunda dürüst çıktı ( DM HOLD aktif)."""
    r = _client.get("/olcum/rapor")
    assert r.status_code == 200
    v = r.json()
    assert v["status"] == "ok"
    assert v["dm_hold"] is True
    rapor = v["rapor"]
    assert "Henüz gönderim yok" in rapor
    assert "0 ödeme" in rapor
    assert "DM HOLD" in rapor
    assert v["varyantlar"] == {}


def test_k6_rapor_veri_varsa_ab_raporu():
    """Veri varsa A/B raporu üretilir.

    Not: dm_hold artık GERÇEK outbox'tan türetilir ( hardcoded değil)
    — bu test yalnızca rapor üretimini sınar, hold değerini varsaymaz.
    """
    xs._ref_sayac_artir("unpump-p1a-tr-01", "deneme")
    xs._ref_sayac_artir("unpump-p1a-tr-01", "odeme")
    r = _client.get("/olcum/rapor")
    v = r.json()
    assert "A/B" in v["rapor"]
    # HOLD aktifken ( gerçek outbox'ta DRAFT var) test-verisi uyarisi ZORUNLU
    if v["dm_hold"] is True:
        assert "TEST verisidir" in v["rapor"]


def test_k6_rapor_ab_varyant_ayri():
    """A ( uzun) ve B ( kisa) ayni profil altında yan yana."""
    xs._ref_sayac_artir("unpump-p1a-tr-01", "deneme")  # A
    xs._ref_sayac_artir("unpump-p1a-tr-01", "odeme")
    xs._ref_sayac_artir("unpump-p1b-en-02", "deneme")  # B
    r = _client.get("/olcum/rapor")
    sonuc = r.json()["varyantlar"]
    # JSON Unicode kacisi: 'AI-oncul SaaS' ( ornek Turkce kayip — ASCII ile sorgula)
    assert any("SaaS" in k for k in sonuc), f"profil YOK: {sonuc}"
    saas = next(k for k in sonuc if "SaaS" in k)
    assert sonuc[saas]["A"]["deneme"] == 1
    assert sonuc[saas]["A"]["odeme"] == 1
    assert sonuc[saas]["B"]["deneme"] == 1
    assert sonuc[saas]["B"]["odeme"] == 0


def test_k6_rapor_profiler_toplanir():
    xs._ref_sayac_artir("unpump-p2b-tr-01", "deneme")
    xs._ref_sayac_artir("unpump-p3a-en-01", "odeme")
    r = _client.get("/olcum/rapor")
    sonuc = r.json()["varyantlar"]
    # JSON Unicode kacisi nedeniyle Turkce harfler ASCII duser — anahtar kelime ile sorgula
    assert any("klinik" in k.lower() or "Dubai" in k for k in sonuc), sonuc
    assert any("gelistirici" in k.lower() or "Bireysel" in k for k in sonuc), sonuc


def test_k6_rapor_kisisel_tanimlayici_yok():
    """K7 ETİK: raporda kişisel tanımlayıcı YOLAR — varyant toplamı."""
    xs._ref_sayac_artir("unpump-p1a-tr-01", "deneme")
    r = _client.get("/olcum/rapor")
    govde = r.text
    # e-posta/isim/telefon gecmemeli
    for yasak in ("@", "0555", "eposta.com"):
        assert yasak not in govde, f"kisisel veri sızdı: {yasak}"


def test_k6_rapor_rate_limit_429():
    r1 = _client.get("/olcum/rapor")
    assert r1.status_code == 200
    r2 = _client.get("/olcum/rapor")
    assert r2.status_code == 429


# --- K3+K6 entegrasyon: endpoint'ler app'te kayitli ---

def test_endpointler_app_te_kayitli():
    yollar = {r.path for r in xs.app.routes}
    assert "/olcum" in yollar
    assert "/olcum/rapor" in yollar


def test_olcum_fonksiyonlari_var():
    assert callable(xs._olcum_rate_limit_ok)
    assert callable(xs.ref_ozet)
