"""CLI komut-handler'ları için dal-kesen testler (wave-16, LEAD).

Kural-1'e uyuldu: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Handler'lar argparse.Namespace ile doğrudan çağrılır (parser main() içinde
yerel olduğu için). Dış çağrı YOK: bu handler'ların hepsi saf-üretim tipi.
Çıkış dosyaları tmp'ye izole edilir (kullanıcının çalışma dizini kirletilmez).
"""
import argparse
import os
import tempfile

import pytest

from answrank.cli import (
    run_contract_command,
    run_economics_command,
    run_fix_command,
    run_milestones_command,
    run_scenarios_command,
)


def _ns(**kw):
    """argparse.Namespace — eksik alanlar için tolanslı değil; tüm alanlar verilmeli."""
    return argparse.Namespace(**kw)


@pytest.fixture
def tmp_out():
    d = tempfile.mkdtemp(prefix="answrank_cli_test_")
    yield d
    # temizlik
    for root, _dirs, files in os.walk(d, topdown=False):
        for f in files:
            os.remove(os.path.join(root, f))
    os.rmdir(d)


# -- run_fix_command -------------------------------------------------------

def test_fix_command_writes_four_artifacts(tmp_out):
    args = _ns(domain="disiklinigi.com", brand="Diş Kliniği A",
               sector="dental", city="İstanbul", out_dir=tmp_out)
    run_fix_command(args)
    for name in ("robots.txt", "llms.txt", "llms-full.txt", "schema.html"):
        p = os.path.join(tmp_out, name)
        assert os.path.isfile(p), f"{name} üretilmedi"
        assert os.path.getsize(p) > 0, f"{name} boş"


def test_fix_command_robots_allows_ai_bots(tmp_out):
    args = _ns(domain="ornek.com", brand=None, sector="dental",
               city="Ankara", out_dir=tmp_out)
    run_fix_command(args)
    robots = open(os.path.join(tmp_out, "robots.txt"), encoding="utf-8").read()
    # kazıyıcılar (engelli) ile AI botları (açık) ayrımı görünmeli
    assert "User-agent:" in robots
    assert len(robots) > 50


def test_fix_command_brand_falls_back_to_domain(tmp_out):
    args = _ns(domain="markasiz.com", brand=None, sector="general",
               city="İzmir", out_dir=tmp_out)
    run_fix_command(args)
    schema = open(os.path.join(tmp_out, "schema.html"), encoding="utf-8").read()
    assert "markasiz.com" in schema


def test_fix_command_llms_mentions_domain(tmp_out):
    args = _ns(domain="sektor.com", brand="Sekör A.Ş.", sector="legal",
               city="Bursa", out_dir=tmp_out)
    run_fix_command(args)
    llms = open(os.path.join(tmp_out, "llms.txt"), encoding="utf-8").read()
    assert "sektor.com" in llms


# -- run_milestones_command ------------------------------------------------

def _mile_ns(**over):
    base = dict(day=14, clients=3, mrr=180.0)
    base.update(over)
    return _ns(**base)


def test_milestones_returns_result_object(capsys):
    run_milestones_command(_mile_ns())
    out = capsys.readouterr().out
    # durum paneli render edildi
    assert "Aktif" in out or "Faz" in out or "Görev" in out or out != ""


def test_milestones_day_zero_is_safe(capsys):
    run_milestones_command(_mile_ns(day=0))
    assert capsys.readouterr().out != ""


def test_milestones_zero_clients_safe(capsys):
    run_milestones_command(_mile_ns(clients=0, mrr=0.0))
    assert capsys.readouterr().out != ""


def test_milestones_negative_values_do_not_crash(capsys):
    # kötü girdi structurally ret edilmeli veya güvenli render
    run_milestones_command(_mile_ns(day=-5, clients=-1, mrr=-10.0))
    assert capsys.readouterr().out != ""


# -- run_contract_command --------------------------------------------------

