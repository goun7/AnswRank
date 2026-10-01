"""TEK-MUKELLEF cok-urun aylik vergi raporu testleri.

Gerekce ( 25 Eyl vergi optimizasyonu): tum urunler TEK mukellef altinda
tek banka hesabina; yurt ici/yurt disi ayrami KDV icin korunur.
Mali mustavir-hazir cikti: reports/vergi_raporu_YYYY_AY.md

Isolasyon: TaxLedger(load_persisted=False) — canli DB'ye dokunulmaz;
rapor ciktilari tmp_path'e yazilir ( repo kirletilmez).
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from answrank.finance.tax_ledger import (  # noqa: E402
    TaxLedger,
    TaxRegime,
    UnifiedTaxReport,
)
from answrank.config import settings  # noqa: E402

RATES = {"GBP": 46.0, "USD": 35.8, "TRY": 1.0, "EUR": 38.9}
TAXPAYER = "Unpump Test Sahis Sirketi"


@pytest.fixture
def ledger():
    return TaxLedger(custom_rates=RATES, load_persisted=False)


@pytest.fixture
def mixed_ledger(ledger):
    """3 urun, karisik yurt ici/yurt disi rejim."""
    kayitlar = [
        ledger.record_invoice("Klinik A", "TR", "TRY", 1000,
                              product_name="answrank/audit"),
        ledger.record_invoice("UK Clinic", "GB", "GBP", 50,
                              product_name="cleartag/dogrula"),
        ledger.record_invoice("Dental B", "TR", "TRY", 500,
                              product_name="pqhaven/tara"),
        ledger.record_invoice("US Lab", "US", "USD", 75,
                              product_name="mcpguard/evaluate"),
        ledger.record_invoice("DE GmbH", "DE", "EUR", 40,
                              product_name="answrank/citations"),
    ]
    # DONEM SABITLEME: record_invoice created_at olarak BUGUNU yazar (UTC);
    # generate_monthly_unified_report donemi created_at'e gore filtreler.
    # Testler 2026-09 donemini sorgular (rapor "Eylul" icerigi + dosya adi
    # bunu varsayar) — bu yuzden kayitlari test edilen aya sabitliyoruz.
    # Gercek API davranisi (created_at donem filtresi) OLDUGU GIBI korunur;
    # bu, dosyadaki test_ay_filtresi_* testlerinde kullanilan ayni idiomdur.
    for r in kayitlar:
        r.created_at = "2026-09-15"
    return ledger


def test_tek_mukellef_cok_urun_toplam(mixed_ledger):
    """Her urun ayri satirda, TOPLAM tek mukellef altinda."""
    rep = mixed_ledger.generate_monthly_unified_report(
        2026, 9, taxpayer_name=TAXPAYER, output_dir=None, write_file=False)

    assert isinstance(rep, UnifiedTaxReport)
    assert rep.taxpayer_name == TAXPAYER
    # 4 ayri urun satiri ( answrank 2 farkli urun)
    urunler = {r.product_name for r in rep.product_rows}
    assert urunler == {"answrank/audit", "answrank/citations",
                       "cleartag/dogrula", "pqhaven/tara",
                       "mcpguard/evaluate"}
    assert len(rep.product_rows) == 5
    # fatura sayilari toplami == tum kayitlar
    assert sum(r.invoices_count for r in rep.product_rows) == 5


def test_foreign_toplam_yurt_disi_toplamina_esit(mixed_ledger):
    """Orkestrator sarti: foreign toplam == yurt disi toplami.

    Yurt disi = HIZMET IHRACATI ( GVK 89/13, KDV %0) — bu iki deger
    birebir esit olmali ki mali mustavir ihracat istisnasini dogru
    uygulayabilsin.
    """
    rep = mixed_ledger.generate_monthly_unified_report(
        2026, 9, output_dir=None, write_file=False)

    export_kayit = [r for r in mixed_ledger.records
                    if r.regime == TaxRegime.EXPORT_SERVICE]
    beklenen = round(sum(r.amount_try for r in export_kayit), 2)

    assert rep.yurt_disi_toplam_try == beklenen
    assert rep.foreign_total_try == rep.yurt_disi_toplam_try
    # urun satirlarinin yurt disi kismi da ayni toplami verir
    satir_toplami = round(sum(r.yurt_disi_try for r in rep.product_rows), 2)
    assert satir_toplami == rep.yurt_disi_toplam_try


def test_kdv_sadece_yurt_iceden(mixed_ledger):
    """KDV yalnizca yurt ici gelirden (%20); yurt disi KDV %0."""
    rep = mixed_ledger.generate_monthly_unified_report(
        2026, 9, output_dir=None, write_file=False)

    assert rep.kdv_toplam_try == round(rep.yurtici_toplam_try * 0.20, 2)
    # yurt disi urunlerin KDV'si 0
    disi = [r for r in rep.product_rows if r.yurt_disi_try > 0]
    for r in disi:
        assert r.kdv_try == 0.0 or r.yurtici_try > 0


def test_matrah_ve_muaf_gelir(mixed_ledger):
    """GVK 89/13: yurt disi muaf, yurt ici matraha tam girer."""
    rep = mixed_ledger.generate_monthly_unified_report(
        2026, 9, output_dir=None, write_file=False)

    assert rep.muaf_gelir_try <= rep.yurt_disi_toplam_try
    # matrah yurt ici ile esit ( ihracat muaf)
    assert rep.matrah_toplam_try == rep.yurtici_toplam_try
    assert rep.brut_gelir_try == round(
        rep.yurtici_toplam_try + rep.yurt_disi_toplam_try, 2)


def test_rapor_markdown_dosyasi_yazilir(mixed_ledger, tmp_path):
    """reports/vergi_raporu_YYYY_AY.md mali-musavir formatta yazilir."""
    out = tmp_path / "reports"
    rep = mixed_ledger.generate_monthly_unified_report(
        2026, 9, taxpayer_name=TAXPAYER, output_dir=str(out))

    assert rep.rapor_yolu is not None
    assert os.path.basename(rep.rapor_yolu) == "vergi_raporu_2026-09.md"
    assert os.path.exists(rep.rapor_yolu)
    icerik = open(rep.rapor_yolu, encoding="utf-8").read()
    # mali musavir gerekli alanlar
    assert "VERGI RAPORU" in icerik
    assert "TEK MUKELLEF" in icerik
    assert TAXPAYER in icerik
    assert "HIZMET IHRACATI" in icerik          # GVK 89/13 isareti
    assert "GVK 89/13" in icerik
    assert "302" in icerik                      # KDV istisna kodu
    assert "Eylul" in icerik                    # ay adi
    # KDV kodlu: yurt ici %20, yurt disi %0
    assert "%20 KDV" in icerik
    assert "KDV %0" in icerik
    # her urun tabloda
    for urun in ["answrank/audit", "mcpguard/evaluate", "pqhaven/tara"]:
        assert urun in icerik


def test_ay_filtresi_aylar_karismaz(ledger, tmp_path):
    """Sadece istenen ayin faturalari rapora girer."""
    r1 = ledger.record_invoice("TR A", "TR", "TRY", 100,
                               product_name="answrank/audit")  # bu ay ( bugun)
    r2 = ledger.record_invoice("TR B", "TR", "TRY", 200,
                               product_name="answrank/audit")  # bu ay
    # bir kaydi gecmisme tasi ( created_at manuel)
    r2.created_at = "2026-08-15"

    rep = ledger.generate_monthly_unified_report(
        2026, 8, output_dir=str(tmp_path), write_file=False)
    # gecmis ayda 1 fatura
    assert sum(r.invoices_count for r in rep.product_rows) == 1
    assert rep.product_rows[0].yurtici_try == 200.0

    rep_bu_ay = ledger.generate_monthly_unified_report(
        2026, 9, output_dir=str(tmp_path), write_file=False)
    # bu ay ( bugunun yili-ayi) — created_at bugun; r1
    bugun_ay = int(r1.created_at[5:7])
    if bugun_ay == 9:
        assert sum(r.invoices_count for r in rep_bu_ay.product_rows) == 1
        assert rep_bu_ay.product_rows[0].yurtici_try == 100.0


def test_bos_donem_bos_rapor(ledger, tmp_path):
    """Ilgili ayda fatura yoksa bos rapor ( dosya YAZILMAZ)."""
    rep = ledger.generate_monthly_unified_report(
        2025, 1, output_dir=str(tmp_path))
    assert rep.product_rows == []
    assert rep.rapor_yolu is None
    assert rep.yurt_disi_toplam_try == 0.0


def test_yurt_disi_rejim_korunuyor_kritik(ledger):
    """Orkestrator: yurt ici/yurt disi ayrami KRITIK — korunmali."""
    r1 = ledger.record_invoice("TR X", "TR", "TRY", 1000,
                               product_name="answrank/audit")
    r2 = ledger.record_invoice("UK Y", "GB", "GBP", 100,
                               product_name="answrank/audit")
    # DONEM SABITLEME: record_invoice BUGUNU (UTC) yazar; test 2026-09
    # donemini sorgular — kayitlari o aya sabitliyoruz (API davranisi ayni).
    r1.created_at = "2026-09-15"
    r2.created_at = "2026-09-15"
    rep = ledger.generate_monthly_unified_report(
        2026, 9, output_dir=None, write_file=False)
    row = rep.product_rows[0]
    # AYNI urun icinde bile ici/disir ayri
    assert row.yurtici_try == 1000.0
    assert row.yurt_disi_try == 4600.0  # 100 GBP * 46
    assert row.kdv_try == 200.0          # %20 sadece icinden
