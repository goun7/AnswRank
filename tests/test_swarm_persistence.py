import os
import tempfile
from answrank.db import Database
from answrank.agents.swarm import SwarmOrchestrator, SwarmStage

def test_swarm_candidate_sqlite_persistence():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db = Database(db_path=db_path)
        orch = SwarmOrchestrator(db=db)

        # Seed target candidate
        cand = orch.seed_target(
            brand_name="Kensington Smiles",
            domain="kensingtonsmiles.co.uk",
            sector="dental",
            city="London",
            country="UK",
            currency="GBP",
            ticket_size=3200.0,
        )
        assert cand.id in orch.pool

        # Verify saved in SQLite database
        saved = db.get_swarm_candidate_sync(cand.id)
        assert saved is not None
        assert saved["brand_name"] == "Kensington Smiles"
        assert saved["domain"] == "kensingtonsmiles.co.uk"
        assert saved["stage"] == "DISCOVERED"

        # Advance candidate stage and verify update
        orch.scout.qualify(cand)
        orch.persist_candidate(cand)

        updated = db.get_swarm_candidate_sync(cand.id)
        assert updated["stage"] == "QUALIFIED"

        # Simulate system reboot / new orchestrator instance
        orch_reboot = SwarmOrchestrator(db=db)
        assert cand.id in orch_reboot.pool
        assert orch_reboot.pool[cand.id].stage == SwarmStage.QUALIFIED
        assert orch_reboot.pool[cand.id].brand_name == "Kensington Smiles"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
