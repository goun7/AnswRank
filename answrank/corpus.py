"""E5 araştırma korpüsü — mini-probe gözlemlerinin kalıcı arşivi + ölçüm-kapısı.

Dürüstlük sözleşmesi:
  * Bir yüzde, yalnızca O ALANI ÖLÇEBİLDİĞİMİZ satırların paydasıyla üretilir.
    Payda 0 ise satır hiç sayı üretmez; "ÖLÇÜLEMEDİ (0 ölçümlü satır)" yazar.
  * collect() hiçbir hükmü uydurmaz: probe patlarsa measured=0 satırı arşivlenir,
    hata detayı (iç bilgi sızıntısı olmasın) NOT olarak sanitize edilir.
  * Korpüs ham gözlemdir; pazarlama iddiasına dönüşmez — rapor metodolojisiyle
    birlikte (örneklem çerçevesi + tarih + araç sürümü) taşınır.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from answrank.probe.miniprobe import MiniProbe, MiniProbeResult

_UNMEASURED = "ÖLÇÜLEMEDİ"


class CorpusStore:
    """corpus_observations tablosunun tek sahibi (yaz + oku + istatistik)."""

    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------ yazma
    def save_observation(self, res: MiniProbeResult, source: str,
                         note: Optional[str] = None) -> None:
        """observation kaydını kalıcı olarak saklar."""
        with self.db._get_connection() as conn:
            conn.execute(
                """INSERT INTO corpus_observations
                   (domain, source, observed_at, measured, verdict,
                    robots_status, llms_status, bot_statuses, blocked_bots,
                    robots_line, llms_line, bots_line, note)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (res.domain, source, datetime.now(timezone.utc).isoformat(),
                 1 if res.measured else 0, res.verdict,
                 res.robots_status, res.llms_status,
                 json.dumps(res.bot_statuses, ensure_ascii=False),
                 json.dumps(res.blocked_bots, ensure_ascii=False),
                 res.robots_line, res.llms_line, res.bots_line, note))
            conn.commit()

    async def collect(self, domains: List[str], politeness_sec: float = 2.0,
                      source: str = "corpus", timeout_sec: float = 6.0) -> int:
        """Verilen domain'leri sırayla yoklar; nazik gecikme uygular; patlayan
        probe measured=0 satırı olur (sayı uydurulmaz, suçlama da yazılmaz)."""
        count = 0
        for i, raw in enumerate(domains):
            if i:
                await asyncio.sleep(politeness_sec)
            host = raw.split("//")[-1].split("/")[0].strip().lower()
            try:
                res = await MiniProbe.run(raw, timeout_sec=timeout_sec)
                self.save_observation(res, source=source)
            except Exception:
                # Detay arşivlenmez (SSRF/iç bilgi sızıntısı yüzeyi olmasın).
                self.save_observation(
                    MiniProbeResult(domain=host, robots_line=f"{_UNMEASURED} (probe koşulmadı)",
                                    llms_line=f"{_UNMEASURED} (probe koşulmadı)",
                                    bots_line="HÜKÜM VERİLEMEDİ (probe koşulmadı)",
                                    blocked_bots=[], probed=0, verdict=_UNMEASURED,
                                    measured=False),
                    source=source, note="probe-exception (detay arşivlenmez)")
            count += 1
        return count

    # ------------------------------------------------------------------ okuma
    def list_observations(self, source: Optional[str] = None) -> List[Dict]:
        """observations kayıtlarını listeler."""
        q = ("SELECT domain, source, observed_at, measured, verdict, robots_status,"
             " llms_status, bot_statuses, blocked_bots, robots_line, llms_line,"
             " bots_line, note FROM corpus_observations")
        args: tuple = ()
        if source:
            q += " WHERE source = ?"
            args = (source,)
        with self.db._get_connection() as conn:
            rows = [dict(r) for r in conn.execute(q + " ORDER BY id", args)]
        for r in rows:
            r["bot_statuses"] = json.loads(r["bot_statuses"] or "{}")
            r["blocked_bots"] = json.loads(r["blocked_bots"] or "[]")
        return rows

    # ------------------------------------------------------------- istatistik
    def stats(self, source: Optional[str] = None) -> Dict:
        """Alan-bazlı paydalar: her metrik yalnız kendi ölçebildiği satırla sayar."""
        rows = self.list_observations(source=source)
        n = len(rows)

        def _frac(pred_rows, num_rows):
            return {"n": len(pred_rows),
                    "pct": (round(100.0 * len(num_rows) / len(pred_rows), 1) if pred_rows else None),
                    "num": len(num_rows)}

        robots_meas = [r for r in rows if "ÖLÇÜLEMEDİ" not in r["robots_line"]]
        robots_open = [r for r in robots_meas if r["robots_line"].startswith("İZİNLİ")]
        llms_meas = [r for r in rows if r["llms_line"] in ("VAR", "YOK")]
        llms_present = [r for r in llms_meas if r["llms_line"] == "VAR"]
        bots_meas = [r for r in rows if r["bot_statuses"]]
        bots_open = [r for r in bots_meas if not r["blocked_bots"]]
        per_bot = {}
        for bot in MiniProbe.MICRO_BOTS:
            seen = [r for r in rows if bot in r["bot_statuses"]]
            blocked = [r for r in seen if bot in r["blocked_bots"]]
            per_bot[bot] = {"seen": len(seen), "blocked": len(blocked),
                            "blocked_pct": (round(100.0 * len(blocked) / len(seen), 1)
                                            if seen else None)}
        verdicts: Dict[str, int] = {}
        for r in rows:
            verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
        return {
            "n": n,
            "unmeasured_rows": sum(1 for r in rows if not r["measured"]),
            "robots_open_pct": _frac(robots_meas, robots_open),
            "robots_llms_present": _frac(llms_meas, llms_present),
            "bots_all_open_pct": _frac(bots_meas, bots_open),
            "per_bot": per_bot,
            "verdicts": verdicts,
            "sources": sorted({r["source"] for r in rows}),
        }


