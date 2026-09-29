"""Zero-Trust static locks for the public landing page.

The landing is marketing, but it embeds a LIVE audit widget. Marketing copy may
promise; it must never fabricate measurement. These locks keep the honesty
surgery in place: no real third-party brands presented as proven results, no
fabricated audit HUD, no auto-probing a real site on empty input.
"""
import re
from pathlib import Path

import pytest

LANDING = Path(__file__).resolve().parent.parent / "answrank" / "api" / "templates" / "landing.html"
SRC = LANDING.read_text(encoding="utf-8")


def test_no_real_third_party_brand_claims_in_showcases():
    # Before/after showcases must use the fictional Meridyen/Meridian brand.
    for token in ("acibadem", "Acıbadem", "ACIBADEM", "Harley Street Dental", "Beverly Hills Dental", "Charité Dental", "charite.de"):
        assert token.lower() not in SRC.lower(), f"real brand {token!r} reappeared in landing showcase copy"


def test_no_fake_wikidata_citation():
    # Q4674092 is a human protein (ANP32A) — it must never be shown as a brand entity.
    assert "Q4674092" not in SRC


def test_roi_chip_does_not_claim_patent():
    lower = SRC.lower()
    assert "patentli" not in lower and "patented" not in lower, "unverified patent claim on landing"


def test_demo_audit_does_not_default_to_a_real_site():
    # No silent '|| acibadem.com.tr'-style fallback: empty input must be validated, not proxied to a third party.
    assert not re.search(r"value\.trim\(\)\s*\|\|\s*['\"][a-z0-9.-]+\.(com|tr|de|co\.uk)", SRC), \
        "empty-input fallback silently audits a real domain"
    assert 'id="domain-input"' in SRC
    assert 'value="acibadem.com.tr"' not in SRC


def test_hud_binds_real_api_category_keys():
    # The old HUD read cats.crawlers_score etc. — keys that /api/audit never returns.
    assert "cats.crawlers_score" not in SRC and "cats.schema_score" not in SRC
    for key in ("cats.robots", "cats.llms_txt", "cats.schema_jsonld", "cats.meta_architecture"):
        assert key in SRC, f"HUD must read real category key {key}"


def test_hud_zero_score_is_not_swallowed_by_falsy_default():
    assert "overall_score || 72" not in SRC
    assert "lost_revenue_monthly_try || 28000" not in SRC
    assert "|| 16, 18" not in SRC  # fabricated pillar defaults removed


def test_audit_failure_state_is_honest():
    fb = SRC[SRC.index("function renderHudFallback"):SRC.index("function updatePillarBar")]
    assert "overall_score: 78" not in fb, "failure path must not fabricate a passing score"
    assert "DEĞERLENDİRİLEMEDİ" in fb, "failure path must show an explicit could-not-evaluate state"


def test_waf_tile_does_not_claim_clean_without_probe():
    assert "TEMİZ (Erişilebilir)" not in SRC, "static WAF-clean claim without any probe"
    assert "BU DEMODA PROBE EDİLMEDİ" in SRC


def test_showcase_disclaimers_present():
    # 1 static element + 4 i18n dictionaries (TR, EN, EN-US, DE)
    assert SRC.count("comp_disclaimer") >= 5, "before/after showcase lost its illustrative-sample disclaimer"
    assert "Temsili örnektir" in SRC or "Temsilî örnektir" in SRC


def test_landing_escapes_server_text_in_innerhtml():
    assert "function esc(" in SRC
    m = re.search(r"KİLİTLİ.*?\n", SRC)
    assert m is None or "${esc(data.brand_name" in SRC, "territory modal must escape DB-provided brand name"


def test_landing_hud_default_state_is_unmeasured():
    """16 Eyl derin-tarama C4: the pre-scan HUD must not fake a finished audit.
    Static defaults are placeholders; the only verdict-bearing tile (Madde 7)
    became neutral program-info because nothing per-visitor measures it."""
    import re
    from pathlib import Path
    html = Path("answrank/api/templates/landing.html").read_text(encoding="utf-8")
    static_forbidden = [
        "hud_complete",
        "UYGUN (+%15",
        "ELIGIBLE (+15",
        "BERECHTIGT (+15",
        "₺28,000/ay",
    ]
    for token in static_forbidden:
        assert token not in html, f"reappeared in landing: {token!r}"
    assert not re.search(r"id=\"p-(crawlers|llmstxt|schema|headers)\">\d+/", html), \
        "pillar tiles must default to placeholder, not fake ratios"
    assert html.count("hud_idle") >= 4  # TR + EN×2 + DE dictionaries


# ── Madde-7.3 skoru: görünürlük karışıklığı (arXiv:2609.07559) ────────────────
# arXiv:2609.07559 (Bajemon & Rochet, 7 Eyl 2026): sorgu-bağımsız deterministik
# içerik skorlarının atıf sinyaliyle within-query Spearman'ı yalnızca 0.11'dir;
# bu sınıf skorlar "citation predictor" değil "quality filter"tir. Madde-7.3'ün
# ölçtüğü overall_score sorgu-bağımsız bir denetim skorudur; "görünürlük skoru"
# etiketi onu ölçülmüş canlı-atıf görünürlüğü gibi sunar.
MISLEADING_GUARANTEE_LABELS = [
    "360° görünürlük skoru",
    "görünürlük skoru",
    "visibility score",
]


@pytest.mark.parametrize("label", MISLEADING_GUARANTEE_LABELS)
def test_guarantee_score_not_labelled_visibility(label):
    """Sözleşmesel skora yanıltıcı 'görünürlük' etiketi yapışmaz."""
    assert label.lower() not in SRC.lower(), (
        f"yanıltıcı etiket {label!r}: Madde-7.3 sorgu-bağımsız denetim skorunu "
        "ölçülmüş canlı-atıf görünürlüğü gibi sunuyor"
    )


# ── Kanıtsız üstünlük vaadleri (konsantrasyon tavanı + Martinez) ──────────────
# SSRN 7366498: AI cevaplarında ilk-3 marka ortalama en fazla ~%26 SoV (CI %20-32)
# tutuyor — "1 numaralı otorite" satılabilir bir vaat değildir. arXiv:2609.06811
# (Martinez): atıf kaynağın katkısını kanıtlamaz; prompt corpus ölçülen "answer
# market"ı tanımlar. "En yetkin/en iyi" iddiaları kanıtlanmış üstünlük anlamına
# gelir ve desteklenemez.
# Kullanıcı sorgusu alıntıları ("en yetkin ... kim?" şeklinde gerçek soru) hariç
# tutulur; hedeflenen yalnızca AnswRank'in marka adına yaptığı üstünlük vaadidir.
UNPROVEN_SUPREMACY_CLAIMS = [
    "1 numaralı önerilen otoriteye",
    "1 numaralı referans olarak alıntılanma",
    "en yetkin klinik",
    "en yetkin implant cerrahi merkezi",
]


@pytest.mark.parametrize("claim", UNPROVEN_SUPREMACY_CLAIMS)
def test_no_unproven_supremacy_claims(claim):
    """Kanıtlanmamış üstünlük vaadi (1 numara / en yetkin) landing'de yer almaz."""
    assert claim.lower() not in SRC.lower(), (
        f"kanıtsız üstünlük vaadi {claim!r}: AI cevaplarında ilk-3 marka ~%26 SoV "
        "tutar (SSRN 7366498); '1 numaralı' satılabilir bir vaat değildir"
    )
