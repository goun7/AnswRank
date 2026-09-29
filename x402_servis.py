"""AnswRank x402 ödemeli servis — Sester metering katmanı ile dogfood.

İş modeli: AI-görünürlük denetimi çağrı başına ücretli (deneysel):
  - /audit      $0.25  (8-kategori AEO/GEO denetimi, 0-100)
  - /citations  $0.75  (5 LLM × soru bankası — en yüksek maliyetli araç)
  - /fix        $0.20  (robots/llms/JSON-LD düzeltme paketi)

Montaj: Sester (ödeme/metering/quota/receipt) + AnswRank (AEO/GEO çekirdeği).
Kalıp: 92-VadeDostu / 53-RepriceAI / 25-ClearTag ile AYNI x402_servis.py deseni.

GÜVENLİK: mainnet modunda imzaya ek olarak gerçek Base zincir USDC transferi
aranır (sıfır-ödeme bypass kapalı). Testler UNPUMP_TEST=1 ile sim'e düşer.
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from sester import __version__ as SESTER_VERSION
from sester.ledger import Ledger
from sester.middleware import SesterMeter
from mainnet_guard import require_mainnet_payment, resolve_treasury

from answrank.audit.engine import AuditEngine
from answrank.citations.runner import MultiLLMCitationRunner
from answrank.reporting.fix_generator import FixGenerator
from answrank.reporting.generator import ReportGenerator
from answrank.db import Database

# --- fiyatlandırma: araç başına (çok-LLM citations en pahalı) ---
# NOT: SesterMeter ASGI katmanında ÖNCE çalışır ve charge_receipt'i taban
# PRICE ile yazar. require_mainnet_payment ise endpoint başına fiyatı
# doğrular. Tutarlılık için SesterMeter'ın taban fiyatı = en düşük araç
# fiyatı olmalı (VadeDostu deseni); çağrı başına gerçek fiyatlandırma
# mainnet doğrulamasında ve _charge kaydında tutulur.
PRICE_AUDIT = float(os.environ.get("ANSWRANK_PRICE_AUDIT", "0.05"))
PRICE_CITATIONS = float(os.environ.get("ANSWRANK_PRICE_CITATIONS", "1.20"))
PRICE_FIX = float(os.environ.get("ANSWRANK_PRICE_FIX", "0.20"))
# SesterMeter'ın ASGI kapısındaki taban fiyat (en düşük araç fiyatı)
PRICE = min(PRICE_AUDIT, PRICE_CITATIONS, PRICE_FIX)

# mainnet: gerçek zincir USDC transferi zorunlu (sıfır-ödeme bypass kapanır)
MAINNET_PAY_TO = resolve_treasury("answrank")  # tek-kasa: UNPUMP_TREASURY_EOA (fail-closed)
DAILY_QUOTA = float(os.environ.get("ANSWRANK_DAILY_QUOTA", "10.00"))
# GUVENLIK: zayif default YOK — demo-secret-v0'ya dusmek receipt-zincirini
# baska-secret ile yazardi ( bu DB'nin bozuk-verify sebebiydi: env gelmeyince
# default'a dustu → verify_chain False). Bos secret = fail-closed.
_raw_secret = os.environ.get("ANSWRANK_SELLER_SECRET", "")
if not _raw_secret:
    raise SystemExit(
        "secret-required: ANSWRANK_SELLER_SECRET-ZORUNLU — bos/zayif-secret "
        "receipt HMAC zincirini baska anahtarla yazar ( verify_chain False).")
SELLER_SECRET = _raw_secret
PAY_TO = os.environ.get("ANSWRANK_PAY_TO", "sester:answrank")
DB_PATH = os.environ.get(
    "ANSWRANK_DB", str(Path.home() / ".workspace" / "answrank" / "receipts.sqlite")
)

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
# AT-193-uyumu: Ledger secret-ZORUNLU; SesterMeter ile AYNI secret.
ledger = Ledger(DB_PATH, secret=SELLER_SECRET)

# --- canlilik sayaci: /healthz kac kez sorgulandi (process-ici, thread-safe) ---
# Gerekce: dis izleyici ( systemd/watchdog) her 10 dk'da /healthz'e vurur.
# call_count, servisin gercekten ayakta ve yanit verdigini ZAMANSAL olarak
# kanitlar — "up" statik bir bayrakken, artan sayaci canlilik kantidir.
_healthz_lock = threading.Lock()
_healthz_call_count = 0

app = FastAPI(
    title="AnswRank ödemeli servis",
    version="0.1.0",
    description="x402 ödemeli AI-görünürlük denetim servisi (Sester metering ile)",
)
app.add_middleware(
    SesterMeter,
    ledger=ledger,
    price=PRICE,
    daily_quota=DAILY_QUOTA,
    currency="USDC",  # USDC-sim -> USDC: gercek musteri yolu ( KOD-1)
                      # mainnet_verify.py gercek Base USDC arar:
                      # 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
                      # Receipt zinciri etkilenmez ( HMAC+seq bagimsiz).
    secret=SELLER_SECRET,
    pay_to=PAY_TO,
    exempt_prefixes=(
        "/healthz", "/ozet", "/docs", "/openapi.json", "/redoc",
        "/favicon.ico", "/ornek",
        # K3+K6: DM ölçüm okuma — read-only, ödeme GEREKMEZ ( 402 DEĞİL)
        "/olcum",
    ),
)

# --- AnswRank çekirdeği ( MCP server.py ile aynı nesneler) ---
engine = AuditEngine()
runner = MultiLLMCitationRunner()
fix_gen = FixGenerator()
rep_gen = ReportGenerator()
db = Database()


# ---------------------------------------------------------------- modeller

class AuditRequest(BaseModel):
    url: str
    sector: str = "general"


class CitationRequest(BaseModel):
    brand_name: str
    domain: str
    sector: str = "dental"
    city: str = "İstanbul"
    lang: str = "tr"


class FixRequest(BaseModel):
    domain: str
    brand_name: Optional[str] = None
    sector: str = "dental"
    city: str = "İstanbul"


# ---------------------------------------------------------------- yardımcılar

# DM-ölçüm çekirdeği ( K1+K5+K7) — docs/DM_OLCUM_ALTYAPISI.md
# ⚠ ETİK KAPI: ref KİŞİYE ÖZGÜ DEĞİLDİR — kişisel tanımlayıcı YASAK.
#    gizli takip YOK; yalnızca DM-varyant atfı yapar ( açık izleme).
_REF_LOCK = threading.Lock()
_REF_PATTERN = re.compile(r"^unpump-(p[123])([ab])-(tr|en)-(\d{2})$")
# sayaçlar: ref -> {deneme, odeme}
_REF_SAYACLAR: dict[str, dict[str, int]] = {}


def _ref_ayir(request: Request) -> str | None:
    """K1: ?ref= URL parametresini ayrıştırır — KATI biçim doğrulaması ile.

    Biçim: unpump-<profil><varyant>-<dil>-<sira>
    Örnek: unpump-p1a-tr-01

    K7 ETİK KAPI: ref kişisel tanımlayıcı içeremez. Yalnızca
    DM-varyant atfı için kullanılır — kişiyi tanımlamaz.
    """
    try:
        ham = request.query_params.get("ref")
    except Exception:
        return None
    if not ham:
        return None
    ham = str(ham).strip()[:64]  # uzunluk sınırı ( kotu kullanım)
    if _REF_PATTERN.match(ham) is None:
        return None  # biçim dışı → sessizce yok say ( kısıt amaclı)
    return ham


def _ref_sayac_artir(ref: str | None, anahtar: str) -> None:
    """K5: ref altında sayaç artırır ( thread-safe).

    anahtar: 'deneme' ( 402/200 cagrisi) | 'odeme' ( 200 + gercek odeme)
    """
    if not ref or anahtar not in ("deneme", "odeme"):
        return
    with _REF_LOCK:
        kayit = _REF_SAYACLAR.setdefault(ref, {"deneme": 0, "odeme": 0})
        kayit[anahtar] = kayit.get(anahtar, 0) + 1


def _ref_kisisel_veri_filtre(ref: str | None) -> str | None:
    """K7 ETİK KAPI: ref kisisel tanimlayici iceriyorsa REDDET.

    Izin verilen: yalnizca 'unpump-p<1-3><a-b>-<tr|en>-<NN>' bicimi.
    Reddedilenler: e-posta, isim, telefon, serbest metin.
    """
    if not ref:
        return None
    return ref if _REF_PATTERN.match(ref) else None


def ref_ozet() -> dict:
    """K5 read-only: ref sayaclari doner ( test + ic-denetim icin)."""
    with _REF_LOCK:
        return {k: dict(v) for k, v in _REF_SAYACLAR.items()}


def _charge(request: Request, price: float, tool: str, detail: dict) -> int:
    """Ödeme kanıtı ledger'a: 'ne için ödendi' hash-chain kaydı.

    Middleware ödemeyi zaten doğruladı; bu satır machine-checkable kanıttır
    ( müşteri tarafından yeniden-hesaplanabilir).
    """
    seq = ledger.append(
        "charge_receipt", "buyer", tool, price, payload=detail,
    )
    return seq.get("seq", -1) if isinstance(seq, dict) else -1


def _payer(request: Request) -> str:
    try:
        return str(request.headers.get("X-Payer-Address", "?"))[:42]
    except Exception:
        return "?"


# ---------------------------------------------------------------- endpoints

@app.get("/healthz")
def healthz() -> dict:
    # Canlilik kaniti: her sorgulamada sayaci artir.
    # Threadpool'da calistigi icin lock altinda artiriyoruz.
    global _healthz_call_count
    with _healthz_lock:
        _healthz_call_count += 1
        count = _healthz_call_count
    return {
        "status": "ok",
        "sester": SESTER_VERSION,
        "ledger_chain_valid": ledger.verify_chain(),
        "healthz_call_count": count,
        "prices": {"audit": f"${PRICE_AUDIT}",
                   "citations": f"${PRICE_CITATIONS}",
                   "fix": f"${PRICE_FIX}"},
        "daily_quota": f"${DAILY_QUOTA}",
        # K5: DM ölçüm sayaçları ( açık, kişisiz — K7 etik kapı)
        "dm_ref_counts": ref_ozet(),
    }


# K3: /olcum rate-limit ( ayni IP'den saniyede 1 istek)
_OLCUM_LOCK = threading.Lock()
_OLCUM_IP: dict[str, float] = {}
_OLCUM_MIN_ARALIK = 1.0  # saniye

# DM outbox yolu ( DRAFT e-postalar burada — gonderim YOK)
_OUTBOX_DIZIN = Path(__file__).resolve().parent / "outbox"
_SENT_ISARETLERI = ("sent", "delivered", "gonderildi")


def _dm_hold_durumu() -> bool:
    """DM HOLD'i GERCEK outbox durumundan turetir ( hardcoded DEGIL).

    Kural: outbox'ta DRAFT e-posta VAR ve hicbiri gonderilmemis ( sent
    isareti YOK) ise → HOLD AKTIF ( true).
    Outbox bosalirsa veya sent isareti varsa → HOLD kalkti ( false).

    ⚠ Bu fonksiyon outbox'a YAZMAZ — yalnizca DURUM OKUR ( K4 gonderim
      YASAK; buradan hicbir DM gonderilmez).
    """
    try:
        if not _OUTBOX_DIZIN.is_dir():
            return False  # outbox yok → gonderim altyapisi kaldirilmis
        dosyalar = list(_OUTBOX_DIZIN.glob("*.eml"))
        if not dosyalar:
            return False  # hic DRAFT yok → HOLD kalkmis demektir
        # herhangi biri gonderilmis mi? ( sent isareti)
        for dosya in dosyalar:
            try:
                metin = dosya.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            kucuk = metin.lower()
            if any(isaret in kucuk for isaret in _SENT_ISARETLERI):
                return False  # en az biri gonderilmis → HOLD KALKTI
        return True  # DRAFT var, sent YOK → HOLD AKTIF
    except Exception:
        return False


def _olcum_rate_limit_ok(istek) -> bool:
    """K3 güvenlik: ayni IP'den saniyede 1 istek — abuse'e karsi.

    Kimlik dogrulama YOK ( read-only) ama rate-limit zorunlu.
    """
    try:
        ip = str(istek.client.host) if istek.client else "?"
    except Exception:
        ip = "?"
    import time as _time
    simdi = _time.monotonic()
    with _OLCUM_LOCK:
        son = _OLCUM_IP.get(ip, 0.0)
        if simdi - son < _OLCUM_MIN_ARALIK:
            return False
        _OLCUM_IP[ip] = simdi
    return True


@app.get("/olcum")
def olcum(istek: Request) -> dict:
    """K3 read-only: DM ölçüm sayaçlarini doner ( ödeme GEREKMEZ — 402 DEGIL).

    ⚠ ETİK ( K7): yalnizca 'unpump-p<1-3><a-b>-<tr|en>-<NN>' kimlikleri
      vardir — kisisel tanimlayıcı YOK. Gizli takip DEGIL, acik izleme.

    Güvenlik: kimlik dogrulama YOK ( read-only) + rate-limit ( 1 istek/s).
    """
    if not _olcum_rate_limit_ok(istek):
        raise HTTPException(status_code=429, detail="rate-limit: saniyede 1 istek")
    sayac = ref_ozet()
    hold = _dm_hold_durumu()  # GERCEK outbox durumundan ( hardcoded DEGIL)
    return {
        "status": "ok",
        "aciklama": "DM-varyant atif sayaclari ( kisisiz, acik izleme)",
        "dm_hold": hold,
        "dm_ref_counts": sayac,
    }


@app.get("/olcum/rapor")
def olcum_rapor(istek: Request) -> dict:
    """K6: A/B karsilastirma raporu — her profil icin A ( uzun) vs B ( kisa).

    DÜRÜST cikti ZORUNLU ( her iki durumda):
      - 0 gonderim + dm_hold=true  → "Henuz gonderim yok... DM HOLD aktif"
      - test verisi ( sandbox) varsa → "test verisi, GERCEK gonderim YOK"
      - dm_hold GERCEK outbox durumundan turetilir ( hardcoded DEGIL)
    """
    if not _olcum_rate_limit_ok(istek):
        raise HTTPException(status_code=429, detail="rate-limit: saniyede 1 istek")
    sayac = ref_ozet()
    hold = _dm_hold_durumu()  # GERCEK outbox durumundan
    aktif = any(v.get("deneme", 0) or v.get("odeme", 0) for v in sayac.values())
    if not aktif:
        # 0 gonderim — HOLD aktif veya kalkmis ama veri yok
        ek = " DM HOLD aktif." if hold else " ( DM HOLD kalkti ama veri yok.)"
        return {
            "status": "ok",
            "rapor": "Henüz gönderim yok — 0 gösterim, 0 tıklama, "
                     "0 deneme, 0 ödeme. Bu rapor DM HOLD kalktıktan "
                     "sonra veri üretir." + ek,
            "dm_hold": hold,
            "varyantlar": {},
        }
    # A/B karsilastirma: profil -> {A: {deneme,odeme}, B: {...}}
    sonuc: dict[str, dict[str, dict[str, int]]] = {}
    for ref, v in sayac.items():
        m = _REF_PATTERN.match(ref)
        if not m:
            continue
        profil, varyant, _dil, _sira = m.groups()
        profil_adi = {"p1": "AI-oncul SaaS", "p2": "Dubai dis klinigi",
                      "p3": "Bireysel gelistirici"}.get(profil, profil)
        sonuc.setdefault(profil_adi, {"A": {"deneme": 0, "odeme": 0},
                                      "B": {"deneme": 0, "odeme": 0}})
        sonuc[profil_adi][varyant.upper()]["deneme"] += v.get("deneme", 0)
        sonuc[profil_adi][varyant.upper()]["odeme"] += v.get("odeme", 0)
    # DÜRÜST not: HOLD aktifken olusan tum veri TEST verisidir ( sandbox)
    test_notu = ""
    if hold:
        test_notu = (" ⚠ Bu sayılar TEST verisidir ( sandbox) — GERÇEK "
                     "gönderim YOK ( DM HOLD aktif).")
    return {
        "status": "ok",
        "rapor": "A/B karsilastirma: A=uzun, B=kisa ( her profil)" + test_notu,
        "dm_hold": hold,
        "varyantlar": sonuc,
    }


@app.get("/ozet")
def ozet() -> dict:
    """Ücretsiz: servis durumu + ledger özeti (satıcı iç-denetim)."""
    per_agent = ledger.per_agent_summary() if hasattr(ledger, "per_agent_summary") else {}
    return {
        "prices": {"audit": f"${PRICE_AUDIT}",
                   "citations": f"${PRICE_CITATIONS}",
                   "fix": f"${PRICE_FIX}"},
        "daily_quota": f"${DAILY_QUOTA}",
        "ledger_seq": getattr(ledger, "next_seq", lambda: -1)(),
        "chain_valid": ledger.verify_chain(),
        "per_agent": per_agent,
        "durust_sinir": {
            "arastirma_kaynagi": ("arXiv:2609.29701 ( Huang et al.; "
                                  "cok-ajan cesitlilik/cekiyor)"),
            "sinir": ("siralama SKOR-tabanlidir; ANCAK skor KESIN "
                      "kaliteyi OLCEMEZ — yanlis-siralama olabilir; "
                      "karar-verme icin TEK basina yeterli DEGILDIR"),
            "uyari": "arastirma-uyumluluk ( toplu degerlendirme)",
        },
    }


@app.post("/audit")
async def audit(request: Request, req: AuditRequest) -> Dict[str, Any]:
    """Ödemeli: 8-kategori AEO/GEO denetimi → 0-100 skor + tavsiyeler.

    Header: X-Payment: Sester-EVM <exact-sester zarfı>  (middleware doğrular)
    ?ref=unpump-p<1-3><a-b>-<tr|en>-<NN> — DM-varyant atfı ( açık, kişisiz)
    """
    # K1: DM ölçüm ref'ini ayrıştır ( K7 etik kapıdan geçerek)
    ref = _ref_kisisel_veri_filtre(_ref_ayir(request))
    _ref_sayac_artir(ref, "deneme")  # K5: çağrı denemesi sayısı

    require_mainnet_payment(
        request, price=PRICE_AUDIT, pay_to=MAINNET_PAY_TO,
        service_name="answrank",
    )
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="url zorunlu")

    try:
        res = await engine.audit_url(req.url, sector=req.sector)
    except Exception:
        raise HTTPException(status_code=500, detail="denetim hatası")

    await db.save_audit(res)
    # K2: receipt'e DM ref'i yazılır — ödeme kanıtına izleme kimliği
    seq = _charge(request, PRICE_AUDIT, "/audit",
                  {"domain": res.domain, "overall_score": res.overall_score,
                   "dm_ref": ref})
    if ref:
        _ref_sayac_artir(ref, "odeme")  # K5: ödeme yapıldı ( 200)
    return {
        "audit_id": res.audit_id,
        "domain": res.domain,
        "overall_score": res.overall_score,
        "score_band": res.score_band,
        "lost_revenue_monthly_try": res.lost_revenue_estimate_monthly_try,
        "categories": res.categories.model_dump(),
        "recommendations": [r.model_dump() for r in res.recommendations],
        "crawl_warnings": res.crawl_warnings,
        "ledger_seq": seq,
    }


@app.post("/citations")
async def citations(request: Request, req: CitationRequest) -> Dict[str, Any]:
    """Ödemeli: 5-LLM marka atıf ölçümü (EN PAHALI araç — çok-LLM çağrısı).

    Header: X-Payment: Sester-EVM <exact-sester zarfı>
    """
    require_mainnet_payment(
        request, price=PRICE_CITATIONS, pay_to=MAINNET_PAY_TO,
        service_name="answrank",
    )
    if not req.brand_name or not req.domain:
        raise HTTPException(status_code=400, detail="brand_name ve domain zorunlu")

    try:
        res = await runner.run_citations(
            brand_name=req.brand_name,
            domain=req.domain,
            sector=req.sector,
            city=req.city,
            lang=req.lang,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="atıf ölçüm hatası")

    await db.save_citations(res)
    seq = _charge(request, PRICE_CITATIONS, "/citations",
                  {"brand": res.brand_name,
                   "citation_rate": res.citation_rate_percentage})
    return {
        "brand": res.brand_name,
        "citation_rate_percentage": res.citation_rate_percentage,
        "citations_found": res.brand_citations_found,
        "total_runs": res.total_runs,
        "live_items_count": res.live_items_count,
        "live_response_rate_percentage": res.live_response_rate_percentage,
        "is_fully_live": res.is_fully_live,
        "top_competitors": res.top_competitors,
        "ledger_seq": seq,
    }


@app.post("/fix")
async def fix(request: Request, req: FixRequest) -> Dict[str, Any]:
    """Ödemeli: robots.txt + llms.txt + JSON-LD düzeltme paketi.

    Header: X-Payment: Sester-EVM <exact-sester zarfı>
    """
    require_mainnet_payment(
        request, price=PRICE_FIX, pay_to=MAINNET_PAY_TO,
        service_name="answrank",
    )
    if not req.domain:
        raise HTTPException(status_code=400, detail="domain zorunlu")

    brand = req.brand_name or req.domain
    try:
        result = {
            "robots_txt": fix_gen.generate_robots_txt(req.domain),
            "llms_txt": fix_gen.generate_llms_txt(brand, req.domain, req.sector, req.city),
            "json_ld": fix_gen.generate_json_ld(brand, req.domain, req.sector, req.city),
        }
    except Exception:
        raise HTTPException(status_code=500, detail="düzeltme paketi hatası")

    seq = _charge(request, PRICE_FIX, "/fix", {"domain": req.domain})
    result["ledger_seq"] = seq
    return result
