"""ai_gorunurluk.olc dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: tum ag yardimcilari monkeypatch (normalize +
ai_alinti_puani + uret_uyarilar GERCEK hesaplama).
"""
import pytest

import ai_gorunurluk as g


def _sorgu(pos=1, bulundu=True):
    return {"sorgu": "test", "bulundu": bulundu,
            "position": pos}


@pytest.fixture
def patched(monkeypatch):
    calls = {}

    def _mk(name, ret):
        def _f(*a, **k):
            calls.setdefault(name, []).append(a)
            return ret
        monkeypatch.setattr(g, name, _f)

    _mk("siralama_olc", {
        "sorgular": [_sorgu()], "sorgu_sayisi": 1,
        "kredi_kullanildi": 1, "hatalar": []})
    _mk("site_durumu", {"govde": "<html>merhaba</html>",
                        "erisilebilir": True, "https": True})
    _mk("yapilandirma", {"baslik": "x"})
    _mk("icerik_derinligi", {"puan": 12, "kelime": 100})
    _mk("robots_ve_sitemap", {"robots_var": True})
    _mk("llms_txt_kontrol", {"var": False})
    _mk("erisim_olce", {"puan": 10, "ai_izin": True})
    _mk("rakip_analizi", {"rakip": []})
    _mk("alt_puanlar", 80.0)
    _mk("rekabet_puani", {"puan": 25, "en_iyi_sira": 3,
                          "ust10_orani": 0.5})
    _mk("olcum_kaydet", None)
    return calls


def _olc(patched, domain="ornek.com", **kw):
    key = kw.pop("api_key", "api-key")
    return g.olc(domain, ["test"], key, **kw)


# -- domain normalizasyonu ---------------------------------------------------------------------------------

def test_returns_dict(patched):
    assert isinstance(_olc(patched), dict)


def test_domain_echoed(patched):
    assert _olc(patched, "ornek.com")["domain"] == "ornek.com"


def test_https_stripped(patched):
    assert _olc(patched, "https://ornek.com")["domain"] == "ornek.com"


def test_http_stripped(patched):
    assert _olc(patched, "http://ornek.com")["domain"] == "ornek.com"


def test_path_stripped(patched):
    assert _olc(patched, "https://ornek.com/a/b")["domain"] == "ornek.com"


def test_uppercase_lowered(patched):
    assert _olc(patched, "ORNEK.COM")["domain"] == "ornek.com"


def test_domain_passed_to_siralama(patched):
    _olc(patched, "https://Ornek.com/x")
    assert patched["siralama_olc"][0][0] == "ornek.com"


def test_domain_passed_to_site(patched):
    _olc(patched, "https://Ornek.com")
    assert patched["site_durumu"][0][0] == "ornek.com"


# -- sonuc semasi ---------------------------------------------------------------------------------

def test_top_level_keys(patched):
    r = _olc(patched)
    assert set(r) >= {"domain", "sorgu_sayisi", "kredi_kullanildi",
                      "alt_puanlar", "siralama", "icerik",
                      "erisim", "rakip", "rekabet",
                      "ai_alinti_puani", "uyarilar"}


def test_sorgu_sayisi(patched):
    assert _olc(patched)["sorgu_sayisi"] == 1


def test_kredi_kullanildi(patched):
    assert _olc(patched)["kredi_kullanildi"] == 1


def test_alt_puanlar_keys(patched):
    assert set(_olc(patched)["alt_puanlar"]) == {
        "siralama", "icerik", "erisim", "rekabet"}


def test_alt_puanlar_has_puan_agirlik_olcek(patched):
    for k, v in _olc(patched)["alt_puanlar"].items():
        assert set(v) >= {"puan", "agirlik"}


def test_alt_puanlar_agirlik_matches(patched):
    r = _olc(patched)["alt_puanlar"]
    assert r["siralama"]["agirlik"] == g.AGIRLIK["siralama"]
    assert r["icerik"]["agirlik"] == g.AGIRLIK["icerik"]


def test_icerik_normalized_25(patched):
    """icerik normalize(12, 25) -> 48."""
    assert _olc(patched)["alt_puanlar"]["icerik"]["puan"] == 48.0


def test_erisim_normalized_20(patched):
    """erisim normalize(10, 20) -> 50."""
    assert _olc(patched)["alt_puanlar"]["erisim"]["puan"] == 50.0


def test_rekabet_normalized_10(patched):
    """rekabet normalize(25, 10) -> 100 (maks 10)."""
    assert _olc(patched)["alt_puanlar"]["rekabet"]["puan"] == 100.0


def test_ai_alinti_puani_float(patched):
    assert isinstance(_olc(patched)["ai_alinti_puani"], (int, float))


