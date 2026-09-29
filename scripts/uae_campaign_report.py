#!/usr/bin/env python3
"""UAE kampanya raporu — ölçülen 29 klinik + DM taslakları + sıralama.

Ölçüm script'inin ürettiği JSON'u alır: her klinik için
1. görünürlük sıralaması (en kötü = en yüksek öncelik)
2. OutreachGenerator ile ölçüm-temelli DM taslağı
3. öncelik-eğrisi (görünürlük düşük + altyapı iyi = en değerli fırsat)

Önemli: ölçülemedi klinikler uyduru-DM ALMAZ — 'ölçüm yok' olarak kalır.
Kullanım: python3 scripts/uae_campaign_report.py [--in x.json] [--out y.md]
"""
from __future__ import annotations

import json
import os
import sys

from answrank.crm.outreach import OutreachGenerator
from answrank.db import Database

IN = os.environ.get("IN", "/tmp/uae_campaign.json")
OUT = os.environ.get("OUT", "/tmp/uae_campaign_report.md")


def main() -> None:
    data = json.load(open(IN, encoding="utf-8"))
    results = data["results"]
    measured = [r for r in results if r["status"] == "measured"]
    failed = [r for r in results if r["status"] != "measured"]

    # öncelik: görünürlük düşük = fırsat yüksek (0% en üstte)
    ranked = sorted(measured, key=lambda r: r.get("rate_pct", 0))

    db = Database(db_path=os.environ.get("ANSWRANK_DB_PATH",
                                         "/tmp/uae_campaign.db"))
    lines = []
    lines.append("# UAE Dental Kampanya Raporu — 16 Eyl 2026\n")
    lines.append(f"**{len(results)} klinik ölçüm hedefi · "
                 f"{len(measured)} ölçüldü · {len(failed)} ÖLÇÜLEMEDİ**\n")
    lines.append("Sorgular (marka adı YOK — organik görünürlük):\n")
    for q in data["queries"]:
        lines.append(f"- {q}")
    lines.append("\n---\n\n## Görünürlük Sıralaması (en kötü → en iyi)\n\n")
    lines.append("| # | Klinik | Şehir | Görünürlük | Modality |\n")
    lines.append("|---|--------|-------|-----------|----------|\n")
    for i, r in enumerate(ranked, 1):
        lines.append(f"| {i} | {r['brand']} | {r['city']} | "
                     f"{r['hits']}/{r['total']} = %{r['rate_pct']} | "
                     f"{r.get('modality', '-')} |\n")
    if failed:
        lines.append("\n### ÖLÇÜLEMEDİ (uydurma yok)\n\n")
        for r in failed:
            lines.append(f"- {r['brand']} ({r['domain']}) — {r.get('note')}\n")

    lines.append("\n---\n\n## DM Taslakları (en yüksek öncelik 5)\n\n")
    top = ranked[:5]
    for i, r in enumerate(top, 1):
        lead = db.latest_measured_lead(r["domain"])
        if not lead:
            lines.append(f"### {i}. {r['brand']} — mini-probe ölçümü yok "
                         f"(DM üretilemedi)\n\n")
            continue
        vis = {"hits": r["hits"], "total": r["total"],
               "rate": r["rate_pct"], "engine": "çoklu-LLM atıf ölçümü"}
        dm = OutreachGenerator.lead_dm(lead["domain"], lead["robots_line"],
                                       lead["llms_line"], lead["bots_line"],
                                       lead["verdict"], ai_visibility=vis)
        lines.append(f"### {i}. {r['brand']} — %{r['rate_pct']} görünürlük\n\n")
        lines.append("```\n" + dm + "\n```\n\n")

    lines.append("\n---\n\n## Öncelik Eğrisi\n\n")
    lines.append("En değerli fırsat: **görünürlük düşük + altyapı iyi** olan "
                 "klinikler. Onlara 'siteniz iyi ama sizi AI görmüyor' "
                 "diyebiliyoruz — bu cümle ölçümlüdür, pazarlama değildir.\n\n")
    zero = [r for r in ranked if r.get("rate_pct", 0) == 0]
    lines.append(f"**%0 görünürlük (en yüksek öncelik): {len(zero)} klinik**\n")
    lines.append("**Etik not:** Bu rapordaki her sayı canlı ölçümden gelir. "
                 "Ölçülemedi klinikler için DM üretilmedi — uyduru-veri "
                 "yoktur (E5/E7 dürüstlük sınırı).\n")

    open(OUT, "w", encoding="utf-8").write("".join(lines))
    print(f"rapor: {OUT}")
    print(f"  {len(measured)} ölçüldü, {len(failed)} ölçülemedi")
    print(f"  %0 görünürlük (en yüksek öncelik): {len(zero)} klinik")


if __name__ == "__main__":
    sys.exit(main())
