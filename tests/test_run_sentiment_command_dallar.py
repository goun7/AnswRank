"""answrank.cli.run_sentiment_command dal-kesen testleri (LEED).

Hedef fonksiyon: module-level, 19 satirlik CLI handler
('answrank sentiment <brand>' komutunu yurutur).

Kural-1: mevcut production dosyalarina DOKUNULMADI; SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory testler — SentimentAnalyzer STUBLANDI
(monkeypatch), gercek AI/LLM/ag cagrisi YAPILMADI; cikti rich Console
ile StringIO'ya yonlendirildi. Sonuc verisi uretlemek icin production'in
saf-veri modelleri (SentimentAnalysisResult/enum) kullanildi.
"""
import argparse
import io

import pytest
from rich.console import Console

from answrank import cli as cli_mod
from answrank.citations.sentiment import (
    BrandSafetyFlag,
    SentimentAnalysisResult,
    SentimentPolarity,
)


# ------------------------------------------------------------------ stub altyapi
class _AnalyzerStub:
    """SentimentAnalyzer.replace: analiz etmez, kaydedilen sonucu dondurur."""

    calls = []
    result = None
    raises = None

    @classmethod
    def reset(cls, result):
        cls.calls = []
        cls.result = result
        cls.raises = None

    def __init__(self):
        pass

    def analyze(self, **kw):
        _AnalyzerStub.calls.append(kw)
        if _AnalyzerStub.raises is not None:
            raise _AnalyzerStub.raises
        return _AnalyzerStub.result


@pytest.fixture
def cap(monkeypatch):
    """cli.console'u kaydeden bir Console ile degistirir."""
    buf = io.StringIO()
    cons = Console(file=buf, width=200, record=True, color_system="standard")
    monkeypatch.setattr(cli_mod, "console", cons)
    monkeypatch.setattr(
        "answrank.citations.sentiment.SentimentAnalyzer", _AnalyzerStub)

    class _Cap:
        def clear(self):
            cons.clear()

        @property
        def text(self):
            # clear=False: export_text varsayilan olarak kaydi temizler
            return cons.export_text(styles=False, clear=False)

        @property
        def styled(self):
            return cons.export_text(styles=True, clear=False)

    return _Cap()


def _args(text="raw yanit metni", brand="Marka", sector="general"):
    return argparse.Namespace(text=text, brand=brand, sector=sector)


def _setup(polarity=SentimentPolarity.POSITIVE_RECOMMENDATION, score=0.5,
           is_brand_safe=True, flags=(), ctx="baglam metni", strategy=None):
    _AnalyzerStub.reset(SentimentAnalysisResult(
        polarity=polarity,
        sentiment_score=score,
        is_brand_safe=is_brand_safe,
        detected_flags=list(flags),
        context_snippet=ctx,
        counter_citation_strategy=strategy,
    ))
    return _AnalyzerStub.result


def _capture_text():
    """Tamamen taze bir Console ile tek bir calistirma yapar; cikti doner.

    export_text kaydi biriktirdigi icin (clear=False) her karsilastirma
    kendi Console'unu kullanmalidir. cap fixture'inden bagimsiz
    calistigindan analyzer stub'ini da kendisi takar.
    """
    import answrank.citations.sentiment as sentiment_mod

    buf = io.StringIO()
    cons = Console(file=buf, width=200, record=True, color_system="standard")
    orig_console = cli_mod.console
    orig_analyzer = sentiment_mod.SentimentAnalyzer
    cli_mod.console = cons
    sentiment_mod.SentimentAnalyzer = _AnalyzerStub
    try:
        cli_mod.run_sentiment_command(_args())
        return cons.export_text(styles=False, clear=False)
    finally:
        cli_mod.console = orig_console
        sentiment_mod.SentimentAnalyzer = orig_analyzer


# ------------------------------------------------------------------ arguman gecisi
def test_analyzer_argumanlari_gecer(cap):
    _setup()
    cli_mod.run_sentiment_command(_args(text="baz metin", brand="Acme", sector="dental"))
    assert _AnalyzerStub.calls == [
        {"raw_response": "baz metin", "brand_name": "Acme", "sector": "dental"}
    ]


def test_analyzer_sektor_varyasyonlari(cap):
    _setup()
    for s in ["general", "dental", "legal", "diş hekimliği"]:
        cli_mod.run_sentiment_command(_args(sector=s))
    assert [c["sector"] for c in _AnalyzerStub.calls] == [
        "general", "dental", "legal", "diş hekimliği"]


