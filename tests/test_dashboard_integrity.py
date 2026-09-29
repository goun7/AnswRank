"""Zero-Trust frontend integrity lock for the operator dashboard.

The dashboard is an audit product: a fabricated "all-clear" value or a JS binding
that silently falls back to a made-up default is the single worst class of defect
it can have. These tests lock the two properties we fixed by hand-audit:

  1. No hardcoded/fabricated result values live in the template any more.
  2. Every client-side binding reads a field name the backend actually returns
     (a mismatch degrades silently to the fabricated default -> false security).
"""
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parents[1] / "answrank" / "api" / "templates" / "dashboard.html"


@pytest.fixture(scope="module")
def html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


# ── 1. Fabricated result literals must never return ───────────────────────────

@pytest.mark.parametrize("token", [
    "acibadem.com.tr",        # fake default domain
    "ELITE_CITABLE",          # tier that is not in the deep_tier enum
    "PASS (Temiz)",           # fake WAF verdict
    "LOW (Risk Yok)",         # fake adversarial risk
    "QID VERIFIED",           # fake grounding claim
    "32,000/ay",              # fabricated monthly revenue-loss figure
    "ONLINE (480ms)",         # fabricated provider latency pill
    "ONLINE (620ms)",         # fabricated provider latency pill
    "5 AJAN DEVREDE",         # static status claim
    "AUTONOMOUS LEAD HARVESTER",  # implies live discovery that does not exist
    "Princeton KDD",          # unverifiable authority badge
])
def test_no_fabricated_literals(html, token):
    assert token not in html, f"fabricated value {token!r} reappeared in dashboard"


def test_no_fabricated_numeric_fallbacks(html):
    # These `|| <magic>` fallbacks made missing data render as green all-clear.
    for bad in ("|| 82", "|| 28000", "|| 32000", "|| 16", "|| 15", "|| 14", "|| 13",
                "|| '2027-09-14'", "'2027-09-14'", "intent_clarity_percentage"):
        assert bad not in html, f"fabricated fallback {bad!r} reappeared"


# ── 2. Bindings must use the REAL backend field names ─────────────────────────

FAKE_JSON_KEYS = [
    "waf_status", "adversarial_scan", "crawlers_score", "llms_txt_score",
    "schema_score", "headers_score", "brand_safety_flag", "polarity_label",
    "direct_quotes", "transaction_id", "original_currency", "converted_try",
    "exempt_base_try", "foreign_amount", "expires_at",
]


@pytest.mark.parametrize("key", FAKE_JSON_KEYS)
def test_frontend_does_not_read_nonexistent_keys(html, key):
    assert key not in html, f"dashboard binds non-existent backend key {key!r}"


REQUIRED_BINDINGS = [
    # deep audit (DeepAuditResult)
    "data.waf_probe", "data.adversarial", "data.entity_grounding",
    "data.composite_deep_score", "data.deep_tier",
    "cats.robots", "cats.llms_txt", "cats.schema_jsonld",
    "cats.meta_architecture",
    "UNVERIFIED",  # unreachable-WAF must render as no-verdict, not "TEMİZ"
    "wikidata_probe_status",  # unreachable-QID must render as SORGULANAMADI, not "❌ Bulunamadı"
    "qid_confidence",  # P856 confidence ladder must drive the wiki probe line
    "REDDEDİLDİ (resmî site çelişkisi)",  # rejected QID may never render as DOĞRULANDI
    "dp-probe-cite",  # SoV cell exists
    "ÖLÇÜLMEDİ",  # null citation run renders honest no-data, never 0%
    # sentiment (SentimentAnalysisResult)
    "data.sentiment_score", "data.is_brand_safe", "data.polarity",
    "data.detected_flags", "data.context_snippet",
    # fiscal (FiscalInvoiceRecord)
    "r.invoice_id", "r.client_brand", "r.amount_try", "r.exempt_income_try",
    "r.fx_source",
    # territory (TerritoryLock)
    "l.created_at", "l.tier",
    # telemetry (ProviderTelemetry)
    "p.avg_latency_ms", "p.has_api_key", "p.is_live_enabled",
]


@pytest.mark.parametrize("binding", REQUIRED_BINDINGS)
def test_frontend_binds_real_fields(html, binding):
    assert binding in html, f"expected real binding {binding!r} missing from dashboard"


# ── 3. Safety & honest-rendering helpers must be present and used ─────────────

def test_html_escape_helper_present_and_used(html):
    assert "function esc(" in html, "esc() sanitizer was removed"
    # every user/model-controlled row renderer must call it
    assert html.count("esc(") >= 25, "esc() is barely used; likely XSS regression"


def test_no_unescaped_scout_autonomous_claim(html):
    # The scout card must be honestly labeled as a curated demo pool.
    assert "KÜRATÖRLÜ DEMO HEDEF HAVUZU" in html


def test_telemetry_matrix_is_dynamic(html):
    # The two static provider rows were replaced with a JS-populated container.
    assert 'id="tel-provider-rows"' in html


def test_error_boxes_exist_for_failure_paths(html):
    # Deep audit + sentiment must have dedicated error containers (no green leak).
    assert 'id="da-error-box"' in html
    assert 'id="sent-error"' in html


def test_success_alert_not_fired_on_failure(html):
    # The old catch blocks alerted "... tamamlandı." on error. Ensure the
    # sentiment/seed catch blocks now say "başarısız"/"hata" not "tamamlandı".
    import re
    for m in re.finditer(r"catch\s*\([^)]*\)\s*\{", html):
        block = html[m.end():m.end() + 220]
        assert "tamamlandı" not in block, "success toast found inside a catch block"


# ── 3. The composite score must not be labelled a visibility predictor ───────
# arXiv:2609.07559 (Bajemon & Rochet, 7 Eyl 2026): sorgu-bağımsız deterministik
# içerik skorlarının atıf sinyaliyle within-query Spearman'ı 0.11'dir; bu
# skorlar "citation predictor" değil "quality filter" olarak konumlanmalıdır.
# "360° görünürlük skoru" etiketi, ölçülmüş canlı-atıf görünürlüğü yerine
# sorgu-bağımsız denetim skorunu sözleşmesel garantiye konu edinir.

MISLEADING_SCORE_LABELS = [
    "360° görünürlük skoru",
    "görünürlük skoru",
    "visibility score",
]


@pytest.mark.parametrize("label", MISLEADING_SCORE_LABELS)
def test_composite_score_not_labelled_visibility(html, label):
    """Denetim/görünürlük karışıklığı: sözleşmesel skora yanıltıcı etiket yapışmaz."""
    assert label.lower() not in html.lower(), (
        f"yanıltıcı etiket {label!r} deterministik denetim skorunu ölçülmüş "
        "görünürlükmüş gibi sunuyor"
    )
