"""uret_rapor.site_durumu dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: urllib.request.urlopen monkeypatch.
"""
import pytest

import uret_rapor as u


class _Resp:
    def __init__(self, status=200, body="", url="https://x"):
        self.status = status
        self._body = body.encode("utf-8")
        self.url = url

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch(monkeypatch, results=None, error=None):
    reqs = []
    errs = []

    def _urlopen(req, timeout=None):
        reqs.append((req.full_url, req.get_header("User-agent"),
                     timeout))
        if error is not None:
            errs.append(1)
            raise error
        for url, ua, t in reqs[-1:]:
            pass
        key = req.full_url
        for target, resp in results or []:
            if key == target:
                return resp
        raise ConnectionError("no-match")
    monkeypatch.setattr(u.urllib.request, "urlopen", _urlopen)
    return reqs


# -- https onceligi ---------------------------------------------------------------------------------

def test_https_tried_first(monkeypatch):
    reqs = _patch(monkeypatch, [("https://ornek.com", _Resp())])
    u.site_durumu("ornek.com")
    assert reqs[0][0] == "https://ornek.com"


def test_reachable(monkeypatch):
    _patch(monkeypatch, [("https://ornek.com", _Resp())])
    r = u.site_durumu("ornek.com")
    assert r["erisilebilir"] is True


def test_status_200(monkeypatch):
    _patch(monkeypatch, [("https://ornek.com", _Resp(200))])
    assert u.site_durumu("ornek.com")["durum"] == 200


def test_https_true(monkeypatch):
    _patch(monkeypatch, [("https://ornek.com",
                          _Resp(url="https://ornek.com"))])
    assert u.site_durumu("ornek.com")["https"] is True


def test_govde_returned(monkeypatch):
    _patch(monkeypatch, [("https://ornek.com",
                          _Resp(body="merhaba"))])
    assert u.site_durumu("ornek.com")["govde"] == "merhaba"


def test_son_url_returned(monkeypatch):
    _patch(monkeypatch, [("https://ornek.com",
                          _Resp(url="https://ornek.com/x"))])
    assert u.site_durumu("ornek.com")["son_url"] == \
        "https://ornek.com/x"


# -- fallback ---------------------------------------------------------------------------------

def test_https_fail_www_tried(monkeypatch):
    reqs = _patch(monkeypatch, [
        ("https://www.ornek.com", _Resp())])
    u.site_durumu("ornek.com")
    urls = [r[0] for r in reqs]
    assert "https://www.ornek.com" in urls


def test_https_fail_www_works(monkeypatch):
    _patch(monkeypatch, [
        ("https://www.ornek.com",
         _Resp(url="https://www.ornek.com"))])
    r = u.site_durumu("ornek.com")
    assert r["erisilebilir"] is True


def test_https_www_fail_http_tried(monkeypatch):
    reqs = _patch(monkeypatch, [("http://ornek.com", _Resp())])
    u.site_durumu("ornek.com")
    urls = [r[0] for r in reqs]
    assert "http://ornek.com" in urls


def test_http_only_https_false(monkeypatch):
    _patch(monkeypatch, [("http://ornek.com",
                          _Resp(url="http://ornek.com"))])
    assert u.site_durumu("ornek.com")["https"] is False


def test_http_only_reachable(monkeypatch):
    _patch(monkeypatch, [("http://ornek.com", _Resp())])
    assert u.site_durumu("ornek.com")["erisilebilir"] is True


# -- hepsi basarisiz ---------------------------------------------------------------------------------

def test_all_fail_unreachable(monkeypatch):
    _patch(monkeypatch, error=ConnectionError("yok"))
    assert u.site_durumu("ornek.com")["erisilebilir"] is False


def test_all_fail_status_none(monkeypatch):
    _patch(monkeypatch, error=ConnectionError("yok"))
    assert u.site_durumu("ornek.com")["durum"] is None


def test_all_fail_https_false(monkeypatch):
    _patch(monkeypatch, error=ConnectionError("yok"))
    assert u.site_durumu("ornek.com")["https"] is False


def test_all_fail_govde_empty(monkeypatch):
    _patch(monkeypatch, error=ConnectionError("yok"))
    assert u.site_durumu("ornek.com")["govde"] == ""


def test_all_fail_son_url_empty(monkeypatch):
    _patch(monkeypatch, error=ConnectionError("yok"))
    assert u.site_durumu("ornek.com")["son_url"] == ""


# -- istek detaylari ---------------------------------------------------------------------------------

def test_user_agent_sent(monkeypatch):
    reqs = _patch(monkeypatch, [("https://ornek.com", _Resp())])
    u.site_durumu("ornek.com")
    assert reqs[0][1] == u.UA


def test_timeout_used(monkeypatch):
    reqs = _patch(monkeypatch, [("https://ornek.com", _Resp())])
    u.site_durumu("ornek.com")
    assert reqs[0][2] == u.timeout_istek


def test_request_is_Request_object(monkeypatch):
    seen = []

    def _urlopen(req, timeout=None):
        seen.append(req)
        return _Resp()
    monkeypatch.setattr(u.urllib.request, "urlopen", _urlopen)
    u.site_durumu("ornek.com")
    import urllib.request as ur
    assert isinstance(seen[0], ur.Request)


# -- redirect ---------------------------------------------------------------------------------

def test_redirect_to_https_https_true(monkeypatch):
    _patch(monkeypatch, [("http://ornek.com",
                          _Resp(url="https://ornek.com"))])
    assert u.site_durumu("ornek.com")["https"] is True


def test_redirect_status_preserved(monkeypatch):
    _patch(monkeypatch, [("https://ornek.com", _Resp(301))])
    assert u.site_durumu("ornek.com")["durum"] == 301


def test_redirect_to_www_son_url(monkeypatch):
    _patch(monkeypatch, [("https://ornek.com",
                          _Resp(url="https://www.ornek.com"))])
    assert u.site_durumu("ornek.com")["son_url"] == \
        "https://www.ornek.com"


# -- govde decode ---------------------------------------------------------------------------------

def test_turkce_chars_decoded(monkeypatch):
    _patch(monkeypatch, [("https://ornek.com",
                          _Resp(body="İstanbul şapka"))])
    assert u.site_durumu("ornek.com")["govde"] == "İstanbul şapka"


def test_binary_body_replaced(monkeypatch):
    r = _Resp(body="\xff\xfe\x00bad")
    _patch(monkeypatch, [("https://ornek.com", r)])
    assert isinstance(u.site_durumu("ornek.com")["govde"], str)


def test_emoji_body(monkeypatch):
    _patch(monkeypatch, [("https://ornek.com",
                          _Resp(body="🚀 test"))])
    assert u.site_durumu("ornek.com")["govde"] == "🚀 test"


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(monkeypatch):
    _patch(monkeypatch, [("https://ornek.com", _Resp())])
    a = u.site_durumu("ornek.com")
    b = u.site_durumu("ornek.com")
    assert a == b


def test_different_domains(monkeypatch):
    reqs = _patch(monkeypatch, [("https://b.com", _Resp())])
    u.site_durumu("b.com")
    assert reqs[0][0] == "https://b.com"


def test_returns_dict(monkeypatch):
    _patch(monkeypatch, [("https://ornek.com", _Resp())])
    assert isinstance(u.site_durumu("ornek.com"), dict)