def test_unicode_marka_ve_metin_gecer(cap):
    _setup()
    cli_mod.run_sentiment_command(_args(
        text="Diş Kliniği İzmir önerilen bir yer", brand="Diş Kliniği İzmir"))
    assert _AnalyzerStub.calls[-1]["brand_name"] == "Diş Kliniği İzmir"
    assert _AnalyzerStub.calls[-1]["raw_response"] == "Diş Kliniği İzmir önerilen bir yer"


def test_bos_metin_argumani_gecer(cap):
    _setup()
    cli_mod.run_sentiment_command(_args(text="", brand="X"))
    assert _AnalyzerStub.calls[-1]["raw_response"] == ""


# ------------------------------------------------------------------ polarity -> renk
@pytest.mark.parametrize("polarity,ansi", [
    (SentimentPolarity.POSITIVE_RECOMMENDATION, "\x1b[1;32m"),  # bold green
    (SentimentPolarity.NEUTRAL_MENTION, "\x1b[1;33m"),          # bold yellow
    (SentimentPolarity.RISK_WARNING, "\x1b[1;31m"),             # bold red
])
def test_polarity_renk_eslemesi(cap, polarity, ansi):
    _setup(polarity=polarity)
    cli_mod.run_sentiment_command(_args())
    assert ansi + polarity.value in cap.styled


def test_polarity_deger_metni_gorunur(cap):
    _setup(polarity=SentimentPolarity.RISK_WARNING)
    cli_mod.run_sentiment_command(_args())
    assert "RISK_WARNING" in cap.text


def test_polarity_etiketi_tr_gorunur(cap):
    _setup()
    cli_mod.run_sentiment_command(_args())
    assert "Duyarlılık Polaritesi:" in cap.text


# ------------------------------------------------------------------ brand safety
def test_brand_safe_true(cap):
    _setup(is_brand_safe=True)
    cli_mod.run_sentiment_command(_args())
    assert "GÜVENLİ" in cap.text
    assert "RİSKLİ" not in cap.text


def test_brand_safe_false(cap):
    _setup(is_brand_safe=False)
    cli_mod.run_sentiment_command(_args())
    assert "RİSKLİ" in cap.text
    assert "GÜVENLİ" not in cap.text


@pytest.mark.parametrize("safe,expected", [(True, "\x1b[32m"), (False, "\x1b[1;31m")])
def test_brand_safe_renk_eslemesi(cap, safe, expected):
    _setup(is_brand_safe=safe)
    cli_mod.run_sentiment_command(_args())
    assert expected in cap.styled


def test_brand_safe_etiketi_gorunur(cap):
    _setup()
    cli_mod.run_sentiment_command(_args())
    assert "Marka Güvenliği:" in cap.text


# ------------------------------------------------------------------ flags
def test_flags_yok(cap):
    _setup(flags=[])
    cli_mod.run_sentiment_command(_args())
    assert "Kırmızı Bayraklar: YOK" in cap.text


def test_flags_tek(cap):
    _setup(flags=[BrandSafetyFlag.HIDDEN_COSTS])
    cli_mod.run_sentiment_command(_args())
    assert "Kırmızı Bayraklar: HIDDEN_COSTS" in cap.text
    assert "Kırmızı Bayraklar: YOK" not in cap.text


def test_flags_coklu_virgul_birlesimi(cap):
    flags = [BrandSafetyFlag.HIDDEN_COSTS, BrandSafetyFlag.NEGATIVE_REVIEWS]
    _setup(flags=flags)
    cli_mod.run_sentiment_command(_args())
    assert "Kırmızı Bayraklar: HIDDEN_COSTS, NEGATIVE_REVIEWS" in cap.text


def test_flags_uc_tamami(cap):
    flags = [BrandSafetyFlag.HIDDEN_COSTS, BrandSafetyFlag.MALPRACTICE_ALLEGATION,
             BrandSafetyFlag.POOR_HYGIENE]
    _setup(flags=flags)
    cli_mod.run_sentiment_command(_args())
    assert "HIDDEN_COSTS, MALPRACTICE_ALLEGATION, POOR_HYGIENE" in cap.text


def test_flags_etiket_gorunur(cap):
    _setup(flags=[])
    cli_mod.run_sentiment_command(_args())
    assert "Kırmızı Bayraklar:" in cap.text


