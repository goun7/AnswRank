"""answrank.crm.outreach dal-kesen testleri (LEED) — 6 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — ag/LLM YOK, sadece sablon-fonksiyonlari.
OutreachGenerator._agency_pitch + _variant_1 + _variant_2 + _variant_3
+ _followup_day3 + _followup_day7.
"""
from types import SimpleNamespace

import pytest

from answrank.citations.runner import MODELS
from answrank.crm.outreach import OutreachGenerator
from answrank.models import AuditResult, CitationRunResult


def _audit(**kw):
    """ORTAM-OGRENDI: AuditResult.categories 8 zorunlu alt-model ister; outreach
    fonksiyonlari yalniz getattr erisimi yaptigi icin model_construct (validation
    atlanir) + SimpleNamespace categories ile saf-in-memory kurulur."""
    base = dict(audit_id="AUD-1", url="https://a.example", domain="a.example",
                sector="dental", overall_score=73, score_band="orta",
                categories=None, lost_revenue_estimate_monthly_try=None)
    base.update(kw)
    return AuditResult.model_construct(**base)


def _citation(**kw):
    base = dict(run_id="R1", brand_name="Marka", domain="a.example", sector="dental",
                city="İstanbul", total_runs=10, brand_citations_found=3,
                citation_rate_percentage=30.0, live_items_count=10,
                is_fully_live=True, top_competitors={"Rakip": 5})
    base.update(kw)
    return CitationRunResult(**base)


G = OutreachGenerator()


# == _agency_pitch ==========================================================================

def test_agency_pitch_temel():
    t = G._agency_pitch(_audit(), "AjansX", "İstanbul", "diş kliniği")
    assert "Sayın Ajans Yetkilisi" in t
    assert "AjansX" in t
    assert "diş kliniği" in t


def test_agency_pitch_sektor_kelimesi_gecer():
    t = G._agency_pitch(_audit(), "A", "B", "estetik merkezi")
    assert "estetik merkezi" in t


def test_agency_pitch_sektor_tire():
    """ORTAM-OGRENDI: 'diş kliniği'.replace(' ','-') TR karakterleri KORUR
    -> 'diş-klinigi' (unicode normalize YOK — Kural-5)."""
    t = G._agency_pitch(_audit(), "A", "B", "diş kliniği")
    assert "musteri-ornek-diş-kliniği.example" in t


def test_agency_pitch_city_yoksa_bolgenizde():
    """ORTAM-OGRENDI: _agency_pitch city'yi 'location' parametresinden DEGIL
    getattr(audit,'city',None)'den okur — AuditResult'ta city ALANI YOK
    -> hep 'bölgenizde' yazi gorunur (production quirk — Kural-5)."""
    t = G._agency_pitch(_audit(), "A", None, "işletme")
    assert "bölgenizde" in t


def test_agency_pitch_location_parametresi_kullanilmaz():
    """ORTAM-OGRENDI: 3. arguman (location) sektor metninde KULLANILMAZ —
    city yalniz audit'ten gelir."""
    t = G._agency_pitch(_audit(), "A", "Ankara", "işletme")
    assert "Ankara" not in t
    assert "bölgenizde" in t


def test_agency_pitch_beyaz_etiket_vurgusu():
    t = G._agency_pitch(_audit(), "A", "B", "işletme")
    assert "beyaz etiket" in t.lower()
    assert "kendi logonuzla" in t
    assert "kendi sözleşmenizle" in t


def test_agency_pitch_answrank_motoru_arkada():
    t = G._agency_pitch(_audit(), "A", "B", "işletme")
    assert "AnswRank" in t
    assert "arka planda" in t


def test_agency_pitch_madde7_garanti():
    t = G._agency_pitch(_audit(), "A", "B", "işletme")
    assert "Madde-7" in t


def test_agency_pitch_kitlik_kurali():
    t = G._agency_pitch(_audit(), "A", "B", "işletme")
    assert "tek müşteri" in t
    assert "reddedilir" in t


def test_agency_pitch_miniprobe_reklami():
    t = G._agency_pitch(_audit(), "A", "B", "işletme")
    assert "/api/miniprobe" in t
    assert "ücretsiz" in t


def test_agency_pitch_ornek_domain_example():
    """ORTAM: ornek musteri .example — gercek marka kullanilmaz;
    TR karakterler replace sonrasi korunur ('müşavir')."""
    t = G._agency_pitch(_audit(), "A", "B", "mali müşavir")
    assert "musteri-ornek-mali-müşavir.example" in t


def test_agency_pitch_unicode_tr_korunur():
    t = G._agency_pitch(_audit(), "Ajansİstanbul", "İzmir", "estetik merkezi")
    assert "Ajansİstanbul" in t
    assert "estetik merkezi" in t


def test_agency_pitch_duz_metin_cok_satirli():
    t = G._agency_pitch(_audit(), "A", "B", "işletme")
    assert t.count("\n\n") >= 3


# == _variant_1 =============================================================================

