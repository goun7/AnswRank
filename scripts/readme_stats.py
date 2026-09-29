#!/usr/bin/env python3
"""README istatistik üretici — her sayıyı KODDAN/healthz'den türetir.

Bu portföyün tekrar eden zayıflığı: README'deki sayılar elle yazılıp
koddan kopup gidiyor (örn. "936 test" gerçekte 1069 idi). Bu script
README'e giren HER sayıyı canlı kaynaktan üretir — elle yazma YOK.

Kullanım:
    .venv/bin/python scripts/readme_stats.py          # tüm sayılar
    .venv/bin/python scripts/readme_stats.py --json   # makine okunur

Kaynaklar ( hiçbiri elle girilmez):
    test sayısı  → pytest tests/ ( çalıştırılır)
    fiyatlar     → healthz HTTP + x402_servis.py sabitleri
    bot sayısı   → answrank.config.settings.ai_bots_total
    WAF botları  → WAFProbeEngine.AI_CRAWLER_USER_AGENTS
    API path     → FastAPI app.routes
    servisler    → start_services.sh start_svc çağrıları
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_KOK))

_VENV_PYTHON = str(_KOK / ".venv" / "bin" / "python")
_START_SCRIPT = Path("/home/gokun/projects/01_unicorn/00-gateway/start_services.sh")
_HEALTHZ_URL = "http://127.0.0.1:8007/healthz"


def _test_sayisi() -> tuple[int, int, int]:
    """pytest tests/ çalıştır → ( passed, failed, total)."""
    try:
        sonuc = subprocess.run(
            [_VENV_PYTHON, "-m", "pytest", "tests/", "-q"],
            capture_output=True, text=True, timeout=280,
            cwd=str(_KOK),
        )
        cikti = sonuc.stdout + sonuc.stderr
        m = re.search(r"^(\d+) passed(?:, (\d+) failed)?", cikti.strip().splitlines()[-1] if cikti.strip() else "")
        if not m:
            return (-1, -1, -1)
        passed = int(m.group(1))
        failed = int(m.group(2) or 0)
        return (passed, failed, passed + failed)
    except Exception as e:
        print(f"  ⚠ test sayısı alınamadı: {e}", file=sys.stderr)
        return (-1, -1, -1)


def _fiyatlar() -> dict:
    """Fiyatları healthz'den ( düşerse KOD sabitlerinden) al."""
    fiyatlar = {}
    # 1) healthz ( canlı)
    try:
        import urllib.request
        with urllib.request.urlopen(_HEALTHZ_URL, timeout=8) as r:
            hz = json.load(r)
        fiyatlar = {k: v for k, v in hz.get("prices", {}).items()}
        fiyatlar["daily_quota"] = hz.get("daily_quota")
        fiyatlar["ledger_chain_valid"] = hz.get("ledger_chain_valid")
    except Exception:
        pass
    # 2) KOD sabitleri ( her zaman doğru kaynak) — env gerekebilir
    try:
        _os = __import__("os")
        _os.environ.setdefault("UNPUMP_TREASURY_EOA",
                               "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5")
        _os.environ.setdefault("ANSWRANK_MAINNET_PAY_TO",
                               "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5")
        _os.environ.setdefault("ANSWRANK_SELLER_SECRET",
                               "readme-stats-read-only")
        import x402_servis as xs
        fiyatlar["audit_kod"] = f"${xs.PRICE_AUDIT}"
        fiyatlar["citations_kod"] = f"${xs.PRICE_CITATIONS}"
        fiyatlar["fix_kod"] = f"${xs.PRICE_FIX}"
        fiyatlar["daily_quota_kod"] = f"${xs.DAILY_QUOTA}"
    except Exception as e:
        print(f"  ⚠ kod sabitleri alınamadı: {e}", file=sys.stderr)
    return fiyatlar


def _bot_sayilari() -> dict:
    """AI bot kaydı: config.py'den ( single source of truth)."""
    try:
        from answrank.config import settings
        from answrank.audit.waf_probe import WAFProbeEngine
        return {
            "ai_bots_total": settings.ai_bots_total,
            "tier_arama": len(settings.ai_bots_search),
            "tier_egitim": len(settings.ai_bots_training),
            "tier_kullanici_ajani": len(settings.ai_bots_user_agents),
            "tier_summary": settings.ai_bots_tier_summary,
            "waf_probe_botlari": len(WAFProbeEngine.AI_CRAWLER_USER_AGENTS),
        }
    except Exception as e:
        print(f"  ⚠ bot sayıları alınamadı: {e}", file=sys.stderr)
        return {}


