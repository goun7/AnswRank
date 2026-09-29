"""Tests for Objection Handler & Automated Rebuttal Generator."""

from answrank.crm.objection import ObjectionHandler, ObjectionCode


def test_objection_detection_seo():
    text = "Biz zaten Google'da ilk sıradayız ve düzenli SEO yapıyoruz."
    code = ObjectionHandler.detect_objection(text)
    assert code == ObjectionCode.SEO_ALREADY


def test_objection_detection_audience():
    text = "Bizim müşterilerimiz yaşlı ve geleneksel, yapay zeka kullanmaz."
    code = ObjectionHandler.detect_objection(text)
    assert code == ObjectionCode.AUDIENCE_OLD


def test_objection_detection_price():
    text = "Fiyatınız çok yüksek geldi, bir başarı garantisi veriyor musunuz?"
    code = ObjectionHandler.detect_objection(text)
    assert code == ObjectionCode.PRICE_OR_GUARANTEE


def test_objection_detection_inhouse():
    text = "Biz bunu kendi içimizdeki ajansımıza söyleriz onlar halleder."
    code = ObjectionHandler.detect_objection(text)
    assert code == ObjectionCode.IN_HOUSE_OR_AGENCY


def test_objection_detection_need_time():
    text = "Ortaklarımla biraz düşünmem lazım, hemen karar veremem."
    code = ObjectionHandler.detect_objection(text)
    assert code == ObjectionCode.NEED_TIME


def test_generate_rebuttal_output():
    res = ObjectionHandler.generate_rebuttal(
        text="SEO yapıyoruz zaten Google'da birinciyiz",
        company_name="DentAura",
        sector="dental",
        competitor_name="DentGroup",
    )
    assert res.matched_code == ObjectionCode.SEO_ALREADY
    assert "DentAura" in res.rebuttal_text
    # Real Ahrefs figure (Aug 2025, 15k prompts): only 12% of AI-cited URLs
    # are in Google's top-10 for the same query — the fabricated 28.3% claim
    # was removed in the honesty pass.
    assert "%12" in res.rebuttal_text
    assert len(res.recommended_talking_points) >= 3
