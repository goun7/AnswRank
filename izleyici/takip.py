"""Takip listesi: hangi alan adları izleniyor, hangi sorgu kümeleriyle.

Depolama: olcumler/izleyici/takip.json — motor'un OLCUM_DIZINI altında
tutulur, böylece tüm izleyici verisi tek kökte toplanır.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IZLE_KOK = os.path.join(HERE, "olcumler", "izleyici")
TAKIP_DOSYASI = os.path.join(IZLE_KOK, "takip.json")

# Alan adı: nokta-ayrı, boş etiket yok -> ".." ve "/" mümkün değil.
# W2'de domain web formundan (güvenilmeyen giriş) gelecek; yol-elemanı
# olarak kullanılmadan ÖNCE burada sıkıştırılır.
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
    r"(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")


def normalle(domain: str) -> str:
    d = (domain or "").lower().strip()
    for on in ("https://", "http://"):
        if d.startswith(on):
            d = d[len(on):]
    d = d.rstrip("/").split("/")[0].removeprefix("www.")
    if not DOMAIN_RE.match(d):
        raise ValueError("geçersiz alan adı: %r" % (domain,))
    return d


def kapsamda(yol: str, kok: str) -> str:
    """Yol <kok> içinde çözümlenmeli — aksi hâlde ValueError."""
    kok_tam = os.path.realpath(os.path.abspath(kok))
    tam = os.path.realpath(os.path.abspath(yol))
    if tam != kok_tam and not tam.startswith(kok_tam + os.sep):
        raise ValueError("yol izinli kökün dışında: %r" % (yol,))
    return tam


def yukle(yol: str = TAKIP_DOSYASI) -> Dict[str, dict]:
    kapsamda(yol, IZLE_KOK)
    if not os.path.exists(yol):
        return {}
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def kaydet(takip: Dict[str, dict], yol: str = TAKIP_DOSYASI) -> str:
    kapsamda(yol, IZLE_KOK)
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(takip, f, ensure_ascii=False, indent=2, sort_keys=True)
    return yol


def ekle(domain: str, sorgular: Optional[List[str]] = None,
         yol: str = TAKIP_DOSYASI) -> Dict[str, dict]:
    d = normalle(domain)
    takip = yukle(yol)
    kayit = takip.get(d, {})
    if sorgular:
        kayit["sorgular"] = list(dict.fromkeys(sorgular))
    kayit.setdefault("sorgular", [])
    kayit.setdefault("eklenme", __import__("datetime").date.today().isoformat())
    takip[d] = kayit
    kaydet(takip, yol)
    return takip


def cikar(domain: str, yol: str = TAKIP_DOSYASI) -> bool:
    d = normalle(domain)
    takip = yukle(yol)
    if d not in takip:
        return False
    del takip[d]
    kaydet(takip, yol)
    return True


def sorgular_icin(domain: str, motor_sorgu_sec) -> List[str]:
    """Takip kaydındaki sorgular; yoksa motorun kümesinden 5 tanesi.

    `motor_sorgu_sec` — ai_gorunurluk.sorgu_kumesi_sec (bağımlılık enjekte
    edilir ki testler ağa/dosyaya bağımlı kalmasın).
    """
    kayit = yukle().get(normalle(domain), {})
    q = kayit.get("sorgular") or []
    return q or motor_sorgu_sec(5)
