"""budget_auditor dal-kesen testleri (LEED) — _servis_harcama + denetle + main.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — receipts.sqlite'lar tmp_path altinda uretilir,
WS modul-niteligine yeniden baglanir (~/.workspace DOKUNULMAZ); dis cagri,
ag veya ana-zincir YOK; cikti dosyasi tmp_path'e yazilir.

DALLAR:
  _servis_harcama: db-yok / connect-hatasi / tablo-yok (cift-hata dali) /
    bugun-toplami / farkli-gun-elene / event_type-filtre / NULL-amount /
    negatif-amount / timestamp-yok fallback / read-only (mode=ro)
  denetle: OK (<80) / UYARI (>=80) / KOTA-DOLDU (>=100) / sinir-79.99 /
    sinir-99.99 / kota=0 defansif dali / KOTALAR.get default / dosya-cikti
    (mkdir parents + append) / dosya=None / karisik ortam (2 alarm)
  main: denetle ile ayni / alarm varken 1 / stdout'a yazar
  sabit: SERVISLER 27 / KOTALAR tutarliligi
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, "/home/gokun/projects/00_TAMGA-MESH/unpump")

import budget_auditor as ba  # noqa: E402

# Sabit tarih — gece-yarisi date.today() atlamasi testleri kirilmasin.
_SABIT_GUN = "2026-09-26"
_DIGER_GUN = "2026-09-25"


class _SabitDate:
    """budget_auditor.date yerine gecer — today() hep ayni gunu doner."""

    @staticmethod
    def today() -> date:
        return date(2026, 9, 26)


@pytest.fixture(autouse=True)
def sabit_tarih(monkeypatch):
    """ORTAM: date.today() sabitlenir (deterministic bugun-filtresi)."""
    monkeypatch.setattr(ba, "date", _SabitDate, raising=False)


@pytest.fixture()
def ws(monkeypatch, tmp_path):
    """ORTAM: WS modul-niteligini tmp'ye baglar — uretim ~/.workspace'sine
    HIC dokunulmaz (Kural-4: saf in-memory)."""
    kok = tmp_path / "ws"
    kok.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ba, "WS", kok, raising=False)
    return kok


@pytest.fixture()
def tek_servis(monkeypatch):
    """denetle'yi TEK servisli kucuk bir ortama hapseder (27 servis yerine)."""

    def _kur(servis: str = "alpha", kota: float = 10.00) -> str:
        monkeypatch.setattr(ba, "SERVISLER", [servis], raising=False)
        monkeypatch.setattr(ba, "KOTALAR", {servis: kota}, raising=False)
        return servis

    return _kur


# == yardimcilar ================================================================================

def _db_yol(kok: Path, servis: str) -> Path:
    return kok / servis / "receipts.sqlite"


def _receipts_yaz(kok: Path, servis: str, satirlar) -> Path:
    """satirlar: (event_type, timestamp, agent_id, amount) demetleri."""
    yol = _db_yol(kok, servis)
    yol.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(yol)
    c.execute(
        "CREATE TABLE events (event_type TEXT, timestamp TEXT, "
        "agent_id TEXT, amount REAL)")
    c.executemany(
        "INSERT INTO events (event_type, timestamp, agent_id, amount) "
        "VALUES (?,?,?,?)", satirlar)
    c.commit()
    c.close()
    return yol


def _receipts_yaz_timestampsiz(kok: Path, servis: str, satirlar) -> Path:
    """timestamp kolonu YOK — denetle'nin fallback dalini zorlar."""
    yol = _db_yol(kok, servis)
    yol.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(yol)
    c.execute(
        "CREATE TABLE events (event_type TEXT, agent_id TEXT, amount REAL)")
    c.executemany(
        "INSERT INTO events (event_type, agent_id, amount) VALUES (?,?,?)",
        satirlar)
    c.commit()
    c.close()
    return yol


def _oku(yol: Path) -> list:
    c = sqlite3.connect(yol)
    satirlar = c.execute(
        "SELECT event_type, timestamp, agent_id, amount FROM events "
        "ORDER BY rowid").fetchall()
    c.close()
    return satirlar


# == _servis_harcama: temel (basari) ==============================================================

