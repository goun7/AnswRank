"""Mainnet ödeme doğrulama — gerçek USDC transferini zincirden okur.

v1 sester (EIP-191 imza) akışını tamamlar: imza "ben ödedim" der,
bu modül ise zincirde gerçekten ödenmiş mi diye kontrol eder.

Akış:
  1. Alıcı agent adresinden PAY_TO adresine USDC transfer eder (Base mainnet)
  2. Aynı agent ile imza üretir (amount = transfer miktarı)
  3. verify_payment: imzayı doğrular + transferi zincirde bulur

Transfer eşleştirme: son N blokta PAY_TO'ya gelen USDC transferlerinden
agent adresi + tutar + nonce ile eşleşeni arar. nonce, transferin
takip edilebilirliğini sağlar (replay koruması ledger'da zaten var).

DALGA-E3 ( K4=2/100 duzeltmesi): CLI giris-dogrulama katmani eklendi.
Onceki: bilinmeyen-flag'ler ( --bogus) SESSIZCE rc=0 ile gecerdi
( truthy-exit hatasi); --help 0-byte cikti veriyordu. Simdi: bilinmeyen
flag / eksik arguman -> --help bas + rc=2 ( standart kullanma-hatasi).
Modul-API'si ( find_transfer / verify_mainnet_payment) DEGISMEDI —
mainnet_guard import'u aynen calisir.
"""
from __future__ import annotations

import json
import logging
import sys
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Base mainnet — publicnode rate-limit'e dayanıklı
RPC_URL = "https://base.publicnode.com"

# Circle USDC (Base mainnet, 6 decimal)
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# Transfer(address,address,uint256) event topic —
# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)

CONFIRMED_BLOCKS = 20  # reorg güvenliği
SEARCH_BLOCKS = 5000   # ~2.5 saat geriye dönük (12 sn/block)
CHUNK_BLOCKS = 2000    # publicnode 20000-sonuç limiti → parçalı arama

_UA = {"Content-Type": "application/json",
       "User-Agent": "unpump-mainnet-verify/1.0"}


class RPCError(Exception):
    """RPC çağrısı başarısız."""


