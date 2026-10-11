"""answrank.audit.sitemap dal-kesen testleri (LEED) — 1 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — gercek httpx/ag YOK; httpx.AsyncClient STUBLA.
SitemapAuditor._fetch_doc (TTL asset_cache + nested _do_fetch).
"""
import asyncio

import httpx
import pytest

from answrank.audit import sitemap
from answrank.audit.sitemap import SitemapAuditor


class FakeResp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class FakeClient:
    """httpx.AsyncClient saf-in-memory stubu — gercek ag YOK."""

    instances = []

    def __init__(self, responses=None, exc=None, timeout=None, verify=None):
        self.responses = responses or {}
        self.exc = exc
        self.timeout = timeout
        self.verify = verify
        self.gets = []
        FakeClient.instances.append(self)

    async def get(self, url):
        self.gets.append(url)
        if self.exc:
            raise self.exc
        return self.responses.get(url, FakeResp(404, "yok"))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.fixture
def fx(monkeypatch):
    """ORTAM: httpx.AsyncClient modul-niteligi STUBLA; cache conftest temizler."""
    FakeClient.instances = []
    yapilan = {"responses": {}, "exc": None}

    def _ctor(**kw):
        yapilan["kwargs"] = kw
        return FakeClient(responses=dict(yapilan["responses"]),
                          exc=yapilan["exc"], **kw)

    monkeypatch.setattr(sitemap.httpx, "AsyncClient", _ctor)
    return yapilan


def _fetch(url, key="k1"):
    return asyncio.run(SitemapAuditor()._fetch_doc(url, key))


# == basarili fetch ===========================================================================

def test_fetch_doc_200_metin(fx):
    fx["responses"] = {"https://a.example/sitemap.xml": FakeResp(200, "<urlset/>")}
    assert _fetch("https://a.example/sitemap.xml", "sitemap:a.example") \
        == "<urlset/>"


def test_fetch_doc_404_none(fx):
    """ORTAM: status_code != 200 -> None (sessizce)."""
    fx["responses"] = {"https://a.example/s.xml": FakeResp(404, "yok")}
    assert _fetch("https://a.example/s.xml") is None


@pytest.mark.parametrize("code", [301, 403, 500, 503, 429])
def test_fetch_doc_diger_status_none(fx, code):
    """ORTAM: yalniz 200 gecerli — 3xx/4xx/5xx hepsi None."""
    fx["responses"] = {"u": FakeResp(code, "x")}
    assert _fetch("u") is None


def test_fetch_doc_200_bos_metin(fx):
    fx["responses"] = {"u": FakeResp(200, "")}
    assert _fetch("u") == ""


def test_fetch_doc_unicode_metin(fx):
    fx["responses"] = {"u": FakeResp(200, "<urlset>İĞÜŞÖ</urlset>")}
    assert _fetch("u") == "<urlset>İĞÜŞÖ</urlset>"


def test_fetch_doc_metin_korunur_tam(fx):
    fx["responses"] = {"u": FakeResp(200, "<?xml version='1.0'?>\n<urlset/>")}
    assert _fetch("u").endswith("<urlset/>")


# == ag hatalari ==============================================================================

@pytest.mark.parametrize("exc", [
    httpx.ConnectError("red"),
    httpx.TimeoutException("8s"),
    httpx.ReadError("kop"),
    ValueError("beklenmeyen"),
    RuntimeError("boom"),
])
def test_fetch_doc_istisna_none_yayilmaz(fx, exc):
    """ORTAM-OGRENDI: her turlu Exception yutulur (logger.warning) -> None;
    istisna ASLA yayilmaz (fail-safe)."""
    fx["exc"] = exc
    assert _fetch("u") is None


def test_fetch_doc_istisna_warning_loglar(fx, caplog):
    """ORTAM: hata 'Sitemap fetch failed for %s' warning ile loglanir."""
    fx["exc"] = RuntimeError("patladı")
    with caplog.at_level("WARNING", logger="answrank.sitemap"):
        _fetch("https://a.example/s.xml")
    mesajlar = [r.message for r in caplog.records]
    assert any("Sitemap fetch failed" in m for m in mesajlar)
    assert any("https://a.example/s.xml" in m for m in mesajlar)


