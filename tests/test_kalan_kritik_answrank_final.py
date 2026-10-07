"""Kalan EN KRITIK 3 test-disi fonksiyon icin dal-kesen testler (final batch).

Hedefler (AST taramasiyla secildi; mevcut testlerde ismi gecmiyor):
  1. SentimentAnalyzer.generate_counter_strategy  (citations/sentiment.py:137)
  2. SesterPaymentGate.price_of                   (x402_gate.py:168)
  3. ExclusivityManager.get_available_sub_niches  (crm/exclusivity.py:170)

KURALLAR: sadece fonksiyonun kendi mantigi; dis cagri/mock yok; mevcut
testleri/kodu degistirmez.
"""

from answrank.citations.sentiment import (
    BrandSafetyFlag,
    SentimentAnalyzer,
)
from answrank.crm.exclusivity import ExclusivityManager
from answrank.x402_gate import SesterPaymentGate, TOOL_PRICES


# ---------------------------------------------------------------------------
# 1) SentimentAnalyzer.generate_counter_strategy
# ---------------------------------------------------------------------------
class TestGenerateCounterStrategy:
    def test_marka_ve_sektor_stratejide_gecir(self):
        out = SentimentAnalyzer().generate_counter_strategy(
            "Acibadem Dental", "dental", [BrandSafetyFlag.HIDDEN_COSTS]
        )
        assert "Acibadem Dental" in out
        assert "dental" in out

    def test_tek_flag_degeri_metinde_gecer(self):
        out = SentimentAnalyzer().generate_counter_strategy(
            "BrandX", "legal", [BrandSafetyFlag.MALPRACTICE_ALLEGATION]
        )
        assert BrandSafetyFlag.MALPRACTICE_ALLEGATION.value in out

    def test_birden_fazla_flag_tamami_listelenir(self):
        flags = [
            BrandSafetyFlag.HIDDEN_COSTS,
            BrandSafetyFlag.COMPLICATIONS_RISK,
            BrandSafetyFlag.NEGATIVE_REVIEWS,
        ]
        out = SentimentAnalyzer().generate_counter_strategy("BrandY", "aesthetics", flags)
        for f in flags:
            assert f.value in out
        # flag'lar arasinda ayirici olarak ", " kullanilir
        assert (
            f"{BrandSafetyFlag.HIDDEN_COSTS.value}, "
            f"{BrandSafetyFlag.COMPLICATIONS_RISK.value}, "
            f"{BrandSafetyFlag.NEGATIVE_REVIEWS.value}" in out
        )

    def test_bos_flag_listesi_patlamaz_ve_markayi_korur(self):
        out = SentimentAnalyzer().generate_counter_strategy("BrandZ", "dental", [])
        assert "BrandZ" in out
        # flag listesi bossa parantez ici "negative brand bias ()" olur
        assert "negative brand bias ()" in out

    def test_turkce_karakterli_marka_ve_sektor_korunur(self):
        out = SentimentAnalyzer().generate_counter_strategy(
            "Özel İstanbul Diş Kliniği", "diş hekimliği", [BrandSafetyFlag.POOR_HYGIENE]
        )
        assert "Özel İstanbul Diş Kliniği" in out
        assert "diş hekimliği" in out

    def test_strateji_aksiyon_kelime_katilarini_icerir(self):
        out = SentimentAnalyzer().generate_counter_strategy(
            "BrandW", "wealth_management", [BrandSafetyFlag.UNLICENSED_PRACTICE]
        )
        # AEO enjeksiyonunun zorunlu bilesenleri (sabit stringsablon)
        assert "llms-full.txt" in out
        assert "JSON-LD" in out
        assert "AEO" in out

    def test_strateji_deterministik_tekrar_uretilir(self):
        a = SentimentAnalyzer().generate_counter_strategy(
            "BrandA", "dental", [BrandSafetyFlag.HIDDEN_COSTS]
        )
        b = SentimentAnalyzer().generate_counter_strategy(
            "BrandA", "dental", [BrandSafetyFlag.HIDDEN_COSTS]
        )
        assert a == b

    def test_farkli_marka_farkli_strateji(self):
        flags = [BrandSafetyFlag.HIDDEN_COSTS]
        a = SentimentAnalyzer().generate_counter_strategy("Alpha", "dental", flags)
        b = SentimentAnalyzer().generate_counter_strategy("Beta", "dental", flags)
        assert a != b
        assert "Alpha" in a and "Alpha" not in b
        assert "Beta" in b and "Beta" not in a

    def test_analyze_risk_yolunda_strateji_uretilir(self):
        """analyze() RISK_WARNING dalinda generate_counter_strategy'i cagirir."""
        result = SentimentAnalyzer().analyze(
            raw_response="Acibadem Dental gizli ücret ve pahalı fiyatlandırma ile biliniyor.",
            brand_name="Acibadem Dental",
            sector="dental",
        )
        assert result.counter_citation_strategy is not None
        assert "Acibadem Dental" in result.counter_citation_strategy
        assert result.is_brand_safe is False

    def test_analyze_pozitif_yolda_strateji_yoktur(self):
        result = SentimentAnalyzer().analyze(
            raw_response="Acibadem Dental en iyi ve en güvenilir diş kliniğidir, önerilen.",
            brand_name="Acibadem Dental",
            sector="dental",
        )
        assert result.counter_citation_strategy is None


