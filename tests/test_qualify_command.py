"""run_qualify_command lead-nitelik CLI testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: monkeypatch CandidateProfile/CandidateQualifier.
"""
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, ".")
sys.path.insert(0, "../../01_unicorn/63-Sester")

import answrank.cli as cli  # noqa: E402
import answrank.crm.qualifier as qual_mod  # noqa: E402


class _Result:
    def __init__(self, is_qualified=True, reason="Tüm kriterler sağlandı",
                 passed=None, failed=None, score=5):
        self.is_qualified = is_qualified
        self.score = score
        self.reason = reason
        self.passed_criteria = passed if passed is not None else ["Kriter 1"]
        self.failed_criteria = failed if failed is not None else []


def _args(**over):
    base = dict(company="Test A.Ş.", sector="SaaS", domain="test.com",
                ticket=5000, revenue=500000, has_ads=True,
                dm_access=True, missing_ai=False,
                competitor_cited=True)
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def qualifier(monkeypatch):
    created = []

    class _Profile:
        def __init__(self, **kw):
            created.append(kw)
            for k, v in kw.items():
                setattr(self, k, v)

    class _Result:
        def __init__(self, is_qualified=True, reason="Tüm kriterler sağlandı",
                     passed=None, failed=None, score=5):
            self.is_qualified = is_qualified
            self.score = score
            self.reason = reason
            self.passed_criteria = passed if passed is not None else [
                "Kriter 1"]
            self.failed_criteria = failed if failed is not None else []

    class _Qualifier:
        last_result = _Result()

        @staticmethod
        def qualify_candidate(p):
            return _Qualifier.last_result

    monkeypatch.setattr(qual_mod, "CandidateProfile", _Profile)
    monkeypatch.setattr(qual_mod, "CandidateQualifier", _Qualifier)
    return created, _Qualifier


@pytest.fixture
def caprich(monkeypatch):
    shown = []
    monkeypatch.setattr(cli, "Panel", lambda *a, **k: shown.append(("panel", a, k)))
    monkeypatch.setattr(cli, "Table", type("T", (), {
        "__init__": lambda self, *a, **k: shown.append(("table", a, k)),
        "add_column": lambda self, *a, **k: None,
        "add_row": lambda self, *a, **k: shown.append(("row", a)),
    }))
    return shown


# -- temel ---------------------------------------------------------------------------

def test_returns_none(qualifier, caprich):
    assert cli.run_qualify_command(_args()) is None


def test_profile_created(qualifier, caprich):
    cli.run_qualify_command(_args(company="Firma X"))
    kw = qualifier[0][0]
    assert kw["company_name"] == "Firma X"


def test_all_profile_fields(qualifier, caprich):
    cli.run_qualify_command(_args())
    kw = qualifier[0][0]
    for f in ("company_name", "sector", "domain", "has_custom_domain",
              "estimated_ticket_size", "estimated_annual_revenue",
              "has_ad_spend", "direct_decision_maker_access",
              "ai_missing_in_top5", "has_competitor_cited"):
        assert f in kw


def test_has_custom_domain_true(qualifier, caprich):
    cli.run_qualify_command(_args(domain="x.com"))
    assert qualifier[0][0]["has_custom_domain"] is True


def test_has_custom_domain_false(qualifier, caprich):
    cli.run_qualify_command(_args(domain=None))
    assert qualifier[0][0]["has_custom_domain"] is False


def test_qualify_called(qualifier, caprich):
    cli.run_qualify_command(_args())
    # result döner ve panel'de gösterilir
    assert any(s[0] == "panel" for s in caprich)


# -- Panel çıktısı ---------------------------------------------------------------------------

def test_panel_shown(qualifier, caprich):
    cli.run_qualify_command(_args())
    assert any(s[0] == "panel" for s in caprich)


def test_panel_contains_company(qualifier, caprich):
    cli.run_qualify_command(_args(company="Acme"))
    panel = [s for s in caprich if s[0] == "panel"][0]
    assert "Acme" in str(panel[1])


def test_panel_contains_verdict(qualifier, caprich):
    cli.run_qualify_command(_args())
    panel = [s for s in caprich if s[0] == "panel"][0]
    assert "UYGUN" in str(panel[1])


def test_panel_contains_reason(qualifier, caprich):
    cli.run_qualify_command(_args())
    panel = [s for s in caprich if s[0] == "panel"][0]
    assert "kriterler" in str(panel[1]).lower()


# -- tablo ---------------------------------------------------------------------------

def test_table_shown(qualifier, caprich):
    cli.run_qualify_command(_args())
    assert any(s[0] == "table" for s in caprich)


def test_table_rows_for_passed(qualifier, caprich):
    cli.run_qualify_command(_args())
    rows = [s for s in caprich if s[0] == "row"]
    assert len(rows) >= 1


def test_table_rows_for_failed(qualifier, caprich, monkeypatch):
    qualifier[1].last_result = _Result(
        is_qualified=False, passed=[], failed=["Kriter 2"])
    cli.run_qualify_command(_args())
    rows = [s for s in caprich if s[0] == "row"]
    assert len(rows) >= 1


# -- reddedilen aday ---------------------------------------------------------------------------

def test_disqualified_verdict(qualifier, caprich):
    qualifier[1].last_result = _Result(
        is_qualified=False, reason="Yetersiz bütçe")
    cli.run_qualify_command(_args())
    panel = [s for s in caprich if s[0] == "panel"][0]
    assert "ELENDİ" in str(panel[1])


def test_disqualified_still_shows_reason(qualifier, caprich):
    qualifier[1].last_result = _Result(
        is_qualified=False, reason="Bütçe yetersiz")
    cli.run_qualify_command(_args())
    panel = [s for s in caprich if s[0] == "panel"][0]
    assert "Bütçe yetersiz" in str(panel[1])


# -- sektör/domain çeşitleri ---------------------------------------------------------------------------

@pytest.mark.parametrize("sector", ["SaaS", "E-ticaret", "Sağlık"])
def test_various_sectors(qualifier, caprich, sector):
    cli.run_qualify_command(_args(sector=sector))
    assert qualifier[0][0]["sector"] == sector


@pytest.mark.parametrize("domain", ["a.com", None, "sub.b.org"])
def test_various_domains(qualifier, caprich, domain):
    cli.run_qualify_command(_args(domain=domain))
    assert qualifier[0][0]["domain"] == domain


# -- bayraklar ---------------------------------------------------------------------------

def test_ads_flag(qualifier, caprich):
    cli.run_qualify_command(_args(has_ads=False))
    assert qualifier[0][0]["has_ad_spend"] is False


def test_decision_maker_flag(qualifier, caprich):
    cli.run_qualify_command(_args(dm_access=False))
    assert qualifier[0][0]["direct_decision_maker_access"] is False


def test_missing_ai_flag(qualifier, caprich):
    cli.run_qualify_command(_args(missing_ai=True))
    assert qualifier[0][0]["ai_missing_in_top5"] is True


def test_competitor_flag(qualifier, caprich):
    cli.run_qualify_command(_args(competitor_cited=False))
    assert qualifier[0][0]["has_competitor_cited"] is False


def test_ticket_and_revenue(qualifier, caprich):
    cli.run_qualify_command(_args(ticket=10000, revenue=2000000))
    assert qualifier[0][0]["estimated_ticket_size"] == 10000
    assert qualifier[0][0]["estimated_annual_revenue"] == 2000000
