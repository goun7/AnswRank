"""Delta: iki snapshot arasındaki değişimi hesaplar ve rapora çevirir.

Saf fonksiyonlar — ağ yok, dosya yok. Girdi: motor'un ürettiği snapshot
sözlükleri (ai_gorunurluk.olc çıktısı + "tarih" alanı).
"""

from __future__ import annotations

from typing import List, Optional


def _puan(snap: Optional[dict], alan: str) -> Optional[float]:
    if not snap:
        return None
    v = snap.get(alan)
    return None if v is None else round(float(v), 1)


def _alt_puanlar(snap: Optional[dict]) -> dict:
    if not snap:
        return {}
    return {k: round(float(v.get("puan", 0.0)), 1)
            for k, v in (snap.get("alt_puanlar") or {}).items()}


def hesapla(eski: Optional[dict], yeni: dict) -> dict:
    """İki snapshot (ilk ölçümde eski=None) arasındaki değişim sözlüğü."""
    d: dict = {
        "domain": yeni.get("domain"),
        "t1": (eski or {}).get("tarih") or "—",
        "t2": yeni.get("tarih"),
        "ilk_olcum": eski is None,
    }
    p1, p2 = _puan(eski, "ai_alinti_puani"), _puan(yeni, "ai_alinti_puani")
    d["puan"] = {"eski": p1, "yeni": p2,
                 "degisim": None if p1 is None else round(p2 - p1, 1)}

    a1, a2 = _alt_puanlar(eski), _alt_puanlar(yeni)
    d["alt_puanlar"] = {
        k: {"eski": a1.get(k), "yeni": a2.get(k),
            "degisim": None if k not in a1 else round(a2[k] - a1[k], 1)}
        for k in sorted(set(a1) | set(a2))
    }

    # sorgu bazında: bulundu bayrağı ve sıra
    q1 = {s.get("sorgu"): s for s in ((eski or {}).get("siralama") or {})
          .get("sorgular", [])}
    q2 = {s.get("sorgu"): s for s in (yeni.get("siralama") or {}).get("sorgular", [])}
    degisimler: List[dict] = []
    for sorgu, y in sorted(q2.items()):
        e = q1.get(sorgu)
        satir = {"sorgu": sorgu,
                 "eski_bulundu": None if e is None else e.get("bulundu"),
                 "yeni_bulundu": y.get("bulundu"),
                 "eski_sira": None if e is None else e.get("position"),
                 "yeni_sira": y.get("position")}
        if e is not None and e.get("bulundu") and not y.get("bulundu"):
            satir["olay"] = "dustu"
        elif e is not None and not e.get("bulundu") and y.get("bulundu"):
            satir["olay"] = "girdi"
        elif (e is not None and e.get("bulundu") and y.get("bulundu")
              and e.get("position") != y.get("position")):
            iyilesme = e.get("position") - y.get("position")
            satir["olay"] = "iyilesti" if iyilesme > 0 else "kotulesti"
            satir["degisim_sira"] = abs(iyilesme)
        degisimler.append(satir)
    d["sorgular"] = degisimler
    d["olaylar"] = [x for x in degisimler if x.get("olay")]
    return d


def _fmt(v):
    """Düz değer: 34.2 gibi. Delta işareti burada YOK."""
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{round(v, 1):.1f}"
    return str(v)


def _fmt_delta(v):
    """Değişim: işaretli (+6.8 / -2.0)."""
    if v is None:
        return "—"
    return f"{round(v, 1):+.1f}"


def rapor_md(eski: Optional[dict], yeni: dict) -> str:
    d = hesapla(eski, yeni)
    satirlar = [
        "# AEO Delta Raporu — %s" % d["domain"],
        "",
        "Ölçüm: %s → %s%s" % (d["t1"], d["t2"],
                              "  *(ilk ölçüm — taban çizgisi)*"
                              if d["ilk_olcum"] else ""),
        "",
        "**AI Alıntı Puanı: %s → %s (%s)**" % (
            _fmt(d["puan"]["eski"]), _fmt(d["puan"]["yeni"]),
            _fmt_delta(d["puan"]["degisim"])),
        "",
        "| Alt puan | Önce | Sonra | Δ |",
        "|---|---|---|---|",
    ]
    for k, v in d["alt_puanlar"].items():
        satirlar.append("| %s | %s | %s | %s |" % (
            k, _fmt(v["eski"]), _fmt(v["yeni"]), _fmt_delta(v["degisim"])))
    satirlar += ["", "| Sorgu | Önce | Sonra | Olay |", "|---|---|---|---|"]
    for s in d["sorgular"]:
        olay = s.get("olay") or ""
        if olay == "iyilesti":
            olay = "↑ +%s sıra" % s.get("degisim_sira")
        elif olay == "kotulesti":
            olay = "↓ -%s sıra" % s.get("degisim_sira")
        elif olay == "girdi":
            olay = "★ ilk 10'a girdi"
        elif olay == "dustu":
            olay = "⚠ ilk 10'dan çıktı"
        satirlar.append("| %s | %s | %s | %s |" % (
            s["sorgu"], _fmt(s["eski_sira"]), _fmt(s["yeni_sira"]), olay))
    return "\n".join(satirlar) + "\n"
