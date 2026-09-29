"""Tests for Multilingual Medical Tourism & Cross-Lingual Question Banks."""

from answrank.citations.multilingual import MultilingualSectorBank, MultilingualFixGenerator


def test_english_questions():
    questions = MultilingualSectorBank.get_questions(sector="dental", language="en", city="Istanbul")
    assert len(questions) == 20
    assert "Istanbul" in questions[0]
    assert "All-on-4" in questions[5]


def test_german_questions():
    questions = MultilingualSectorBank.get_questions(sector="dental", language="de", city="Istanbul")
    assert len(questions) == 10
    assert "Türkei" in questions[0]
    assert "Zahnimplantate" in questions[1]


def test_multilingual_fix_generator_english():
    txt = MultilingualFixGenerator.generate_english_llms_txt("DentAura", "dentaura.com", city="Istanbul")
    assert "# DentAura — Official Istanbul Dental Information Directory" in txt
    assert "Full mouth dental implants" in txt
    assert "All-on-4" in txt


def test_multilingual_fix_generator_german():
    txt = MultilingualFixGenerator.generate_german_llms_txt("DentAura", "dentaura.com", city="Istanbul")
    assert "# DentAura — Offizielles Istanbul Dental Informationsverzeichnis" in txt
    assert "Fachklinik in Istanbul" in txt