def test_db_yok_sifir_doner(ws):
    assert ba._servis_harcama(_db_yol(ws, "yokservis")) == (0.0, 0)


def test_db_yok_float_int_tipleri(ws):
    harcama, cagri = ba._servis_harcama(_db_yol(ws, "yokservis"))
    assert isinstance(harcama, float)
    assert isinstance(cagri, int)


def test_tablo_yok_alarm_verir_unpump_b1(ws, capsys):
    """UNPUMP-B1 (DUZELTILDI): events-tablosu-yoksa-eski-kod-harcamayi-
    gizliyordu-( 0.0, 0-fail-open). Artik-okunamayan-veri-alarm-vericidir
    ( inf-asim-indirir-ve-stderr-uyarisi-yazar)."""
    yol = _db_yol(ws, "gamma")
    yol.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(yol)  # bos DB (hic tablo yok)
    c.close()
    sonuc = ba._servis_harcama(yol)
    assert sonuc[0] == float("inf")
    assert "okunamadi" in capsys.readouterr().err


def test_bos_tablo_sifir_doner(ws):
    _receipts_yaz(ws, "delta", [])
    assert ba._servis_harcama(_db_yol(ws, "delta")) == (0.0, 0)


def test_tek_receipt_toplami(ws):
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T12:00:00Z", "0xali", 3.50)])
    assert ba._servis_harcama(_db_yol(ws, "alpha")) == (3.50, 1)


def test_uc_receipt_toplam_ve_sayi(ws):
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 1.50),
        ("charge_receipt", _SABIT_GUN + "T02:00:00Z", "0xbet", 2.50),
        ("charge_receipt", _SABIT_GUN + "T03:00:00Z", "0xgam", 4.00)])
    assert ba._servis_harcama(_db_yol(ws, "alpha")) == (8.00, 3)


def test_tutar_float_doner(ws):
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 1.0)])
    harcama, _ = ba._servis_harcama(_db_yol(ws, "alpha"))
    assert isinstance(harcama, float)


def test_cagri_int_doner(ws):
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 1.0)])
    _, cagri = ba._servis_harcama(_db_yol(ws, "alpha"))
    assert isinstance(cagri, int)


def test_charge_receipt_disinda_event_elene(ws):
    """ORTAM: sadece event_type='charge_receipt' sayilir."""
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 1.00),
        ("other_event", _SABIT_GUN + "T02:00:00Z", "0xbet", 100.00),
        ("audit_log", _SABIT_GUN + "T03:00:00Z", "0xgam", 999.00)])
    assert ba._servis_harcama(_db_yol(ws, "alpha")) == (1.00, 1)


def test_farkli_gun_receipt_elene(ws):
    """ORTAM: substr(timestamp,1,10) bugun degilse sayilmaz."""
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _DIGER_GUN + "T01:00:00Z", "0xali", 50.00),
        ("charge_receipt", "2026-09-24T01:00:00Z", "0xbet", 60.00)])
    assert ba._servis_harcama(_db_yol(ws, "alpha")) == (0.0, 0)


def test_bugun_receipt_diger_gunden_ayrilir(ws):
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 2.00),
        ("charge_receipt", _DIGER_GUN + "T01:00:00Z", "0xbet", 9.00)])
    assert ba._servis_harcama(_db_yol(ws, "alpha")) == (2.00, 1)


def test_tarihsiz_timestamp_elene(ws):
    """ORTAM: substr(1,10) 'bugun' gibi tarih olmayan degerse eslesmez."""
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", "bugun", "0xali", 7.00)])
    assert ba._servis_harcama(_db_yol(ws, "alpha")) == (0.0, 0)


def test_amount_null_cagri_sayilir(ws):
    """ORTAM: COALESCE(SUM(amount),0) -> NULL 0.0; COUNT(*) 1."""
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", None)])
    assert ba._servis_harcama(_db_yol(ws, "alpha")) == (0.0, 1)


def test_negatif_amount_toplanir(ws):
    """ORTAM: defansif — negatif amount kontrolu YOK, oldugu gibi toplanir."""
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 5.00),
        ("charge_receipt", _SABIT_GUN + "T02:00:00Z", "0xbet", -2.50)])
    assert ba._servis_harcama(_db_yol(ws, "alpha")) == (2.50, 2)


