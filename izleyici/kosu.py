"""Snapshot koşusu: takipli tüm alan adlarını motorla ölçer, tarihli dosyaya yazar.

Snapshot yolu:  olcumler/izleyici/snapshots/<domain>/<YYYY-MM-DD>.json
(Aynı gün tekrar koşulursa üstüne yazar — gün başına bir snapshot.)
"""

from __future__ import annotations

import datetime
import json
import os
import re
from typing import Callable, Optional

from . import takip

SNAP_KOK = os.path.join(takip.IZLE_KOK, "snapshots")
TARIH_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def snapshot_yolu(domain: str, tarih: Optional[str] = None) -> str:
    d = takip.normalle(domain)  # regex doğrulaması: ".."/"/" imkânsız
    t = tarih or datetime.date.today().isoformat()
    if not TARIH_RE.match(t):
        raise ValueError("geçersiz tarih: %r" % (tarih,))
    yol = os.path.join(SNAP_KOK, d, f"{t}.json")
    takip.kapsamda(yol, SNAP_KOK)  # savunma-derinliği: kapsama iddiası
    return yol


def snapshot_yaz(sonuc: dict, yol: str) -> str:
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    kayit = dict(sonuc)
    kayit.setdefault("tarih", datetime.date.today().isoformat())
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(kayit, f, ensure_ascii=False, indent=2)
    return yol


def snapshot_oku(domain: str, tarih: Optional[str] = None) -> Optional[dict]:
    yol = snapshot_yolu(domain, tarih)
    if not os.path.exists(yol):
        return None
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def son_iki_snapshot(domain: str) -> tuple:
    """(eski, yeni) — alfabede son iki tarihli snapshot. (<2 ise None'lar.)"""
    d = takip.normalle(domain)
    dizin = os.path.join(SNAP_KOK, d)
    if not os.path.isdir(dizin):
        return None, None
    tarihler = sorted(fn[:-5] for fn in os.listdir(dizin)
                      if fn.endswith(".json"))
    if len(tarihler) < 2:
        return None, None
    eski = snapshot_oku(d, tarihler[-2])
    yeni = snapshot_oku(d, tarihler[-1])
    return eski, yeni


def kos(domainler: Optional[list] = None, olc_fn: Optional[Callable] = None,
        api_key: Optional[str] = None, sorgular_fn: Optional[Callable] = None,
        kaydet_fn: Optional[Callable] = None) -> list:
    """Takipli (veya verilen) alan adlarını ölçüp snapshot'lar.

    Bağımlılık enjeksiyonu: `olc_fn` (ai_gorunurluk.olc), `sorgular_fn`
    (takip.sorgular_icin), `kaydet_fn` (snapshot_yaz) — testler ağsız koşar.
    """
    import ai_gorunurluk as motor  # LOCAL import — motor değiştirilmez

    olc_fn = olc_fn or motor.olc
    if sorgular_fn is None:
        sorgular_fn = (lambda d, _sec=motor.sorgu_kumesi_sec:
                       takip.sorgular_icin(d, _sec))
    kaydet_fn = kaydet_fn or snapshot_yaz
    api_key = api_key or (motor.env_oku().get("SERPER_API_KEY") or "")
    hedefler = domainler or list(takip.yukle().keys())

    cikti = []
    for d in hedefler:
        sorgular = sorgular_fn(d)
        sonuc = olc_fn(d, sorgular, api_key)
        yol = snapshot_yaz(sonuc, snapshot_yolu(d))
        cikti.append({"domain": d, "puan": sonuc.get("ai_alinti_puani"),
                      "snapshot": yol})
    return cikti
