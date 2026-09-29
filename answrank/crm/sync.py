"""CRM Synchronization: Two-way sync between takip_tablosu.csv and SQLite prospects table."""

import csv
import os
from typing import List, Dict, Any, Optional
from answrank.models import Prospect, utc_now
from answrank.db import Database

class CRMSync:
    """Manages prospects, candidate lists, and synchronization with takip_tablosu.csv."""

    def __init__(self, csv_path: str = "takip_tablosu.csv", db: Optional[Database] = None):
        self.csv_path = csv_path
        self.db = db or Database()

    async def import_csv_to_db(self) -> int:
        """Reads takip_tablosu.csv and inserts/updates prospects in the database."""
        if not os.path.exists(self.csv_path):
            return 0

        imported_count = 0
        with open(self.csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                brand = row.get("iseletme") or row.get("isletme") or "Bilinmeyen İşletme"
                contact = row.get("ad") or ""
                sector = row.get("sektor") or "dental"
                platform = row.get("platform") or "instagram"
                status = row.get("durum") or "lead"
                p_id = f"lead_{brand.lower().replace(' ', '_')[:20]}"

                prospect = Prospect(
                    id=p_id,
                    brand_name=brand,
                    sector=sector,
                    city="İstanbul",
                    contact_person=contact,
                    platform=platform,
                    status=status,
                    created_at=utc_now(),
                )
                await self.db.save_prospect(prospect)
                imported_count += 1

        return imported_count

    async def export_db_to_csv(self) -> int:
        """Exports all prospects from the database to takip_tablosu.csv."""
        def _sync_export():
            with self.db._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM prospects ORDER BY created_at DESC")
                rows = cursor.fetchall()
                if not rows:
                    return 0

                fieldnames = ["ad", "iseletme", "sektor", "platform", "iletisim", "durum", "skor_80", "not"]
                with open(self.csv_path, mode="w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for r in rows:
                        writer.writerow({
                            "ad": r["contact_person"] or "",
                            "iseletme": r["brand_name"],
                            "sektor": r["sector"],
                            "platform": r["platform"] or "instagram",
                            "iletisim": r["website_url"] or "",
                            "durum": r["status"] or "lead",
                            "skor_80": "0",
                            "not": f"ID: {r['id']}",
                        })
                return len(rows)

        import asyncio
        return await asyncio.to_thread(_sync_export)

    async def list_prospects(self) -> List[Dict[str, Any]]:
        """Returns all prospects from the database."""
        def _sync_list():
            with self.db._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM prospects ORDER BY created_at DESC")
                return [dict(r) for r in cursor.fetchall()]

        import asyncio
        return await asyncio.to_thread(_sync_list)