# == _servis_harcama: fallback (timestamp kolonu yok) ==============================================

def test_timestamp_yok_fallback_tumunu_sayar(ws):
    """ORTAM: timestamp kolonu yoksailk sorgu patlar, fallback tum
    charge_receipt'leri sayar (tarih filtresiz)."""
    _receipts_yaz_timestampsiz(ws, "alpha", [
        ("charge_receipt", "0xali", 1.00),
        ("charge_receipt", "0xbet", 2.00),
        ("other_event", "0xgam", 9.00)])
    assert ba._servis_harcama(_db_yol(ws, "alpha")) == (3.00, 2)


def test_timestamp_yok_fallback_sadece_charge(ws):
    _receipts_yaz_timestampsiz(ws, "alpha", [
        ("audit_log", "0xgam", 9.00),
        ("charge_receipt", "0xali", 4.00)])
    assert ba._servis_harcama(_db_yol(ws, "alpha")) == (4.00, 1)


def test_timestamp_yok_bos_sifir(ws):
    _receipts_yaz_timestampsiz(ws, "alpha", [])
    assert ba._servis_harcama(_db_yol(ws, "alpha")) == (0.0, 0)


# == _servis_harcama: hata dallari (basarisizlik) ===================================================

def test_db_dizin_connect_hatasi_alarm_verir_unpump_b1(ws, capsys):
    """UNPUMP-B1 (DUZELTILDI): yol-DIZIN-ise-connect-patlar — eski-kod-
    ( 0.0, 0)-fail-open; artik-inf-alarm ( gizli-harcama-yok)."""
    yol = _db_yol(ws, "dizinservis")
    yol.mkdir(parents=True, exist_ok=True)
    sonuc = ba._servis_harcama(yol)
    assert sonuc[0] == float("inf")
    assert "okunamadi" in capsys.readouterr().err


def test_connect_istisna_alarm_verir_unpump_b1(monkeypatch, ws, capsys):
    """UNPUMP-B1 (DUZELTILDI): connect-istisnasinda-eski-kod-( 0.0, 0)-
    donup-harcamayi-gizliyordu; artik-inf-alarm-ve-stderr-uyarisi."""
    yol = _db_yol(ws, "epsilon")
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.touch()

    def _patla(*args, **kwargs):
        raise sqlite3.OperationalError("db-down")

    monkeypatch.setattr(ba.sqlite3, "connect", _patla)
    sonuc = ba._servis_harcama(yol)
    assert sonuc[0] == float("inf")
    assert "okunamadi" in capsys.readouterr().err


def test_ro_uri_yazmaya_izin_vermez(ws):
    """ORTAM: 'file:...?mode=ro' URI'si gercekten read-only — INSERT
    OperationalError firlatir (read-only kontrat)."""
    yol = _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 1.00)])
    c = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        c.execute("INSERT INTO events (event_type) VALUES ('x')")
    c.close()


def test_read_only_db_degismez(ws):
    """ORTAM: denetim read-only — cagri sonrasi icerik birebir ayni kalir."""
    yol = _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 1.50),
        ("charge_receipt", _SABIT_GUN + "T02:00:00Z", "0xbet", 2.50)])
    once = _oku(yol)
    assert ba._servis_harcama(yol) == (4.00, 2)
    assert _oku(yol) == once


# == denetle: durum dallari ========================================================================

def test_denetle_bos_ortam_sifir_doner(ws, tek_servis):
    tek_servis("alpha")
    assert ba.denetle() == 0


def test_denetle_alarmsiz_yazdirir(ws, tek_servis, capsys):
    tek_servis("alpha")
    rc = ba.denetle()
    cikti = capsys.readouterr().out
    assert rc == 0
    assert "ALARMSIZ" in cikti
    assert "tum servisler kota icinde" in cikti


def test_denetle_baslik_ve_ozet(ws, tek_servis, capsys):
    tek_servis("alpha")
    ba.denetle()
    cikti = capsys.readouterr().out
    assert "BUDGET AUDIT" in cikti
    assert f"{_SABIT_GUN}" in cikti
    assert "TOPLAM harcama" in cikti
    assert "read-only" in cikti