def test_ai_alinti_puani_0_100(patched):
    p = _olc(patched)["ai_alinti_puani"]
    assert 0 <= p <= 100


def test_ai_alinti_puani_weighted(patched):
    """0.45*80 + 0.25*48 + 0.2*50 + 0.1*100 = 68.0."""
    p = _olc(patched)["ai_alinti_puani"]
    w = g.AGIRLIK
    expected = (w["siralama"] * 80 + w["icerik"] * 48 +
                w["erisim"] * 50 + w["rekabet"] * 100)
    assert abs(p - round(expected, 2)) < 0.5


def test_siralama_keys(patched):
    assert set(_olc(patched)["siralama"]) >= {
        "en_iyi_sira", "ust10_orani", "ortalama_sira_puani",
        "sorgular", "hatalar"}


def test_siralama_en_iyi(patched):
    assert _olc(patched)["siralama"]["en_iyi_sira"] == 3


def test_siralama_ust10(patched):
    assert _olc(patched)["siralama"]["ust10_orani"] == 0.5


def test_siralama_hatalar_echoed(patched):
    assert _olc(patched)["siralama"]["hatalar"] == []


def test_siralama_sorgular_echoed(patched):
    assert len(_olc(patched)["siralama"]["sorgular"]) == 1


def test_uyarilar_list(patched):
    assert isinstance(_olc(patched)["uyarilar"], list)


def test_uyarilar_nonempty(patched):
    assert len(_olc(patched)["uyarilar"]) >= 3


def test_uyarilar_has_arxiv(patched):
    joined = " ".join(_olc(patched)["uyarilar"])
    assert "arXiv" in joined or "arxiv" in joined.lower()


# -- akis ---------------------------------------------------------------------------------

def test_siralama_olc_called(patched):
    _olc(patched)
    assert "siralama_olc" in patched


def test_api_key_passed(patched):
    _olc(patched, api_key="ANAHTAR-1")
    assert patched["siralama_olc"][0][2] == "ANAHTAR-1"


def test_govde_given_skips_site(patched):
    _olc(patched, govde="<html>x</html>")
    assert "site_durumu" not in patched


def test_govde_used_for_icerik(patched):
    _olc(patched, govde="gövde-metni")
    assert patched["icerik_derinligi"][0][0] == "gövde-metni"


def test_no_govde_calls_site(patched):
    _olc(patched)
    assert len(patched["site_durumu"]) == 1


def test_robots_given_skips_urllib(patched, monkeypatch):
    import urllib.request as ur
    called = []
    monkeypatch.setattr(ur, "urlopen",
                        lambda *a, **k: called.append(1))
    _olc(patched, robots_metni="User-agent: *")
    assert called == []


def test_robots_passed_to_erisim(patched):
    _olc(patched, robots_metni="User-agent: *\nAllow: /")
    assert patched["erisim_olce"][0][1] == "User-agent: *\nAllow: /"


def test_kaydet_true_calls_kaydet(patched):
    _olc(patched, kaydet=True)
    assert len(patched["olcum_kaydet"]) == 1


def test_kaydet_false_skips_kaydet(patched):
    _olc(patched, kaydet=False)
    assert "olcum_kaydet" not in patched


def test_kaydet_sonuc_passed(patched):
    _olc(patched, kaydet=True)
    sonuc = patched["olcum_kaydet"][0][0]
    assert sonuc["domain"] == "ornek.com"


def test_site_fetch_fn_used(patched):
    seen = []

    def _fetch(domain):
        seen.append(domain)
        return {"govde": "ozel", "erisilebilir": True,
                "https": True}
    _olc(patched, site_fetch_fn=_fetch)
    assert seen == ["ornek.com"]
    assert "site_durumu" not in patched


def test_llms_kontrol_called(patched):
    _olc(patched)
    assert len(patched["llms_txt_kontrol"]) == 1


def test_rakip_called(patched):
    _olc(patched)
    assert len(patched["rakip_analizi"]) == 1


def test_robots_sitemap_called(patched):
    _olc(patched)
    assert len(patched["robots_ve_sitemap"]) == 1


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(patched):
    a = _olc(patched)
    b = _olc(patched)
    assert a["ai_alinti_puani"] == b["ai_alinti_puani"]


def test_two_domains_independent(patched):
    a = _olc(patched, "a.com")
    b = _olc(patched, "b.com")
    assert a["domain"] == "a.com"
    assert b["domain"] == "b.com"


def test_sorgular_passed_through(patched):
    monkeypatch_keys = patched
    r = g.olc("ornek.com", ["q1", "q2"], "key",
              robots_metni="x", govde="y")
    assert monkeypatch_keys["siralama_olc"][0][1] == ["q1", "q2"]
