"""AnswRank <-> Sester x402 odeeme kapisi -- mesh code bond (2026-10-05).

Mesh recetesi (orkestrasyon/PORTFOY_SINERJI_HARITASI_2026-09-24.md S7.0.2):
  "85-AnswRank -- MCP server'a SADECE Sester sarmasi gerekiyor
   (en duskuk maliyet)".

Bu modul o sarmadir: AnswRank'in ucretli MCP araclarini (answrank_audit /
answrank_citations / answrank_generate_fixes) Sester x402 rayina baglar ve
her odemeyi hash-zincir makbuz ile anchorlar. Böylece "bu denetim icin bu
odeme alindi" iddiasi musteri tarafindan yeniden-hesaplanabilir kanit olur
(mesh "kanit -> odeme" deseni; Delilix / VadeDostu / ClearTag ile ayni).

Akis (MCP stdio; HTTP header'i yoktur, makbuz tool argumanidir):
  1. istemci Sester ile oder -> satici hash-zincir makbuz uretir
  2. makbuzu tool cagrisinda `payment_receipt` olarak verir
  3. require(): makbuz dogrulanir (sester.verify_receipt, ayni satici
     secret'i ile) + mainnet modunda zincirde USDC transferi aranir
  4. arac calisir
  5. settle(): ciktinin SHA-256 anchor hash'i ile ledger'a
     `charge_receipt` yazilir -> seq (machine-checkable teslimat kaniiti)

GUVENLIK -- fail-closed (x402_servis.py + mainnet_guard.py ile ayni kurallar):
  - Odemeli mod icin ANSWRANK_SELLER_SECRET ZORUNLU ve >= 16 karakter;
    zayif/bos secret ile kapi ACILMAZ (ucretsiz-bypass yok). Bos secret
    ile Ledger farkli anahtarla yazilir ve verify_chain False doner --
    bu repo'da daha once yasanan bir hatadir, bilincli engellenir.
  - mainnet mod (varsayilan): zincirde transfer YOKSA PaymentRequired --
    sifir-odeme bypass kapali.
  - UNPUMP_TEST=1 / ANSWRANK_TEST=1 -> zincir aranmaz (sim); cikti
    "paid-test" olarak etiketlenir ("simulation is labelled" ilkesi).

GERI-UYUMLULUK (mevcut davranis korunur, testler zayiflamaz):
  - secret yok -> kapi devre disi, UCRETSIZ mod; araclar calisir, yanit
    `payment.mode = "free"` ile acikca etiketlenir ("no silent guessing").
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("answrank.x402_gate")

# --- fiyatlandirma: x402_servis.py ile AYNI env adi (tek kaynak) ---------
TOOL_PRICES: Dict[str, float] = {
    "answrank_audit": float(os.environ.get("ANSWRANK_PRICE_AUDIT", "0.05")),
    "answrank_citations": float(os.environ.get("ANSWRANK_PRICE_CITATIONS", "1.20")),
    "answrank_generate_fixes": float(os.environ.get("ANSWRANK_PRICE_FIX", "0.20")),
}

MIN_SECRET_LEN = 16
DEFAULT_DB = os.environ.get(
    "ANSWRANK_RECEIPTS_DB",
    str(Path.home() / ".workspace" / "answrank" / "receipts.sqlite"),
)


class PaymentRequired(RuntimeError):
    """402 karsiligi -- odeme yok / gecersiz / zincirde transfer yok
    (fail-closed: ucretsiz hizmet yanilgisi yok)."""


class WeakSecretError(ValueError):
    """Yapilandirma hatasi -- zayif secret ile odemeli mod acilamaz."""


@dataclass(frozen=True)
class Charge:
    """Tek bir odeme/teslimat kaniiti. `as_dict` MCP/API yanitina konur."""

    seq: int                    # ledger sira no (0 = ucretsiz mod, yazilmadi)
    receipt_hash: str           # makbuz hash'i ("" = ucretsiz mod)
    anchor_hash: str            # odenen ciktinin kanonik SHA-256 anchor'i
    mode: str                   # "free" | "paid-test" | "paid-mainnet"
    price_usdc: float
    ledger_chain_valid: Optional[bool] = None
    note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "receipt_hash": self.receipt_hash,
            "anchor_hash": self.anchor_hash,
            "mode": self.mode,
            "price_usdc": self.price_usdc,
            "ledger_chain_valid": self.ledger_chain_valid,
            "note": self.note,
        }


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _valid_eoa(addr: str) -> bool:
    """Ethereum EOA format kontrolu (mainnet_guard ile ayni kural):
    "0x" + 40 hex. EIP-55 checksum zorunlu degil -- env degerleri
    checksum'suz olabilir; burada yanlis-adres yakalanir, imza dogrulamasi
    zincir tarafinda yapilir."""
    if not isinstance(addr, str):
        return False
    if not addr.startswith("0x"):
        return False
    body = addr[2:]
    return len(body) == 40 and all(c in "0123456789abcdefABCDEF" for c in body)


class SesterPaymentGate:
    """AnswRank <-> Sester x402 odeeme kapisi.

    Kullanim (MCP sunucusu / API / herhangi bir ucretli yuzey):

        gate = SesterPaymentGate()            # env'den yapilanir
        gate.require(tool="answrank_audit",   # ONECE: 402 fail-closed
                     receipt=receipt, payer=payer)
        result = run_tool(...)
        charge = gate.settle(tool="answrank_audit",  # SONRA: teslimat kaniiti
                             anchor={"domain": ..., "overall_score": ...},
                             receipt=receipt, payer=payer)

    Tum parametreler test icin enjekte edilebilir; zincir dogrulayici
    (`chain_verifier`) taklit edilebilir, boylece testler ASLA ana aga
    baglanmaz (MAINNET YASAK mesh kurali).
    """

    def __init__(
        self,
        *,
        db_path: Optional[str] = None,
        secret: Optional[str] = None,
        test_mode: Optional[bool] = None,
        pay_to: Optional[str] = None,
        chain_verifier: Optional[Callable[..., Any]] = None,
        ledger: Any = None,
    ) -> None:
        if secret is None:
            secret = os.environ.get("ANSWRANK_SELLER_SECRET", "")
        # Acikca verilen zayif secret = yapilandirma hatasi (sessizce
        # devre disi birakilmaz; kapali kapinin "acik" sanilmasi onlenir).
        if secret is not None and 0 < len(secret) < MIN_SECRET_LEN:
            raise WeakSecretError(
                f"ANSWRANK_SELLER_SECRET cok kisa ({len(secret)} < {MIN_SECRET_LEN})"
                " -- zayif secret receipt HMAC zincirini baska anahtarla yazar"
                " (verify_chain False). 16+ karakter verin ya da bos birakip"
                " ucretsiz modda calisin.")
        self._secret = secret or ""
        self.enabled = bool(self._secret)

        if test_mode is None:
            # mesh convention'u: UNPUMP_TEST tum x402 ajanlarini sim'e dusurur
            test_mode = _truthy("ANSWRANK_TEST") or _truthy("UNPUMP_TEST")
        self.test_mode = bool(test_mode)

        self.pay_to = pay_to or os.environ.get("ANSWRANK_PAY_TO", "sester:answrank")
        self.db_path = db_path or DEFAULT_DB
        self._chain_verifier = chain_verifier
        self._ledger = ledger
        # ucretsiz modda HICBIR dosya/ledger acilmaz (testleri ve local
        # kullanimi temiz tutar)
        self._ledger_opened = ledger is not None

    # ------------------------------------------------------------------ durum

    def price_of(self, tool: str) -> float:
        """Aracin USD fiyatini doner; ucretsiz araclar icin 0.0."""
        return TOOL_PRICES.get(tool, 0.0)

    def status(self) -> Dict[str, Any]:
        """Durust durum yuzeyi: neyin acik oldugu acikca yazilir."""
        return {
            "enabled": self.enabled,
            "mode": "free" if not self.enabled
                    else ("paid-test" if self.test_mode else "paid-mainnet"),
            "sester_metering": self.enabled,
            "prices_usdc": dict(TOOL_PRICES),
            "pay_to": self.pay_to,
            "chain_check": (not self.test_mode) if self.enabled else False,
            "note": ("ucretsiz mod -- ANSWRANK_SELLER_SECRET ayarli degil"
                     if not self.enabled else
                     ("sim modu -- zincirde transfer ARANMIYOR (test)"
                      if self.test_mode else
                      "mainnet mod -- zincirde USDC transferi ZORUNLU")),
        }

    # ------------------------------------------------------------------ ledger

    def _get_ledger(self) -> Any:
        if self._ledger is None:
            from sester.ledger import Ledger  # gecici import: ucretsiz modda gerekmez
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._ledger = Ledger(self.db_path, secret=self._secret)
            self._ledger_opened = True
        return self._ledger

    def verify_chain(self) -> bool:
        """Satici receipt ledger'inin hash-zinciri gecerli mi?"""
        if not self._ledger_opened:
            return True  # acilmamis ledger = bos zincir = gecerli
        try:
            return bool(self._get_ledger().verify_chain())
        except Exception as exc:  # kanit yanlisi nadir degil: gizlice gecme
            logger.warning("ledger verify_chain hatasi: %s", exc)
            return False

    # ------------------------------------------------------------------ kanit

    @staticmethod
    def anchor_hash(payload: Dict[str, Any]) -> str:
        """Ciktinin kanonik SHA-256 anchor hash'i.

        Kanonik form: JSON, sorted keys, bosluksuz, ensure_ascii=False.
        Musteri ayni ciktiyi tekrar hesaplayarak makbuzun HANGI ciktiya
        ait oldugunu bagimsiz dogrular (machine-checkable).
        """
        canon = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

    def _receipt_hash(self, receipt: Any) -> str:
        try:
            from sester.receipt import receipt_hash
            return receipt_hash(receipt)
        except Exception as exc:
            logger.debug("receipt_hash hesaplanamadi: %s", exc)
            return ""

    # ------------------------------------------------------------------ kapilar

    def require(self, *, tool: str, receipt: Any = None,
                payer: Optional[str] = None) -> None:
        """ON-KONTROL (402 fail-closed). Ucretsiz modda hicbir sey istemez.

        Ucretli modda:
          - makbuz yok -> PaymentRequired (odeme gerekli)
          - makbuz gecersiz -> PaymentRequired (HMAC zincir dogrulanmadi)
          - mainnet modda zincirde USDC transferi yok -> PaymentRequired
        """
        if not self.enabled:
            return
        price = self.price_of(tool)
        if price <= 0:
            return  # ucretsiz arac (TOOL_PRICES disi) -- kapidan gecer

        if not isinstance(receipt, dict):
            raise PaymentRequired(
                f"{tool} odeme gerektirir (${price:.2f} USDC) --"
                " 'payment_receipt' (Sester makbuzu) eksik")
        try:
            from sester.receipt import verify_receipt
        except Exception as exc:  # pragma: no cover - sester kurulu degilse
            raise PaymentRequired(f"Sester makbuz dogrulayici yok: {exc}") from exc

        ok, reason = verify_receipt(receipt, node_secret=self._secret)
        if not ok:
            raise PaymentRequired(f"makbuz gecersiz ({reason}) -- odeme dogrulanmadi")

        # zincir katmani: imza "odemis" der ama transfer olmayabilir;
        # mainnet modda gercek USDC hareketi aranir (sifir-odeme bypass kapali)
        if self.test_mode:
            return  # sim: zincir aranmaz, cikti "paid-test" etiketi tasiyacak

        if not _valid_eoa(payer or ""):
            raise PaymentRequired(
                "mainnet modda gecerli bir 'payer_address' (0x + 40 hex)"
                " zorunlu -- zincir aramasi icin")
        verifier = self._chain_verifier
        if verifier is None:
            try:  # repo kokundeki ortak dogrulayici (pytest pythonpath=".")
                import mainnet_verify
                verifier = mainnet_verify.verify_mainnet_payment
            except Exception as exc:
                raise PaymentRequired(
                    f"mainnet zincir dogrulayici yok -- odeme kanitlanamadi: {exc}"
                ) from exc
        try:
            found = verifier(from_addr=payer, to_addr=self.pay_to, amount_usd=price)
        except TypeError:
            found = verifier(payer, self.pay_to, price)  # eski imza uyumu
        if not getattr(found, "found", False):
            raise PaymentRequired(
                f"zincirde transfer yok ({getattr(found, 'detail', 'belirsiz')})"
                f" -- {payer[:10]}.. -> {self.pay_to} ${price:.2f} USDC"
                " (son bloklarda eslesen odeme bulunamadi)")

    def settle(self, *, tool: str, anchor: Dict[str, Any],
               receipt: Any = None, payer: Optional[str] = None) -> Charge:
        """TESLIMAT KANITI. Ledger'a `charge_receipt` yazar ve ciktinin
        anchor hash'ini makbuz payload'ina baglar.

        Ucretsiz modda (kapı devre disi) HICBIR sey yazilmaz; yine de
        anchor_hash hesaplanir ve yanit 'free' olarak etiketlenir.
        """
        price = self.price_of(tool)
        ah = self.anchor_hash(anchor)

        if not self.enabled:
            return Charge(
                seq=0, receipt_hash="", anchor_hash=ah, mode="free",
                price_usdc=price, ledger_chain_valid=None,
                note="ucretsiz mod -- odeme alinmadi (ANSWRANK_SELLER_SECRET yok)")

        rh = self._receipt_hash(receipt)
        mode = "paid-test" if self.test_mode else "paid-mainnet"
        agent_id = (payer or "buyer") if isinstance(payer, str) else "buyer"
        try:
            seq = self._get_ledger().append(
                "charge_receipt", agent_id, tool, price,
                payload={
                    "tool": tool,
                    "anchor_hash": ah,
                    "receipt_hash": rh,
                    "payer": agent_id,
                    "mode": mode,
                },
            )
            seq_no = int(seq.get("seq", -1)) if isinstance(seq, dict) else -1
            chain_ok = self.verify_chain()
        except Exception as exc:
            logger.exception("ledger'a charge yazilamadi: %s", exc)
            raise PaymentRequired(f"odeme kaniti yazilamadi: {exc}") from exc

        return Charge(
            seq=seq_no, receipt_hash=rh, anchor_hash=ah, mode=mode,
            price_usdc=price, ledger_chain_valid=chain_ok,
            note=("sim odemeli -- zincirde GERCEK transfer YOK (test)"
                  if self.test_mode else "mainnet odemeli -- zincirde dogrulandi"),
        )
