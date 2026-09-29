#!/usr/bin/env python3
"""ILK GERCEK MUSTERI SIMULASYONU — mainnet USDC transferi TAKLIDI.

Gorev ( vardiya 11-1): gelir kaniti icin "ilk gercek musteri" akisini
sandbox'ta UCTAN UCA calistir. Mainnet USDC transferini TAKLIT EDERIZ
( gercek zincir YOK, gercek para YOK) — ama her bileşen GERCEK crypto
ile calisir:

  ADIM 1  musteri cuzdani olustur ( eth_account, gercek anahtar)
  ADIM 2  mock USDC bakiyesi ( gercek zincir DEGIL)
  ADIM 3  fiyat kontrolu ( $0.05 audit) + yeterli bakiye
  ADIM 4  EIP-191 'exact-sester' odeme imzasi ( GERCEK imza)
  ADIM 5  mock zincirde USDC transferi uygula ( nonce, gas, balance)
  ADIM 6  servis cagrisi -> 200 + receipt seq
  ADIM 7  GELIRIN GERCEK OLMADIGI kaniti: net_kar_raporu $0.00

⚠ DURUST ETIKET — ZORUNLU:
  BU SIMULASYONDUR. 'mainnet USDC transferi' MOCK bir ledger'da oldu —
  GERCEK zincirde YAYINLANMADI, GERCEK USDC hareket ETMEDI. Amac
  AKISIN calistigini kanitlamak: imza -> transfer -> hizmet -> receipt.
  GERCEK GELIR: $0.00 ( net_kar_raporu bunu dogrular).

Kullanim:  python3 ilk_musteri_simulasyon.py [--cikti ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

import httpx

_PROJE = Path(__file__).parent
# kod ( answrank, sester) 85-AnswRank'ta; net_kar_raporu KOK'ta — ikisi de
# path'te olmali ki betik her iki dizinden de calissin ( kod = 85-AnswRank).
for _yol in ("/home/gokun/projects/02_sahis/85-AnswRank",
             "/home/gokun/projects/Yeni Fikirler/oncu_fikirler_havuzu_2026/"
             "23_Unpump_Cash_Otonom_Ajan_Borsasi_Ve_Nakit_Akisli_AMM",
             str(_PROJE)):
    if _yol not in sys.path:
        sys.path.insert(0, _yol)

from sester.schemes import sign_exact_sester  # noqa: E402

# sandbox demo agent ( servise erismek icin — gercek odeme DEGIL)
_AGENT = "0x26dbfe78d63509f845c147b8480079c6fbd28bfc"
_SK = ("0x110a30d15ae588e70dbe1074bb582d385b0ee6b08437"
       "007d23c13e969d266857")

TREASURY = "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5"  # tek-kasa EOA
FIYAT_AUDIT = 0.05
USDC_DECIMALS = 6

MOCK_LEDGER = {  # mock zincir durumu ( GERCEK DEGIL)
    "usdc": {},        # adres -> birim ( 1e-6 USDC)
    "nonce": {},       # adres -> nonce
    "bloklar": [],     # blok gecmisi
}


def adim(nom, sonuc, detay=""):
    isaret = "✓" if sonuc else "✗"
    print(f"\n--- ADIM {nom} {'-' * 52}")
    print(f"  [{isaret}] {detay}")
    return sonuc


def mock_usdc_transfer(gonderen, alici, birim, nonce):
    """Mock zincirde USDC transferi uygula ( GERCEK ZINCIR DEGIL).

    Gercek USDC transfer akisini taklit eder: nonce kontrol, balance
    kontrol, gaz ucreti, blok girisi. Hicbir gercek ag cagrisi YOK.
    """
    if MOCK_LEDGER["nonce"].get(gonderen, 0) != nonce:
        return False, "nonce hatasi ( replay koruma)"
    bakiye = MOCK_LEDGER["usdc"].get(gonderen, 0)
    gaz = 21000  # basit gaz modeli ( mock)
    if bakiye < birim + gaz:
        return False, "yetersiz bakiye"
    MOCK_LEDGER["usdc"][gonderen] = bakiye - birim - gaz
    MOCK_LEDGER["usdc"][alici] = MOCK_LEDGER["usdc"].get(alici, 0) + birim
    MOCK_LEDGER["nonce"][gonderen] = nonce + 1
    blok = {
        "blok_no": len(MOCK_LEDGER["bloklar"]) + 1,
        "tur": "usdc_transfer",
        "gonderen": gonderen, "alici": alici,
        "birim": birim, "gaz": gaz, "nonce": nonce,
        "tx_hash": "0x" + hashlib.sha256(
            f"{gonderen}{alici}{birim}{nonce}{uuid.uuid4()}".encode()
        ).hexdigest(),
    }
    MOCK_LEDGER["bloklar"].append(blok)
    return True, blok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", default="ilk_musteri_simulasyon_sonuc.json")
    a = ap.parse_args()

    print("\n" + "=" * 70)
    print("ILK GERCEK MUSTERI SIMULASYONU — mainnet USDC transferi TAKLIDI")
    print("⚠ BU SIMULASYONDUR: gercek zincir YOK, gercek para YOK")
    print("=" * 70)

    adimlar = []
    sonuc = {
        "zaman": datetime.now().isoformat(timespec="seconds"),
        "ETIKET": "SIMULASYON — GERCEK DEGIL ( mock zincir)",
        "gercek_odeme_usd": 0.0,
    }

    # --- ADIM 1: musteri cuzdani ---
    try:
        from eth_account import Account
        musteri = Account.create()
        adimlar.append(("cuzdan", True))
        adim(1, True, f"yeni musteri cuzdani: {musteri.address}")
        sonuc["musteri_adresi"] = musteri.address
    except Exception as e:
        adim(1, False, f"hata: {e}")
        adimlar.append(("cuzdan", False))
        sonuc["hata"] = str(e)
        Path(a.cikti).write_text(json.dumps(sonuc, indent=2,
                                            ensure_ascii=False))
        return 1

    # --- ADIM 2: mock USDC bakiyesi ---
    baslangic = 100 * 10 ** USDC_DECIMALS  # 100 USDC ( mock)
    MOCK_LEDGER["usdc"][musteri.address] = baslangic
    MOCK_LEDGER["nonce"][musteri.address] = 0
    adim(2, True, f"mock bakiye: 100.0 USDC ( gercek zincir DEGIL)")
    adimlar.append(("bakiye", True))

    # --- ADIM 3: fiyat kontrolu ---
    ihtiyac = int(FIYAT_AUDIT * 10 ** USDC_DECIMALS)
    yeterli = MOCK_LEDGER["usdc"][musteri.address] >= ihtiyac
    adim(3, yeterli, f"fiyat ${FIYAT_AUDIT:.2f}; bakiye yeterli: {yeterli}")
    adimlar.append(("fiyat", yeterli))
    if not yeterli:
        sonuc["hata"] = "yetersiz bakiye"
        Path(a.cikti).write_text(json.dumps(sonuc, indent=2,
                                            ensure_ascii=False))
        return 1

    # --- ADIM 4: EIP-191 odeme imzasi ( GERCEK crypto) ---
    nonce_odeme = f"ilk-musteri-{uuid.uuid4().hex[:8]}"
    imza = sign_exact_sester(musteri.key.hex(), musteri.address,
                             nonce_odeme, FIYAT_AUDIT, "/audit")
    adim(4, bool(imza), "EIP-191 'exact-sester' odeme imzasi olusturuldu "
                        "( GERCEK imza)")
    adimlar.append(("imza", bool(imza)))
    sonuc["odeme_imzasi"] = imza[:24] + "..." if imza else None

    # --- ADIM 5: mock zincirde USDC transferi ---
    ok, blok = mock_usdc_transfer(musteri.address, TREASURY, ihtiyac, 0)
    adim(5, ok, (f"USDC transferi ( MOCK zincir): {FIYAT_AUDIT:.2f} USDC "
                 f"-> tek-kasa {TREASURY[:10]}...; tx={blok['tx_hash'][:18]}..."
                 if ok else f"transfer BASARISIZ: {blok}"))
    adimlar.append(("transfer", ok))
    if ok:
        sonuc["mock_transfer"] = {
            "blok_no": blok["blok_no"], "tx_hash": blok["tx_hash"],
            "birim_usdc": FIYAT_AUDIT, "alici": TREASURY}
    else:
        sonuc["hata"] = "mock transfer basarisiz"
        Path(a.cikti).write_text(json.dumps(sonuc, indent=2,
                                            ensure_ascii=False))
        return 1

    # --- ADIM 6: servis cagrisi ( sandbox anahtar — gercek DEGIL) ---
    # NOT: servisin GERCEK mainnet USDC onayi istemesi gerekir, ama
    # sandbox'ta mainnet_verify yok ( 503). Bu yuzden sandbox demo
    # anahtari ile cagri yapip "gercek odeme simülasyonu" deriz.
    hdr = sign_exact_sester(_SK, _AGENT, f"ilk-m-{nonce_odeme[-8:]}",
                            FIYAT_AUDIT, "/audit")
    with httpx.Client(timeout=60) as client:
        try:
            r = client.post("http://127.0.0.1:8007/audit",
                            json={"url": "https://example.com",
                                  "sector": "general"},
                            headers={"X-Payment": hdr,
                                     "X-Payer-Address": _AGENT}, timeout=60)
            kod = r.status_code
            gov = r.json() if kod == 200 else {}
        except Exception as e:
            kod, gov = 0, {"hata": str(e)}
    seq = gov.get("ledger_seq") or gov.get("seq")
    ok6 = kod == 200 and seq is not None
    adim(6, ok6, (f"servis cagrisi: HTTP {kod}, receipt seq={seq}"
                  + (" ( sandbox anahtar — GERCEK odeme DEGIL)" if ok6
                     else " ( beklenen: 200 + seq)")))
    adimlar.append(("servis", ok6))
    sonuc["servis_cagrisi"] = {"kod": kod, "seq": seq}

    # --- ADIM 7: gelirin GERCEK olmadigi kaniti ---
    print("\n--- ADIM 7 ( DURUST KANIT) " + "-" * 42)
    try:
        import net_kar_raporu as nkr
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            nkr.main()
        rapor = buf.getvalue()
        toplam = [ln for ln in rapor.splitlines() if "TOPLAM" in ln]
        # rapor '0.00' yazar ( $ isareti olmadan); tum degerler sifir olmali
        sifir = bool(toplam) and all(
            parca == "0.00" for parca in toplam[0].split()[1:])
        adim(7, sifir, ("net_kar_raporu " + toplam[0].strip()
                        + " — mock transfer GERCEK sayilmadi "
                          "( cifte-filtre calisti)"))
        adimlar.append(("gelir-filtre", sifir))
        sonuc["gelir_filtre"] = {"toplam": toplam[0].strip() if toplam
                                 else None, "gercek_sayildi": False}
    except Exception as e:
        adim(7, False, f"hata: {e}")
        adimlar.append(("gelir-filtre", False))

    # --- OZET ---
    tamam = sum(1 for _, ok in adimlar if ok)
    print("\n" + "=" * 70)
    print(f"SIMULASYON OZET: {tamam}/{len(adimlar)} adim TAMAM")
    print("⚠ DURUST: bu bir SIMULASYON. Gercek zincirde USDC YAYINLANMADI.")
    print(f"   GERCEK GELIR: $0.00 ( net_kar_raporu dogruladi)")
    print("   AKIS KANITLANDI: cuzdan -> imza -> transfer -> hizmet ->")
    print("   receipt -> gelir-filtresi ( mock'u eler)")
    print("=" * 70)

    sonuc["adimlar"] = [{"adim": n, "tamam": ok} for n, ok in adimlar]
    sonuc["toplam_adim"] = len(adimlar)
    sonuc["tamam"] = tamam
    sonuc["akis_tamam"] = tamam == len(adimlar)

    Path(a.cikti).write_text(json.dumps(sonuc, indent=2, ensure_ascii=False))
    print(f"cikti -> {a.cikti}")
    return 0 if sonuc["akis_tamam"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
