"""net_kar_raporu dal-kesen testleri (LEED) — UNP-FIN-1 (DALGA-C-3).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: _sandbox_adresleri_tamamla uretim .env.production'ina DOKUNMAZ —
geçici-dizine yönlendirilmiş sahte-env ile fail-closed davranışı kanıtlanır.

DALLAR:
  _sandbox_adresleri_tamamla: env-okunur → UNPUMP_SANDBOX_KEYS eklenir;
    env-YOK → SystemExit(3) + stderr ( FAIL-CLOSED — sandbox-küçülmesi
    = test-odemelerinin-gerçek-gelir-sayılması = buyback-şişmesi).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.environ.get(
    "MESH_UNPUMP_ROOT",
    "/home/gokun/projects/00_TAMGA-MESH/unpump"))  # G47

try:
    import net_kar_raporu as nkr  # noqa: E402
except ImportError as _g47_hatasi:  # G47: kardes-repo-CI'de-YOK
    pytest.importorskip(
        "net_kar_raporu",
        reason=(
            "kardes-repo-unpump bu-checkout'ta-YOK; "
            "MESH_UNPUMP_ROOT-ile-kok-verebilirsiniz "
            "( yerel: %s)" % _g47_hatasi))


class TestSandboxAdresleriTamamla:
    def test_env_okununca_sandbox_anahtarlari_eklenir(self, tmp_path, monkeypatch):
        """Pozitif-yol: UNPUMP_SANDBOX_KEYS satiri okununca adresler birlesir."""
        sahte_env = tmp_path / ".env.production"
        sahte_env.write_text(
            "UNPUMP_SANDBOX_KEYS=0xtest1,0xTEST2, 0xtest3\nDIGER=1\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(nkr, "SANDBOX_ADRESLERI", {"0xsabit"})
        # modul-ici env_yolu sabit — patch'le
        kaynak = nkr._sandbox_adresleri_tamamla.__code__
        assert kaynak is not None
        # dogrudan fonksiyon-icinde env_yolu'nu degistir: modul-kaynagini
        # degistirmedan, gecici olarak open-oneri — en dogrusu okuma-izni
        # testidir; burada ENV-ICERIK okumasini kimiliyor.
        import unittest.mock as mock
        with mock.patch("builtins.open", mock.mock_open(
                read_data="UNPUMP_SANDBOX_KEYS=0xyeni1,0xyeni2\n")):
            # open mock'laninca Path-exists kontrolu kalkar — OSError deil
            adresler = nkr._sandbox_adresleri_tamamla()
        assert "0xsabit" in adresler
        assert "0xyeni1" in adresler and "0xyeni2" in adresler

    def test_env_yoksa_systemexit3_fail_closed(self, monkeypatch, capsys):
        """UNP-FIN-1 (DUZELTILDI): env okunamazsa sandbox SESSIZCE kuculmez —
        SystemExit(3) + stderr ( onceki: except OSError: pass)."""
        def _ac(*a, **k):
            raise OSError(2, "No such file or directory", a[0])

        monkeypatch.setattr("builtins.open", _ac)
        with pytest.raises(SystemExit) as hata:
            nkr._sandbox_adresleri_tamamla()
        assert hata.value.code == 3
        err = capsys.readouterr().err
        assert "FAIL-CLOSED" in err
        assert "UNPUMP_SANDBOX_KEYS okunamiyor" in err


class TestSabitler:
    def test_esik_cagri_ve_harcama_sabit(self):
        assert isinstance(nkr.ESIK_CAGRI, int) and nkr.ESIK_CAGRI >= 1
        assert isinstance(nkr.ESIK_HARCAMA, (int, float)) and nkr.ESIK_HARCAMA > 0
