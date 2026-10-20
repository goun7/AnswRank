"""tax_ledger dal-kesen testleri (LEED) — UNP-FIN-2/3/4 (DALGA-C-3).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: sahte-receipts-DB tmp_path icinde uretilir (~/.workspace DOKUNULMAZ).

DALLAR:
  _gercek_gelir: olu-kod-duzeltmesi — sandbox-disi gercek-geliri gosterir
    ( onceki koşulsuz 'return 0.0, 0'); sandbox-adres-filtresi + esik.
  gelir_cek: TEK-KASA sayisi artik dondurulur ( UNP-FIN-2).
  _sandbox_adresleri: 'buyer' + TEST_ADDR_MAINNET_VERIFY dahil ( UNP-FIN-4).
"""
from __future__ import annotations

import sqlite3
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.environ.get(
    "MESH_UNPUMP_ROOT",
    "/home/gokun/projects/00_TAMGA-MESH/unpump"))  # G47

import tax_ledger as tl  # noqa: E402


@pytest.fixture
def sahte_receipts(tmp_path, monkeypatch):
    """Servis-DB'sini tmp'ye yonlendirip ornek receipts yazar."""
    db = tmp_path / "receipts.sqlite"

    def _servis_db(isim: str) -> Path:
        return db

    monkeypatch.setattr(tl, "servis_db", _servis_db)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (agent_id TEXT, amount REAL, "
                "ts REAL, event_type TEXT, payload TEXT)")
    import time as _time
    _bugun = _time.time()  # gelir_cek BUGUN filtresi yapar
    con.executemany(
        "INSERT INTO events VALUES (?,?,?,?,?)",
        [
            ("0x26dbfe78d63509f845c147b8480079c6fbd28bfc", 0.05, _bugun,
             "charge_receipt", "{}"),
            ("buyer", 0.05, _bugun, "charge_receipt", "{}"),
            ("0x1563915e194d8cfba1943570603f7606a3115508", 0.05, _bugun,
             "charge_receipt", "{}"),
            ("0xgercek1", 0.05, _bugun, "charge_receipt",
             '{"pay_to": "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5"}'),
        ] * 10,  # 0xgercek1: 10 cagri >= ESIK_CAGRI
    )
    con.commit()
    con.close()
    return db


class TestGercekGelir:
    def test_sandbox_disi_esik_gecen_gercek_musteri(self, sahte_receipts):
        """UNP-FIN-3: _gercek_gelir artik DB'den OKUYOR — 0xgercek1
        ( 10 cagri >= ESIK) gercek-geliri olarak sayilir."""
        from net_kar_raporu import ESIK_CAGRI
        gelir, cagri = tl._gercek_gelir("callsnap",
                                        tl._sandbox_adresleri())
        assert gelir == pytest.approx(0.5, abs=1e-6), "10*0.05"
        assert cagri == 10
        assert 10 >= ESIK_CAGRI

    def test_sandbox_ve_test_anahtarlar_elendi(self, sahte_receipts):
        sb = tl._sandbox_adresleri()
        assert "buyer" in sb
        assert "0x1563915e194d8cfba1943570603f7606a3115508".lower() in sb
        gelir, cagri = tl._gercek_gelir("callsnap", sb)
        assert cagri == 10


class TestGelirCekTekKasa:
    def test_tek_kasa_sayisi_dondurulur(self, sahte_receipts):
        """UNP-FIN-2: gelir_cek artik ( gelir, cagri, tek_kasa) doner."""
        gelir, cagri, tek_kasa = tl.gelir_cek("callsnap")
        assert gelir == pytest.approx(2.0, abs=1e-6)  # 40*0.05
        assert cagri == 40
        assert tek_kasa == 10, "10 olayda TEK-KASA EOA payload'ta"

    def test_tek_kasa_sayisi_eskiden_yutuluyordu(self):
        """Yapi-garantisi: 3-demet donusu ( onceki 2'ydi)."""
        import inspect
        sig = str(inspect.signature(tl.gelir_cek))
        assert sig.count(",") == 2, "gelir_cek (gelir,cagri,tek_kasa) donmeli"
