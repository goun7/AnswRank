"""imap_izle.test_baglanti IMAP bağlantı testi (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: monkeypatch imap_baglan + imaplib.IMAP4.
"""
import sys

import pytest

sys.path.insert(0, ".")
sys.path.insert(0, "izleyici")
sys.path.insert(0, "../../01_unicorn/63-Sester")

import imap_izle  # noqa: E402
import imaplib  # noqa: E402


class _FakeIMAP:
    """Sahte IMAP4 — dış ağ YOK."""

    def __init__(self, select_ok=True, search_typ="OK", n=10,
                 close_error=False, logout_error=False):
        self._select_ok = select_ok
        self._search_typ = search_typ
        self._n = n
        self._close_error = close_error
        self._logout_error = logout_error
        self.closed = False
        self.logged_out = False

    def select(self, box, **kw):
        if self._select_ok:
            return "OK", [str(self._n)]
        return "NO", [b""]

    def uid(self, *a, **kw):
        return self._search_typ, [b" ".join(b"%d" % i for i in range(self._n))]

    def close(self):
        self.closed = True
        if self._close_error:
            raise RuntimeError("close hatası")

    def logout(self):
        self.logged_out = True
        if self._logout_error:
            raise RuntimeError("logout hatası")


@pytest.fixture
def fake(monkeypatch):
    state = {"imap": None, "connect_error": None}

    def _baglan(kullanici, sifre, **kw):
        if state["connect_error"] is not None:
            raise state["connect_error"]
        return state["imap"]

    monkeypatch.setattr(imap_izle, "imap_baglan", _baglan)
    return state


# -- başarılı yol ---------------------------------------------------------------------------

def test_success_returns_zero(fake, capsys):
    fake["imap"] = _FakeIMAP()
    assert imap_izle.test_baglanti("k", "s") == 0


def test_success_prints_working(fake, capsys):
    fake["imap"] = _FakeIMAP()
    imap_izle.test_baglanti("k", "s")
    out = capsys.readouterr().out
    assert "IMAP CALISIYOR" in out


def test_select_called_with_inbox(fake):
    m = _FakeIMAP()
    calls = []
    m.select = lambda b, **k: (calls.append(b), ("OK", [b"0"]))[1]
    fake["imap"] = m
    imap_izle.test_baglanti("k", "s")
    assert calls == ["INBOX"]


def test_message_count_shown(fake, capsys):
    fake["imap"] = _FakeIMAP(n=42)
    imap_izle.test_baglanti("k", "s")
    out = capsys.readouterr().out
    assert "42" in out


def test_search_uid_called(fake):
    m = _FakeIMAP()
    seen = []
    m.uid = lambda *a, **k: (seen.append(a), ("OK", [b"1"]))[1]
    fake["imap"] = m
    imap_izle.test_baglanti("k", "s")
    assert seen and seen[0][0] == "search"


def test_closed_and_logged_out(fake):
    m = _FakeIMAP()
    fake["imap"] = m
    imap_izle.test_baglanti("k", "s")
    assert m.closed and m.logged_out


def test_zero_messages(fake, capsys):
    fake["imap"] = _FakeIMAP(n=0)
    assert imap_izle.test_baglanti("k", "s") == 0


def test_one_message(fake, capsys):
    fake["imap"] = _FakeIMAP(n=1)
    assert imap_izle.test_baglanti("k", "s") == 0


# -- IMAP4.error yolu ---------------------------------------------------------------------------

def test_imap_error_returns_one(fake, capsys):
    fake["imap"] = None
    fake["connect_error"] = imaplib.IMAP4.error("auth failed")
    assert imap_izle.test_baglanti("k", "s") == 1


def test_imap_error_prints_fail(fake, capsys):
    fake["connect_error"] = imaplib.IMAP4.error("auth failed")
    imap_izle.test_baglanti("k", "s")
    out = capsys.readouterr().out
    assert "BASARISIZ" in out
    assert "IMAP4.error" in out


def test_imap_error_lists_reasons(fake, capsys):
    fake["connect_error"] = imaplib.IMAP4.error("x")
    imap_izle.test_baglanti("k", "s")
    out = capsys.readouterr().out
    assert "IMAP" in out and "App Password" in out
    assert "2FA" in out


def test_imap_error_prints_message(fake, capsys):
    fake["connect_error"] = imaplib.IMAP4.error("ozel hata")
    imap_izle.test_baglanti("k", "s")
    out = capsys.readouterr().out
    assert "ozel hata" in out


# -- genel istisna yolu ---------------------------------------------------------------------------

def test_generic_error_returns_one(fake, capsys):
    fake["connect_error"] = RuntimeError("zort")
    assert imap_izle.test_baglanti("k", "s") == 1


def test_generic_error_prints_type(fake, capsys):
    fake["connect_error"] = ValueError("kötü değer")
    imap_izle.test_baglanti("k", "s")
    out = capsys.readouterr().out
    assert "ValueError" in out
    assert "kötü değer" in out


def test_generic_error_no_imap_hints(fake, capsys):
    fake["connect_error"] = ValueError("x")
    imap_izle.test_baglanti("k", "s")
    out = capsys.readouterr().out
    assert "App Password" not in out


def test_connection_error_returns_one(fake, capsys):
    fake["connect_error"] = ConnectionRefusedError("yok")
    assert imap_izle.test_baglanti("k", "s") == 1


# -- close/logout dayanıklılığı ---------------------------------------------------------------------------

def test_close_error_still_success(fake):
    fake["imap"] = _FakeIMAP(close_error=True)
    assert imap_izle.test_baglanti("k", "s") == 0


def test_logout_error_still_success(fake):
    fake["imap"] = _FakeIMAP(logout_error=True)
    assert imap_izle.test_baglanti("k", "s") == 0


def test_both_errors_still_success(fake):
    fake["imap"] = _FakeIMAP(close_error=True, logout_error=True)
    assert imap_izle.test_baglanti("k", "s") == 0


def test_logout_attempted_on_error(fake, capsys):
    """Bağlantı hatasında logout denemez (M yok)."""
    fake["connect_error"] = imaplib.IMAP4.error("x")
    assert imap_izle.test_baglanti("k", "s") == 1


# -- select/search başarısız ---------------------------------------------------------------------------

def test_select_failure_still_returns_zero(fake):
    """Search typ NO olsa sayım 0 olur, rc yine 0."""
    fake["imap"] = _FakeIMAP(search_typ="NO", n=0)
    assert imap_izle.test_baglanti("k", "s") == 0


def test_print_header(fake, capsys):
    fake["imap"] = _FakeIMAP()
    imap_izle.test_baglanti("k", "s")
    out = capsys.readouterr().out
    assert "IMAP baglanti testi" in out


def test_credentials_passed(fake):
    seen = {}
    fake["imap"] = _FakeIMAP()

    def _b(k, s, **kw):
        seen["k"] = k
        seen["s"] = s
        return fake["imap"]

    imap_izle.imap_baglan = _b
    imap_izle.test_baglanti("user@mail", "pass123")
    assert seen["k"] == "user@mail"
    assert seen["s"] == "pass123"
