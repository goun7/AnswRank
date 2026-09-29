"""AI bot registry integrity tests.

The 15 Sept 2026 live audit against knownagents.com (HTTP 404 verified) found that
the previous Tier-3 roster carried three fabricated tokens ("Google-Sessel",
"ChatGPT-SearchUser", "Meta-ExternalAgent-User") and missed 2026 answer engines.
These tests lock the corrected, directory-verified registry in place and make the
marketing/legal "N AI botu" copy drift-proof by asserting it equals the live config.
"""

from answrank.config import settings
from answrank.audit.waf_probe import WAFProbeEngine
from answrank.reporting.fix_generator import FixGenerator

# Tokens proven absent from the daily-updated directory (HTTP 404) on 2026-09-15.
FABRICATED = {"Google-Sessel", "ChatGPT-SearchUser", "Meta-ExternalAgent-User"}

# Live-verified additions (HTTP 200 + robots User-agent token from knownagents.com):
VERIFIED_2026_SEARCH = {"xAI-SearchBot", "Kimi-SearchBot", "Amzn-SearchBot"}
VERIFIED_2026_TRAINING = {"Bravebot"}
VERIFIED_2026_USER = {"Kimi-User", "MistralAI-User", "Amzn-User", "DuckAssistBot"}

# 16 Sept 2026 live re-verification: /agents/<slug> HTTP 200 + documented User-agent token.
VERIFIED_2026_09_16_AGENTIC = {
    "AmazonBuyForMe", "CohereBot", "QwenBot", "Cursor", "Browserbase", "Anchor", "SaaSBrowserBot",
}
# Deliberately NOT added: Known-Agents-Browser — page rendered a truncated UA token ("Known"),
# unverifiable identifiers never ship.


def _all_registry_bots():
    return set(settings.ai_bots_search) | set(settings.ai_bots_training) | set(settings.ai_bots_user_agents)


def test_no_fabricated_bots_anywhere():
    assert not (FABRICATED & _all_registry_bots())


def test_verified_2026_bots_present_in_expected_tiers():
    assert VERIFIED_2026_SEARCH <= set(settings.ai_bots_search)
    assert VERIFIED_2026_TRAINING <= set(settings.ai_bots_training)
    assert VERIFIED_2026_USER <= set(settings.ai_bots_user_agents)
    assert VERIFIED_2026_09_16_AGENTIC <= set(settings.ai_bots_user_agents)
    assert "Known-Agents-Browser" not in _all_registry_bots()


def test_registry_has_no_duplicates_within_tiers():
    for tier in (settings.ai_bots_search, settings.ai_bots_training, settings.ai_bots_user_agents):
        assert len(tier) == len(set(tier))
    # Core engines that must never regress out of the search tier:
    assert {"OAI-SearchBot", "PerplexityBot", "Claude-SearchBot", "Google-Extended"} <= set(settings.ai_bots_search)


def test_config_tier_count_helpers_match_lists():
    assert settings.ai_bots_total == len(_all_registry_bots()) == 39
    assert settings.ai_bots_tier_summary == "39 AI botu (11 arama + 14 eğitim + 14 kullanıcı-ajanı)"


def test_waf_probe_roster_is_subset_of_search_and_training_tiers():
    # Every bot WAF-probed must be a curated registry bot (no invented probes).
    assert set(WAFProbeEngine.AI_CRAWLER_USER_AGENTS) <= _all_registry_bots()
    assert len(WAFProbeEngine.AI_CRAWLER_USER_AGENTS) == 9
    for ua in WAFProbeEngine.AI_CRAWLER_USER_AGENTS.values():
        assert ua.startswith("Mozilla/5.0")


def test_generated_robots_txt_uses_live_registry_and_skips_blocked():
    txt = FixGenerator().generate_robots_txt("example.com")
    for bot in settings.ai_bots_search + settings.ai_bots_training + settings.ai_bots_user_agents:
        if bot in FixGenerator.BLOCKED_BY_DEFAULT:
            assert f"User-agent: {bot}\nAllow" not in txt  # blocked scrapers never auto-allowed
        else:
            assert f"User-agent: {bot}" in txt
    for fake in FABRICATED:
        assert fake not in txt
    # header counts are derived, not hard-coded:
    assert f"({len(settings.ai_bots_search)} - Mandatory for AEO)" in txt
    assert f"({len(settings.ai_bots_user_agents)} - Human-Triggered Sessions)" in txt


