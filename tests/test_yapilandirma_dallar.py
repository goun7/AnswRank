"""uret_rapor.yapilandirma dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-3: site_durumu stub — gercek HTTP YAPILMADI.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uret_rapor as U  # noqa: E402


def _stub(monkeypatch, govde):
    calls = {"domains": []}

    def _site_durumu(domain):
        calls["domains"].append(domain)
        return {"status": 200, "govde": govde, "url": f"https://{domain}"}
    monkeypatch.setattr(U, "site_durumu", _site_durumu)
    return calls


_HTML = """<html lang="tr">
<head>
<meta charset="utf-8">
<title>Deneme Basligi</title>
<meta name="description" content="test">
<script type="application/ld+json">{"@type":"Organization"}</script>
<meta property="og:title" content="Deneme">
</head>
<body><h1>Baslik</h1><h1>Ikinci</h1></body>
</html>"""


# -- temel ---------------------------------------------------------------------------------

def test_returns_dict(monkeypatch):
    _stub(monkeypatch, _HTML)
    assert isinstance(U.yapilandirma("ornek.com"), dict)


def test_passes_domain(monkeypatch):
    c = _stub(monkeypatch, _HTML)
    U.yapilandirma("site.net")
    assert c["domains"] == ["site.net"]


def test_keys_present(monkeypatch):
    _stub(monkeypatch, _HTML)
    r = U.yapilandirma("ornek.com")
    assert set(r) == {"schema_org", "open_graph", "meta_aciklama",
                      "h1_sayisi", "title_uzunlugu", "title", "lang"}


def test_empty_body_returns_error(monkeypatch):
    _stub(monkeypatch, "")
    assert U.yapilandirma("ornek.com") == {"hata": "site okunamadi"}


def test_none_body_returns_error(monkeypatch):
    _stub(monkeypatch, None)
    assert U.yapilandirma("ornek.com") == {"hata": "site okunamadi"}


# -- schema / og / meta ---------------------------------------------------------------------------------

def test_schema_org_detected(monkeypatch):
    _stub(monkeypatch, _HTML)
    assert U.yapilandirma("ornek.com")["schema_org"] is True


def test_schema_org_missing(monkeypatch):
    h = _HTML.replace('<script type="application/ld+json">', "")
    _stub(monkeypatch, h)
    assert U.yapilandirma("ornek.com")["schema_org"] is False


def test_open_graph_detected(monkeypatch):
    _stub(monkeypatch, _HTML)
    assert U.yapilandirma("ornek.com")["open_graph"] is True


def test_open_graph_missing(monkeypatch):
    h = _HTML.replace('<meta property="og:title" content="Deneme">', "")
    _stub(monkeypatch, h)
    assert U.yapilandirma("ornek.com")["open_graph"] is False


def test_meta_aciklama_detected(monkeypatch):
    _stub(monkeypatch, _HTML)
    assert U.yapilandirma("ornek.com")["meta_aciklama"] is True


def test_meta_aciklama_missing(monkeypatch):
    h = _HTML.replace('<meta name="description" content="test">', "")
    _stub(monkeypatch, h)
    assert U.yapilandirma("ornek.com")["meta_aciklama"] is False


# -- h1 ---------------------------------------------------------------------------------

def test_h1_count(monkeypatch):
    _stub(monkeypatch, _HTML)
    assert U.yapilandirma("ornek.com")["h1_sayisi"] == 2


def test_h1_none(monkeypatch):
    _stub(monkeypatch, "<html><body></body></html>")
    assert U.yapilandirma("ornek.com")["h1_sayisi"] == 0


def test_h1_case_insensitive(monkeypatch):
    _stub(monkeypatch, "<h1>a</H1>")
    assert U.yapilandirma("ornek.com")["h1_sayisi"] == 1


# -- title ---------------------------------------------------------------------------------

def test_title_extracted(monkeypatch):
    _stub(monkeypatch, _HTML)
    assert U.yapilandirma("ornek.com")["title"] == "Deneme Basligi"


def test_title_length(monkeypatch):
    _stub(monkeypatch, _HTML)
    assert U.yapilandirma("ornek.com")["title_uzunlugu"] == 14


def test_title_missing(monkeypatch):
    _stub(monkeypatch, "<html><body></body></html>")
    r = U.yapilandirma("ornek.com")
    assert r["title"] == "" and r["title_uzunlugu"] == 0


def test_title_tags_stripped(monkeypatch):
    h = "<html><head><title><b>Kalın</b></title></head></html>"
    _stub(monkeypatch, h)
    assert U.yapilandirma("ornek.com")["title"] == "Kalın"


def test_title_truncated_60(monkeypatch):
    h = '<html><head><title>' + "x" * 100 + '</title></head></html>'
    _stub(monkeypatch, h)
    r = U.yapilandirma("ornek.com")
    assert len(r["title"]) == 60
    assert r["title_uzunlugu"] == 100


def test_title_multiline(monkeypatch):
    h = "<html><head><title>bir\niki</title></head></html>"
    _stub(monkeypatch, h)
    assert U.yapilandirma("ornek.com")["title"] == "bir\niki"


# -- lang ---------------------------------------------------------------------------------

def test_lang_detected(monkeypatch):
    _stub(monkeypatch, _HTML)
    assert U.yapilandirma("ornek.com")["lang"] == "tr"


def test_lang_missing_default(monkeypatch):
    _stub(monkeypatch, "<html><body></body></html>")
    assert U.yapilandirma("ornek.com")["lang"] == "belirtilmemis"


def test_lang_en(monkeypatch):
    h = '<html lang="en-US"><body></body></html>'
    _stub(monkeypatch, h)
    assert U.yapilandirma("ornek.com")["lang"] == "en-US"


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(monkeypatch):
    _stub(monkeypatch, _HTML)
    assert U.yapilandirma("a.com") == U.yapilandirma("a.com")


def test_different_domains_same_result(monkeypatch):
    _stub(monkeypatch, _HTML)
    assert U.yapilandirma("a.com") == U.yapilandirma("b.com")
