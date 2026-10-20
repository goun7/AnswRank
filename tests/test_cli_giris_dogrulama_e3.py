#!/usr/bin/env python3
"""DALGA-E3 — CLI giris-dogrulama gate'i ( K4=2/100 duzeltmesi).

Onceki durum ( olcum-sonuclari):
  mainnet_verify.py --bogus  -> rc=0 ( SESSIZCE-yok-say)
  net_kar_raporu.py --bogus  -> rc=0 ( raporu-basip 'ok' dondu)
  --help                      -> rc=0 ama 0-BYTE cikti ( usage YOK)

Bu test GERCEK-subprocess ile rc'yi olcer ( import/monkeypatch DEGIL):
her cagri ayri bir python sureci oldugu icin 'truthy-exit' hatasi
kovalanamaz. PIPE yerine capture_output kullanildi ( gorev kurali:
ciktiyi PIPE-etme, rc'yi olc).

KAPSAM:
  A) mainnet_verify.py: --bogus rc=2, --help rc=0+cikti, -h rc=0,
     eksik-degerli flag rc=2, modul-importu bozulmaz
  B) net_kar_raporu.py: --bogus rc=2 ( rapor-basma YOK), --help
     rc=0+cikti, pozisyonel arguman rc=2, normal-akis rc=0
     ( finansal-akis DEGISMEZ)
  C) cli_dogrula birim-testleri ( hizli, surece-girmeden)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_KOK = Path(os.environ.get(
    "MESH_UNPUMP_ROOT",
    "/home/gokun/projects/00_TAMGA-MESH/unpump"))  # G47
_MAINNET_VERIFY = _KOK / "mainnet_verify.py"
_NET_KAR = _KOK / "net_kar_raporu.py"


def _calistir(script: Path, *args: str, timeout: float = 120.0
              ) -> tuple[int, str, str]:
    """Gercek subprocess — rc + stdout + stderr ( PIPE KULLANILMAZ).

    capture_output=True kullanildi; komut bittikten sonra rc kesindir.
    """
    env = dict(os.environ)
    # Mainnet YASAK — testlerin hicbiri zincire dokunmaz.
    env.setdefault("UNPUMP_TEST", "1")
    proses = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True, text=True, timeout=timeout, env=env,
    )
    return proses.returncode, proses.stdout, proses.stderr


@pytest.fixture(autouse=True)
def _kok_hazir():
    """Script'lerin gercekten var oldugundan emin ol ( symlink-repo).

    G47: kardes-repo bu-checkout-ta-YOKSA ( GitHub-CI) modul-satisfy
    edilemez — acik-gerekceyle-skip ( sessiz-toplama-hatasi-DEGIL).
    """
    if not (_MAINNET_VERIFY.is_file() and _NET_KAR.is_file()):
        pytest.skip(
            "unpump-kardes-repo bu-checkout-ta-YOK; "
            "MESH_UNPUMP_ROOT-ile-kok-verilir")
    yield


# ---------------------------------------------------------------------------
# A) mainnet_verify.py — CLI gate
# ---------------------------------------------------------------------------

class TestMainnetVerifyCLI:
    def test_bogus_flag_rc2_olmali_onceki_rc0(self):
        """K4-1: --bogus bilinmeyen-flag → rc=2 ( onceki: rc=0 sessiz)."""
        rc, out, err = _calistir(_MAINNET_VERIFY, "--bogus")
        assert rc == 2, f"--bogus rc={rc} olmali=2 ( out={out[:120]})"
        # kullaniciya neden-soyle: stderr'de kullanma-hatasi etiketi
        assert "kullanma-hatasi" in (err + out), "hata-nedeni aciklanmadi"

    def test_bogus_flag_help_basmali(self):
        """K4-2: kullanma-hatasinda --help ciktisi basilir ( self-doküman)."""
        rc, out, err = _calistir(_MAINNET_VERIFY, "--bogus")
        birlesik = out + err
        assert "Kullanim" in birlesik, "usage satiri YOK"
        assert "--help" in birlesik, "--help secenegeri tarif edilmemis"

    def test_help_rc0_ve_gercek_cikti(self):
        """K4-3: --help rc=0 + gercek usage ( onceki: 0-byte cikti)."""
        rc, out, _ = _calistir(_MAINNET_VERIFY, "--help")
        assert rc == 0
        assert len(out.strip()) > 50, f"--help ciktisi bos-kisa: {out!r}"
        assert "Kullanim" in out, "usage basligi YOK"
        assert "mainnet_verify" in out, " program-adi gecmeli"

    def test_kisa_help_flag_de_calisir(self):
        """K4-4: -h standalone → rc=0 + usage ( POSIX aliskanlik)."""
        rc, out, _ = _calistir(_MAINNET_VERIFY, "-h")
        assert rc == 0
        assert len(out.strip()) > 50

    def test_eksik_degerli_flag_rc2(self):
        """K4-5: --from deger-ister — eksikse rc=2 ( yarim komut)."""
        rc, out, err = _calistir(_MAINNET_VERIFY, "--from")
        assert rc == 2
        assert "kullanma-hatasi" in (err + out)

    def test_coklu_bilinmeyen_flag_rc2(self):
        """K4-6: --bogus --bogus2 → rc=2 ( hepsi raporlanmali)."""
        rc, _, err = _calistir(_MAINNET_VERIFY, "--bogus", "--bogus2")
        assert rc == 2
        assert "--bogus" in err, "bilinmeyen flag raporlanmadi"


# ---------------------------------------------------------------------------
# B) net_kar_raporu.py — CLI gate ( finansal-akisi koruyarak)
# ---------------------------------------------------------------------------

class TestNetKarRaporuCLI:
    def test_bogus_flag_rc2_olmali_onceki_rc0(self):
        """K4-7: --bogus → rc=2 ( onceki: rapor-bas + rc = 'ok' yanilgisi).

        Onemli: hatali-cagrida rapor-BASILMAMALI — cunku rc=2 ile
        birlikte rapor, 'kismen-okundu' yanilgisini dogurur.
        """
        rc, out, err = _calistir(_NET_KAR, "--bogus", timeout=60.0)
        assert rc == 2, f"--bogus rc={rc} olmali=2"
        assert "NET-KAR RAPORU" not in out, (
            "kullanma-hatasinda finansal-rapor BASILMAMALI"
        )
        assert "kullanma-hatasi" in err

    def test_help_rc0_ve_gercek_cikti(self):
        """K4-8: --help rc=0 + anlamlı usage ( onceki: 0-byte)."""
        rc, out, _ = _calistir(_NET_KAR, "--help", timeout=60.0)
        assert rc == 0
        assert len(out.strip()) > 50, f"--help ciktisi bos: {out!r}"
        assert "Kullanim" in out
        assert "net_kar_raporu" in out

    def test_pozisyonel_arguman_rc2(self):
        """K4-9: `net_kar_raporu.py rapor` → rc=2 ( arguman-kabul-etmez)."""
        rc, _, err = _calistir(_NET_KAR, "rapor", timeout=60.0)
        assert rc == 2, f"pozisyonel arg rc={rc} olmali=2"
        assert "kullanma-hatasi" in err

    def test_normal_akis_rc0_korunmali(self):
        """K4-10: argumansiz cagri → rapor-basarili rc=0 ( dusus-0).

        Bu FINANSAL-AKISIN korundugunu kanitlar: CLI-gate sadece
        GIRIS-katmani, hesaplamaya DOKUNMAZ.
        """
        rc, out, _ = _calistir(_NET_KAR, timeout=180.0)
        assert rc == 0, f"normal-akis rc={rc} olmali=0 ( kirildi?)"
        # Rapor-icerigi hala orada ( finansal-cikti)
        assert "NET-KAR RAPORU" in out
        assert "BUYBACK" in out


# ---------------------------------------------------------------------------
# C) cli_dogrula birim-testleri — surece-girmeden ( hizli)
# ---------------------------------------------------------------------------

class TestCliDogrulaBirimsel:
    """Import-bazli — modul-ice-gorme ( subprocess masrafi YOK)."""

    @pytest.fixture(autouse=True)
    def _path_ekle(self):
        sys.path.insert(0, str(_KOK))
        yield
        try:
            sys.path.remove(str(_KOK))
        except ValueError:
            pass

    def test_mainnet_verify_cli_dogrula_gecersiz_flag(self):
        import mainnet_verify as mv  # noqa: PLC0415
        assert mv.cli_dogrula(["--bogus"]) == 2
        # argumansiz cagri onceki gibi devam-etir ( rc=0) — degisim-YOK
        assert mv.cli_dogrula([]) == 0
        assert mv.cli_dogrula(["--help"]) == 99
        assert mv.cli_dogrula(["--from", "0x11"]) == 0

    def test_mainnet_verify_cli_dogrula_eksik_deger(self):
        import mainnet_verify as mv  # noqa: PLC0415
        assert mv.cli_dogrula(["--from"]) == 2
        assert mv.cli_dogrula(["--from", "0x11", "--amount"]) == 2
        assert mv.cli_dogrula(
            ["--from", "0x11", "--to", "0x22", "--amount", "0.05"]) == 0

    def test_net_kar_cli_dogrula_gecersiz_flag(self):
        import net_kar_raporu as nkr  # noqa: PLC0415
        assert nkr.cli_dogrula(["--bogus"]) == 2
        assert nkr.cli_dogrula([]) == 0
        assert nkr.cli_dogrula(["--help"]) == 99

    def test_net_kar_cli_dogrula_pozisyonel(self):
        import net_kar_raporu as nkr  # noqa: PLC0415
        assert nkr.cli_dogrula(["rapor"]) == 2
        assert nkr.cli_dogrula(["-h"]) == 99


# ---------------------------------------------------------------------------
# D) import-maskesi — kutuphane-kullanimi kirilmadi
# ---------------------------------------------------------------------------

class TestImportMaskesi:
    def test_mainnet_verify_import_edilebilir_ve_fonksiyonlar_saglam(self):
        """mainnet_guard'in import ettigi API degismedi ( igde-sabitleme)."""
        sys.path.insert(0, str(_KOK))
        try:
            import mainnet_verify as mv  # noqa: PLC0415
            assert callable(mv.find_transfer)
            assert callable(mv.verify_mainnet_payment)
            assert mv.SEARCH_BLOCKS > 0
            assert mv.USDC_CONTRACT.startswith("0x")
        finally:
            sys.path.remove(str(_KOK))

    def test_net_kar_raporu_import_edilebilir_ve_sabitler_saglam(self):
        """hazirlik_kontrol/agent_kanit_tablosu import'u kirilmadi."""
        sys.path.insert(0, str(_KOK))
        try:
            import net_kar_raporu as nkr  # noqa: PLC0415
            assert nkr.ESIK_CAGRI >= 1
            assert nkr.ESIK_HARCAMA > 0
            assert callable(nkr._servis_brut_gelir)
            assert callable(nkr.main)
            assert len(nkr.SERVIS_DBLERI) > 20, "servis-DB-listesi kuculdu"
        finally:
            sys.path.remove(str(_KOK))