def test_denetle_ortalama_ok(ws, tek_servis, capsys):
    tek_servis("alpha")
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 5.00)])
    rc = ba.denetle()
    cikti = capsys.readouterr().out
    assert rc == 0
    assert " OK" in cikti


def test_denetle_tam_seksen_uyari(ws, tek_servis, capsys):
    """SINIR: %80.0 -> UYARI + alarm (>=80)."""
    tek_servis("alpha")
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 8.00)])
    rc = ba.denetle()
    cikti = capsys.readouterr().out
    assert rc == 1
    assert "UYARI" in cikti
    assert "alarm: 1 servis" in cikti


def test_denetle_yetmis_dokuz_dokuz_ok(ws, tek_servis, capsys):
    """SINIR: %79.99 -> OK (>=80 DEGIL), alarm YOK."""
    tek_servis("alpha")
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 7.999)])
    rc = ba.denetle()
    cikti = capsys.readouterr().out
    assert rc == 0
    assert "UYARI" not in cikti


def test_denetle_tam_yuz_kota_doldu(ws, tek_servis, capsys):
    """SINIR: %100.0 -> KOTA-DOLDU + asim listesi."""
    tek_servis("alpha")
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 10.00)])
    rc = ba.denetle()
    cikti = capsys.readouterr().out
    assert rc == 1
    assert "KOTA-DOLDU" in cikti
    assert "ALARMLAR:" in cikti
    assert "alpha" in cikti


def test_denetle_doksan_dokuz_dokuz_uyari(ws, tek_servis, capsys):
    """SINIR: %99.99 -> UYARI (>=100 DEGIL, asim listesinde YOK)."""
    tek_servis("alpha")
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 9.999)])
    rc = ba.denetle()
    cikti = capsys.readouterr().out
    assert rc == 1
    assert "UYARI" in cikti
    assert "KOTA-DOLDU" not in cikti


def test_denetle_yuz_elli_asim_mesaji(ws, tek_servis, capsys):
    tek_servis("alpha")
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 15.00)])
    rc = ba.denetle()
    cikti = capsys.readouterr().out
    assert rc == 1
    assert "gunluk kotayi doldurdu" in cikti
    assert "fail-closed budget" in cikti


