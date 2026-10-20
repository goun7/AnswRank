"""G45: gunluk-duzenlenen-cikti-dosyalari git'e-ait-degil ( kronik-kirlilik).

log_ozeti.sh her-sabah 08:00'te ( systemd-timer) docs/ altinda
sabah_log_ozeti_08.txt'YENIDEN-olusturuyordu; bu-dosya-git tarafindan
izlendiginden agac her-sabah KIRLI-kaliyordu ( clean-kapisi-kirmizi).

Bu-pin iki-seyi-garantiler:
  ( 1) log_ozeti.sh cikti-yolu docs/ DEGIL logs/ altinda,
  ( 2) gunluk-cikti-desenleri .gitignore'da ( docs/sabah_log_ozeti_08.txt,
      docs/canlilik_kanit_watchdog_30dk.log, logs/),
  ( 3) bu-dosyalar-takip-edilmiyor ( ls-files bos).
"""
import os
import subprocess
from pathlib import Path

import pytest

# tests/ sembolik-baglanti ( tek-kaynak: 85-AnswRank/tests). conftest.py
# cwd'yi 85-AnswRank'a tasidigi icin __file__ resolve() OLMAZ — bu dosyanin
# kanonik-rcnsi ( log_ozeti.sh + .gitignore burada) sabit-yol ile alinu.
# MESH_UNPUMP_ROOT-ile-baska-checkout-ta-gecersiz-kilinabilir ( CI-sim).
KANONIK_ROOT = Path(os.environ.get(
    "MESH_UNPUMP_ROOT",
    "/home/gokun/projects/Yeni Fikirler/oncu_fikirler_havuzu_2026"
    "/23_Unpump_Cash_Otonom_Ajan_Borsasi_Ve_Nakit_Akisli_AMM"))
ROOT = KANONIK_ROOT

# G47: bu-pin-sahip-oldugu-saban-servis-dosyalari ( log_ozeti.sh) yalnizca
# isletme-makinesinde-mevcuttur — GitHub-runner'da kardes-repo-YOK.
# Eksikken-topluca-atla ( 4-testin-de-hepsi ayni-dosyalari-okur).
if not (ROOT / "log_ozeti.sh").is_file():
    pytest.skip(
        "unpump kardes-repo bu-checkout-ta-YOK ( log_ozeti.sh-eksik);"
        " MESH_UNPUMP_ROOT-ile-kok-verilir ( G47)",
        allow_module_level=True)


def _git_is_clean_of_generated() -> bool:
    out = subprocess.run(
        ["git", "ls-files", "--",
         "docs/sabah_log_ozeti_08.txt",
         "docs/canlilik_kanit_watchdog_30dk.log",
         "logs/"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    return out.returncode == 0 and out.stdout.strip() == ""


def test_log_ozeti_cikti_yeri_logs_altinda():
    script = (ROOT / "log_ozeti.sh").read_text(encoding="utf-8", errors="replace")
    # cikti-yolu docs/ altinda OLMAMALI
    assert 'CIKTI="$PROJE/docs/' not in script, (
        "log_ozeti.sh cikti-yolu hala docs/ altinda — gunluk-dosya"
            "-git-agacini-kirli-birakir ( G45)")
    # logs/ altinda OLMALI
    assert 'CIKTI="$PROJE/logs/' in script, (
        "log_ozeti.sh cikti-yonu logs/ degil — G45-cozumu-uygulanmadi")


def test_gitignore_generated_log_desenlerini_kapsar():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8", errors="replace")
    for pat in ("logs/", "docs/sabah_log_ozeti_08.txt",
                "docs/canlilik_kanit_watchdog_30dk.log"):
        assert pat in gi, ".gitignore-deseni-eksi: %s" % pat


def test_generated_ciktitlar_git_tarafindan_takip_edilmiyor():
    assert _git_is_clean_of_generated(), (
        "docs/sabah_log_ozeti_08.txt / canlilik_kanit_watchdog_30dk.log /"
            "-logs/ hala-git-takibinde ( git-rm --cached-kosulmadi)")


def test_log_ozeti_clistisi_ignored_dosyada_degil_docsda():
    """Kosulmadan-once: cikti-gercekten-calisiyor-mu ( rc=0)."""
    res = subprocess.run(
        ["bash", "log_ozeti.sh"], cwd=str(ROOT),
        capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-300:]
    cikti = ROOT / "logs" / "sabah_log_ozeti_08.txt"
    assert cikti.exists(), "log_ozeti.sh-cikti-dosyasi-olusmadi"
    metin = cikti.read_text(encoding="utf-8", errors="replace")
    assert "SABAH LOG OZETI" in metin, "cikti-icerigi-beklenenden-farkli"
    # cikti-git tarafindan gosterilmemeli ( kirmizi-kapiden-onlem)
    s = subprocess.run(["git", "status", "--short", "--", "logs/"],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert s.stdout.strip() == "", (
        "logs/ cikti-dosyasi-git-agacini-kirli-birakiyor: %r" % s.stdout)