# ------------------------------------------------------------------ skor formati
@pytest.mark.parametrize("score,beklenen", [
    (0.5, "+0.50"), (0.0, "+0.00"), (-0.75, "-0.75"),
    (1.0, "+1.00"), (-1.0, "-1.00"), (0.125, "+0.12"),
])
def test_skor_formati(cap, score, beklenen):
    _setup(score=score)
    cli_mod.run_sentiment_command(_args())
    assert f"Duyarlılık Skoru: {beklenen}" in cap.text


def test_skor_aralik_etiketi(cap):
    _setup(score=0.0)
    cli_mod.run_sentiment_command(_args())
    assert "(-1.0 ile +1.0)" in cap.text


# ------------------------------------------------------------------ baglam
def test_baglam_metni_gorunur(cap):
    _setup(ctx="LLM yanıtı bağlamı")
    cli_mod.run_sentiment_command(_args())
    assert "Bağlam: LLM yanıtı bağlamı" in cap.text


def test_baglam_none_gorunur(cap):
    _setup(ctx=None)
    cli_mod.run_sentiment_command(_args())
    assert "Bağlam: None" in cap.text


def test_baglam_unicode(cap):
    _setup(ctx="Çok şık bir bağlam — ğğ")
    cli_mod.run_sentiment_command(_args())
    assert "Bağlam: Çok şık bir bağlam — ğğ" in cap.text


# ------------------------------------------------------------------ counter strategy
def test_counter_strategy_yok(cap):
    _setup(strategy=None)
    cli_mod.run_sentiment_command(_args())
    assert "Acil Karşı-Atıf Stratejisi" not in cap.text


def test_counter_strategy_var(cap):
    _setup(strategy="Hemen özgün makale yayınla.")
    cli_mod.run_sentiment_command(_args())
    assert "Acil Karşı-Atıf Stratejisi" in cap.text
    assert "Hemen özgün makale yayınla." in cap.text


def test_counter_strategy_unicode(cap):
    _setup(strategy="Karşı-atıf: İzmir'de diş hekimi ğğ")
    cli_mod.run_sentiment_command(_args())
    assert "Karşı-atıf: İzmir'de diş hekimi ğğ" in cap.text


def test_counter_strategy_bos_string_yok(cap):
    _setup(strategy="")
    cli_mod.run_sentiment_command(_args())
    assert "Acil Karşı-Atıf Stratejisi" not in cap.text


# ------------------------------------------------------------------ sabitler
def test_panel_basligi(cap):
    _setup()
    cli_mod.run_sentiment_command(_args())
    assert "AnswRank Zero-Click Citation Sentiment & Brand Safety" in cap.text


def test_marka_ve_sektor_gorunur(cap):
    _setup()
    cli_mod.run_sentiment_command(_args(brand="Acme", sector="dental"))
    assert "Marka: Acme" in cap.text
    assert "Sektör: dental" in cap.text


def test_unicode_sektor_gorunur(cap):
    _setup()
    cli_mod.run_sentiment_command(_args(sector="diş hekimliği"))
    assert "Sektör: diş hekimliği" in cap.text


# ------------------------------------------------------------------ davranis
def test_tekrar_uretilebilir():
    _setup()
    once = _capture_text()
    _setup()
    assert once == _capture_text()


def test_farkli_sonuc_farkli_cikti():
    _setup(polarity=SentimentPolarity.POSITIVE_RECOMMENDATION)
    pos = _capture_text()
    _setup(polarity=SentimentPolarity.RISK_WARNING)
    neg = _capture_text()
    assert pos != neg
    assert "POSITIVE_RECOMMENDATION" in pos
    assert "RISK_WARNING" in neg


def test_analyzer_hata_yayilir(cap):
    _setup()
    _AnalyzerStub.raises = RuntimeError("LLM saglayici yanit vermedi")
    with pytest.raises(RuntimeError, match="LLM saglayici yanit vermedi"):
        cli_mod.run_sentiment_command(_args())


def test_analyzer_hic_cagri_yapilmadan_cikti_yok(cap):
    # hata durumunda console'a baski yapilmamali
    _setup()
    _AnalyzerStub.raises = ValueError("boom")
    try:
        cli_mod.run_sentiment_command(_args())
    except ValueError:
        pass
    assert cap.text == ""


def test_her_cagri_tek_analiz(cap):
    _setup()
    cli_mod.run_sentiment_command(_args())
    cli_mod.run_sentiment_command(_args())
    assert len(_AnalyzerStub.calls) == 2
