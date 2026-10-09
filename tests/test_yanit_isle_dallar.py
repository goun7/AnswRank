"""imap_izle.yanit_isle dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: tüm yardımcı fonksiyonlar monkeypatch + tmp_path.
"""
import os

import pytest

import imap_izle


class _Ctx:
    """Yardimci cagrilarini kaydeder."""
    def __init__(self):
        self.eml = None
        self.sinif = "sicak"
        self.guven = 0.9
        self.isaretler = []
        self.hata = None
        self.returns_none = False
        self.kredi = 10
        self.kaynak = "cache"
        self.rapor = None
        self.draft_ok = True
        self.gecerli = True
        self.bilgi = "ok"
        self.calls = []


@pytest.fixture
def ctx(monkeypatch, tmp_path):
    c = _Ctx()
    c.eml = str(tmp_path / "yanit.eml")

    def _kaydet(msg, raw, domain, klasor):
        c.calls.append(("kaydet", domain, klasor))
        return c.eml

    def _siniflandir(yol):
        c.calls.append(("siniflandir", yol))
        if c.returns_none:
            return None
        r = {"sinif": c.sinif, "guven": c.guven,
             "isaretler": c.isaretler}
        if c.hata:
            r["hata"] = c.hata
        return r

    def _olc(domain):
        c.calls.append(("olc", domain))
        return c.kredi, c.kaynak

    def _rapor(domain):
        c.calls.append(("rapor", domain))
        return c.rapor

    def _draft_hazirla():
        c.calls.append(("hazirla",))
        return c.draft_ok

    def _draft_dogrula(domain):
        c.calls.append(("dogrula", domain))
        return c.gecerli, c.bilgi

    monkeypatch.setattr(imap_izle, "yanit_kaydet", _kaydet)
    monkeypatch.setattr(imap_izle, "yanit_siniflandir", _siniflandir)
    monkeypatch.setattr(imap_izle, "domain_olc", _olc)
    monkeypatch.setattr(imap_izle, "rapor_uret", _rapor)
    monkeypatch.setattr(imap_izle, "draft_hazirla", _draft_hazirla)
    monkeypatch.setattr(imap_izle, "draft_dogrula", _draft_dogrula)
    return c


def _isle(ctx, domain="ornek.com"):
    return imap_izle.yanit_isle(
        42, "msg-objesi", b"raw-bytes", domain, "INBOX")


# -- temel ---------------------------------------------------------------------------------

def test_returns_none(ctx):
    assert _isle(ctx) is None


def test_kaydet_called(ctx):
    _isle(ctx, "ornek.com")
    assert c_first(ctx, "kaydet") == ("kaydet", "ornek.com", "INBOX")


def test_siniflandir_called(ctx):
    _isle(ctx)
    assert ctx.calls[1][0] == "siniflandir"


def test_eml_path_passed(ctx):
    _isle(ctx)
    assert ctx.calls[1][1] == ctx.eml


def c_first(ctx, name):
    return next(c for c in ctx.calls if c[0] == name)


# -- siniflandirma kisa-devre ---------------------------------------------------------------------------------

def test_none_sinif_stops(ctx):
    ctx.returns_none = True
    _isle(ctx)
    assert len(ctx.calls) == 2


def test_none_no_olc(ctx):
    ctx.returns_none = True
    _isle(ctx)
    assert not any(c[0] == "olc" for c in ctx.calls)


def test_hata_stops(ctx):
    ctx.hata = "parse-hatasi"
    _isle(ctx)
    assert len(ctx.calls) == 2


def test_hata_no_draft(ctx):
    ctx.hata = "x"
    _isle(ctx)
    assert not any(c[0] == "hazirla" for c in ctx.calls)


# -- sicak olmayan ---------------------------------------------------------------------------------

def test_soguk_stops(ctx):
    ctx.sinif = "soguk"
    _isle(ctx)
    assert not any(c[0] == "olc" for c in ctx.calls)


def test_ilgili_but_not_sicak(ctx):
    ctx.sinif = "ilgili"
    _isle(ctx)
    assert not any(c[0] == "olc" for c in ctx.calls)


def test_soguk_no_draft(ctx):
    ctx.sinif = "soguk"
    _isle(ctx)
    assert not any(c[0] == "hazirla" for c in ctx.calls)


# -- sicak tam pipeline ---------------------------------------------------------------------------------

def test_sicak_calls_olc(ctx):
    _isle(ctx, "sicak.com")
    assert c_first(ctx, "olc") == ("olc", "sicak.com")


def test_sicak_calls_rapor(ctx):
    _isle(ctx)
    assert any(c[0] == "rapor" for c in ctx.calls)


def test_sicak_calls_hazirla(ctx):
    _isle(ctx)
    assert any(c[0] == "hazirla" for c in ctx.calls)


def test_sicak_calls_dogrula(ctx):
    _isle(ctx)
    assert c_first(ctx, "dogrula") == ("dogrula", "ornek.com")


def test_gecerli_dogrula(ctx):
    ctx.gecerli = True
    _isle(ctx)
    assert c_first(ctx, "dogrula")[1] == "ornek.com"


def test_gecersiz_dogrula(ctx):
    ctx.gecerli = False
    ctx.bilgi = "eksik"
    assert _isle(ctx) is None


def test_draft_hazirlanamadi_stops(ctx):
    ctx.draft_ok = False
    _isle(ctx)
    assert not any(c[0] == "dogrula" for c in ctx.calls)


# -- isaretler ---------------------------------------------------------------------------------

def test_isaretler_empty_ok(ctx):
    ctx.isaretler = []
    assert _isle(ctx) is None


def test_isaretler_list_ok(ctx):
    ctx.isaretler = ["test1", "test2"]
    assert _isle(ctx) is None


def test_isaretler_none_ok(ctx):
    ctx.isaretler = None
    assert _isle(ctx) is None


# -- rapor ---------------------------------------------------------------------------------

def test_rapor_none_ok(ctx):
    ctx.rapor = None
    assert _isle(ctx) is None


def test_rapor_path_ok(ctx):
    ctx.rapor = "/tmp/rapor.md"
    assert _isle(ctx) is None


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(ctx):
    _isle(ctx)
    n1 = len(ctx.calls)
    _isle(ctx)
    assert len(ctx.calls) == 2 * n1


def test_uid_ignored(ctx):
    imap_izle.yanit_isle(
        999, "m", b"r", "d.com", "INBOX")
    assert c_first(ctx, "kaydet")[1] == "d.com"


def test_klasor_variants(ctx):
    imap_izle.yanit_isle(1, "m", b"r", "d.com", "ARSIV")
    assert c_first(ctx, "kaydet")[2] == "ARSIV"


def test_domain_none_ok(ctx):
    _isle(ctx, None)
    assert c_first(ctx, "kaydet")[1] is None