def test_fetch_doc_url_aktarilir(fx):
    fx["responses"] = {"https://b.example/s.xml": FakeResp(200, "x")}
    _fetch("https://b.example/s.xml")
    assert FakeClient.instances[0].gets == ["https://b.example/s.xml"]


def test_fetch_doc_olmayan_url_404(fx):
    """ORTAM: responses'ta olmayan URL -> varsayilan 404 -> None."""
    assert _fetch("https://yok.example/s.xml") is None


# == httpx client argumanlari =================================================================

def test_fetch_doc_timeout_10(fx):
    """ORTAM: AsyncClient(timeout=10.0, verify=True) sabit argumanlari."""
    _fetch("u")
    assert fx["kwargs"]["timeout"] == 10.0
    assert fx["kwargs"]["verify"] is True


def test_fetch_doc_bir_client_per_fetch(fx):
    """ORTAM: her fetch yeni bir AsyncClient acar (async context manager)."""
    fx["responses"] = {"u": FakeResp(200, "x")}
    _fetch("u", "k1")
    _fetch("u", "k2")
    assert len(FakeClient.instances) == 2


# == TTL cache davranisi ======================================================================

def test_fetch_doc_cache_key_vurma(fx):
    """ORTAM: ayni cache_key -> _do_fetch TEKRAR cagrilmaz (cache hit)."""
    fx["responses"] = {"u": FakeResp(200, "ilk")}
    a = _fetch("u", "ortak")
    fx["responses"] = {"u": FakeResp(200, "ikinci")}
    b = _fetch("u", "ortak")
    assert a == b == "ilk"
    assert len(FakeClient.instances) == 1


def test_fetch_doc_farkli_key_yeniden_fetch(fx):
    """ORTAM: farkli cache_key -> gercek fetch (cache miss)."""
    fx["responses"] = {"u": FakeResp(200, "ilk")}
    _fetch("u", "k1")
    fx["responses"] = {"u": FakeResp(200, "ikinci")}
    b = _fetch("u", "k2")
    assert b == "ikinci"
    assert len(FakeClient.instances) == 2


def test_fetch_doc_cache_none_saklanir(fx):
    """ORTAM-OGRENDI: None SONUCU DA cache'lenir — 404 tekrar sorgulanmaz
    (consistently-failing URL icin backpressure)."""
    fx["responses"] = {"u": FakeResp(404)}
    assert _fetch("u", "k1") is None
    fx["responses"] = {"u": FakeResp(200, "artik var")}
    assert _fetch("u", "k1") is None
    assert len(FakeClient.instances) == 1


def test_fetch_doc_cache_farkli_auditor_paylasir(fx):
    """ORTAM: asset_cache GLOBAL — farkli auditor instance'lari paylasir."""
    fx["responses"] = {"u": FakeResp(200, "ilk")}
    asyncio.run(SitemapAuditor()._fetch_doc("u", "paylasim"))
    fx["responses"] = {"u": FakeResp(200, "ikinci")}
    b = asyncio.run(SitemapAuditor()._fetch_doc("u", "paylasim"))
    assert b == "ilk"


def test_fetch_doc_cache_key_sitemap_disinda_serbest(fx):
    """ORTAM: cache_key sadece cache anahtari — URL ile ayni olmak zorunda DEGIL."""
    fx["responses"] = {"https://a.example/s.xml": FakeResp(200, "x")}
    assert _fetch("https://a.example/s.xml", "ozel-anahtar-42") == "x"


def test_fetch_doc_cache_ttl_saniyesi_ayar(fx, monkeypatch):
    """ORTAM: settings.asset_cache_ttl_seconds cache TTL'ine aktarilir."""
    from answrank.config import settings
    monkeypatch.setattr(settings, "asset_cache_ttl_seconds", 999)
    _fetch("u")
    # cache'leme calisiyor: ikinci cagri ayni sonuc, yeni fetch yok
    assert _fetch("u") is None
    assert len(FakeClient.instances) == 1
