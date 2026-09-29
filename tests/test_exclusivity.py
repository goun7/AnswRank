from answrank.crm.exclusivity import ExclusivityManager
from answrank.agents.swarm import SwarmOrchestrator, SwarmStage

def test_exclusivity_lock_and_conflict_detection():
    mgr = ExclusivityManager()

    # Initial check: no conflict
    check = mgr.check_conflict(country="UK", city="London", niche="dental", candidate_domain="harleydental.co.uk")
    assert check.has_conflict is False
    assert check.action_recommended == "PROCEED"

    # Lock territory for client 1
    lock = mgr.lock_territory(
        country="UK",
        city="London",
        niche="dental",
        client_domain="harleydental.co.uk",
        brand_name="Harley Dental",
        contract_id="ANSW-001",
    )
    assert lock.lock_id.startswith("LOCK-")

    # Same client re-checking territory: OK
    same_check = mgr.check_conflict(country="UK", city="London", niche="dental", candidate_domain="harleydental.co.uk")
    assert same_check.has_conflict is False

    # Competitor in same territory & niche: CONFLICT DETECTED
    comp_check = mgr.check_conflict(country="UK", city="London", niche="dental", candidate_domain="rivaldental.co.uk")
    assert comp_check.has_conflict is True
    assert comp_check.action_recommended in ("PARTITION_SUB_NICHE", "REJECT_CONFLICT")
    assert "Harley Dental" in comp_check.conflict_reason
    assert len(comp_check.suggested_sub_niches) > 0

def test_swarm_exclusivity_enforcement():
    orch = SwarmOrchestrator()

    # Client 1: Harley Dental in London
    cand1 = orch.seed_target(
        brand_name="Harley Dental",
        domain="harleydental.co.uk",
        sector="dental",
        city="London",
        country="UK",
        currency="GBP",
    )
    assert orch.scout.qualify(cand1) is True
    orch.fulfillment.generate_contract(cand1)
    assert cand1.territory_locked is True

    # Client 2: Rival Dental in London, same sector -> Scout must reject to protect Article 7 guarantee
    cand2 = orch.seed_target(
        brand_name="Rival Dental",
        domain="rivaldental.co.uk",
        sector="dental",
        city="London",
        country="UK",
        currency="GBP",
    )
    assert orch.scout.qualify(cand2) is False
    assert cand2.stage == SwarmStage.CONFLICT_DISQUALIFIED
    assert "Harley Dental" in cand2.conflict_reason