def render_report_md(st: Dict, method: str, title: str = "AnswRank Kamusal Erişilebilirlik Korpüsü") -> str:
    """Markdown korpüs raporu — sayı yalnız ölçümlü paydadan; 0 payda = oran yok."""
    def _pct(cell) -> str:
        if not cell["n"]:
            return f"{_UNMEASURED} (0 ölçümlü satır — oran üretilmez)"
        return f"%{cell['pct']} ({cell['num']}/{cell['n']} ölçümlü satır)"

    lines = [
        f"# {title}",
        "",
        f"**Gözlem sayısı:** n={st['n']} · **Tamamen ölçülemeyen satır:** {st['unmeasured_rows']}",
        "",
        "## Yöntem",
        method,
        "",
        "Araç: `answrank corpus` (mini-probe arşivi). Her satır canlı HTTP tanığıdır;",
        "hiçbir alan tahminle doldurulmamıştır. Paydasız oran üretilmez.",
        "",
        "## Bulgular",
        "",
        "| Gösterge | Sonuç |",
        "|---|---|",
        f"| robots.txt'te AI aramasına izin | {_pct(st['robots_open_pct'])} |",
        f"| llms.txt bulunurluğu | {_pct(st['robots_llms_present'])} |",
        f"| 3 örnek botun tamamına açık | {_pct(st['bots_all_open_pct'])} |",
    ]
    for bot, d in st["per_bot"].items():
        pct = f"%{d['blocked_pct']} engelli ({d['blocked']}/{d['seen']})" if d["seen"] \
            else f"{_UNMEASURED} (0 ölçümlü satır)"
        lines.append(f"| {bot} engelleme payı | {pct} |")
    lines += ["", "## Hüküm dağılımı", ""]
    for v, c in sorted(st["verdicts"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {v}: {c}")
    lines += ["", f"Kaynak etiketleri: {', '.join(st['sources']) or '—'}", ""]
    return "\n".join(lines)
