import pytest
from unittest.mock import AsyncMock, patch
from answrank.audit.engine import AuditEngine
from answrank.audit.crawler import CrawlData
from answrank.models import DeepAuditResult

RICH_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>
  <title>Yılmaz Diş Kliniği - Kadıköy İmplant</title>
  <meta name="description" content="Kadıköy bölgesinde dijital cerrahi implant ve estetik zirkonyum hizmetleri.">
  <link rel="canonical" href="https://yilmazdental.com">
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "Dentist",
    "name": "Yılmaz Diş Kliniği",
    "telephone": "+902161234567",
    "priceRange": "$$"
  }
  </script>
</head>
<body>
  <h1>Kadıköy İmplant Tedavisi</h1>
  <h2>İmplant Fiyatları</h2>
  <p>Yılmaz Diş Kliniği olarak 15 yıldır 10.000 başarılı implant operasyonu gerçekleştirdik.</p>
  <p>İstanbul bölgesinde implant tedavisi için uzman hekim kadromuzla hizmet vermekteyiz.</p>
  <p>Dr. Yılmaz belirtmektedir: "Kliniğimizde %98 başarı oranıyla 3.500 vaka tamamlanmıştır."</p>
</body>
</html>
"""

def _mock_crawl():
    return CrawlData(
        url="https://yilmazdental.com",
        domain="yilmazdental.com",
        html_content=RICH_HTML,
        status_code=200,
        headers={"content-type": "text/html"},
        robots_txt="User-agent: *\nAllow: /",
        llms_txt="# Yılmaz Diş Kliniği\n> Kadıköy implant merkezi.",
        llms_full_txt=None,
        is_https=True,
    )


@pytest.mark.anyio
async def test_audit_url_deep():
    engine = AuditEngine()
    mock_crawl = _mock_crawl()

    with patch.object(engine.crawler, "fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_crawl
        res = await engine.audit_url_deep(
            url="https://yilmazdental.com",
            sector="dental",
            brand_name="Yılmaz Diş",
            probe_waf=False,
            check_grounding=False,
        )

        assert isinstance(res, DeepAuditResult)
        assert res.base_audit.overall_score > 40
        assert res.composite_deep_score > 30
        assert res.deep_tier in ("ENTERPRISE_READY", "STABLE", "RISK_EXPOSED")
        assert res.adversarial is not None
        assert res.adversarial.get("is_clean") is True


@pytest.mark.anyio
async def test_deep_audit_rag_score_field_regression():
    """REGRESSION (denetim bulgusu A.1): The deep-audit result and key findings must
    read the REAL field name `rag_retrieval_score` — not the fabricated
    `overall_rag_citability_score` that always rendered 0% on screen."""
    engine = AuditEngine()

    with patch.object(engine.crawler, "fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _mock_crawl()
        res = await engine.audit_url_deep(
            url="https://yilmazdental.com",
            sector="dental",
            brand_name="Yılmaz Diş",
            probe_waf=False,
            check_grounding=False,
        )

    assert res.rag_analysis is not None
    # The real field must exist and be a plausible 0-100 score
    real_score = res.rag_analysis.get("rag_retrieval_score")
    assert real_score is not None
    assert 0.0 <= real_score <= 100.0
    # Key findings must quote the real score, not zero by default
    findings_text = " ".join(res.key_findings)
    if res.rag_analysis.get("total_chunks_extracted", 0) > 0:
        assert f"%{real_score:.0f}" in findings_text


@pytest.mark.anyio
async def test_deep_audit_composite_includes_rag():
    """RAG readiness must be a first-class component of the composite deep score
    (previously it was computed but silently ignored in the weighted sum)."""
    engine = AuditEngine()

    with patch.object(engine.crawler, "fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _mock_crawl()
        res = await engine.audit_url_deep(
            url="https://yilmazdental.com",
            sector="dental",
            brand_name="Yılmaz Diş",
            probe_waf=False,
            check_grounding=False,
            check_rag=True,
        )

    # 16 Eyl C9 policy: EXECUTED dims only (base 45 + adv 10 + RAG 20 here),
    # renormalized to 100 — disabled dims earn nothing and never inflate.
    assert res.rag_analysis is not None
    rag_score = res.rag_analysis.get("rag_retrieval_score", 0)

    earned = res.base_audit.overall_score * 0.45 + 20.0 * (rag_score / 100.0)
    possible = 45.0 + 20.0
    if res.adversarial:
        earned += max(0.0, 10.0 * (1.0 - (res.adversarial.get("risk_score", 0) / 100.0)))
        possible += 10.0
    expected = round(100.0 * earned / possible, 1)
    assert res.composite_deep_score == pytest.approx(expected, abs=0.15)
    # un-run dims are declared, never silently full-marked
    assert any("renormalize" in f for f in res.key_findings)