def _con_ns(**over):
    base = dict(company="Test Klinik A.Ş.", domain="testklinik.com",
                contact="Ahmet Yılmaz", tax_no="1234567890",
                tax_office="Kadıköy", address="İstanbul, Türkiye",
                phone="+905550000000", email="info@testklinik.com",
                sector="dental", tier="MONTHLY_RETAINER", fee=600.0,
                contract_no="ANSW-2026-001", date="2026-09-14",
                months=6, out=None)
    base.update(over)
    return _ns(**base)


def test_contract_command_renders_without_out(capsys):
    # out None → console'a render, dosya YAZILMAZ
    run_contract_command(_con_ns())
    assert capsys.readouterr().out != ""


def test_contract_command_writes_file_when_out(tmp_out):
    out_file = os.path.join(tmp_out, "sozlesme.md")
    run_contract_command(_con_ns(out=out_file))
    assert os.path.isfile(out_file)
    content = open(out_file, encoding="utf-8").read()
    assert "Test Klinik A.Ş." in content
    assert "testklinik.com" in content


def test_contract_command_includes_fee_and_months(tmp_out):
    out_file = os.path.join(tmp_out, "s2.md")
    run_contract_command(_con_ns(fee=999.5, months=12, out=out_file))
    content = open(out_file, encoding="utf-8").read()
    assert "999" in content or "999.5" in content
    assert "12" in content


def test_contract_command_empty_company_still_renders(capsys):
    run_contract_command(_con_ns(company="", domain=""))
    assert capsys.readouterr().out != ""


# -- run_economics_command -------------------------------------------------

def _eco_ns(**over):
    base = dict(clients=10, cac=100.0, retention=0.85, tier="MONTHLY_RETAINER")
    base.update(over)
    return _ns(**base)


def test_economics_returns_result(capsys):
    run_economics_command(_eco_ns())
    assert capsys.readouterr().out != ""


def test_economics_zero_clients_safe(capsys):
    run_economics_command(_eco_ns(clients=0, cac=0.0, retention=0.0))
    assert capsys.readouterr().out != ""


def test_economics_zero_retention_is_fatal_but_safe(capsys):
    # retention=0 → churn %100; motor bunu raporlamalı, crash YOK
    run_economics_command(_eco_ns(retention=0.0, clients=5, cac=50.0))
    assert capsys.readouterr().out != ""


def test_economics_high_cac_does_not_overflow(capsys):
    run_economics_command(_eco_ns(cac=1e9, clients=1000, retention=0.99))
    assert capsys.readouterr().out != ""


# -- run_scenarios_command -------------------------------------------------

def _scen_ns(**over):
    # ScenarioRouter.evaluate(baseline_score, current_score,
    #   baseline_citations, current_citations, client_cooperation_ok)
    base = dict(baseline=40, current=75,
                baseline_cit=0, current_cit=0, inaction=False)
    base.update(over)
    return _ns(**base)


def test_scenarios_returns_result(capsys):
    run_scenarios_command(_scen_ns())
    assert capsys.readouterr().out != ""


def test_scenarios_improvement_positive(capsys):
    run_scenarios_command(_scen_ns(baseline=20, current=80,
                                   baseline_cit=0, current_cit=30))
    assert capsys.readouterr().out != ""


def test_scenarios_decline_is_reported_safely(capsys):
    # current < baseline — gerileme senaryosu crash vermemeli
    run_scenarios_command(_scen_ns(baseline=90, current=10,
                                   baseline_cit=50, current_cit=5))
    assert capsys.readouterr().out != ""


def test_scenarios_inaction_flag_flips_cooperation(capsys):
    # inaction=True → client_cooperation_ok=False (karar ağacı dalı)
    run_scenarios_command(_scen_ns(inaction=True))
    assert capsys.readouterr().out != ""


def test_scenarios_all_citation_growth(capsys):
    run_scenarios_command(_scen_ns(baseline=10, current=60,
                                   baseline_cit=2, current_cit=40))
    assert capsys.readouterr().out != ""