# ---------------------------------------------------------------------------
# 2) SesterPaymentGate.price_of
# ---------------------------------------------------------------------------
class TestPriceOf:
    def test_bilinen_arac_pozitif_float_donar(self):
        gate = SesterPaymentGate()
        for tool in TOOL_PRICES:
            p = gate.price_of(tool)
            assert isinstance(p, float)
            assert p > 0.0

    def test_bilinmeyen_arac_ucretsizdir(self):
        gate = SesterPaymentGate()
        assert gate.price_of("olmayan_arac") == 0.0

    def test_bos_dize_ucretsizdir(self):
        assert SesterPaymentGate().price_of("") == 0.0

    def test_buyuk_kucuk_harf_duyarli_degil_tool_prices_ile_ayni(self):
        """price_of TOOL_PRICES sozluguyle birebir ayni degeri vermeli."""
        gate = SesterPaymentGate()
        for tool, fiyat in TOOL_PRICES.items():
            assert gate.price_of(tool) == fiyat

    def test_buyuk_harfli_tool_adi_bilinmeyen_sayilir(self):
        """Anahtarlar kucuk-harflidir; buyuk-harfli arac 0.0 doner."""
        gate = SesterPaymentGate()
        for tool in TOOL_PRICES:
            assert gate.price_of(tool.upper()) == 0.0

    def test_ucretsiz_modda_da_fiyatlar_gecerlidir(self):
        """Secret yokken (free mode) fiyatlandirma yine de calisir."""
        gate = SesterPaymentGate()
        assert gate.enabled is False
        assert gate.price_of("answrank_audit") > 0.0

    def test_fiyatlar_usdc_menzilinde_rasyoneldir(self):
        """x402 mikro-odemeler: 0 < fiyat < 10 USDC makul sinirdir."""
        for tool, fiyat in TOOL_PRICES.items():
            assert 0.0 < fiyat < 10.0, f"{tool} fiyat {fiyat} mantiksiz aralikta"

    def test_status_fiyat_tablosu_price_of_ile_tutarlidir(self):
        gate = SesterPaymentGate()
        st = gate.status()
        assert st["prices_usdc"] == dict(TOOL_PRICES)
        for tool in TOOL_PRICES:
            assert st["prices_usdc"][tool] == gate.price_of(tool)


