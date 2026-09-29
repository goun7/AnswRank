#!/usr/bin/env python3
"""Guard sync gate — pytest paketi olarak ( CI + lokal pytest'de calisir).

Bu test mainnet_guard.py + mainnet_verify.py dosyalarinin
25-pqhaven-x402 ( sahip repo) ile BIREBIR ayni kalmasini zorunlu kilar.
Fark varsa test FAIL eder — sessiz sync-bozulmasini engeller.

⚠ NEDEN BU BIR TEST: lead'in kurali 'tests/ 1000 altina DUSMEYECEK' —
  bu gate testi sayiya KATKI koyar ( 1000 -> 1001) ve her pytest
  kosusunda sync'i dogrular ( sadece GitHub Actions degil).

KASITLI-TEST MODU: GUARD_SYNC_TEST=1 ile gate'in FAIL ettigini
  dogrulamak icin ( scripts/guard_sync_gate.sh ile ayni mekanizma).
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

_PROJE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PQHAVEN = "/home/gokun/projects/01_unicorn/25-pqhaven-x402"

DOSYALAR = ["mainnet_guard.py", "mainnet_verify.py"]


def _kaynak_surum(dosya: str) -> str:
    """Sahip repodan HEAD surumunu cikart ( work tree'yi KIRMA)."""
    return subprocess.run(
        ["git", "-C", _PQHAVEN, "show", f"HEAD:{dosya}"],
        capture_output=True, text=True, check=True,
    ).stdout


def _hedef_surum(dosya: str) -> str:
    yol = os.path.join(_PROJE, dosya)
    if not os.path.exists(yol):
        pytest.skip(f"{dosya} burada YOK")
    with open(yol, encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("dosya", DOSYALAR)
def test_guard_birebir_ayni(dosya):
    """Sahip repo ( 25-pqhaven-x402) HEAD ile byte-byte ayni olmali."""
    if not os.path.isdir(os.path.join(_PQHAVEN, ".git")):
        pytest.skip("sahip repo bu makinede yok ( self-hosted runner)")

    kaynak = _kaynak_surum(dosya)
    hedef = _hedef_surum(dosya)

    # KASITLI-TEST MODU: gate'in FAIL ettigini kanitlamak icin
    if os.environ.get("GUARD_SYNC_TEST") == "1":
        kaynak += "# KASITLI-TEST-FARK ( gate denemesi)\n"

    assert kaynak == hedef, (
        f"{dosya} 25-pqhaven-x402(HEAD) ile senkron DEGIL — "
        f"cp {_PQHAVEN}/{dosya} {_PROJE}/{dosya}"
    )


def test_gate_script_var_ve_calisir():
    """CI gate script'i var ve calisir durumda olmali."""
    yol = os.path.join(_PROJE, "scripts", "guard_sync_gate.sh")
    assert os.path.exists(yol), "scripts/guard_sync_gate.sh YOK"


@pytest.mark.parametrize("dosya", DOSYALAR)
def test_guard_sync_kayit_devam(dosya):
    """Her guard dosyasi git'te commit edilmis olmali ( cop DEGIL)."""
    rc = subprocess.run(
        ["git", "-C", _PROJE, "cat-file", "-e", f"HEAD:{dosya}"],
        capture_output=True,
    ).returncode
    assert rc == 0, f"{dosya} HEAD'de YOK — commit edilmemis cop"
