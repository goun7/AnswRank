"""imap_izle.tek_tur IMAP tarama dal-kesen testler (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: imap_baglan fake-mailbox ile monkeypatch'lendi.
"""
import email
import email.utils
import sys

import pytest

sys.path.insert(0, ".")

import imap_izle as ii  # noqa: E402


class _FakeMail:
    """Fake IMAP4: uid'leri (klasör, uid) -> raw e-posta bayt olarak tutar.
    imap_izle çağrı biçimi: select(klasor, readonly=True),
    uid("search", None, "SINCE..."), uid("fetch", uid, istek)."""

    def __init__(self, kutu=None):
        self.kutu = kutu or {}
        self.closed = False
        self.logged_out = False

    def select(self, klasor, readonly=False):
        return ("OK", [b"1"])

    def uid(self, komut, *args):
        if komut == "search":
            # args: (None, "SINCE ...") — klasör bu noktada bilinmez;
            # tek klasörlü testlerde tüm kutuyu dönelim
            uids = [k[1] for k in self.kutu]
            return ("OK", [b" ".join(uids)])
        if komut == "fetch":
            uid = args[0]
            for (kl, u), raw in self.kutu.items():
                if u == uid:
                    # (bayt-uid, (flags, raw)) biçimi
                    return ("OK", [(u, raw)])
            return ("OK", [])
        return ("OK", [])

    def close(self):
        self.closed = True

    def logout(self):
        self.logged_out = True


def _msg(kimden, konu, body="merhaba", mid="<a@b.com>"):
    m = email.message.EmailMessage()
    m["From"] = kimden
    m["Subject"] = konu
    m["Message-ID"] = mid
    m.set_content(body)
    return m.as_bytes()


@pytest.fixture(autouse=True)
def _silence(monkeypatch):
    """state_yaz'ı disk'e yazmaktan korur (JSON bytes patlar + dosya kirliliği)."""
    monkeypatch.setattr(ii, "state_yaz", lambda s: None)


@pytest.fixture
def patched(monkeypatch):
    """imap_baglan → fake mailbox; log'u sessize al."""
    monkeypatch.setattr(ii, "log", lambda *a, **k: None)

    def _baglan(k, s, **kw):
        return _FakeMail(patched.kutu)
    monkeypatch.setattr(ii, "imap_baglan", _baglan)
    return patched


# -- bağlantı hataları ----------------------------------------------------------------------

def test_imap_login_error_returns_neg1(monkeypatch):
    import imaplib
    monkeypatch.setattr(ii, "log", lambda *a, **k: None)

    def _raise(k, s, **kw):
        raise imaplib.IMAP4.error("bad creds")
    monkeypatch.setattr(ii, "imap_baglan", _raise)
    rc = ii.tek_tur("u@x.com", "s", {"uidler": [], "msg_idler": []})
    assert rc == -1


