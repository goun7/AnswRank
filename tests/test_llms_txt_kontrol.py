"""Tests for llms_txt_kontrol.py — llms.txt v2 standardi denetimi.

Isolation: HICBIR test gercek ag istegi YAPMAZ; fetch_fn ile sahte
yanitlar saglanir.
"""
import pytest

import llms_txt_kontrol as lt

# llmstxt.org'un gercek llms.txt'sinden esinlenmis gecerli ornek
GECERLI = """# llms.txt

> A proposal that those interested in providing LLM-friendly content add a
> /llms.txt file to their site.

## Docs

- [llms.txt proposal](https://llmstxt.org/index.md): The proposal for llms.txt
- [Python library docs](https://llmstxt.org/intro.html.md): Docs for the lib
"""


def fake_fetch_200(icerik):
    def fetch(url, timeout=15):
        return 200, icerik
    return fetch


def fake_fetch_404():
    def fetch(url, timeout=15):
        return 404, ""
    return fetch


# ---------------------------------------------------------------------------
# Format denetimi
# ---------------------------------------------------------------------------
def test_denetle_gecerli_tam_dosya():
    d = lt.llms_txt_denetle(GECERLI)
    assert d["h1_var"] is True
    assert d["blockquote_var"] is True
    assert d["h2_sayisi"] >= 1
    assert d["link_sayisi"] >= 2
    assert d["gecersiz_link_sayisi"] == 0
    assert d["html_gorunuyor"] is False
    assert d["boyut_durum"] == "uygun"


def test_denetle_sadece_h1():
    d = lt.llms_txt_denetle("# Sitem\n")
    assert d["h1_var"] is True
    assert d["blockquote_var"] is False
    assert d["link_sayisi"] == 0


def test_denetle_bos_icerik():
    d = lt.llms_txt_denetle("")
    assert d["h1_var"] is False
    assert d["boyut_byte"] == 0


def test_denetle_html_donusu():
    d = lt.llms_txt_denetle("<html><body>404 - not found</body></html>")
    assert d["html_gorunuyor"] is True


def test_denetle_gecersiz_link():
    d = lt.llms_txt_denetle("# X\n\n## A\n- [a](/relative/path)\n")
    assert d["gecersiz_link_sayisi"] == 1


def test_denetle_boyut_cok_buyuk():
    d = lt.llms_txt_denetle("# X\n" + "a " * 60_000)
    assert d["boyut_durum"] == "cok_buyuk"


def test_denetle_boyut_cok_kucuk():
    d = lt.llms_txt_denetle("# X")
    assert d["boyut_durum"] == "bos"


# ---------------------------------------------------------------------------
# Skor
# ---------------------------------------------------------------------------
def test_skor_yok_0():
    assert lt.llms_txt_skoru({"var": False}, None) == 0


def test_skor_html_veya_h1_yoksa_1():
    d = lt.llms_txt_denetle("<html></html>")
    assert lt.llms_txt_skoru({"var": True}, d) == 1


def test_skor_sadece_h1_2():
    d = lt.llms_txt_denetle("# Sitem\n")
    assert lt.llms_txt_skoru({"var": True}, d) == 2


def test_skor_tam_v2_3():
    d = lt.llms_txt_denetle(GECERLI)
    assert lt.llms_txt_skoru({"var": True}, d) == 3


# ---------------------------------------------------------------------------
# Tam denetim (injected fetch)
# ---------------------------------------------------------------------------
def test_kontrol_gecerli_site():
    s = lt.llms_txt_kontrol("llmstxt.org", fetch_fn=fake_fetch_200(GECERLI))
    assert s["var"] is True
    assert s["skor"] == 3
    assert s["onem_derecesi"] == "dusuk"  # akademik etkisi KANITLI degil


def test_kontrol_yok_404():
    s = lt.llms_txt_kontrol("orphan.com", fetch_fn=fake_fetch_404())
    assert s["var"] is False
    assert s["skor"] == 0
    assert "YOK" in s["aciklama"]


def test_kontrol_www_fallback():
    """Kok https 404 verse www varyanti denenmeli."""
    yanitlar = {
        "https://orphan.com/llms.txt": (404, ""),
        "https://www.orphan.com/llms.txt": (200, GECERLI),
    }

    def fetch(url, timeout=15):
        return yanitlar.get(url, (404, ""))

    s = lt.llms_txt_kontrol("orphan.com", fetch_fn=fetch)
    assert s["var"] is True
    assert "www.orphan.com" in s["yer"]


def test_kontrol_domain_normalizasyon():
    """https:// ve son / temizlenmeli."""
    s = lt.llms_txt_kontrol("https://WWW.Example.com/", fetch_fn=fake_fetch_404())
    assert s["domain"] == "example.com"


def test_llms_full_txt_cek_var():
    def fetch(url, timeout=15):
        if "llms-full.txt" in url:
            return 200, "# Full\n"
        return 404, ""

    r = lt.llms_full_txt_cek("x.com", fetch_fn=fetch)
    assert r["var"] is True
    assert r["boyut_byte"] > 0


def test_llms_full_txt_cek_yok():
    r = lt.llms_full_txt_cek("x.com", fetch_fn=fake_fetch_404())
    assert r["var"] is False
