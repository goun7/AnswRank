"""Tests for automated fix file generator."""

import json
from answrank.reporting.fix_generator import FixGenerator

def test_fix_generator_robots_txt():
    gen = FixGenerator()
    robots = gen.generate_robots_txt(domain="example.com")
    assert "User-agent: OAI-SearchBot" in robots
    assert "User-agent: PerplexityBot" in robots
    assert "User-agent: Claude-SearchBot" in robots
    assert "User-agent: Google-Extended" in robots
    assert "Allow: /" in robots
    assert "https://example.com/llms.txt" in robots

def test_fix_generator_llms_txt():
    gen = FixGenerator()
    llms = gen.generate_llms_txt(
        brand_name="Yılmaz Dental",
        domain="yilmazdental.com",
        sector="dental",
        city="Kadıköy",
    )
    assert "# Yılmaz Dental — Kadıköy Dental Resmi Bilgi Dizini" in llms
    assert "> Yılmaz Dental, Kadıköy bölgesinde" in llms
    assert "llms-full.txt" in llms

def test_fix_generator_json_ld():
    gen = FixGenerator()
    json_ld_raw = gen.generate_json_ld(
        brand_name="Yılmaz Dental",
        domain="yilmazdental.com",
        sector="dental",
        city="İstanbul",
    )
    assert '<script type="application/ld+json">' in json_ld_raw
    # Extract json body
    json_str = json_ld_raw.replace('<script type="application/ld+json">', '').replace('</script>', '').strip()
    data = json.loads(json_str)
    assert "@context" in data
    assert "@graph" in data
    types = [item["@type"] for item in data["@graph"]]
    assert "Dentist" in types
    assert "FAQPage" in types

def test_fix_generator_llms_full_txt():
    gen = FixGenerator()
    full_txt = gen.generate_llms_full_txt(
        brand_name="Yılmaz Dental",
        domain="yilmazdental.com",
        sector="dental",
        city="İstanbul",
    )
    assert "# Yılmaz Dental — Kapsamlı Kurumsal ve Klinik Bilgi Bankası (llms-full.txt)" in full_txt
    assert "HEKİM KADROSU VE AKADEMİK YETKİNLİK" in full_txt
    assert "KLİNİK VE OPERASYONEL STANDARTLAR" in full_txt
    assert "ŞEFFAF FİYATLANDIRMA VE GARANTİ POLİTİKASI" in full_txt

