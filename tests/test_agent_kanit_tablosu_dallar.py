"""agent_kanit_tablosu dal-kesen testleri (LEED) — _agent_istatistik + main.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — receipts.sqlite'lar tmp_path altinda uretilir,
WS modul-niteligine yeniden baglanir (~/.workspace DOKUNULMAZ);
_sandbox_adresleri_tamamla stub'lanir (uretim .env.production OKUNMAZ);
dis ag / ana-zincir / subprocess YOK.

DALLAR:
  _agent_istatistik: db-yok / tablo-yok / bos-tablo / sandbox-elene /
    sandbox case-quirk (buyuk harf eslesmez) / agent_id None / amount None /
    case-insensitive merge / event_type-filtre / cifte-filtre sinirlari
    (>=5 cagri VEYA >=$5) / round-2 / gercek_musteri / read-only
  main: rc=0 / sandbox-fonksiyonu cagrilir / hicbir-agent-yok mesaji /
    ✓ EVET / ✗ hayir / planlock-4021 satiri / toplam receipt / gercek
    sayisi / PQHaven notu / sorted iterasyon / baslik+esik
  sabit: ESIK degerleri / PLANLOCK / PORTLAR tipleri / import bag'i
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/home/gokun/projects/00_TAMGA-MESH/unpump")

import agent_kanit_tablosu as akt  # noqa: E402

BOS_IST = {"toplam": 0, "sandbox_disi": 0, "gercek": 0,
           "gercek_gelir": 0.0, "gercek_musteri": False}


@pytest.fixture()
def ws(monkeypatch, tmp_path):
    """ORTAM: WS modul-niteligini tmp'ye baglar — uretim ~/.workspace'sine
    HIC dokunulmaz (Kural-4: saf in-memory)."""
    kok = tmp_path / "ws"
    kok.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(akt, "WS", kok, raising=False)
    return kok


@pytest.fixture()
def sandboxlar(monkeypatch):
    """_sandbox_adresleri_tamamla -> sabit canli kume (disk/ag OKUMA YOK).
    Testler bu kumeye eleman ekleyip cikarabilir; main() ayni kumeyi gorur."""
    sabit = {"0xsandbox"}
    monkeypatch.setattr(akt, "_sandbox_adresleri_tamamla",
                        lambda: sabit, raising=False)
    return sabit


@pytest.fixture()
def kucuk_portlar(monkeypatch):
    """main()'i 2 servisli kucuk bir gateway'e hapseder (30 port yerine)."""
    monkeypatch.setattr(akt, "PORTLAR",
                        {"beta": 8002, "alpha": 8001}, raising=False)
    return akt.PORTLAR


# == yardimcilar ================================================================================

def _db_yol(kok: Path, isim: str) -> Path:
    return kok / isim / "receipts.sqlite"


def _receipts_yaz(kok: Path, isim: str, satirlar) -> Path:
    """satirlar: (event_type, agent_id, amount) demetleri."""
    yol = _db_yol(kok, isim)
    yol.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(yol)
    c.execute(
        "CREATE TABLE IF NOT EXISTS events (event_type TEXT, agent_id TEXT, "
        "amount REAL)")
    c.executemany(
        "INSERT INTO events (event_type, agent_id, amount) VALUES (?,?,?)",
        satirlar)
    c.commit()
    c.close()
    return yol


def _coğalt(kok: Path, isim: str, agent: str, adet: int,
            tutar: float = 0.50) -> Path:
    """Ayni agent icin 'adet' adet charge_receipt ekle."""
    return _receipts_yaz(kok, isim,
                         [("charge_receipt", agent, tutar)] * adet)


def _oku(yol: Path) -> list:
    c = sqlite3.connect(yol)
    satirlar = c.execute(
        "SELECT event_type, agent_id, amount FROM events ORDER BY rowid"
    ).fetchall()
    c.close()
    return satirlar


# == _agent_istatistik: temel (basari) ============================================================

def test_db_yok_bos_donar(ws):
    assert akt._agent_istatistik(_db_yol(ws, "yokagent"), set()) == BOS_IST


def test_db_yok_bes_anahtar(ws):
    ist = akt._agent_istatistik(_db_yol(ws, "yokagent"), set())
    assert set(ist.keys()) == {"toplam", "sandbox_disi", "gercek",
                               "gercek_gelir", "gercek_musteri"}


def test_tablo_yok_bos_donar(ws):
    """ORTAM: events tablosu yoksa sorgu patlar -> bos sozluk."""
    yol = _db_yol(ws, "gamma")
    yol.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(yol)
    c.close()
    assert akt._agent_istatistik(yol, set()) == BOS_IST


def test_bos_tablo_bos_donar(ws):
    _receipts_yaz(ws, "delta", [])
    assert akt._agent_istatistik(_db_yol(ws, "delta"), set()) == BOS_IST


def test_tek_receipt_toplam_bir(ws):
    _receipts_yaz(ws, "alpha", [("charge_receipt", "0xali", 1.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["toplam"] == 1
    assert ist["sandbox_disi"] == 1


def test_tek_receipt_gercek_degil(ws):
    """ORTAM: 1 cagri $1 -> cifte-filtreye TAKILMADI (<5 cagri, <$5)."""
    _receipts_yaz(ws, "alpha", [("charge_receipt", "0xali", 1.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["gercek"] == 0
    assert ist["gercek_musteri"] is False


def test_tipleri_doğru(ws):
    """ORTAM: gecen agent varsa gercek_gelir float (sum float uzerinde)."""
    _coğalt(ws, "alpha", "0xali", adet=6, tutar=1.00)
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert isinstance(ist["toplam"], int)
    assert isinstance(ist["sandbox_disi"], int)
    assert isinstance(ist["gercek"], int)
    assert isinstance(ist["gercek_gelir"], float)
    assert isinstance(ist["gercek_musteri"], bool)


def test_bos_toplam_gercek_gelir_sifir(ws):
    """ORTAM (quirk): gecen agent YOKSA sum([]) -> int 0 (round(0,2) int).
    Deger 0.0'a esittir (0 == 0.0)."""
    _receipts_yaz(ws, "alpha", [("charge_receipt", "0xali", 1.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["gercek_gelir"] == 0.0
    assert ist["gercek_gelir"] == 0


# == _agent_istatistik: sandbox filtreleme =========================================================

def test_sandbox_agent_elene(ws, sandboxlar):
    _receipts_yaz(ws, "alpha", [("charge_receipt", "0xsandbox", 99.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), sandboxlar)
    assert ist["toplam"] == 1
    assert ist["sandbox_disi"] == 0
    assert ist["gercek"] == 0


def test_sandbox_agent_cifte_filtreye_girmez(ws, sandboxlar):
    """ORTAM: sandbox adresi esik gecse bile gercek sayilmaz."""
    _coğalt(ws, "alpha", "0xsandbox", adet=10, tutar=10.00)
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), sandboxlar)
    assert ist["toplam"] == 10
    assert ist["sandbox_disi"] == 0
    assert ist["gercek"] == 0
    assert ist["gercek_musteri"] is False


def test_sandbox_lowercase_eslesir(ws, sandboxlar):
    """ORTAM: agent_id lower()'laninca kucuk-harfli sandbox kumesine takilir."""
    sandboxlar.add("0xabc")
    _receipts_yaz(ws, "alpha", [("charge_receipt", "0xABC", 5.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), sandboxlar)
    assert ist["sandbox_disi"] == 0


def test_sandbox_buyuk_harf_eslesmez(ws, sandboxlar):
    """ORTAM (quirk): sandbox kumesinde BUYUK harf varsa lower()'li agent
    takilmaz — karsilastirma case-sensitive."""
    sandboxlar.add("0xABC")
    _receipts_yaz(ws, "alpha", [("charge_receipt", "0xabc", 5.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), sandboxlar)
    assert ist["sandbox_disi"] == 1


def test_sandbox_bos_kume_hic_elemez(ws):
    _receipts_yaz(ws, "alpha", [("charge_receipt", "0xali", 5.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["sandbox_disi"] == 1


def test_karisan_sandbox_ve_gercek(ws, sandboxlar):
    """ORTAM: sandbox (esik geciyor) + gercek (esik geciyor) karisimi —
    gercek sadece gercek agent'tan sayilir."""
    _coğalt(ws, "alpha", "0xsandbox", adet=10, tutar=10.00)
    _coğalt(ws, "alpha", "0xgercek", adet=6, tutar=1.00)
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), sandboxlar)
    assert ist["toplam"] == 16
    assert ist["sandbox_disi"] == 6
    assert ist["gercek"] == 6
    assert ist["gercek_gelir"] == 6.00
    assert ist["gercek_musteri"] is True


# == _agent_istatistik: veri bicimi dallari =======================================================

def test_amount_none_gelir_sifir(ws):
    """ORTAM: float(amount or 0) — NULL amount 0.0 sayilir, cagri sayilir."""
    _receipts_yaz(ws, "alpha", [("charge_receipt", "0xali", None)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["toplam"] == 1
    assert ist["sandbox_disi"] == 1
    assert ist["gercek_gelir"] == 0.0


def test_agent_id_none_bos_bucket(ws):
    """ORTAM: (agent_id or '').lower() -> '' bucket'inda toplanir."""
    _receipts_yaz(ws, "alpha", [("charge_receipt", None, 5.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["sandbox_disi"] == 1


def test_iki_agent_iki_bucket(ws):
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", "0xali", 1.00),
        ("charge_receipt", "0xbet", 2.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["toplam"] == 2
    assert ist["sandbox_disi"] == 2


def test_ayni_agent_merge_olur(ws):
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", "0xali", 1.00),
        ("charge_receipt", "0xali", 2.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["toplam"] == 2
    assert ist["sandbox_disi"] == 2


def test_case_insensitive_merge(ws):
    """ORTAM: 'Agent1' ve 'agent1' ayni bucket'ta birlesir (lower())."""
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", "Agent1", 1.00),
        ("charge_receipt", "agent1", 2.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["toplam"] == 2
    assert ist["sandbox_disi"] == 2


def test_event_type_filtre(ws):
    """ORTAM: sadece event_type='charge_receipt' sayilir."""
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", "0xali", 1.00),
        ("audit_log", "0xali", 1.00),
        ("other_event", "0xali", 1.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["toplam"] == 1
    assert ist["sandbox_disi"] == 1


# == _agent_istatistik: cifte-filtre sinirlari (>=5 cagri VEYA >=$5) ===============================

def test_bes_cagri_gercek_tam_esik(ws):
    """SINIR: tam 5 cagri ($2.50) -> gercek (cagri esigi >=5)."""
    _coğalt(ws, "alpha", "0xali", adet=5, tutar=0.50)
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["gercek"] == 5
    assert ist["gercek_gelir"] == 2.50
    assert ist["gercek_musteri"] is True


def test_dort_cagri_dort_dolar_gercek_degil(ws):
    """SINIR: 4 cagri $4.00 -> esik altinda her iki kosulda da (<5, <$5)."""
    _coğalt(ws, "alpha", "0xali", adet=4, tutar=1.00)
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["gercek"] == 0
    assert ist["gercek_musteri"] is False


def test_dort_cagri_bes_dolar_gercek_tam_esik(ws):
    """SINIR: 4 cagri $5.00 -> gercek (harcama esigi >=$5, tam sinir)."""
    _coğalt(ws, "alpha", "0xali", adet=4, tutar=1.25)
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["gercek"] == 4
    assert ist["gercek_gelir"] == 5.00
    assert ist["gercek_musteri"] is True


def test_dort_cagri_esik_alti_gercek_degil(ws):
    """SINIR: 4 cagri $4.75 -> <5 cagri VE <$5 -> gercek degil."""
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", "0xali", 1.25),
        ("charge_receipt", "0xali", 1.25),
        ("charge_receipt", "0xali", 1.25),
        ("charge_receipt", "0xali", 1.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["gercek"] == 0


def test_tek_cagri_buyuk_gelir_gercek(ws):
    """SINIR: 1 cagri $100 -> gelir esigi gecer (cagri esigi onemsiz)."""
    _receipts_yaz(ws, "alpha", [("charge_receipt", "0xali", 100.00)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["gercek"] == 1
    assert ist["gercek_gelir"] == 100.00
    assert ist["gercek_musteri"] is True


def test_bes_cagri_buyuk_gelir_gercek(ws):
    """ORTAM: her iki esik de gecer (>=5 cagri VE >=$5)."""
    _coğalt(ws, "alpha", "0xali", adet=5, tutar=10.00)
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["gercek"] == 5
    assert ist["gercek_gelir"] == 50.00


def test_gercek_gelir_iki_basamak_round(ws):
    """ORTAM: round(gercek_gelir, 2) — 4x$1.3333 = $5.3332 -> $5.33."""
    _coğalt(ws, "alpha", "0xali", adet=4, tutar=1.3333)
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["gercek_gelir"] == 5.33


def test_gercek_sayisi_cagri_olarak_donar(ws):
    """ORTAM: 'gercek' gecen agent'in CAGRI sayisidir (gelir DEGIL)."""
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", "0xali", 2.50),
        ("charge_receipt", "0xali", 2.50)])
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["gercek"] == 2  # 2 cagri, $5.00 -> esik gecti


def test_sandbox_disi_gercegi_kapsar(ws):
    """ORTAM: gercek ⊆ sandbox_disi ⊆ toplam (gerçek ayrık küme)."""
    _coğalt(ws, "alpha", "0xali", adet=6, tutar=1.00)   # gercek
    _coğalt(ws, "alpha", "0xbet", adet=2, tutar=1.00)   # esik alti
    ist = akt._agent_istatistik(_db_yol(ws, "alpha"), set())
    assert ist["toplam"] == 8
    assert ist["sandbox_disi"] == 8
    assert ist["gercek"] == 6
    assert ist["gercek"] <= ist["sandbox_disi"] <= ist["toplam"]


# == _agent_istatistik: hata dallari (basarisizlik) ================================================

def test_db_dizin_connect_hatasi_bos(ws):
    """ORTAM: yol bir DIZIN ise exists() True ama mode=ro connect patlar
    -> bos sozluk."""
    yol = _db_yol(ws, "dizinagent")
    yol.mkdir(parents=True, exist_ok=True)
    assert akt._agent_istatistik(yol, set()) == BOS_IST


def test_connect_istisna_bos_donar(monkeypatch, ws):
    """ORTAM: sqlite3.connect exception firlatirsa -> bos sozluk."""
    yol = _db_yol(ws, "epsilon")
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.touch()

    def _patla(*args, **kwargs):
        raise sqlite3.OperationalError("db-down")

    monkeypatch.setattr(akt.sqlite3, "connect", _patla)
    assert akt._agent_istatistik(yol, set()) == BOS_IST


def test_ro_uri_yazmaya_izin_vermez(ws):
    """ORTAM: 'file:...?mode=ro' URI'si read-only — INSERT patlar."""
    yol = _receipts_yaz(ws, "alpha", [("charge_receipt", "0xali", 1.00)])
    c = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        c.execute("INSERT INTO events (event_type) VALUES ('x')")
    c.close()


def test_read_only_db_degismez(ws):
    """ORTAM: istatistik read-only — cagri sonrasi icerik birebir ayni."""
    yol = _receipts_yaz(ws, "alpha", [
        ("charge_receipt", "0xali", 1.00),
        ("charge_receipt", "0xbet", 2.00)])
    once = _oku(yol)
    akt._agent_istatistik(yol, set())
    assert _oku(yol) == once


# == main ==========================================================================================

def test_main_sifir_doner(ws, kucuk_portlar, sandboxlar):
    assert akt.main() == 0


def test_main_baslik_ve_esik_yazdirir(ws, kucuk_portlar, sandboxlar, capsys):
    akt.main()
    cikti = capsys.readouterr().out
    assert "AGENT BAZINDA GERCEK-ODEME KANIT TABLOSU" in cikti
    assert "esik: >=5 cagri VEYA >=$5" in cikti
    assert "audit-test adresleri elenir" in cikti


def test_main_sandbox_fonksiyonu_cagrilir(monkeypatch, ws):
    """ORTAM: main() _sandbox_adresleri_tamamla()'yi cagirir (stub spy)."""
    cagri = []

    def _spy():
        cagri.append(1)
        return {"0xsbx"}

    monkeypatch.setattr(akt, "_sandbox_adresleri_tamamla", _spy)
    monkeypatch.setattr(akt, "PORTLAR", {"alpha": 8001}, raising=False)
    akt.main()
    assert cagri == [1]


def test_main_bos_ortam_hicbir_agent_yok(ws, kucuk_portlar, sandboxlar,
                                         capsys):
    """ORTAM: gercek musteri YOKSA 'HICBIR agent'ta GERCEK musteri YOK'
    mesaji yazilir (dürüst rapor)."""
    akt.main()
    cikti = capsys.readouterr().out
    assert "HICBIR agent'ta GERCEK musteri YOK" in cikti
    assert "0/20" in cikti or "DURUST" in cikti


def test_main_bos_ortam_hayir_isareti(ws, kucuk_portlar, sandboxlar, capsys):
    akt.main()
    cikti = capsys.readouterr().out
    assert "✗ hayir" in cikti


def test_main_gercek_agent_evet_yazdirir(ws, kucuk_portlar, sandboxlar,
                                         capsys):
    _coğalt(ws, "alpha", "0xali", adet=5, tutar=0.50)
    akt.main()
    cikti = capsys.readouterr().out
    assert "✓ EVET" in cikti
    assert "✅ 1 agent GERCEK odeme aldi" in cikti
    assert "alpha: 5 cagri, $2.50" in cikti


def test_main_gercek_sayisi_dogru(ws, kucuk_portlar, sandboxlar, capsys):
    _coğalt(ws, "alpha", "0xali", adet=5, tutar=0.50)
    _receipts_yaz(ws, "beta", [("charge_receipt", "0xbet", 100.00)])
    akt.main()
    cikti = capsys.readouterr().out
    assert "GERCEK musteri olan agent   : 2" in cikti


def test_main_planlock_satiri_4021(ws, kucuk_portlar, sandboxlar, capsys):
    """ORTAM: PlanLock (TypeScript) sabit 4021 port satiri eklenir."""
    akt.main()
    cikti = capsys.readouterr().out
    assert "planlock" in cikti
    assert "4021" in cikti
    assert "(TS)" in cikti


def test_main_toplam_receipt_dogru(ws, kucuk_portlar, sandboxlar, capsys):
    _coğalt(ws, "alpha", "0xali", adet=5, tutar=0.50)
    _receipts_yaz(ws, "beta", [("charge_receipt", "0xbet", 100.00)])
    akt.main()
    cikti = capsys.readouterr().out
    assert "Toplam receipt ( tum cagri) : 6" in cikti


def test_main_gercek_odeme_toplami(ws, kucuk_portlar, sandboxlar, capsys):
    """ORTAM: $2.50 (alpha) + $100.00 (beta) = $102.50."""
    _coğalt(ws, "alpha", "0xali", adet=5, tutar=0.50)
    _receipts_yaz(ws, "beta", [("charge_receipt", "0xbet", 100.00)])
    akt.main()
    cikti = capsys.readouterr().out
    assert "GERCEK odeme ( cifte-filtre): $102.50" in cikti


def test_main_toplam_agent_sayisi(ws, kucuk_portlar, sandboxlar, capsys):
    """ORTAM: len(tum) = PORTLAR + 1 (planlock satiri)."""
    akt.main()
    cikti = capsys.readouterr().out
    assert "Toplam agent ( gateway)      : 3" in cikti


def test_main_tum_portlarin_satiri_var(ws, kucuk_portlar, sandboxlar,
                                       capsys):
    akt.main()
    cikti = capsys.readouterr().out
    assert "alpha" in cikti
    assert "beta" in cikti
    assert "8001" in cikti
    assert "8002" in cikti


def test_main_sorted_iterasyon(ws, kucuk_portlar, sandboxlar, capsys):
    """ORTAM: main() sorted(PORTLAR) uzerinde iterasyon — tabloda alpha
    beta'dan once gelir."""
    _receipts_yaz(ws, "alpha", [("charge_receipt", "0xali", 1.00)])
    _receipts_yaz(ws, "beta", [("charge_receipt", "0xbet", 1.00)])
    akt.main()
    cikti = capsys.readouterr().out
    assert cikti.index("alpha") < cikti.index("beta")


def test_main_pqhaven_notu(ws, kucuk_portlar, sandboxlar, capsys):
    akt.main()
    cikti = capsys.readouterr().out
    assert "NOT ( PQHaven)" in cikti
    assert "gunluk kota $10.00 dolu" in cikti


def test_main_gercek_agent_sandbox_elene(ws, kucuk_portlar, sandboxlar,
                                         capsys):
    """ORTAM: sandbox adresi esik gecse bile '✓ EVET' listesinde YOK."""
    _coğalt(ws, "alpha", "0xsandbox", adet=10, tutar=10.00)
    akt.main()
    cikti = capsys.readouterr().out
    assert "✅" not in cikti
    assert "GERCEK musteri olan agent   : 0" in cikti


# == sabit degerler (modul kontrati) ================================================================

def test_esik_degerleri():
    assert akt.ESIK_CAGRI == 5
    assert akt.ESIK_HARCAMA == 5.0


def test_planlock_sozlugu():
    assert akt.PLANLOCK == {"planlock": 4021}


def test_portlar_int_tipli():
    for port in akt.PORTLAR.values():
        assert isinstance(port, int)


def test_net_kar_raporu_import_baginti():
    """ORTAM: net_kar_raporu'dan alinan SERVIS_DBLERI + fonksiyonlar
    modulde mevcut (import bag'i)."""
    assert isinstance(akt.SERVIS_DBLERI, dict)
    assert callable(akt._sandbox_adresleri_tamamla)


def test_gomulu_test_gecer(ws, kucuk_portlar, sandboxlar):
    """ORTAM: modulun kendi test_agent_kanit_gecer kapsulu calisir
    (main()==0 doner)."""
    akt.test_agent_kanit_geçer()