def test_denetle_karisik_ortam_iki_alarm(ws, monkeypatch, capsys):
    """ORTAM: OK + UYARI + KOTA-DOLDU karisimi -> 2 alarm, asim listesinde
    sadece asan servis."""
    monkeypatch.setattr(ba, "SERVISLER", ["ok_s", "uyari_s", "asim_s"],
                        raising=False)
    monkeypatch.setattr(ba, "KOTALAR",
                        {"ok_s": 10.00, "uyari_s": 10.00, "asim_s": 10.00},
                        raising=False)
    _receipts_yaz(ws, "ok_s", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0x1", 5.00)])
    _receipts_yaz(ws, "uyari_s", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0x2", 8.00)])
    _receipts_yaz(ws, "asim_s", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0x3", 15.00)])
    rc = ba.denetle()
    cikti = capsys.readouterr().out
    assert rc == 1
    assert "alarm: 2 servis" in cikti
    assert "ALARMLAR: asim_s" in cikti
    assert "uyari_s" in cikti  # tablo satiri var
    assert "KOTA-DOLDU" in cikti


def test_denetle_kota_sifir_yuzde_sifir(ws, monkeypatch, capsys):
    """DEFANSIF DAL: kota=0.0 ise yuzde 0.0 (sifira bolme korumasi),
    durum OK, alarm YOK."""
    monkeypatch.setattr(ba, "SERVISLER", ["sifir_kota"], raising=False)
    monkeypatch.setattr(ba, "KOTALAR", {"sifir_kota": 0.0}, raising=False)
    _receipts_yaz(ws, "sifir_kota", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0x1", 100.00)])
    rc = ba.denetle()
    cikti = capsys.readouterr().out
    assert rc == 0
    assert "ALARMSIZ" in cikti


def test_denetle_kotalarda_yoksa_default_on(ws, monkeypatch, capsys):
    """ORTAM: KOTALAR.get(servis, 10.00) — servisin kotasi yoksa default
    10.00 uygulanir (9.00 harcama -> %90 -> UYARI)."""
    monkeypatch.setattr(ba, "SERVISLER", ["yeni_servis"], raising=False)
    monkeypatch.setattr(ba, "KOTALAR", {}, raising=False)
    _receipts_yaz(ws, "yeni_servis", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0x1", 9.00)])
    rc = ba.denetle()
    cikti = capsys.readouterr().out
    assert rc == 1  # %90 >= 80 -> UYARI
    assert "UYARI" in cikti


def test_denetle_servis_satiri_formati(ws, tek_servis, capsys):
    tek_servis("alpha")
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 5.00),
        ("charge_receipt", _SABIT_GUN + "T02:00:00Z", "0xbet", 1.00)])
    ba.denetle()
    cikti = capsys.readouterr().out
    assert "alpha" in cikti
    assert "harcama=$" in cikti
    assert "cagri=2" in cikti


# == denetle: dosya cikti dali =====================================================================

def test_denetle_dosya_none_olusmaz(ws, tek_servis, tmp_path):
    tek_servis("alpha")
    ba.denetle()
    assert list(tmp_path.glob("**/*.txt")) == []


def test_denetle_dosya_parent_olustur_ve_yazar(ws, tek_servis, tmp_path):
    """ORTAM: dosya.parent mkdir(parents=True) — olmayan derin klasor
    olusturulur ve rapor append'lenir."""
    tek_servis("alpha")
    dosya = tmp_path / "cikti" / "klasor" / "rapor.txt"
    rc = ba.denetle(dosya=dosya)
    assert rc == 0
    assert dosya.exists()
    icerik = dosya.read_text(encoding="utf-8")
    assert "BUDGET AUDIT" in icerik
    assert "ALARMSIZ" in icerik


def test_denetle_dosya_iki_cagri_append(ws, tek_servis, tmp_path):
    """ORTAM: append modu — iki cagrida iki rapor blogu."""
    tek_servis("alpha")
    dosya = tmp_path / "rapor.txt"
    ba.denetle(dosya=dosya)
    ba.denetle(dosya=dosya)
    icerik = dosya.read_text(encoding="utf-8")
    assert icerik.count("BUDGET AUDIT") == 2


def test_denetle_dosya_stdout_da_yazar(ws, tek_servis, tmp_path, capsys):
    tek_servis("alpha")
    dosya = tmp_path / "rapor.txt"
    ba.denetle(dosya=dosya)
    cikti = capsys.readouterr().out
    assert "BUDGET AUDIT" in cikti
    assert dosya.exists()


# == main ==========================================================================================

def test_main_denetle_ile_ayni(ws, tek_servis):
    """ORTAM: main() argumansiz denetle() cagirir."""
    tek_servis("alpha")
    assert ba.main() == ba.denetle()


def test_main_alarm_varsa_bir_doner(ws, tek_servis):
    tek_servis("alpha")
    _receipts_yaz(ws, "alpha", [
        ("charge_receipt", _SABIT_GUN + "T01:00:00Z", "0xali", 15.00)])
    assert ba.main() == 1


def test_main_stdout_a_yazar(ws, tek_servis, capsys):
    tek_servis("alpha")
    rc = ba.main()
    cikti = capsys.readouterr().out
    assert rc == 0
    assert "BUDGET AUDIT" in cikti


def test_main_gomulu_test_gecer(ws, tek_servis):
    """ORTAM: modulun kendi test_budget_auditor_gecer kapsulu calisir
    (main()==0 doner)."""
    tek_servis("alpha")
    ba.test_budget_auditor_geçer()


# == sabit degerler (modul kontrati) ================================================================

def test_servisler_yirmi_yedi():
    assert len(ba.SERVISLER) == 27


def test_servisler_benzersiz():
    assert len(set(ba.SERVISLER)) == len(ba.SERVISLER)


def test_kodincelemesi_kota_elli():
    assert ba.KOTALAR["kodincelemesi"] == 50.00


@pytest.mark.parametrize("servis",
                         [s for s in ba.SERVISLER if s != "kodincelemesi"])
def test_diger_servislerin_kotasi_on(servis):
    assert ba.KOTALAR[servis] == 10.00


def test_her_servisin_kotasi_var():
    """ORTAM: SERVISLER'in her uyesi KOTALAR'da mevcut (tutarlilik)."""
    for servis in ba.SERVISLER:
        assert servis in ba.KOTALAR
