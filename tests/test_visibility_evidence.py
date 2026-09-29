"""Offline disk-backed contract for both DM visibility consumers."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from answrank.db import Database
from answrank.config import settings
from answrank.models import CitationQueryItem, CitationRunResult
from answrank.queue_gates import DmGateAuditor
from answrank.citations.runner import MultiLLMCitationRunner


def live_run(domain="target.example", run_id="live", **changes):
    data = dict(run_id=run_id, brand_name="X", domain=domain, sector="dental",
                city="Dubai", total_runs=2, brand_citations_found=1,
                citation_rate_percentage=50.0, live_items_count=2,
                live_response_rate_percentage=100.0, is_fully_live=True,
                grounding_status={"test-model": "model-recall"},
                items=[CitationQueryItem(question_id=i, question=f"Q{i}",
                                         model="test-model", was_simulated=False,
                                         brand_mentioned=i == 0)
                       for i in range(2)])
    data.update(changes)
    return CitationRunResult(**data)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "evidence.db")
    monkeypatch.setattr(settings, "db_path", path)
    monkeypatch.setenv("ANSWRANK_DB_PATH", path)
    return Database()


@pytest.fixture(params=[DmGateAuditor, MultiLLMCitationRunner])
def visibility(db, request):
    consumer = request.param(db=db)
    return consumer.db_visibility if isinstance(consumer, DmGateAuditor) else consumer.visibility_for


def test_valid_live_recall_preserves_provenance(db, visibility):
    asyncio.run(db.save_citations(live_run()))
    result = visibility("target.example")
    assert result["hits"] == 1 and result["total"] == 2
    assert result["run_id"] == "live"
    assert result["grounding_status"] == {"test-model": "model-recall"}
    assert result["created_at"]


def test_other_domain_is_never_evidence(db, visibility):
    asyncio.run(db.save_citations(live_run(domain="other.example")))
    assert visibility("target.example") is None


@pytest.mark.parametrize("mutation", [
    {"is_fully_live": False}, {"is_fully_live": "false"},
    {"items": []}, {"live_items_count": 1}, {"total_runs": 3},
    {"brand_citations_found": 2}, {"domain": "wrong.example"},
    {"run_id": "wrong"}, {"grounding_status": {}},
    {"live_response_rate_percentage": 50.0},
])
def test_inconsistent_raw_evidence_is_rejected(db, visibility, mutation):
    run = live_run()
    asyncio.run(db.save_citations(run))
    raw = run.model_dump(mode="json")
    raw.update(mutation)
    with db._get_connection() as conn:
        conn.execute("UPDATE citations SET raw_json=?", (json.dumps(raw),))
        conn.commit()
    assert visibility("target.example") is None


@pytest.mark.parametrize("invalid", ["{bad", "[]", "null"])
def test_corrupt_latest_does_not_fall_back(db, visibility, invalid):
    asyncio.run(db.save_citations(live_run(timestamp=datetime.now(timezone.utc)-timedelta(days=2))))
    asyncio.run(db.save_citations(live_run(run_id="new")))
    with db._get_connection() as conn:
        conn.execute("UPDATE citations SET raw_json=? WHERE run_id='new'", (invalid,))
        conn.commit()
    assert visibility("target.example") is None


def test_new_simulation_does_not_fall_back(db, visibility):
    asyncio.run(db.save_citations(live_run(timestamp=datetime.now(timezone.utc)-timedelta(days=2))))
    asyncio.run(db.save_citations(live_run(run_id="new", is_fully_live=False)))
    assert visibility("target.example") is None


def test_simulated_item_cannot_hide_behind_live_flag(db, visibility):
    run = live_run()
    run.items[0].was_simulated = True
    asyncio.run(db.save_citations(run))
    assert visibility("target.example") is None


def test_dm_copy_describes_response_sample_not_organic_search(db):
    from answrank.crm.outreach import OutreachGenerator
    asyncio.run(db.save_citations(live_run()))
    vis = DmGateAuditor(db=db).db_visibility("target.example")
    text = OutreachGenerator.lead_dm("target.example", "İZİNLİ", "VAR", "3/3",
                                     "TEMİZ", ai_visibility=vis)
    assert "organik" not in text
    assert "altyapınız iyi" not in text
    assert "siteniz cevaplarda belirdi" not in text
    assert "2 test yanıtının 1 tanesinde marka adı veya domain" in text
    assert "model-recall" in text
    assert "arama kaynaklandırmasını bağımsız olarak doğrulamaz" in text
    assert vis["run_id"] in text and vis["created_at"] in text


def test_dm_copy_omits_unproven_visibility():
    from answrank.crm.outreach import OutreachGenerator
    text = OutreachGenerator.lead_dm("target.example", "İZİNLİ", "VAR", "3/3",
                                     "TEMİZ", ai_visibility={"hits": 1, "total": 8})
    assert "görünürlüğünüzü ölçtük" not in text
    assert "organik" not in text


@pytest.mark.parametrize("state", ["missing", "invalid-latest", "valid"])
def test_cli_visibility_draft_requires_valid_latest_run(db, monkeypatch, capsys, state):
    import sys
    from answrank.cli import main
    from answrank.probe.miniprobe import MiniProbeResult

    asyncio.run(db.save_miniprobe_lead(MiniProbeResult(
        domain="target.example", verdict="TEMİZ", robots_line="İZİNLİ",
        llms_line="VAR", bots_line="3/3", blocked_bots=[], probed=3, measured=True)))
    if state != "missing":
        asyncio.run(db.save_citations(live_run()))
    if state == "invalid-latest":
        asyncio.run(db.save_citations(live_run(run_id="new", is_fully_live=False)))
    monkeypatch.setattr(sys, "argv", ["answrank", "crm", "draft",
                                     "--from-lead", "target.example", "--with-visibility"])
    main()
    output = " ".join(capsys.readouterr().out.replace("│", " ").split())
    if state == "valid":
        assert "E7 Lead DM" in output
        assert "Koşu: live" in output
    else:
        assert "E7 Lead DM" not in output, "Geçersiz kanıtla taslak üretildi"
        assert "taslak üretilmedi" in output


def test_missing_optional_raw_field_rejected(db, monkeypatch):
    """Pydantic'in varsayılanla doldurabildiği ham alanlar eksikse kanıt geçersiz."""
    asyncio.run(db.save_citations(live_run()))
    _corrupt(db, "target.example", drop="city")
    assert visibility_strict("target.example") is None


