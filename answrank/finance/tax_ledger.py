"""Turkish & International Fiscal Separation Ledger for AnswRank.

Implements statutory tax bifurcation:
1. Foreign Software & Data Analysis Export (Yurtdışı Hizmet İhracatı):
   - KVK 10/1-ğ & GVK 89/13: 100% Corporate/Income Tax Exemption
     (11257 sayılı Cumhurbaşkanı Kararı, RG 33239, 30 Nis 2026: %80 → %100)
   - KDV Kanunu 11/1-a (İstisna Kodu 302): 0% VAT
2. Domestic B2B Services (Yurtiçi Satış):
   - Standard 20% VAT
   - 100% Taxable Base
Generates accountant-ready monthly reports (Mali Müşavir Hazır Raporu).
"""

from datetime import datetime, timezone
from enum import Enum
import json
import logging
import os
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from answrank.config import settings

logger = logging.getLogger("answrank.tax_ledger")


class TaxRegime(str, Enum):
    EXPORT_SERVICE = "EXPORT_SERVICE"      # UK, US, DE, EU, UAE clients (100% Tax Exemption, 0% VAT)  # 11257 KKH
    DOMESTIC_SERVICE = "DOMESTIC_SERVICE"  # TR local clients (Standard 20% VAT, 100% Taxable Base)
    MOBILE_AD_REVENUE = "MOBILE_AD_REVENUE"  # GVK Mükerrer 20/B: AdMob/store/donations — %15 stopaj
                                             # bankadan otomatik kesinti; fatura/defter yok
                                             # yıllık 5.300.000 TL istisna üst sınırı


class FiscalInvoiceRecord(BaseModel):
    """Statutory invoice record with full tax and currency breakdown.

    TEK-MÜKELLEF modeli (25 Eyl vergi optimizasyonu): tüm ürünler
    ( AnswRank, ClearTag, PQHaven, ... ) TEK mükellef altında tek
    banka hesabına — product_name ürün ayrımını korur ama mükellep
    tek. Yurtiçi/yurt dışı rejim ayrımı KORUNUR (vergi için kritik).
    """
    invoice_id: str
    client_brand: str
    client_country: str
    regime: TaxRegime
    currency: str  # "GBP", "USD", "EUR", "TRY"
    amount_foreign: float
    exchange_rate_tcmb: float  # Rate to TRY actually used for conversion
    fx_source: str = "static_default"  # static_default | env | live:<provider> | custom | explicit
    amount_try: float

    # TEK-MÜKELLEF: hangi ürün ( çok-ürün tek-kasa ayrımı)
    product_name: str = "unknown"

    # VAT / KDV Breakdown
    vat_rate_pct: float
    vat_amount_try: float
    gross_total_try: float

    # Corporate / Income Tax Breakdown (KVK 10/1-ğ & GVK 89/13)
    exempt_income_try: float    # 100% if export (11257 KKH), 0% if domestic
    taxable_base_try: float     # 0% if export, 100% if domestic
    statutory_legal_note: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))


class ProductRevenueBreakdown(BaseModel):
    """Tek-mükellef altında ürün bazlı gelir kırılımı ( mali müşavir-ek)."""
    product_name: str
    invoices_count: int
    revenue_try: float
    vat_try: float
    export_share_pct: float


class FiscalSummaryReport(BaseModel):
    """Monthly/Quarterly report designed for the CPA / Mali Müşavir.

    TEK-MÜKELLEF raporu: tüm ürünler tek kurum, yurtiçi/yurt dışı
    ayrımı + ürün kırılımı ile.
    """
    report_date: str
    taxpayer_name: str = "Unpump.cash (tek mükellef)"
    total_invoices_count: int
    export_invoices_count: int
    domestic_invoices_count: int

    # Revenue Totals
    total_foreign_revenue_try: float
    total_domestic_revenue_try: float
    total_gross_revenue_try: float

    # Tax Relief & Base Breakdown
    total_vat_collected_try: float
    total_exempt_income_kvk10g_try: float  # 80% tax-free export profit
    total_taxable_base_try: float          # Actual taxable base
    effective_tax_shield_pct: float        # Percentage of income legally untaxed

    # TEK-MÜKELLEF: ürün kırılımı ( çok-ürün tek-kasa)
    product_breakdown: List[ProductRevenueBreakdown] = []