def test_sales_and_legal_copy_match_live_registry():
    """Marketing/legal strings must equal settings-derived numbers (no 27-bot drift)."""
    import inspect
    import answrank.audit.analyzers.robots as robots_mod
    from answrank.crm.objection import ObjectionLibrary
    from answrank.economics import EconomicsEngine

    total = settings.ai_bots_total
    breakdown = settings.ai_bots_tier_summary  # e.g. "32 AI botu (11 arama + 14 eğitim + 7 kullanıcı-ajanı)"
    n_search = len(settings.ai_bots_search)

    # objection rebuttal + talking point
    all_text = " ".join(
        (s.rebuttal_template or "") + " " + " ".join(s.talking_points)
        for s in ObjectionLibrary.SCRIPTS.values()
    )
    assert f"{total} bağımsız AI botunun" in all_text
    assert breakdown == "39 AI botu (11 arama + 14 eğitim + 14 kullanıcı-ajanı)"
    talking_points_text = " ".join(
        tp for s in ObjectionLibrary.SCRIPTS.values() for tp in s.talking_points
    )
    assert f"3 katman: {len(settings.ai_bots_search)} arama + {len(settings.ai_bots_training)} eğitim + {len(settings.ai_bots_user_agents)} kullanıcı-ajanı" in talking_points_text
    # stale counts must be gone
    assert "27 bağımsız AI" not in all_text and "27 AI botu" not in all_text

    # contract clause — BEHAVIORAL: render a real contract, not source-grep
    # (the count is derived from settings at render time and may never be a literal).
    from answrank.legal.contract_generator import ContractGenerator, ClientLegalDetails, ContractMetadata
    from answrank.economics import PricingTier
    client = ClientLegalDetails(
        client_name="Test Kliniği A.Ş.", company_title="Test Ltd.",
        tax_number="1111111111", tax_office="Test", address="Test Sok. 1",
        authorized_person="Test Yetkili", email="test@example.com",
        phone="+900000000000", domain="test.example", sector="dental",
    )
    meta = ContractMetadata(
        contract_number="ANSW-DRIFT-TEST", service_tier=PricingTier.MONTHLY_RETAINER,
        monthly_fee_try=1000.0, start_date="2026-09-16", duration_months=6,
    )
    rendered = ContractGenerator.generate_contract(client, meta).contract_text
    assert f"{total} AI botu izin protokollerini" in rendered
    assert "27 AI botu izin" not in rendered and "32 AI botu izin" not in rendered
    # engine list rendered from ENGINE_LEGAL_NAMES must name every live MODELS engine
    from answrank.citations.runner import MODELS
    from answrank.legal.contract_generator import ENGINE_LEGAL_NAMES
    for legal_name in ENGINE_LEGAL_NAMES.values():
        assert legal_name in rendered, f"contract missing engine {legal_name}"
    assert len(ENGINE_LEGAL_NAMES) == len(MODELS)

    # economics feature bullet
    robots_feature = next(
        f
        for pkg in EconomicsEngine.PACKAGES.values()
        for f in pkg.features
        if "robots.txt" in f and "AI" in f
    )
    assert f"{total} AI Botu" in robots_feature

    # analyzer docstring no longer hardcodes a stale count
    analyzer_src = inspect.getsource(robots_mod)
    assert "27 AI Crawlers" not in analyzer_src
    assert n_search >= 11  # grok/kimi/amazon search engines counted in tier-1


def test_contract_guarantee_defaults_match_sold_band():
    """16 Eyl C8: contract Madde 7 defaults may never exceed what landing/MASTER
    sell (the +12–15 citation band → contractual floor +12; score floor +12)."""
    from answrank.legal.contract_generator import (
        ContractGenerator, ClientLegalDetails, ContractMetadata)
    from answrank.economics import PricingTier
    client = ClientLegalDetails(
        client_name="Test Kliniği A.Ş.", company_title="Test Ltd.",
        tax_number="1111111111", tax_office="Test", address="Test Sok. 1",
        authorized_person="Test Yetkili", email="test@example.com",
        phone="+900000000000", domain="test.example", sector="dental",
    )
    meta = ContractMetadata(
        contract_number="ANSW-GUAR-TEST", service_tier=PricingTier.MONTHLY_RETAINER,
        monthly_fee_try=1000.0, start_date="2026-09-16", duration_months=6,
    )
    rendered = ContractGenerator.generate_contract(client, meta).contract_text
    assert "en az +12 net puan" in rendered
    assert "en az +%12.0 net büyüme" in rendered  # float repr locked honestly
    for inflated in ("en az +25 net puan", "en az +30", "25 net puan artışı"):
        assert inflated not in rendered