def test_variant_1_citationsiz_olcum_yok_mesaji():
    t = G._variant_1(_audit(), "Marka", "Ahmet", "İstanbul", "diş kliniği", None)
    assert "henüz ölçülmedi" in t
    assert "ilk ölçümü biz yapalım" in t
    assert "Marka" in t and "Ahmet" in t and "İstanbul" in t


def test_variant_1_citationsiz_motor_listesi():
    t = G._variant_1(_audit(), "M", "A", "İ", "işletme", None)
    for m in MODELS[:2]:
        assert m.split("-")[0] in t


def test_variant_1_citation_tam_canli():
    t = G._variant_1(_audit(), "M", "A", "İ", "işletme", _citation())
    assert "10 soru×motor" in t
    assert "%30" in t
    assert "(10/10 koşu canlı API ölçümü.)" in t


def test_variant_1_citation_kismi_canli():
    c = _citation(live_items_count=4, total_runs=10, is_fully_live=False)
    t = G._variant_1(_audit(), "M", "A", "İ", "işletme", c)
    assert "(4/10 koşu gerçek API ölçümü.)" in t


def test_variant_1_citation_saf_simulasyon():
    c = _citation(live_items_count=0, is_fully_live=False)
    t = G._variant_1(_audit(), "M", "A", "İ", "işletme", c)
    assert "deterministik simülasyon" in t


def test_variant_1_rakip_clause():
    t = G._variant_1(_audit(), "M", "A", "İ", "işletme", _citation())
    assert "Rakip" in t
    assert "5 tanesinde" in t
    assert "3 yanıtta geçti" in t


def test_variant_1_rakip_yoksa_clause_yok():
    c = _citation(top_competitors={})
    t = G._variant_1(_audit(), "M", "A", "İ", "işletme", c)
    assert "öne çıktı" not in t
    assert "10 soru×motor" in t


def test_variant_1_total_runs_sifir_olcum_yok():
    """ORTAM: citation.total_runs falsy -> 'henüz ölçülmedi' dali."""
    c = _citation(total_runs=0)
    t = G._variant_1(_audit(), "M", "A", "İ", "işletme", c)
    assert "henüz ölçülmedi" in t


def test_variant_1_motor_ilk_tokenler():
    t = G._variant_1(_audit(), "M", "A", "İ", "işletme", _citation())
    for m in MODELS:
        assert m.split("-")[0] in t


def test_variant_1_bitis_sorusu():
    t = G._variant_1(_audit(), "M", "A", "İ", "işletme", None)
    assert t.rstrip().endswith("ücretsiz iletmemi ister misiniz?")


def test_variant_1_findings_clause_gomulu():
    """ORTAM: _audit_findings_clause cikti 'Teknik taraf:' sonrasi gelir."""
    t = G._variant_1(_audit(), "M", "A", "İ", "işletme", None)
    assert "Teknik taraf:" in t


def test_variant_1_categories_ile_findings():
    cats = SimpleNamespace(robots=SimpleNamespace(exists=False),
                           llms_txt=SimpleNamespace(has_llms_txt=False))
    t = G._variant_1(_audit(categories=cats), "M", "A", "İ", "işletme", None)
    assert "robots.txt hiç yok" in t
    assert "llms.txt / AI-erişim dosyaları yok" in t


# == _variant_2 =============================================================================

def test_variant_2_ciro_var():
    a = _audit(lost_revenue_estimate_monthly_try=12500)
    t = G._variant_2(a, "M", "A", "İ", "diş kliniği", None)
    assert "12,500 TL" in t
    assert "model kestirimidir, ölçüm değil" in t


@pytest.mark.parametrize("lost", [0, None])
def test_variant_2_ciro_yoksa_dürüst_metin(lost):
    a = _audit(lost_revenue_estimate_monthly_try=lost)
    t = G._variant_2(a, "M", "A", "İ", "diş kliniği", None)
    assert "sağlam bir model girdisi bulunamadı" in t
    assert "TL olarak hesaplanmadı" in t or "rakam paylaşmıyoruz" in t


def test_variant_2_citation_yok_mesaj():
    t = G._variant_2(_audit(), "M", "A", "İ", "işletme", None)
    assert "Alıntı görünürlüğü henüz ölçülmedi" in t


def test_variant_2_citation_simulasyon():
    c = _citation(is_fully_live=False, citation_rate_percentage=42.0)
    t = G._variant_2(_audit(), "M", "A", "İ", "işletme", c)
    assert "%42" in t
    assert "simülasyon karışıklı" in t


def test_variant_2_citation_canli():
    c = _citation(is_fully_live=True, citation_rate_percentage=55.5)
    t = G._variant_2(_audit(), "M", "A", "İ", "işletme", c)
    assert "%55.5" in t
    assert "(canlı API)" in t


@pytest.mark.parametrize("rate", [0.0, 12.5, 100.0])
def test_variant_2_rate_formati(rate):
    c = _citation(is_fully_live=True, citation_rate_percentage=rate)
    t = G._variant_2(_audit(), "M", "A", "İ", "işletme", c)
    assert f"%{rate:g}" in t


