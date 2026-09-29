"""Zero-drift locks for the LLM engine roster.

Adding/removing a provider must NOT require hunting copy strings: every
user-facing engine count is derived from `runner.MODELS`, and these tests fail
if any surface goes stale or any structural wiring is missed.
"""
import re
from unittest.mock import patch

from answrank.citations.runner import MODELS, MODEL_PROVIDER_MAP, MultiLLMCitationRunner
from answrank.citations.key_manager import HybridKeyManager


def test_every_model_has_full_structural_wiring():
    for model in MODELS:
        provider = MODEL_PROVIDER_MAP[model]
        assert provider in HybridKeyManager.ENV_KEY_MAP, f"{provider} lacks env key"
        assert provider in HybridKeyManager.COST_PER_QUERY, f"{provider} lacks cost"
        method = MultiLLMCitationRunner.PROVIDER_QUERY_METHODS[provider]
        assert callable(method)
        assert provider.name == str(provider).split(".")[-1]


def test_cli_citations_help_is_derived_from_models(capsys):
    """Parent-command listing renders each subparser help; the engine count in
    the citations help must come from MODELS, never a stale literal."""
    from answrank.cli import main
    with patch("sys.argv", ["answrank", "--help"]):
        try:
            main()
        except SystemExit:
            pass
    out = " ".join(capsys.readouterr().out.split())
    assert f"{len(MODELS)} LLM motorunda 20 soruluk atıf testi" in out
    assert "4 LLM motorunda" not in out  # pre-Mistral literal must not return


def test_mcp_tool_description_derives_count_and_names():
    from answrank.mcp.server import AnswRankMCPServer
    defs = AnswRankMCPServer().get_tool_definitions()
    desc = next(t["description"] for t in defs if t["name"] == "answrank_citations")
    assert f"across {len(MODELS)} AI models" in desc
    for model in MODELS:
        assert model.split("-")[0] in desc


def test_landing_has_no_hardcoded_engine_count_claims():
    """Landing copy may NAME flagship engines as examples but must never state
    a numeric engine total (that number lives only in code)."""
    from pathlib import Path
    html = Path("answrank/api/templates/landing.html").read_text(encoding="utf-8")
    stale = re.findall(r"\b(4|5|6|7|dört|four)\s+(büyük|large|major|AI|LLM)", html, re.I)
    assert not stale, f"static engine-count claims: {stale[:3]}"


def test_telemetry_endpoint_would_expose_every_provider():
    """ProviderTelemetry enumeration completeness: every ENV-mapped provider
    appears in the telemetry payload (no silently missing 5th engine)."""
    km = HybridKeyManager(custom_keys={})
    report = km.get_telemetry_report()
    names = {p.name for p in HybridKeyManager.ENV_KEY_MAP}
    keys = set(report.get("providers", {}).keys())
    assert names <= keys, f"telemetry missing providers: {names - keys}"


def test_legal_engine_names_cover_models_exactly():
    """The contract's engine list is rendered from ENGINE_LEGAL_NAMES; every
    MODELS token must have a legal marketing name and vice versa."""
    from answrank.legal.contract_generator import ENGINE_LEGAL_NAMES
    assert set(ENGINE_LEGAL_NAMES.keys()) == set(MODELS)
    assert all(v.strip() for v in ENGINE_LEGAL_NAMES.values())


def test_cli_live_flag_help_counts_providers():
    """--live help once named only 2 providers while 5 existed — counts and
    provider naming in argparse help must derive from MODELS."""
    from unittest.mock import patch as _patch
    import io, contextlib
    from answrank.cli import main
    buf = io.StringIO()
    with _patch("sys.argv", ["answrank", "citations", "--help"]):
        try:
            with contextlib.redirect_stdout(buf):
                main()
        except SystemExit:
            pass
    text = " ".join(buf.getvalue().split())
    assert f"{len(MODELS)} sağlayıcı" in text
    assert "Perplexity Sonar & OpenAI" not in text


def test_ruff_f_rules_clean_with_deduped_normalizer():
    """16 Eyl hygiene lock: unused imports/vars (F401/F841) and literal-comparison
    bugs must not regrow. Skips gracefully if ruff isn't installed."""
    import shutil, subprocess
    if not shutil.which("ruff") and subprocess.run(
            ["python3", "-m", "ruff", "--version"], capture_output=True).returncode != 0:
        import pytest as _pt
        _pt.skip("ruff unavailable in this environment")
    r = subprocess.run(["python3", "-m", "ruff", "check", "answrank/",
                        "--select", "F401,F841,F632,F811"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[:600]


def test_textnorm_single_owner_semantics():
    """Five old normalizers now delegate to answrank/textnorm.py — lock behavior."""
    from answrank.textnorm import netloc, core_label, brand_from_domain
    assert netloc("HTTPS://www.Acibadem.com.tr/kurumsal/") == "acibadem.com.tr"
    assert netloc("acibadem.com.tr") == "acibadem.com.tr"
    assert netloc("") == ""
    assert core_label("www.acibadem.com.tr") == "acibadem"
    assert brand_from_domain("acibadem-klinik.example") == "Acibadem Klinik"
    assert brand_from_domain("yilmaz_dental.test") == "Yilmaz Dental"


def test_p856_netloc_comparison_paths():
    from answrank.audit.entity_grounding import EntityGroundingEngine as E
    assert E._p856_matches_domain(["", "junk-no-scheme", "https://www.acibadem.com.tr/kurumsal"], "acibadem.com.tr") is True
    assert E._p856_matches_domain(["https://kurumsal.acibadem.com.tr"], "acibadem.com.tr") is True
    assert E._p856_matches_domain(["https://acibadem.com"], "acibadem.com.tr") is False
    assert E._p856_matches_domain([], "x.com") is False


def test_proprietary_license_sealed():
    """16 Eyl lisans kararı (D-16.09-L): kapalı kaynak beyanı üç yerde tutarlı.

    2026-09-28: 7 repo public olsa da AnswRank PROPRİETARY kaldı —
    bu ürünün kendisi satılır, kodu değil. Ekip 8 Apache'ye çevirmişti,
    kullanıcı kararıyla geri alındı.
    """
    import tomllib, pathlib
    lic = pathlib.Path("LICENSE").read_text(encoding="utf-8")
    assert "T\u00fcm haklar\u0131 sakl\u0131d\u0131r" in lic and "LicenseRef-AnswRank-Proprietary" in lic
    meta = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))
    assert meta["project"]["license"] == "LicenseRef-AnswRank-Proprietary"
    readme = pathlib.Path("README.md").read_text(encoding="utf-8")
    assert "Proprietary" in readme or "proprietary" in readme