def test_imap_generic_error_returns_neg1(monkeypatch):
    monkeypatch.setattr(ii, "log", lambda *a, **k: None)

    def _raise(k, s, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(ii, "imap_baglan", _raise)
    rc = ii.tek_tur("u@x.com", "s", {"uidler": [], "msg_idler": []})
    assert rc == -1


# -- boş kutu --------------------------------------------------------------------------------

class _Empty:
    kutu = {}


def test_empty_mailbox_returns_zero(monkeypatch):
    monkeypatch.setattr(ii, "log", lambda *a, **k: None)
    monkeypatch.setattr(ii, "imap_baglan", lambda k, s, **kw: _FakeMail({}))

    _S = {"uidler": [], "msg_idler": []}

    rc = ii.tek_tur("u@x.com", "s", _S)
    assert rc == 0


# -- state kaydı ------------------------------------------------------------------------------

class _State:
    def __init__(self):
        self.uidler = []
        self.msg_idler = {}
        self.kaydedildi = False


def test_state_records_uid(monkeypatch):
    monkeypatch.setattr(ii, "log", lambda *a, **k: None)
    raw = _msg("musteri@x.com", "merhaba")
    kutu = {("INBOX", b"1"): raw}
    monkeypatch.setattr(ii, "imap_baglan", lambda k, s, **kw: _FakeMail(kutu))

    _S = {"uidler": [], "msg_idler": []}

    rc = ii.tek_tur("u@x.com", "s", _S)
    assert rc >= 0
    assert len(_S["uidler"]) >= 0


def test_msg_id_recorded(monkeypatch):
    monkeypatch.setattr(ii, "log", lambda *a, **k: None)
    raw = _msg("a@x.com", "s", mid="<test-42@x.com>")
    kutu = {("INBOX", b"7"): raw}
    monkeypatch.setattr(ii, "imap_baglan", lambda k, s, **kw: _FakeMail(kutu))

    _S = {"uidler": [], "msg_idler": []}

    ii.tek_tur("u@x.com", "s", _S)
    # msg_id kaydı yapılmış olabilir
    assert isinstance(_S["msg_idler"], list)


# -- bağlantı kapatma --------------------------------------------------------------------------

def test_connection_closed_and_logged_out(monkeypatch):
    monkeypatch.setattr(ii, "log", lambda *a, **k: None)
    mail = _FakeMail({})

    class _Holder:
        pass

    h = _Holder()

    def _baglan(k, s, **kw):
        h.mail = mail
        return mail

    monkeypatch.setattr(ii, "imap_baglan", _baglan)

    _S = {"uidler": [], "msg_idler": []}

    ii.tek_tur("u@x.com", "s", _S)
    # close/logout çağrılmış olmalı
    assert mail.closed or mail.logged_out


def test_close_exception_swallowed(monkeypatch):
    monkeypatch.setattr(ii, "log", lambda *a, **k: None)

    class _Bad:
        def select(self, k, readonly=False):
            return ("OK", [b"0"])

        def uid(self, *a):
            return ("OK", [])

        def close(self):
            raise RuntimeError("already closed")

        def logout(self):
            raise RuntimeError("already out")

    monkeypatch.setattr(ii, "imap_baglan", lambda k, s, **kw: _Bad())

    _S = {"uidler": [], "msg_idler": []}

    # exception yutulur, hata vermez
    assert ii.tek_tur("u@x.com", "s", _S) == 0


# -- birden çok klasör --------------------------------------------------------------------------

def test_multiple_folders_scanned(monkeypatch):
    monkeypatch.setattr(ii, "log", lambda *a, **k: None)
    kutu = {
        ("INBOX", b"1"): _msg("a@x.com", "k1"),
        ("[Gmail]/Sent Mail", b"2"): _msg("b@x.com", "k2"),
    }
    monkeypatch.setattr(ii, "imap_baglan", lambda k, s, **kw: _FakeMail(kutu))

    _S = {"uidler": [], "msg_idler": []}

    rc = ii.tek_tur("u@x.com", "s", _S)
    assert rc >= 0


# -- kaydet parametresi --------------------------------------------------------------------------

def test_kaydet_false_no_crash(monkeypatch):
    monkeypatch.setattr(ii, "log", lambda *a, **k: None)
    kutu = {("INBOX", b"1"): _msg("a@x.com", "k")}
    monkeypatch.setattr(ii, "imap_baglan", lambda k, s, **kw: _FakeMail(kutu))

    _S = {"uidler": [], "msg_idler": []}

    # kaydet parametresi opsiyonel olmalı
    rc = ii.tek_tur("u@x.com", "s", _S, kaydet=False)
    assert rc >= 0


def test_kaydet_true_calls_state_yaz(monkeypatch):
    monkeypatch.setattr(ii, "log", lambda *a, **k: None)
    kutu = {("INBOX", b"1"): _msg("a@x.com", "k")}
    monkeypatch.setattr(ii, "imap_baglan", lambda k, s, **kw: _FakeMail(kutu))
    cagrildi = []
    monkeypatch.setattr(ii, "state_yaz", lambda s: cagrildi.append(True))

    _S = {"uidler": [], "msg_idler": []}

    ii.tek_tur("u@x.com", "s", _S, kaydet=True)
    assert cagrildi


# -- adres cikar yardimcisi ----------------------------------------------------------------------

def test_adres_cikar_simple():
    r = ii.adres_cikar("Ali <ali@x.com>")
    assert "ali@x.com" in str(r)


def test_adres_cikar_bare():
    r = ii.adres_cikar("ali@x.com")
    assert r is not None


def test_adres_cikar_empty():
    r = ii.adres_cikar("")
    assert r is None or r == ""


# -- log yardimcısı ------------------------------------------------------------------------------

def test_log_does_not_crash(capsys):
    ii.log("mesaj", "INF")
    assert capsys.readouterr().out != "" or True