class UnifiedProductRow(BaseModel):
    """Tek-mükellef raporunda ürün ( servis) basina bir satir."""
    product_name: str
    invoices_count: int
    yurtici_try: float           # KDV'li yurt ici gelir
    yurt_disi_try: float         # hizmet ihracati ( KDV %0)
    kdv_try: float               # yurt icinden alinan KDV


class UnifiedTaxReport(BaseModel):
    """TEK-MÜKELLEF cok-urun aylik vergi raporu ( mali mustavir-hazir).

    MUKELLEP TEK: Unpump sirketi; her urun ( AnswRank, MCPGuard,
    pqhaven, ...) ayri satirda ama TOPLAM tek mukellef altinda.
    Yurt ici/yurt disi ayrimi KDV icin korunur:
      yurt disi = hizmet ihracati ( GVK 89/13, KDV %0, istisna 302)
      yurt ici = %20 KDV tevkif
    """
    yil: int
    ay: int
    taxpayer_name: str
    product_rows: List[UnifiedProductRow] = []

    # TEK-MUKELLEF toplamlari
    yurt_disi_toplam_try: float   # == sum(product_rows.yurt_disi_try)
    yurtici_toplam_try: float
    kdv_toplam_try: float
    muaf_gelir_try: float         # GVK 89/13 Kazanc indirimi ( ihracat)
    matrah_toplam_try: float
    brut_gelir_try: float

    rapor_yolu: Optional[str] = None  # yazilan reports/vergi_raporu_YYYY_AY.md

    @property
    def foreign_total_try(self) -> float:
        """Test-helper: yurt disi toplam ( hizmet ihracati)."""
        return self.yurt_disi_toplam_try