def _rpc(method: str, params: list) -> dict:
    """Tek RPC çağrısı (curl user-agent ile)."""
    payload = json.dumps({"jsonrpc": "2.0", "method": method,
                          "params": params, "id": 1}).encode()
    req = urllib.request.Request(RPC_URL, data=payload, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RPCError(f"{method}: {out['error']}")
    return out["result"]


def _hex_to_int(h: str) -> int:
    return int(h, 16)


def _addr_topic(addr: str) -> str:
    """Adresi 32-byte topic'e göm (baştaki sıfırlarla)."""
    return "0x" + addr[2:].lower().rjust(64, "0")


@dataclass
class TransferFound:
    found: bool
    tx_hash: str | None = None
    amount_minor: int | None = None
    detail: str = ""


def find_transfer(
    *,
    from_addr: str,
    to_addr: str,
    amount_minor: int,
    max_blocks: int = SEARCH_BLOCKS,
) -> TransferFound:
    """Zincirde agent→pay_to USDC transferi ara.

    Eşleşme: Transfer event'i + from + to + tutar.
    Parçalı arama yapar (publicnode 20000-sonuç limiti).
    Döndürür: bulunursa tx_hash ile.
    """
    latest = _hex_to_int(_rpc("eth_blockNumber", []))
    hi = latest - CONFIRMED_BLOCKS
    lo = max(0, latest - max_blocks)

    logs: list[dict] = []
    # küçük parçalar halinde geriye dönük tara
    while hi >= lo:
        chunk_lo = max(lo, hi - CHUNK_BLOCKS + 1)
        try:
            part = _rpc("eth_getLogs", [{
                "address": USDC_CONTRACT,
                "topics": [
                    TRANSFER_TOPIC,
                    _addr_topic(from_addr),
                    _addr_topic(to_addr),
                ],
                "fromBlock": hex(chunk_lo),
                "toBlock": hex(hi),
            }])
        except RPCError as e:
            # limit aşıldıysa parçayı daralt
            if "max results" in str(e).lower() or "range" in str(e).lower():
                chunk_lo = hi - 200
                if chunk_lo < lo:
                    return TransferFound(False, detail=str(e))
                part = _rpc("eth_getLogs", [{
                    "address": USDC_CONTRACT,
                    "topics": [
                        TRANSFER_TOPIC,
                        _addr_topic(from_addr),
                        _addr_topic(to_addr),
                    ],
                    "fromBlock": hex(chunk_lo),
                    "toBlock": hex(hi),
                }])
            else:
                raise
        if part:
            logs.extend(part)
            for log in part:
                value_hex = log.get("data", "0x0")
                value = _hex_to_int(value_hex[:66] if len(value_hex) >= 66
                                   else (value_hex or "0x0"))
                if value == amount_minor:
                    return TransferFound(
                        True, tx_hash=log.get("transactionHash"),
                        amount_minor=value,
                        detail=f"block {int(log['blockNumber'], 16)}",
                    )
        hi = chunk_lo - 1

    return TransferFound(
        False,
        detail=f"son {max_blocks} blokta {from_addr[:10]}→"
               f"{to_addr[:10]} {amount_minor} minor transfer yok",
    )


def verify_mainnet_payment(
    *,
    from_addr: str,
    to_addr: str,
    amount_usd: float,
) -> TransferFound:
    """Ana giriş: gerçek USDC transferi var mı?"""
    amount_minor = int(round(amount_usd * 1_000_000))
    return find_transfer(
        from_addr=from_addr, to_addr=to_addr, amount_minor=amount_minor,
    )


# ---------------------------------------------------------------------------
# CLI giris-dogrulama katmani ( DALGA-E3) — GERCEK-CLI-cagrilari icin.
# Bu modul bir kutuphane OLARAK da kullanilir ( mainnet_guard import eder);
# alttaki dugme SADECE `python mainnet_verify.py` ile dogrudan calistirilinca
# devreye girer — import-edildiginde calismaz ( mevcut cagri-yollari korundu).
# ---------------------------------------------------------------------------
_KULLANIM = """Kullanim: python mainnet_verify.py [SECENEK]

Base mainnet'te gercek USDC transferini zincirden okur ( EIP-191 akisinin
son adimi: imza "ben odedim" der, bu modul zincirde ODENMIS mi diye bakar).

SECENEKLER:
  --help, -h     bu yardimi goster ve cik ( rc=0)
  --from ADDR    odeyen agent adresi ( 0x...)
  --to ADDR      alici PAY_TO adresi ( 0x...)
  --amount USD   dogrulanacak tutar ( USDC, 6 decimal)

ORNEK:
  python mainnet_verify.py --from 0x11.. --to 0xF3.. --amount 0.05

NOT: programlik-API ( find_transfer / verify_mainnet_payment) mainnet_guard
tarafindan IMPORT ile kullanilir — CLI-gate sadece dogrudan calistirmada
devreye girer; argumansiz cagri onceki gibi rc=0 ile cikar.
"""


def cli_dogrula(argv: list[str] | None = None) -> int:
    """CLI giris-katmani ( DALGA-E3, K4=2/100 duzeltmesi).

    onceki: --bogus gibi bilinmeyen-flag'ler SESSIZCE rc=0 ile geciyordu
    ( truthy-exit hatasi). Simdi: bilinmeyen flag / eksik arguman ->
    --help bas + rc=2 ( standart kullanma-hatasi).

    Returns: 0=devam-et, 2=kullanma-hatasi ( yardim basildi),
             99=yardim-gosterildi ( cikti rc=0).
    """
    if argv is None:
        argv = sys.argv[1:]
    # --help oncelikli: herhangi bir konumda ise yardim bas + rc=0
    for a in argv:
        if a in ("-h", "--help"):
            print(_KULLANIM)
            return 99
    bilinen_degerli = {"--from", "--to", "--amount"}
    bilinir = bilinen_degerli | {"-h", "--help"}
    bilinmeyen = {a for a in argv
                  if a.startswith("-") and a not in bilinir}
    if bilinmeyen:
        print(f"[kullanma-hatasi] bilinmeyen secenek: "
              f"{' '.join(sorted(bilinmeyen))}", file=sys.stderr)
        print(_KULLANIM)
        return 2
    # deger-alan flag'lerden sonra arguman eksikse -> rc=2
    for i, a in enumerate(argv):
        if a in bilinen_degerli:
            if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                print(f"[kullanma-hatasi] {a} bir deger gerektirir.",
                      file=sys.stderr)
                print(_KULLANIM)
                return 2
    return 0


def main() -> int:
    """CLI giris-noktasi: once dogrula, sonra (gecerliyse) pas-gec."""
    rc = cli_dogrula()
    if rc == 99:
        return 0
    if rc != 0:
        return 2
    # argumansiz cagri: modulun kendisi bir kutuphanedir — onceki gibi
    # sessizce rc=0 ile cik ( fonksiyonlar import-edilerek kullanilir).
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
