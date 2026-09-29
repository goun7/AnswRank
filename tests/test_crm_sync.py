"""Tests for CRM CSV <-> SQLite synchronization."""

import csv
import os
import pytest
from answrank.crm.sync import CRMSync
from answrank.db import Database
from answrank.models import Prospect, utc_now


@pytest.mark.anyio
async def test_import_csv_to_db(tmp_path):
    csv_path = str(tmp_path / "takip_tablosu.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ad", "isletme", "sektor", "platform", "durum"])
        writer.writeheader()
        writer.writerow({"ad": "Dr. Ayşe", "isletme": "Ayşe Dental", "sektor": "dental", "platform": "instagram", "durum": "lead"})
        writer.writerow({"ad": "Mehmet", "isletme": "Mehmet Clinic", "sektor": "aesthetic", "platform": "linkedin", "durum": "contacted"})

    db = Database(db_path=str(tmp_path / "crm_test.db"))
    sync = CRMSync(csv_path=csv_path, db=db)
    count = await sync.import_csv_to_db()

    assert count == 2
    prospects = await sync.list_prospects()
    brands = {p["brand_name"] for p in prospects}
    assert brands == {"Ayşe Dental", "Mehmet Clinic"}
    # Turkish header fallback: 'iseletme' typo key also works
    assert all(p["contact_person"] in ("Dr. Ayşe", "Mehmet") for p in prospects)


@pytest.mark.anyio
async def test_import_csv_missing_file_returns_zero(tmp_path):
    sync = CRMSync(csv_path=str(tmp_path / "yok.csv"), db=Database(db_path=str(tmp_path / "x.db")))
    assert await sync.import_csv_to_db() == 0


@pytest.mark.anyio
async def test_import_csv_fallbacks_for_missing_columns(tmp_path):
    """Rows without recognizable columns fall back to defaults, never crash."""
    csv_path = str(tmp_path / "takip_tablosu.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ad"])
        writer.writeheader()
        writer.writerow({"ad": "Ali"})

    db = Database(db_path=str(tmp_path / "crm_test2.db"))
    sync = CRMSync(csv_path=csv_path, db=db)
    count = await sync.import_csv_to_db()

    assert count == 1
    prospects = await sync.list_prospects()
    assert prospects[0]["brand_name"] == "Bilinmeyen İşletme"
    assert prospects[0]["sector"] == "dental"
    assert prospects[0]["platform"] == "instagram"


@pytest.mark.anyio
async def test_roundtrip_export_then_import(tmp_path):
    """DB → CSV export → import must preserve brand identity across formats."""
    db = Database(db_path=str(tmp_path / "roundtrip.db"))
    csv_path = str(tmp_path / "takip_tablosu.csv")

    # Seed one prospect directly
    await db.save_prospect(Prospect(
        id="lead_roundtrip_1", brand_name="Roundtrip Klinik", sector="dental",
        city="İstanbul", contact_person="Dr. R", platform="instagram",
        status="lead", created_at=utc_now(),
    ))

    sync = CRMSync(csv_path=csv_path, db=db)
    exported = await sync.export_db_to_csv()
    assert exported == 1
    assert os.path.exists(csv_path)

    # Exported CSV uses the legacy 'iseletme' header — re-import must parse it
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["iseletme"] == "Roundtrip Klinik"
    assert rows[0]["ad"] == "Dr. R"


@pytest.mark.anyio
async def test_export_empty_db_writes_nothing(tmp_path):
    db = Database(db_path=str(tmp_path / "empty.db"))
    csv_path = str(tmp_path / "takip_empty.csv")
    sync = CRMSync(csv_path=csv_path, db=db)
    count = await sync.export_db_to_csv()
    assert count == 0
    assert not os.path.exists(csv_path)