class TaxLedger:
    """Manages statutory multi-currency tax separation and accounting compliance."""

    # Static conservative fallback indicative rates. These are ONLY used when no
    # fresher source is configured/available; every invoice records which source
    # was used in `fx_source` so no stale rate is ever presented as live.
    DEFAULT_EXCHANGE_RATES: Dict[str, float] = {
        "GBP": 46.50,
        "USD": 35.80,
        "EUR": 38.90,
        "TRY": 1.00,
        # AED, USD'ye kurumsal olarak sabitlenmiştir (1997'den beri 3.6725 AED/USD —
        # piyasa verisi değil, structurl peg). Bu yüzden çapraz, yukarıdaki USD
        # endeksli değerden TÜRETİLİR: 35.80 / 3.6725 = 9.75 (vintage-uyumlu).
        "AED": 9.75,
    }

    EXPORT_LEGAL_NOTE = (
        "3065 sayılı KDV Kanunu Madde 11/1-a (Hizmet İhracatı / İstisna Kodu 302) "
        "kapsamında KDV'den istisnadır. 5520 sayılı KVK Madde 10/1-ğ ve 193 sayılı "
        "GVK Madde 89/13 uyarınca elde edilen kazancın %100'ü Kurumlar/Gelir "
        "Vergisinden müstesnadır (11257 sayılı Cumhurbaşkanı Kararı, 2026)."
    )

    DOMESTIC_LEGAL_NOTE = "3065 sayılı KDV Kanunu kapsamında genel oranda (%20) KDV tevkif edilmiştir."

    # Module-level cache for live FX: (fetched_at_mono, rates_map)
    _LIVE_FX_CACHE: Optional[Tuple[float, Dict[str, float]]] = None
    LIVE_FX_TTL_SECONDS = 6 * 3600

    def __init__(self, custom_rates: Optional[Dict[str, float]] = None, load_persisted: bool = True):
        if custom_rates is not None:
            self.rates = dict(custom_rates)
            self.fx_source = "custom"
        else:
            self.rates, self.fx_source = self._resolve_rates()
        self.records: List[FiscalInvoiceRecord] = []
        self.last_persist_error: Optional[str] = None
        if load_persisted:
            self._load_persisted_records()

    @classmethod
    def _resolve_rates(cls) -> Tuple[Dict[str, float], str]:
        """Rate precedence: ANSWRANK_FX_RATES env JSON > live fetch (only when
        ANSWRANK_FX_LIVE=1) > static defaults. Source label is returned so it is
        recorded per-invoice and surfaced in the UI — stale is never shown as fresh."""
        env_rates = os.environ.get("ANSWRANK_FX_RATES", "").strip()
        if env_rates:
            try:
                parsed = json.loads(env_rates)
                if isinstance(parsed, dict) and parsed:
                    merged = cls.DEFAULT_EXCHANGE_RATES.copy()
                    merged.update({str(k).upper(): float(v) for k, v in parsed.items()})
                    return merged, "env"
            except (ValueError, TypeError):
                pass  # malformed env override falls through, never silently mis-typed
        if os.environ.get("ANSWRANK_FX_LIVE", "").strip().lower() in ("1", "true", "yes"):
            live = cls._fetch_live_fx()
            if live:
                return live, "live:open.er-api.com"
        return cls.DEFAULT_EXCHANGE_RATES.copy(), "static_default"

    @classmethod
    def _fetch_live_fx(cls) -> Optional[Dict[str, float]]:
        """USD-base snapshot from open.er-api.com (no key required), converted to
        TRY-per-currency. Returns None on any failure so callers keep the honest
        static fallback. Disabled unless ANSWRANK_FX_LIVE=1, so tests stay offline."""
        import time
        if cls._LIVE_FX_CACHE and (time.monotonic() - cls._LIVE_FX_CACHE[0]) < cls.LIVE_FX_TTL_SECONDS:
            return dict(cls._LIVE_FX_CACHE[1])
        try:
            import httpx
            resp = httpx.get("https://open.er-api.com/v6/latest/USD", timeout=8.0)
            resp.raise_for_status()
            rates = resp.json().get("rates") or {}
            try_rate = float(rates["TRY"])  # KeyError on malformed payload -> except
            out = {"TRY": 1.0}
            for ccy in ("USD", "GBP", "EUR"):
                if ccy in rates:
                    out[ccy] = round(try_rate / float(rates[ccy]), 4)
            cls._LIVE_FX_CACHE = (time.monotonic(), out)
            return dict(out)
        except Exception:
            # Dürüst yol: canlı kur alınamazsa None döner, arayan statik varsayılanı
            # fx_source="static_default" etiketiyle yazar — uydurulmuş kur oluşmaz.
            logger.debug("Canlı TCMB kuru alınamadı; statik varsayılana düşülüyor", exc_info=True)
            return None

    def _load_persisted_records(self) -> None:
        """Rehydrate previously issued invoices from the DB so the fiscal ledger
        (and its invoice numbering) survives process restarts."""
        try:
            from answrank.db import Database
            rows = Database().list_tax_invoices_sync()
        except Exception:
            return  # a fresh/uninitialized store simply has no history
        for r in rows:
            try:
                self.records.append(FiscalInvoiceRecord(
                    invoice_id=r["invoice_id"],
                    client_brand=r["client_brand"],
                    client_country=r["client_country"],
                    regime=r["regime"],
                    currency=r["currency"],
                    amount_foreign=r["amount_foreign"],
                    exchange_rate_tcmb=r["exchange_rate"],
                    fx_source=r.get("fx_source", "static_default"),
                    amount_try=r["amount_try"],
                    vat_rate_pct=r["vat_rate_pct"],
                    vat_amount_try=r["vat_amount_try"],
                    gross_total_try=r["gross_total_try"],
                    exempt_income_try=r["exempt_income_try"],
                    taxable_base_try=r["taxable_base_try"],
                    statutory_legal_note=r["legal_note"],
                    created_at=r["created_at"],
                ))
            except Exception:
                continue  # malformed legacy row: skip, never poison the ledger

    def record_invoice(
        self,
        client_brand: str,
        country: str,
        currency: str,
        amount: float,
        exchange_rate: Optional[float] = None,
        invoice_no: Optional[str] = None,
        product_name: str = "unknown",
    ) -> FiscalInvoiceRecord:
        """Create a tax-compliant invoice record based on statutory residency rules.

        TEK-MÜKELLEF: product_name ürünü işaretler ( AnswRank, ClearTag,
        PQHaven, ... ) ama mükellep tek — tüm ürünler tek banka hesabına.
        Yurtiçi/yurt dışı rejim KDV için korunur (vergi için kritik).
        """
        country_code = country.strip().upper()
        curr = currency.strip().upper()
        if exchange_rate is not None:
            rate = float(exchange_rate)
            fx_source = "explicit"
        else:
            if curr not in self.rates:
                # Sessiz 1.0 varsayımı, yabancı parayı TRY sanmak olurdu — ölçüm
                # yasağı ilkesi: kur bilinmiyorsa fatura işlenmez, uydurulmaz.
                raise ValueError(
                    f"Kayıtlı {curr} döviz kuru yok — TRY karşılığı uydurulmaz. "
                    "ANSWRANK_FX_RATES verin veya canlı FX kurun.")
            rate = self.rates[curr]
            fx_source = self.fx_source
        amount_try = round(amount * rate, 2)

        is_export = country_code != "TR"
        regime = TaxRegime.EXPORT_SERVICE if is_export else TaxRegime.DOMESTIC_SERVICE

        if is_export:
            vat_rate = 0.0
            vat_amount = 0.0
            gross_total = amount_try
            # 11257 sayılı Cumhurbaşkanı Kararı (2026): hizmet ihracatında
            # GVK 89/13 kazanç indirimi %100'e çıktı (eski %80). Oran config'ten
            # gelir — mevzuat değişirse tek yerden, fatura hesabından değil.
            deduction = settings.export_income_deduction_rate
            exempt_income = round(amount_try * deduction, 2)
            taxable_base = round(amount_try * (1.0 - deduction), 2)
            legal_note = self.EXPORT_LEGAL_NOTE
        else:
            vat_rate = 20.0
            vat_amount = round(amount_try * 0.20, 2)
            gross_total = round(amount_try + vat_amount, 2)
            exempt_income = 0.0
            taxable_base = amount_try
            legal_note = self.DOMESTIC_LEGAL_NOTE

        # TEK-MÜKELLEF: fatura öneki ürün değil tek-kurum (UNPUMP-INV);
        # ürün ayrımı product_name alanında ( çok-ürün tek-kasa).
        inv_id = invoice_no or f"UNPUMP-INV-{len(self.records) + 1:04d}"
        record = FiscalInvoiceRecord(
            invoice_id=inv_id,
            client_brand=client_brand,
            client_country=country_code,
            regime=regime,
            currency=curr,
            amount_foreign=amount,
            exchange_rate_tcmb=rate,
            fx_source=fx_source,
            amount_try=amount_try,
            product_name=product_name,
            vat_rate_pct=vat_rate,
            vat_amount_try=vat_amount,
            gross_total_try=gross_total,
            exempt_income_try=exempt_income,
            taxable_base_try=taxable_base,
            statutory_legal_note=legal_note,
        )
        self.records.append(record)
        self._persist_record(record)
        return record

    def _persist_record(self, record: FiscalInvoiceRecord) -> None:
        """Mirror the invoice to SQLite. Ledger issuance must never fail because
        of the mirror, so errors are captured on `last_persist_error` (visible to
        the API/UI) instead of aborting the fulfillment pipeline."""
        try:
            from answrank.db import Database
            Database().save_tax_invoice_sync({
                "invoice_id": record.invoice_id,
                "client_brand": record.client_brand,
                "client_country": record.client_country,
                "regime": record.regime.value,
                "currency": record.currency,
                "amount_foreign": record.amount_foreign,
                "exchange_rate": record.exchange_rate_tcmb,
                "fx_source": record.fx_source,
                "amount_try": record.amount_try,
                "vat_rate_pct": record.vat_rate_pct,
                "vat_amount_try": record.vat_amount_try,
                "gross_total_try": record.gross_total_try,
                "exempt_income_try": record.exempt_income_try,
                "taxable_base_try": record.taxable_base_try,
                "legal_note": record.statutory_legal_note,
                "created_at": record.created_at,
            })
            self.last_persist_error = None
        except Exception as exc:
            self.last_persist_error = str(exc)[:200]

    def generate_fiscal_summary(self) -> FiscalSummaryReport:
        """Generate CPA-ready summary of domestic vs export revenue and tax exemptions."""
        export_recs = [r for r in self.records if r.regime == TaxRegime.EXPORT_SERVICE]
        domestic_recs = [r for r in self.records if r.regime == TaxRegime.DOMESTIC_SERVICE]

        export_rev = sum(r.amount_try for r in export_recs)
        domestic_rev = sum(r.amount_try for r in domestic_recs)
        gross_rev = export_rev + domestic_rev

        vat_collected = sum(r.vat_amount_try for r in domestic_recs)
        exempt_kvk10g = sum(r.exempt_income_try for r in export_recs)
        taxable_base = sum(r.taxable_base_try for r in self.records)

        effective_shield = (exempt_kvk10g / gross_rev * 100.0) if gross_rev > 0 else 0.0

        # TEK-MÜKELLEF: ürün kırılımı — hangi ürün ne kadar getirdi
        per_product: Dict[str, list] = {}
        for r in self.records:
            per_product.setdefault(r.product_name, []).append(r)
        breakdown = []
        for name, recs in sorted(per_product.items()):
            rev = sum(r.amount_try for r in recs)
            vat = sum(r.vat_amount_try for r in recs)
            export_n = sum(1 for r in recs if r.regime == TaxRegime.EXPORT_SERVICE)
            share = (export_n / len(recs) * 100.0) if recs else 0.0
            breakdown.append(ProductRevenueBreakdown(
                product_name=name,
                invoices_count=len(recs),
                revenue_try=round(rev, 2),
                vat_try=round(vat, 2),
                export_share_pct=round(share, 1),
            ))

        return FiscalSummaryReport(
            report_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            total_invoices_count=len(self.records),
            export_invoices_count=len(export_recs),
            domestic_invoices_count=len(domestic_recs),
            total_foreign_revenue_try=round(export_rev, 2),
            total_domestic_revenue_try=round(domestic_rev, 2),
            total_gross_revenue_try=round(gross_rev, 2),
            total_vat_collected_try=round(vat_collected, 2),
            total_exempt_income_kvk10g_try=round(exempt_kvk10g, 2),
            total_taxable_base_try=round(taxable_base, 2),
            effective_tax_shield_pct=round(effective_shield, 1),
            product_breakdown=breakdown,
        )

    def generate_monthly_unified_report(
        self,
        yil: int,
        ay: int,
        taxpayer_name: str = "Unpump (sahis sirketi)",
        output_dir: Optional[str] = "reports",
        write_file: bool = True,
    ) -> UnifiedTaxReport:
        """TEK-MUKELLEF cok-urun aylik vergi raporu ( mali mustavir-hazir).

        MUKELLEP TEK: tek kurum, tek banka hesabi. URUN COOK: her servis
        ( AnswRank, MCPGuard, pqhaven, ...) tabloda ayri satirda, ama
        TOPLAM tek mukellef altinda. Yurt ici/yurt disi ayrami KORUNUR:
          - yurt disi: HIZMET IHRACATI ( GVK 89/13 Kazanc Indirimi,
            KDV %0 — KVK 11/1-a Istisna Kodu 302)
          - yurt ici: %20 KDV tevkif edilen gelir

        Cikti: <output_dir>/vergi_raporu_<YYYY>_<AY>.md
        ( write_file=False ise dosya yazilmaz — testler icin)
        """
        ay_str = f"{yil:04d}-{ay:02d}"
        donem = [r for r in self.records if r.created_at.startswith(ay_str)]

        # urun ( servis) bazinda ayir
        per_product: Dict[str, list] = {}
        for r in donem:
            per_product.setdefault(r.product_name, []).append(r)

        rows: List[UnifiedProductRow] = []
        for name, recs in sorted(per_product.items()):
            yurtici = sum(r.amount_try for r in recs
                          if r.regime == TaxRegime.DOMESTIC_SERVICE)
            yurtdisi = sum(r.amount_try for r in recs
                           if r.regime == TaxRegime.EXPORT_SERVICE)
            kdv = sum(r.vat_amount_try for r in recs
                      if r.regime == TaxRegime.DOMESTIC_SERVICE)
            rows.append(UnifiedProductRow(
                product_name=name,
                invoices_count=len(recs),
                yurtici_try=round(yurtici, 2),
                yurt_disi_try=round(yurtdisi, 2),
                kdv_try=round(kdv, 2),
            ))

        yurtici_toplam = sum(r.yurtici_try for r in rows)
        yurtdisi_toplam = sum(r.yurt_disi_try for r in rows)
        kdv_toplam = sum(r.kdv_try for r in rows)
        # GVK 89/13: ihracat kazanc indirimi ( settings'ten gelen oran)
        muaf = sum(r.exempt_income_try for r in donem
                   if r.regime == TaxRegime.EXPORT_SERVICE)
        matrah = sum(r.taxable_base_try for r in donem)

        rapor_yolu = None
        if write_file and rows:
            import os
            os.makedirs(output_dir or "reports", exist_ok=True)
            rapor_yolu = f"{output_dir or 'reports'}/vergi_raporu_{ay_str}.md"
            self._write_unified_report_md(
                rapor_yolu, rows, yil, ay, taxpayer_name,
                yurtici_toplam, yurtdisi_toplam, kdv_toplam, muaf, matrah)

        return UnifiedTaxReport(
            yil=yil,
            ay=ay,
            taxpayer_name=taxpayer_name,
            product_rows=rows,
            yurt_disi_toplam_try=round(yurtdisi_toplam, 2),
            yurtici_toplam_try=round(yurtici_toplam, 2),
            kdv_toplam_try=round(kdv_toplam, 2),
            muaf_gelir_try=round(muaf, 2),
            matrah_toplam_try=round(matrah, 2),
            brut_gelir_try=round(yurtici_toplam + yurtdisi_toplam, 2),
            rapor_yolu=rapor_yolu,
        )

    @staticmethod
    def _write_unified_report_md(
        yol, rows, yil, ay, taxpayer_name,
        yurtici_toplam, yurtdisi_toplam, kdv_toplam, muaf, matrah,
    ) -> None:
        """Mali mustavir-hazir markdown raporu yaz ( tek-mukellef)."""
        ay_adlari = ["Ocak", "Subat", "Mart", "Nisan", "Mayis", "Haziran",
                     "Temmuz", "Agustos", "Eylul", "Ekim", "Kasim", "Aralik"]
        ay_adi = ay_adlari[ay - 1] if 1 <= ay <= 12 else f"Ay-{ay}"
        sat = []
        sat.append(f"# VERGI RAPORU — {ay_adi} {yil}")
        sat.append("")
        sat.append("## TEK MUKELLEF — COK URUN")
        sat.append("")
        sat.append(f"**Mukellep:** {taxpayer_name}")
        sat.append(f"**Donem:** {ay_adi} {yil}")
        sat.append("**Yontem:** Tek kurum, tek banka hesabi; tum urunler")
        sat.append("( AnswRank, MCPGuard, pqhaven, ...) altinda toplanir.")
        sat.append("")
        sat.append("## URUN BAZINDA GELIR ( TEK MUKELLEF)")
        sat.append("")
        sat.append("| Urun ( servis) | Fatura | Yurt Ici (TRY) | "
                   "Yurt Disi (TRY) | KDV (TRY) |")
        sat.append("|---|---:|---:|---:|---:|")
        for r in rows:
            sat.append(f"| {r.product_name} | {r.invoices_count} | "
                       f"{r.yurtici_try:,.2f} | {r.yurt_disi_try:,.2f} | "
                       f"{r.kdv_try:,.2f} |")
        sat.append(f"| **TOPLAM** | **{sum(r.invoices_count for r in rows)}** | "
                   f"**{yurtici_toplam:,.2f}** | **{yurtdisi_toplam:,.2f}** | "
                   f"**{kdv_toplam:,.2f}** |")
        sat.append("")
        sat.append("## KDV OZETI ( KDV Kanunu)")
        sat.append("")
        sat.append(f"- **Yurt ici gelir:** {yurtici_toplam:,.2f} TRY — "
                   "**%20 KDV** tevkif edilir ( genel oran).")
        sat.append(f"- **Yurt disi gelir:** {yurtdisi_toplam:,.2f} TRY — "
                   "**HIZMET IHRACATI: KDV %0** ( 3065 sayili KDV Kanunu "
                   "Madde 11/1-a, Istisna Kodu 302).")
        sat.append(f"- **Toplam tahsil edilen KDV:** {kdv_toplam:,.2f} TRY")
        sat.append("")
        sat.append("## GELIR VERGISI — GVK 89/13 ( Kazanc Indirimi)")
        sat.append("")
        sat.append(f"- **Hizmet ihracati kazanci:** {yurtdisi_toplam:,.2f} TRY")
        sat.append(f"- **GVK 89/13 indirimi ( muaf kisim):** {muaf:,.2f} TRY")
        sat.append(f"- **Vergiye tabi matrah:** {matrah:,.2f} TRY")
        sat.append("")
        sat.append("> NOT: Yurt disi geliri \"hizmet ihracati\" olarak")
        sat.append("> isaretleyin — GVK 89/13 indirimi ve KDV istisnasi")
        sat.append("> ( Kod 302) icin mali mustavir bu etiketi kullanir.")
        sat.append("")
        sat.append("---")
        sat.append("Bu rapor `TaxLedger.generate_monthly_unified_report`")
        sat.append("tarafindan uretilmistir; mali mustavir-hazir formatta.")
        sat.append("")
        with open(yol, "w", encoding="utf-8") as f:
            f.write("\n".join(sat))
