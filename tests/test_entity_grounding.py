"""Tests for Knowledge Graph & Wikidata Entity Grounding Engine."""

import pytest
from answrank.audit.entity_grounding import EntityGroundingEngine, GroundingTier, EntityGroundingResult


@pytest.mark.anyio
async def test_entity_grounding_offline_evaluation(monkeypatch):
    """Test grounding scoring with mock Wikidata result and schema HTML."""
    async def mock_wiki_search(brand, timeout_sec=5.0, language="en", uselang=None):
        return {
            "qid": "Q12345678",
            "label": "Acıbadem Sağlık Grubu",
            "description": "Türkiye merkezli özel sağlık grubu",
            "url": "https://www.wikidata.org/wiki/Q12345678",
        }

    async def mock_p856_match(qid, timeout_sec=5.0):
        assert qid == "Q12345678"
        return {"status": "ok", "urls": ["https://www.acibadem.com/"]}

    monkeypatch.setattr(EntityGroundingEngine, "probe_wikidata", mock_wiki_search)
    monkeypatch.setattr(EntityGroundingEngine, "probe_official_websites", mock_p856_match)

    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {"@type": "MedicalClinic", "name": "Acıbadem", "sameAs": ["https://maps.google.com/?cid=9999", "https://linkedin.com/company/acibadem"]}
        </script>
      </head>
      <body><p>Sağlık hizmetleri</p></body>
    </html>
    """

    res: EntityGroundingResult = await EntityGroundingEngine.evaluate_grounding("Acıbadem", "acibadem.com", html_content=html)
    assert res.has_wikidata is True
    assert res.wikidata_qid == "Q12345678"
    assert res.has_google_maps_cid is True
    assert res.has_linkedin_entity is True
    assert res.tier == GroundingTier.GROUNDED_AUTHORITY
    assert res.grounding_score >= 80.0


@pytest.mark.anyio
async def test_entity_grounding_ungrounded(monkeypatch):
    """Test ungrounded entity evaluation."""
    async def mock_empty_wiki(brand, timeout_sec=5.0, language="en", uselang=None):
        return {"qid": None, "label": None, "description": None, "url": None}

    monkeypatch.setattr(EntityGroundingEngine, "probe_wikidata", mock_empty_wiki)

    res: EntityGroundingResult = await EntityGroundingEngine.evaluate_grounding("Bilinmeyen Marka", "bilinmeyen.com", html_content="<html><body>Test</body></html>")
    assert res.has_wikidata is False
    assert res.tier == GroundingTier.UNGROUNDED_STRING
    assert len(res.action_roadmap) >= 2


@pytest.mark.anyio
async def test_probe_wikidata_language_params():
    """The default search language must be English (global), not hardcoded Turkish."""
    import inspect
    sig = inspect.signature(EntityGroundingEngine.probe_wikidata)
    assert sig.parameters["language"].default == "en"
    assert "uselang" in sig.parameters


@pytest.mark.anyio
async def test_probe_wikidata_live_path_with_mocked_api():
    """The real Wikidata HTTP path: mocked 200 response → parsed QID."""
    from unittest.mock import patch

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "search": [
                    {
                        "id": "Q7186",
                        "label": "Acıbadem Healthcare Group",
                        "description": "Turkish healthcare group",
                        "concepturi": "https://www.wikidata.org/wiki/Q7186",
                    }
                ]
            }

    async def fake_get(self, url, params=None, headers=None, **kw):
        assert "wikidata" in url
        assert params["search"] == "Acıbadem"
        assert params["language"] == "en"  # default English search language
        return FakeResp()

    with patch("httpx.AsyncClient.get", new=fake_get):
        res = await EntityGroundingEngine.probe_wikidata("Acıbadem", timeout_sec=5.0)

    assert res["qid"] == "Q7186"
    assert res["label"] == "Acıbadem Healthcare Group"
    assert res["url"] == "https://www.wikidata.org/wiki/Q7186"
    assert res["status"] == "found"


@pytest.mark.anyio
async def test_probe_wikidata_empty_search_returns_none_fields():
    from unittest.mock import patch

    class FakeResp:
        status_code = 200
        def json(self):
            return {"search": []}  # no match

    async def fake_get(self, url, params=None, headers=None, **kw):
        return FakeResp()

    with patch("httpx.AsyncClient.get", new=fake_get):
        res = await EntityGroundingEngine.probe_wikidata("Bilinmeyen", timeout_sec=5.0)

    assert res["qid"] is None
    assert res["label"] is None
    assert res["status"] == "not_found"


@pytest.mark.anyio
async def test_probe_wikidata_network_error_is_unreachable_not_missing():
    """A network error must be labeled 'unreachable' (no verdict) so the audit
    never reports a transient failure as 'the brand has no Wikidata entity'."""
    from unittest.mock import patch

    async def failing_get(self, url, **kw):
        raise ConnectionError("wikidata down")

    with patch("httpx.AsyncClient.get", new=failing_get):
        res = await EntityGroundingEngine.probe_wikidata("X", timeout_sec=1.0)

    assert res["qid"] is None
    assert res["status"] == "unreachable"


@pytest.mark.anyio
async def test_probe_wikidata_non_200_is_unreachable():
    from unittest.mock import patch

    class FakeResp:
        status_code = 503
        def json(self):
            return {}

    async def fake_get(self, url, params=None, headers=None, **kw):
        return FakeResp()

    with patch("httpx.AsyncClient.get", new=fake_get):
        res = await EntityGroundingEngine.probe_wikidata("X", timeout_sec=1.0)
    assert res["status"] == "unreachable"


@pytest.mark.anyio
async def test_evaluate_grounding_unreachable_not_called_missing(monkeypatch):
    async def unreachable(brand, timeout_sec=5.0, language="en", uselang=None):
        return {"qid": None, "label": None, "description": None, "url": None, "status": "unreachable"}

    monkeypatch.setattr(EntityGroundingEngine, "probe_wikidata", unreachable)
    res = await EntityGroundingEngine.evaluate_grounding("X", "x.com", html_content="<html></html>")
    text = " ".join(res.missing_foundations)
    assert "DOĞRULANAMADI" in text            # honest: verdict withheld
    assert "Kimlik yok." not in text           # must NOT accuse of lacking an entity
    assert res.wikidata_probe_status == "unreachable"
    assert res.has_wikidata is False


@pytest.mark.anyio
async def test_evaluate_grounding_not_found_says_missing(monkeypatch):
    async def not_found(brand, timeout_sec=5.0, language="en", uselang=None):
        return {"qid": None, "label": None, "description": None, "url": None, "status": "not_found"}

    monkeypatch.setattr(EntityGroundingEngine, "probe_wikidata", not_found)
    res = await EntityGroundingEngine.evaluate_grounding("Yok", "yok.com", html_content="<html></html>")
    assert res.wikidata_probe_status == "not_found"
    assert any("eksik" in m for m in res.missing_foundations)  # genuine absence reported as such


@pytest.mark.anyio
async def test_probe_wikidata_custom_language_params_passed():
    from unittest.mock import patch

    captured = {}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"search": [{"id": "Q1", "label": "L", "description": "D", "concepturi": "u"}]}

    async def fake_get(self, url, params=None, headers=None, **kw):
        captured.update(params)
        return FakeResp()

    with patch("httpx.AsyncClient.get", new=fake_get):
        await EntityGroundingEngine.probe_wikidata("Brand", timeout_sec=5.0, language="de", uselang="de")

    assert captured["language"] == "de"
    assert captured["uselang"] == "de"


# ---------- P856 official-site cross-verification (wrong-QID credit guard) ----------

def _patch_probes(monkeypatch, search, claims):
    async def s(*a, **k):
        return search
    async def c(qid, timeout_sec=5.0):
        return claims
    monkeypatch.setattr(EntityGroundingEngine, "probe_wikidata", s)
    monkeypatch.setattr(EntityGroundingEngine, "probe_official_websites", c)


@pytest.mark.anyio
async def test_p856_match_grants_full_verified_credit(monkeypatch):
    _patch_probes(monkeypatch,
                  {"qid": "Q312", "label": "Apple", "description": "d", "url": "u", "status": "found"},
                  {"status": "ok", "urls": ["https://apple.com/at/", "https://www.apple.com/"]})
    res = await EntityGroundingEngine.evaluate_grounding("Apple Inc", "apple.com", html_content="<html></html>")
    assert res.p856_verified is True
    assert res.qid_confidence == "verified"
    assert any("P856" in sig and "TEYİTLİ" in sig for sig in res.grounding_signals)


@pytest.mark.anyio
async def test_p856_conflict_rejects_credit_entirely(monkeypatch):
    _patch_probes(monkeypatch,
                  {"qid": "Q777", "label": "Example", "description": "protein", "url": "u", "status": "found"},
                  {"status": "ok", "urls": ["https://unrelated-corp.org/"]})
    res = await EntityGroundingEngine.evaluate_grounding("Example", "example.com", html_content="<html></html>")
    assert res.p856_verified is False
    assert res.qid_confidence == "rejected"
    assert res.grounding_score == 0.0
    assert any("REDDEDİLDİ" in m for m in res.missing_foundations)
    assert not any("TEYİTLİ" in sig for sig in res.grounding_signals)


@pytest.mark.anyio
async def test_no_p856_exact_label_partial_credit(monkeypatch):
    _patch_probes(monkeypatch,
                  {"qid": "Q555", "label": "Meridyen Klinik", "description": None, "url": "u", "status": "found"},
                  {"status": "ok", "urls": []})
    res = await EntityGroundingEngine.evaluate_grounding("Meridyen Klinik", "meridyen-klinik.example", html_content="<html></html>")
    assert res.qid_confidence == "exact_name_no_conflict"
    assert res.p856_verified is None
    assert res.grounding_score == 35.0


@pytest.mark.anyio
async def test_no_p856_fuzzy_label_low_caution_credit(monkeypatch):
    _patch_probes(monkeypatch,
                  {"qid": "Q556", "label": "Meronia", "description": None, "url": "u", "status": "found"},
                  {"status": "ok", "urls": []})
    res = await EntityGroundingEngine.evaluate_grounding("Meridyen Klinik", "meridyen-klinik.example", html_content="<html></html>")
    assert res.qid_confidence == "unverified"
    assert res.grounding_score == 15.0
    assert any("yanlış-varlık riski" in sig for sig in res.grounding_signals)


@pytest.mark.anyio
async def test_p856_fetch_unreachable_withholds_verdict(monkeypatch):
    _patch_probes(monkeypatch,
                  {"qid": "Q557", "label": "Meridyen Klinik", "description": "x", "url": "u", "status": "found"},
                  {"status": "unreachable", "urls": []})
    res = await EntityGroundingEngine.evaluate_grounding("Meridyen Klinik", "meridyen-klinik.example", html_content="<html></html>")
    assert res.qid_confidence == "unverified"
    assert res.p856_verified is None
    assert res.grounding_score == 25.0  # conservative, never full 45
    assert any("DOĞRULANAMADI" in m for m in res.missing_foundations)


def test_p856_domain_matching_rules():
    E = EntityGroundingEngine
    assert E._p856_matches_domain(["https://www.acibadem.com.tr/"], "acibadem.com.tr")
    assert E._p856_matches_domain(["http://sub.domain.co.uk/x"], "domain.co.uk")     # subdomain of target
    assert E._p856_matches_domain(["https://group.example/"], "brand.group.example") # superdomain match
    assert not E._p856_matches_domain(["https://apple.com/"], "apple.inc")
    assert not E._p856_matches_domain([], "apple.com")
    assert not E._p856_matches_domain(["not a url"], "apple.com")
    assert not E._p856_matches_domain(["https://apple.com/"], "")
    assert E._p856_matches_domain(["https://www.apple.com/"], "www.apple.com")  # www-prefixed target
    assert E._p856_matches_domain(["https://apple.com/"], "  www.Apple.com  ")  # case/space normalize


@pytest.mark.anyio
async def test_probe_official_websites_parses_claim_shape(monkeypatch):
    import httpx
    captured = {}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"claims": {"P856": [
                {"mainsnak": {"datavalue": {"value": "https://www.apple.com/", "type": "string"}}},
                {"mainsnak": {}},
                None,
            ]}}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None, headers=None, **kw):
            captured.update(params or {})
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    out = await EntityGroundingEngine.probe_official_websites("Q312")
    assert out == {"status": "ok", "urls": ["https://www.apple.com/"]}
    assert captured["property"] == "P856" and captured["entity"] == "Q312"


@pytest.mark.anyio
async def test_probe_official_websites_network_error_is_unreachable(monkeypatch):
    import httpx

    class BoomClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise httpx.ConnectError("dns down")

    monkeypatch.setattr(httpx, "AsyncClient", BoomClient)
    out = await EntityGroundingEngine.probe_official_websites("Q1")
    assert out == {"status": "unreachable", "urls": []}


@pytest.mark.anyio
async def test_probe_official_websites_non200_is_unreachable(monkeypatch):
    import httpx

    class FakeResp:
        status_code = 503
        def json(self):  # must never be reached
            raise AssertionError("json() on non-200")

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    out = await EntityGroundingEngine.probe_official_websites("Q312")
    assert out == {"status": "unreachable", "urls": []}