def _api_pathleri() -> dict:
    """REST API path/handler sayısı: FastAPI app.routes'tan."""
    try:
        from answrank.api import app as api_mod
        app = getattr(api_mod, "app", None)
        if app is None:
            return {}
        yollar, handler = set(), 0
        for rota in app.routes:
            try:
                yontemler = getattr(rota, "methods", set()) or set()
                if yontemler & {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                    handler += 1
                    yollar.add(rota.path)
            except Exception:
                pass
        return {"dokümante_path": len(yollar), "handler": handler}
    except Exception as e:
        print(f"  ⚠ API pathleri alınamadı: {e}", file=sys.stderr)
        return {}


def _servis_sayisi() -> dict:
    """Servis filanı: start_services.sh start_svc çağrılarından."""
    try:
        metin = _START_SCRIPT.read_text(encoding="utf-8", errors="ignore")
        servisler = re.findall(r"start_svc\s+(\S+)", metin)
        benzersiz = sorted(set(servisler))
        return {
            "toplam": len(servisler),
            "benzersiz": len(benzersiz),
            "liste": benzersiz,
        }
    except Exception as e:
        print(f"  ⚠ servis sayısı alınamadı: {e}", file=sys.stderr)
        return {}


def _charge_shield() -> dict:
    """ChargeShield ters-ibraz fiyatı — FARKLI servis ( AnswRank değil)."""
    # README'de $0.25/ibraz — bu Unpump.cash'in başka servisi.
    # AnswRank fiyat tablosuyla KARIŞMAMASI için ayrı tutulur.
    return {
        "servis": "ChargeShield",
        "hizmet": "ters-ibraz savunması",
        "fiyat": "$0.25/ibraz",
        "uyari": "AnswRank /audit $0.05'ten FARKLI bir servistir — "
                 "karışıklık: aynı fiyat tablosunda DEĞİL, ayrı",
    }


def tum_sayilar() -> dict:
    passed, failed, total = _test_sayisi()
    return {
        "testler": {"passed": passed, "failed": failed, "total": total},
        "fiyatlar": _fiyatlar(),
        "botlar": _bot_sayilari(),
        "api": _api_pathleri(),
        "servisler": _servis_sayisi(),
        "charge_shield": _charge_shield(),
    }


def main() -> None:
    if "--json" in sys.argv:
        print(json.dumps(tum_sayilar(), ensure_ascii=False, indent=1))
        return
    d = tum_sayilar()
    print("═" * 60)
    print("README İSTATİSTİKLERİ — koddan/healthz'den ÜRETİLDİ")
    print("═" * 60)
    t = d["testler"]
    print(f"\n[Testler]")
    print(f"  passed      : {t['passed']}")
    print(f"  failed      : {t['failed']}")
    print(f"  total       : {t['total']}")
    f = d["fiyatlar"]
    print(f"\n[Fiyatlar — x402 USDC]")
    print(f"  /audit      : {f.get('audit_kod', '?')} ( healthz: {f.get('audit', '?')})")
    print(f"  /citations  : {f.get('citations_kod', '?')} ( healthz: {f.get('citations', '?')})")
    print(f"  /fix        : {f.get('fix_kod', '?')} ( healthz: {f.get('fix', '?')})")
    print(f"  daily quota : {f.get('daily_quota_kod', '?')}")
    b = d["botlar"]
    print(f"\n[AI bot kaydı]")
    print(f"  toplam      : {b.get('ai_bots_total', '?')}")
    print(f"  WAF probu   : {b.get('waf_probe_botlari', '?')} bot")
    a = d["api"]
    print(f"\n[REST API]")
    print(f"  path        : {a.get('dokümante_path', '?')}")
    print(f"  handler     : {a.get('handler', '?')}")
    s = d["servisler"]
    print(f"\n[Servis filası]")
    print(f"  servis      : {s.get('toplam', '?')} ( start_services.sh)")
    c = d["charge_shield"]
    print(f"\n[ChargeShield — FARKLI servis]")
    print(f"  {c['fiyat']} — {c['uyari']}")
    print("\n" + "═" * 60)


if __name__ == "__main__":
    main()
