"""Tests for Candidate Qualifier and Intake Scoring Engine."""

from answrank.crm.qualifier import (
    CandidateQualifier,
    CandidateProfile,
    IntakeResponse,
)


def test_candidate_qualifier_success():
    candidate = CandidateProfile(
        company_name="Örnek Dental",
        sector="dental",
        domain="ornekdental.com",
        has_custom_domain=True,
        estimated_ticket_size=7500.0,
        estimated_annual_revenue=2500000.0,
        has_ad_spend=True,
        direct_decision_maker_access=True,
        ai_missing_in_top5=True,
        has_competitor_cited=True,
    )
    res = CandidateQualifier.qualify_candidate(candidate)
    assert res.is_qualified is True
    assert res.score == 5
    assert len(res.passed_criteria) == 5
    assert len(res.failed_criteria) == 0


def test_candidate_qualifier_disqualified():
    candidate = CandidateProfile(
        company_name="Bütçesiz İşletme",
        sector="dental",
        domain=None,
        has_custom_domain=False,
        estimated_ticket_size=500.0,
        estimated_annual_revenue=100000.0,
        has_ad_spend=False,
        direct_decision_maker_access=False,
        ai_missing_in_top5=False,
        has_competitor_cited=False,
    )
    res = CandidateQualifier.qualify_candidate(candidate)
    assert res.is_qualified is False
    assert res.score == 0
    assert len(res.failed_criteria) == 5


def test_intake_scoring_priority_a():
    intake = IntakeResponse(
        monthly_new_client_goal="50_plus",       # 30p
        monthly_marketing_budget="30k_plus",     # 25p
        ai_visibility_awareness="tested_not_cited",  # 20p
        decision_maker_status="sole_owner",      # 15p
        action_timeline="immediately_14d",       # 10p
    )
    res = CandidateQualifier.score_intake(intake)
    assert res.total_score == 100
    assert res.priority_tier == "PRIORITY_A"


def test_intake_scoring_disqualified():
    intake = IntakeResponse(
        monthly_new_client_goal="under_10",       # 5p
        monthly_marketing_budget="under_10k",     # 5p
        ai_visibility_awareness="already_ranking",  # 5p
        decision_maker_status="employee_agency", # 0p
        action_timeline="just_researching",      # 0p
    )
    res = CandidateQualifier.score_intake(intake)
    assert res.total_score == 15
    assert res.priority_tier == "DISQUALIFIED"
