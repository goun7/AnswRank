#!/usr/bin/env python3
"""UAE kampanya ölçümü — 29 klinik × organik AI görünürlük (E12 genişletme).

Perplexity Sonar (search-grounded) ile her klinik için organik sorgularda
marka görünürlüğü ölçülür. Önemli: ölçülemeyen klinik uyduru-veri ALMAZ,
'ölçülemedi' olarak kalır. Sonuçlar kampanya DB'sine + JSON rapora yazılır.

Kullanım: python3 scripts/uae_campaign_measure.py [--limit N] [--out x.json]
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

# --- maskeleme + anahtar yükleme (probe ile aynı) -------------------------
import importlib.util

_spec = importlib.util.spec_from_file_location("probe", "scripts/live_citation_probe.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_loaded = _mod.load_env_file(os.environ.get("ANSWRANK_ENV_FILE",
                                            "/home/gokun/.answrank/keys.env"))
import os as _o
if not _o.path.isdir("answrank"): _o.chdir("/home/gokun/projects/02_sahis/85-AnswRank")
_mod._redact_secrets(list(_loaded.values()))

from answrank.citations.runner import MultiLLMCitationRunner  # noqa: E402
from answrank.db import Database  # noqa: E402
from answrank.models import CitationRunResult  # noqa: E402

# Organik sorgular: bir hastanın klinik ararken yazacağı şeyler — marka adı
# YOK (marka adı sormak görünürlüğü ölçmez, hatırlamayı ölçer).
QUERIES = [
    "best dental clinic in Dubai",
    "best dental clinic in Abu Dhabi",
    "top dental clinics in UAE for implants",
    "affordable dental clinic Dubai Marina",
    "cosmetic dentistry clinic Dubai",
    "dental clinic near me Dubai",
    "best dentist in UAE reviews",
    "medical tourism dental clinic UAE",
]


async def measure_one(runner: MultiLLMCitationRunner, brand: str, domain: str,
                      city: str, db: Database, results: list) -> None:
    """Tek klinik için görünürlük ölç; başarısızlık ölçülemedi olarak kaydolur."""
    hits = 0
    measured = 0
    label = None
    for q in QUERIES:
        try:
            ans = await runner.query_perplexity_live(q)
        except Exception:
            ans = None
        if ans is None:
            continue
        measured += 1
        # marka adının ANLAMLI parçası (lokasyon/sonek olmadan); en az 2 kelime
        # veya 8 harf — tek-kelime kısa adlar ("Derma") substring yanlış vuruş
        # yapar (16 Eyl kampanya dumanında bulundu).
        key = brand.split(" - ")[0].split(",")[0].strip().lower()
        words = key.split()
        too_generic = len(words) < 2 and len(key) < 8
        if not too_generic and key and key in ans.lower():
            hits += 1
        elif too_generic:
            # kısa adlarda domain'den türeyen daha belirgin anahtarı dene
            dom = (domain or "").replace("www.", "").split(".")[0].lower()
            if dom and len(dom) >= 8 and dom in ans.lower().replace("-", ""):
                hits += 1
    label = runner.grounding_status.get("Perplexity-Sonar", "ölçülemedi")
    total = measured or len(QUERIES)
    rate = round(100 * hits / total, 1) if measured else 0.0
    # ölçüm yoksa uyduru-oran yazma
    if measured == 0:
        entry = {"brand": brand, "domain": domain, "city": city,
                 "status": "ölçülemedi", "note": "API reddetti/kota"}
    else:
        entry = {"brand": brand, "domain": domain, "city": city,
                 "status": "measured", "hits": hits, "total": total,
                 "rate_pct": rate, "modality": label}
        # citations tablosuna gerçek ölçüm kaydı (DM kanıtı için)
        await db.save_citations(CitationRunResult(
            run_id=f"uae-{domain.replace('.', '-')}",
            brand_name=brand, domain=domain, sector="dental", city=city,
            total_runs=total, brand_citations_found=hits,
            citation_rate_percentage=rate))
    results.append(entry)
    print(f"[{entry['status']:>11}] {brand[:42]:<42} "
          f"{entry.get('rate_pct', '-'):>5}% ({entry.get('hits', 0)}/"
          f"{entry.get('total', 0)})", flush=True)


async def main() -> None:
    limit = int(os.environ.get("LIMIT", "0")) or None
    out_path = os.environ.get("OUT", "/tmp/uae_campaign.json")
    leads = json.load(open("/tmp/uae_leads_raw.json", encoding="utf-8"))
    if limit:
        leads = leads[:limit]

    db = Database(db_path=os.environ.get("ANSWRANK_DB_PATH",
                                         "/tmp/uae_campaign.db"))
    runner = MultiLLMCitationRunner(db=db)
    results: list = []

    # klinikleri art arda ölç (kota dostu: paralel değil)
    for i, lead in enumerate(leads, 1):
        print(f"[{i}/{len(leads)}] {lead['brand']}", flush=True)
        await measure_one(runner, lead["brand"], lead.get("domain", ""),
                          lead.get("city", ""), db, results)
        # her klinikten sonra labeling sıfırlanmasın diye runner'ı koru

    json.dump({"queries": QUERIES, "n": len(results), "results": results},
              open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    measured = [r for r in results if r["status"] == "measured"]
    print(f"\nÖZET: {len(measured)}/{len(results)} klinik ölçüldü, "
          f"{len(results) - len(measured)} ölçülemedi (uydurma yok)")
    print(f"Rapor: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