def test_variant_2_düzeltme_recetesi():
    t = G._variant_2(_audit(), "M", "A", "İ", "işletme", None)
    assert "Düzeltme reçetemiz hazır" in t
    assert "2-4 haftada" in t


def test_variant_2_gorusme_cagrisi():
    t = G._variant_2(_audit(), "M", "A", "İ", "işletme", None)
    assert "15 dakikalık" in t
    assert "Hangi gün müsaitsiniz?" in t


def test_variant_2_unicode_tr():
    t = G._variant_2(_audit(), "MarkaİĞ", "İrem", "İzmir", "estetik merkezi", None)
    assert "MarkaİĞ" in t and "İrem" in t and "İzmir" in t


# == _variant_3 =============================================================================

def test_variant_3_temel():
    t = G._variant_3(_audit(), "M", "A", None)
    assert "Merhaba A" in t
    assert "M için denetimimiz tamamlandı" in t
    assert "Mevcut teknik denetim skorunuz: 73/100." in t


@pytest.mark.parametrize("score", [0, 25, 73, 99, 100])
def test_variant_3_skor(score):
    t = G._variant_3(_audit(overall_score=score), "M", "A", None)
    assert f"skorunuz: {score}/100." in t


def test_variant_3_citation_yok_vaka_uydurma_yok():
    t = G._variant_3(_audit(), "M", "A", None)
    assert "Vaka rakamı uydurmuyoruz" in t


def test_variant_3_citation_var_olcum_kanit():
    t = G._variant_3(_audit(), "M", "A", _citation())
    assert "Alıntı testiniz de ölçüldü" in t
    assert "çıtayı birlikte koymadan" in t


def test_variant_3_rapor_teklifi():
    t = G._variant_3(_audit(), "M", "A", None)
    assert "10 dakikalık" in t
    assert "raporu göndereyim mi?" in t


# == _followup_day_3 ========================================================================

def test_followup_day3_temel():
    t = G._followup_day3("M", "A", "İstanbul", "RakipX")
    assert "Merhaba A" in t
    assert "M için hazırladığım" in t
    assert "İstanbul" in t


def test_followup_day3_rakip_var():
    t = G._followup_day3("M", "A", "İ", "RakipX")
    assert "Rakibiniz RakipX öndeyse" in t


@pytest.mark.parametrize("comp", [None, ""])
def test_followup_day3_rakip_yok_cumle_yok(comp):
    t = G._followup_day3("M", "A", "İ", comp)
    assert "öndeyse" not in t


def test_followup_day3_kitlik_lider_kontenjani():
    t = G._followup_day3("M", "A", "İ", None)
    assert "lider kontenjanı" in t
    assert "tek işletmeyle çalışıyoruz" in t


def test_followup_day3_inceleme_cagrisi():
    t = G._followup_day3("M", "A", "İ", None)
    assert "10 dakikalık bir inceleme" in t


def test_followup_day3_unicode():
    t = G._followup_day3("Markaİ", "İrem", "İzmir", "Rakipİ")
    assert "Markaİ" in t and "İrem" in t and "İzmir" in t and "Rakipİ" in t


# == _followup_day_7 ========================================================================

def test_followup_day7_temel():
    t = G._followup_day7("A", _audit())
    assert "A merhaba" in t
    assert "yoğunluğunuzu anlıyorum" in t


def test_followup_day7_audit_id_gecer():
    t = G._followup_day7("A", _audit(audit_id="AUD-42"))
    assert "(AUD-42)" in t


@pytest.mark.parametrize("aid", ["AUD-1", "x", "AUD-999"])
def test_followup_day7_audit_id_param(aid):
    t = G._followup_day7("A", _audit(audit_id=aid))
    assert f"({aid})" in t


def test_followup_day7_tek_mesaj_yeterli():
    t = G._followup_day7("A", _audit())
    assert "tek mesaj yeterli" in t


def test_followup_day7_olumlu_kapanis():
    t = G._followup_day7("A", _audit())
    assert "Sağlıklı ve bereketli" in t


def test_followup_day7_unicode_isim():
    t = G._followup_day7("İrem", _audit())
    assert t.startswith("İrem merhaba")


# == generate_all_variants entegrasyon ======================================================

def test_generate_all_variants_6_anahtar():
    out = G.generate_all_variants(_audit())
    assert set(out) == {"agency_pitch", "variant_1_pain_numbers",
                        "variant_2_lost_revenue", "variant_3_case_study",
                        "followup_day_3", "followup_day_7"}


def test_generate_all_variants_hepsi_dolu_string():
    out = G.generate_all_variants(_audit())
    assert all(isinstance(v, str) and v.strip() for v in out.values())


def test_generate_all_variants_citation_gecirme():
    out = G.generate_all_variants(_audit(), citation=_citation())
    assert "10 soru×motor" in out["variant_1_pain_numbers"]
    assert "Alıntı testiniz de ölçüldü" in out["variant_3_case_study"]