def test_missing_item_field_rejected(db):
    asyncio.run(db.save_citations(live_run()))
    _corrupt(db, "target.example", drop_item="domain_cited")
    assert visibility_strict("target.example") is None


def test_missing_grounding_rejected(db):
    asyncio.run(db.save_citations(live_run()))
    _corrupt(db, "target.example", drop="grounding_status")
    assert visibility_strict("target.example") is None


def _corrupt(db, domain, drop=None, drop_item=None):
    import json as _json
    with db._get_connection() as conn:
        row = conn.execute("SELECT raw_json FROM citations WHERE domain=?"
                           " ORDER BY created_at DESC, rowid DESC LIMIT 1",
                           (domain,)).fetchone()
        raw = _json.loads(row["raw_json"])
        if drop:
            raw.pop(drop, None)
        if drop_item:
            raw["items"][0].pop(drop_item, None)
        conn.execute("UPDATE citations SET raw_json=? WHERE domain=?",
                     (_json.dumps(raw), domain))
        conn.commit()


def visibility_strict(domain):
    from answrank.citations.evidence import visibility_from_row
    from answrank.db import Database
    with Database()._get_connection() as conn:
        row = conn.execute("SELECT * FROM citations WHERE domain=?"
                           " ORDER BY created_at DESC, rowid DESC LIMIT 1",
                           (domain,)).fetchone()
        return visibility_from_row(row, domain)


def test_report_reader_does_not_fall_back_to_older_run(db, monkeypatch):
    """Rapor sayfası okuyucusu da 'son koşu geçersizse durdur' sözleşmesine uyar."""
    asyncio.run(db.save_citations(live_run()))
    asyncio.run(db.save_citations(live_run(run_id="new", is_fully_live=False)))
    import asyncio as _a
    older = _a.run(db.get_latest_citations_for_domain("target.example"))
    assert older is None, "bozuk son koşuda eski koşuya dönüş olmaz"


def test_report_reader_returns_valid_latest(db):
    asyncio.run(db.save_citations(live_run()))
    import asyncio as _a
    res = _a.run(db.get_latest_citations_for_domain("target.example"))
    assert res is not None and res.run_id == "live"


def test_denormalized_counts_must_match(db, visibility):
    asyncio.run(db.save_citations(live_run()))
    with db._get_connection() as conn:
        conn.execute("UPDATE citations SET citations_found=2, citation_rate=100")
        conn.commit()
    assert visibility("target.example") is None


def test_dm_body_discloses_single_measurement_uncertainty(db):
    """Akademik kanıt (arXiv:2607.14035): run-to-run değişkenlik yüksektir.
    DM tek ölçümü kesin sonuç gibi sunamaz — belirsizlik etiketi şart."""
    from answrank.crm.outreach import OutreachGenerator
    asyncio.run(db.save_citations(live_run()))
    vis = DmGateAuditor(db=db).db_visibility("target.example")
    assert vis is not None
    body = OutreachGenerator.lead_dm(
        "target.example", "İZİNLİ", "VAR", "3/3", "TEMİZ", ai_visibility=vis)
    low = body.lower()
    assert "tek bir ölçüm" in low or "tekrar" in low, (
        "DM tek-ölçüm belirsizliğini açıklamalı (run-to-run değişkenlik)")
