"""answrank.crm.prospector dal-kesen testleri (LEED) — 2 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — gercek httpx YOK; _fetch enjekte edilir (stub).
LeadProspector._safe + LeadProspector._normalize.
"""
import pytest

from answrank.crm.prospector import LeadProspector


# == _normalize =============================================================================

@pytest.mark.parametrize("d, beklenen", [
    ("https://a.example/page", "a.example"),
    ("http://b.example", "b.example"),
    ("c.example", "c.example"),
    ("HTTPS://D.example/", "d.example"),
    ("https://e.example:8080/x", "e.example:8080"),
    ("https://f.example", "f.example"),
    ("  g.example  ", "g.example"),
    ("h.example.", "h.example"),
    ("https://i.example/a/b?c=1", "i.example"),
    ("//j.example/x", "j.example"),
])
def test_normalize_temel(d, beklenen):
    """ORTAM: split('//')[-1].split('/')[0].strip().lower().rstrip('.')."""
    assert LeadProspector._normalize(d) == beklenen


@pytest.mark.parametrize("d, beklenen", [(None, ""), ("", ""), ("   ", "")])
def test_normalize_falsy(d, beklenen):
    """ORTAM: (domain or '') — None/bos -> bos string."""
    assert LeadProspector._normalize(d) == beklenen


def test_normalize_turkce_kucuklenme():
    """ORTAM-OGRENDI: .lower() 'İ' -> 'i̇' (combining dot) yapar;
    'İSTANBUL.example' -> 'i̇stanbul.example' (unicode quirk — Kural-5)."""
    out = LeadProspector._normalize("İSTANBUL.example")
    assert out == "i̇stanbul.example"
    assert out.endswith(".example")


def test_normalize_cok_sayda_slash():
    """ORTAM-OGRENDI: split('//')[-1] EN SON '//'-sonrasini alir —
    'a.example//b//c' -> 'c' (ilk parca DEGIL)."""
    assert LeadProspector._normalize("a.example//b//c") == "c"


def test_normalize_protokol_yok_sonlu_nokta():
    assert LeadProspector._normalize("A.Example.") == "a.example"


def test_normalize_ip_adresi():
    assert LeadProspector._normalize("https://192.168.1.1:80/x") == "192.168.1.1:80"


def test_normalize_query_kORUNUR():
    """ORTAM-OGRENDI: query-string ATILMAZ — '?x=1&y=2' domain'de kalir
    (regex-free split; production quirk — Kural-5)."""
    assert LeadProspector._normalize("a.example?x=1&y=2") == "a.example?x=1&y=2"


def test_normalize_fragment_korunur():
    assert LeadProspector._normalize("a.example#frag") == "a.example#frag"


def test_normalize_static_metot():
    assert callable(LeadProspector._normalize)


# == _safe ===================================================================================

class _Boom(Exception):
    pass


def _raise(exc):
    raise exc


def _async(ret):
    """ORTAM: _fetch AWAITABLE dondurmelidir — senkron lambda tuple verince
    await TypeError firlatir ve _safe bunu (None,'') ile yutar."""
    async def _fake(url, t):
        if isinstance(ret, Exception):
            raise ret
        return ret
    return _fake


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


@pytest.mark.parametrize("exc", [
    _Boom("ag hatasi"), ConnectionError("red"), TimeoutError(),
    OSError("DNS"), ValueError("bozuk"), RuntimeError("beklenmeyen"),
])
def test_safe_istisna_yutulur_none_bos_metin(exc):
    """ORTAM-OGRENDI: her turlu Exception -> (None, '') — fail-safe, YAYILMAZ."""
    p = LeadProspector(fetch=_async(exc))
    assert asyncio_run(p._safe("https://a.example")) == (None, "")


def test_safe_basarili_status_ve_metin():
    p = LeadProspector(fetch=_async((200, "<html>merhaba</html>")))
    assert asyncio_run(p._safe("https://a.example")) == (200, "<html>merhaba</html>")


def test_safe_hata_status_kodlari_gecer():
    """ORTAM: 4xx/5xx HTTP hatalari istisna DEGIL — (status, text) doner."""
    p = LeadProspector(fetch=_async((403, "Forbidden")))
    assert asyncio_run(p._safe("https://a.example")) == (403, "Forbidden")


def test_safe_bos_govde():
    p = LeadProspector(fetch=_async((200, "")))
    assert asyncio_run(p._safe("https://a.example")) == (200, "")


def test_safe_none_status():
    p = LeadProspector(fetch=_async((None, "x")))
    assert asyncio_run(p._safe("https://a.example")) == (None, "x")


def test_safe_fetch_cagrisi_url_aktarilir():
    """ORTAM: _fetch(url, self.timeout) — url ve timeout aynen aktarilir."""
    gorulen = []

    async def fake(url, t):
        gorulen.append((url, t))
        return (200, "ok")

    p = LeadProspector(fetch=fake, timeout=4.2)
    asyncio_run(p._safe("https://b.example"))
    assert gorulen == [("https://b.example", 4.2)]


def test_safe_birden_cok_url_bagimsiz():
    async def fake(url, t):
        return (200, url)

    p = LeadProspector(fetch=fake)
    assert asyncio_run(p._safe("https://a.example"))[1] == "https://a.example"
    assert asyncio_run(p._safe("https://b.example"))[1] == "https://b.example"


def test_safe_aradan_istisna_sonra_tekrar_calisir():
    """ORTAM: state YOK — bir hata sonraki cagriyi etkilemez."""
    state = {"i": 0}

    async def fake(url, t):
        state["i"] += 1
        if state["i"] == 1:
            raise _Boom("ilk hata")
        return (200, "ok")

    p = LeadProspector(fetch=fake)
    assert asyncio_run(p._safe("https://a.example")) == (None, "")
    assert asyncio_run(p._safe("https://a.example")) == (200, "ok")


def test_safe_timeout_degeri_farklilasir():
    """ORTAM: constructor timeout'u _fetch'e aktarilir."""
    async def fake(url, t):
        return (200, str(t))

    p = LeadProspector(fetch=fake, timeout=0.5)
    assert asyncio_run(p._safe("https://a.example")) == (200, "0.5")


def test_safe_default_fetch_httpx_stublanamaz():
    """ORTAM-ANATOMI: fetch verilmezse _httpx_fetch kullanilir (gercek ag).
    Bu test _httpx_fetch'in varligini ve varsayilim oldugunu kanitlar —
    cagrilmiyor (Kural-4)."""
    p = LeadProspector()
    assert p._fetch == LeadProspector._httpx_fetch