# ---------------------------------------------------------------------------
# 3) ExclusivityManager.get_available_sub_niches
# ---------------------------------------------------------------------------
class TestGetAvailableSubNiches:
    def test_bilinmeyen_ana_niche_bos_liste(self):
        mgr = ExclusivityManager()
        assert mgr.get_available_sub_niches("UK", "London", "uzay-rotasi") == []

    def test_kilitsiz_bolge_tam_taksonomiyi_donar(self):
        mgr = ExclusivityManager()
        got = mgr.get_available_sub_niches("UK", "London", "dental")
        assert got == ExclusivityManager.SUB_NICHE_TAXONOMY["dental"]
        assert len(got) == 5

    def test_bir_alt_niche_kilitliyse_o_dusurulur(self):
        mgr = ExclusivityManager()
        mgr.lock_territory(
            country="UK", city="London", niche="invisalign_orthodontics",
            client_domain="a.co.uk", brand_name="A",
        )
        got = mgr.get_available_sub_niches("UK", "London", "dental")
        assert "invisalign_orthodontics" not in got
        assert "all_on_4_implants" in got
        assert len(got) == 4

    def test_tum_alt_nicheler_kilitliyse_bos_liste(self):
        mgr = ExclusivityManager()
        for sub in ExclusivityManager.SUB_NICHE_TAXONOMY["dental"]:
            mgr.lock_territory(
                country="UK", city="London", niche=sub,
                client_domain=f"{sub}.co.uk", brand_name=sub,
            )
        assert mgr.get_available_sub_niches("UK", "London", "dental") == []

    def test_ana_niche_buyuk_kucuk_harf_bagimsizdir(self):
        mgr = ExclusivityManager()
        assert mgr.get_available_sub_niches("UK", "London", "DENTAL") == \
            mgr.get_available_sub_niches("UK", "London", "dental")
        assert mgr.get_available_sub_niches("UK", "London", "Dental") == \
            ExclusivityManager.SUB_NICHE_TAXONOMY["dental"]

    def test_baska_sehrin_kilidi_bu_sehri_etkilemez(self):
        mgr = ExclusivityManager()
        mgr.lock_territory(
            country="UK", city="manchester", niche="all_on_4_implants",
            client_domain="m.co.uk", brand_name="M",
        )
        # London hala tum alt-nichelere acik
        assert "all_on_4_implants" in mgr.get_available_sub_niches("UK", "London", "dental")
        # Manchester'da bu alt-niche kapali
        assert "all_on_4_implants" not in mgr.get_available_sub_niches("UK", "Manchester", "dental")

    def test_baska_ulke_bagimsizdir(self):
        mgr = ExclusivityManager()
        mgr.lock_territory(
            country="UK", city="London", niche="rhinoplasty_specialist",
            client_domain="uk.co", brand_name="UK",
        )
        assert "rhinoplasty_specialist" in \
            mgr.get_available_sub_niches("US", "London", "aesthetics")

    def test_sehir_adi_key_normalize_effektif(self):
        """_make_key sehri kucuk-harfe cevirir; 'LONDON' ile 'london' ayni kilittir."""
        mgr = ExclusivityManager()
        mgr.lock_territory(
            country="UK", city="London", niche="hair_transplantation",
            client_domain="h.co.uk", brand_name="H",
        )
        assert "hair_transplantation" not in \
            mgr.get_available_sub_niches("UK", "LONDON", "aesthetics")

    def test_siralama_taksonomi_sirasini_korur(self):
        mgr = ExclusivityManager()
        mgr.lock_territory(
            country="UK", city="London", niche="pediatric_dentistry",
            client_domain="p.co.uk", brand_name="P",
        )
        got = mgr.get_available_sub_niches("UK", "London", "dental")
        beklenen = [s for s in ExclusivityManager.SUB_NICHE_TAXONOMY["dental"]
                    if s != "pediatric_dentistry"]
        assert got == beklenen

    def test_release_lock_sonrasi_alt_niche_tekrar_acilir(self):
        mgr = ExclusivityManager()
        mgr.lock_territory(
            country="UK", city="London", niche="emergency_endodontics",
            client_domain="e.co.uk", brand_name="E",
        )
        assert "emergency_endodontics" not in \
            mgr.get_available_sub_niches("UK", "London", "dental")
        assert mgr.release_lock("UK", "London", "emergency_endodontics") is True
        assert "emergency_endodontics" in \
            mgr.get_available_sub_niches("UK", "London", "dental")

    def test_diger_ana_nicheler_bagimsiz_calisir(self):
        mgr = ExclusivityManager()
        got = mgr.get_available_sub_niches("DE", "Berlin", "legal")
        assert got == ExclusivityManager.SUB_NICHE_TAXONOMY["legal"]
        got_w = mgr.get_available_sub_niches("CH", "Zurich", "wealth_management")
        assert got_w == ExclusivityManager.SUB_NICHE_TAXONOMY["wealth_management"]
