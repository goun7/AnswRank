"""Tests for the objection detector's Turkish classification branches."""

from answrank.crm.objection import ObjectionHandler, ObjectionCode


def test_detect_price():
    assert ObjectionHandler.detect_objection("Fiyatınız bize yüksek geldi") == ObjectionCode.PRICE_OR_GUARANTEE


def test_detect_in_house():
    assert ObjectionHandler.detect_objection("Bunu kendi ekibimiz halleder, dış ajansa ihtiyacımız yok") == ObjectionCode.IN_HOUSE_OR_AGENCY


def test_detect_in_house_agency_keyword():
    assert ObjectionHandler.detect_objection("Zaten bir ajansla çalışıyoruz") == ObjectionCode.IN_HOUSE_OR_AGENCY


def test_detect_seo():
    # "ajans" matches IN_HOUSE before SEO — use an agency-free SEO sentence
    assert ObjectionHandler.detect_objection("Google organik aramada zaten ilk sıradayız") == ObjectionCode.SEO_ALREADY


def test_detect_old_audience():
    assert ObjectionHandler.detect_objection("Bizim kitle yaşlı, AI kullanmaz") == ObjectionCode.AUDIENCE_OLD


def test_detect_need_time():
    assert ObjectionHandler.detect_objection("Bir düşünelim, sonra döneriz") == ObjectionCode.NEED_TIME


def test_detect_unknown():
    assert ObjectionHandler.detect_objection("İnşaat projemiz var") == ObjectionCode.UNKNOWN


def test_rebuttal_unknown_has_low_confidence():
    res = ObjectionHandler.generate_rebuttal("alıntıinti kuantum zeka", "X")
    assert res.matched_code == ObjectionCode.UNKNOWN
    assert res.confidence == 0.0
    assert res.rebuttal_text  # still returns a graceful text


def test_rebuttal_price_mentions_guarantee():
    res = ObjectionHandler.generate_rebuttal("Fiyat çok pahalı geldi bize", "Klinik", "dental")
    assert res.matched_code == ObjectionCode.PRICE_OR_GUARANTEE
    assert res.confidence > 0.0
    # The delta guarantee (Article 7) should feature in the price rebuttal
    assert "garanti" in res.rebuttal_text.lower()
