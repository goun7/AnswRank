"""answrank.crm.dm_sender dal-kesen testleri (LEED) — 3 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-3: out/ veya .html URETILMEZ — OUTBOX_DIR tmp_path'e yonlendirilir.
Kural-4: saf in-memory — gercek SMTP YOK; smtplib.SMTP STUBLA, sqlite tmp.
DMSender._send_smtp + _send_manual + _log.
"""
import sqlite3
from contextlib import contextmanager

import pytest

from answrank.crm import dm_sender
from answrank.crm.dm_sender import DMSender, SendResult

_DDL = """
CREATE TABLE IF NOT EXISTS dm_send_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_id INTEGER NOT NULL,
    domain TEXT NOT NULL,
    recipient TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN
        ('GÖNDERİLDİ','HATA','HEDEF_YOK','YAPILANDIRILMAMIŞ','DRY_RUN')),
    note TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    variant_key TEXT NOT NULL DEFAULT 'variant_1',
    UNIQUE(queue_id, recipient)
);
"""


class FakeSMTP:
    """Saf-in-memory SMTP stubu — gercek ag YOK."""

    def __init__(self, record, exc=None, fail_methods=()):
        self._record = record
        self._exc = exc
        self._fail = fail_methods
        self.srv = None

    def __call__(self, host, port, timeout=None):
        self._record.append(("connect", host, port, timeout))
        if "connect" in self._fail:
            raise self._exc or ConnectionError("connect red")
        outer = self

        class _Srv:
            def __init__(self):
                self.started_tls = False
                self.logged_in = None
                self.sent = []

            def starttls(self):
                outer._record.append(("starttls",))
                if "starttls" in outer._fail:
                    raise outer._exc or OSError("tls")
                self.started_tls = True

            def login(self, user, pw):
                outer._record.append(("login", user))
                if "login" in outer._fail:
                    raise outer._exc or OSError("login")
                self.logged_in = user

            def send_message(self, msg):
                outer._record.append(("send", str(msg)))
                if "send" in outer._fail:
                    raise outer._exc or RuntimeError("send patladı")
                self.sent.append(msg)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                outer._record.append(("quit",))
                return False

        self.srv = _Srv()
        return self.srv


@pytest.fixture
def sender(tmp_path, monkeypatch):
    """ORTAM: OUTBOX_DIR + db_path tmp_path'e (Kural-3/4); smtplib STUBLA."""
    outbox = tmp_path / "outbox"
    monkeypatch.setattr(dm_sender, "OUTBOX_DIR", outbox)
    db = tmp_path / "dm.db"
    with sqlite3.connect(db) as c:
        c.execute(_DDL)
        c.commit()
    rec = []
    monkeypatch.setattr(dm_sender.smtplib, "SMTP", FakeSMTP(rec))
    s = DMSender(db_path=str(db))
    s._record = rec
    s._outbox = outbox
    return s


_CREDS_BASE = {"host": "smtp.example", "port": 587, "user": "a@b.example",
              "pass": "s3cret", "from_name": "AnswRank"}


def _creds(**kw):
    """ORTAM-OGRENDI: production creds['pass'] ile okur ('password' DEGIL) —
    'pass' Python keyword oldugu icin dict literal kullanilir."""
    base = dict(_CREDS_BASE)
    base.update(kw)
    return base


def _smtp_fail(sender, fail_methods, exc=None):
    sender._record.clear()
    dm_sender.smtplib.SMTP = FakeSMTP(sender._record, exc=exc,
                                      fail_methods=fail_methods)


def _log_rows(sender):
    with sqlite3.connect(sender.db_path) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(
            "SELECT queue_id, domain, recipient, status, note, variant_key"
            " FROM dm_send_log")]


# == _send_smtp — basarili ====================================================================

def test_send_smtp_basarili(sender):
    r = sender._send_smtp(7, "a.example", "x@y.example", "Konu", "Gövde",
                          "variant_1", _creds())
    assert isinstance(r, SendResult)
    assert r.queue_id == 7
    assert r.domain == "a.example"
    assert r.recipient == "x@y.example"
    assert r.channel == "smtp"
    assert r.status == "GÖNDERİLDİ"
    assert "smtp.example ile gönderildi" in r.note


def test_send_smtp_baglanti_sirasi(sender):
    sender._send_smtp(1, "d", "r", "K", "G", "v1", _creds())
    adimlar = [x[0] for x in sender._record]
    assert adimlar == ["connect", "starttls", "login", "send", "quit"]


def test_send_smtp_host_port_timeout(sender):
    sender._send_smtp(1, "d", "r", "K", "G", "v1",
                      _creds(host="mail.test", port=2525))
    bag = [x for x in sender._record if x[0] == "connect"][0]
    assert bag[1] == "mail.test" and bag[2] == 2525
    assert bag[3] == 30


def test_send_smtp_mesaj_basliklari(sender):
    sender._send_smtp(1, "d", "r@y.example", "Merhaba", "Gövde metni", "v1",
                      _creds(from_name="Takım", user="gönderen@b.example"))
    giden = [x[1] for x in sender._record if x[0] == "send"][0]
    assert "From: Takım <gönderen@b.example>" in giden
    assert "To: r@y.example" in giden
    assert "Subject: Merhaba" in giden
    """ORTAM-OGRENDI: EmailMessage.set_content base64 transfer-encoding
    uygular — govde acik metin DEGIL, 'R8O2dmRlIG1ldG5p' (base64) gider."""
    assert "R8O2dmRlIG1ldG5p" in giden


def test_send_smtp_starttls_cagriliyor(sender):
    sender._send_smtp(1, "d", "r", "K", "G", "v1", _creds())
    assert sender._record[1] == ("starttls",)


def test_send_smtp_login_kullanici_ile(sender):
    sender._send_smtp(1, "d", "r", "K", "G", "v1", _creds(user="u@b"))
    assert ("login", "u@b") in sender._record


def test_send_smtp_kullanici_yoksa_login_atlar(sender):
    """ORTAM: creds['user'] falsy -> login ATLANIR (open relay / anonim)."""
    sender._send_smtp(1, "d", "r", "K", "G", "v1", _creds(user=""))
    assert not any(x[0] == "login" for x in sender._record)
    assert any(x[0] == "send" for x in sender._record)


def test_send_smtp_gonderim_basari_durumu(sender):
    r = sender._send_smtp(1, "d", "r", "K", "G", "v1", _creds())
    assert r.status == "GÖNDERİLDİ"


# == _send_smtp — fail-closed dallari =========================================================

@pytest.mark.parametrize("fail, exc", [
    ("connect", ConnectionRefusedError("61")),
    ("starttls", OSError("tls reddi")),
    ("login", RuntimeError("auth 535")),
    ("send", ValueError("çok büyük")),
])
def test_send_smtp_hata_fail_closed(sender, fail, exc):
    """ORTAM-OGRENDI: her turlu Exception -> 'HATA' + tip+mesaj notta;
    istisna YAYILMAZ (fail-closed), _log YINE cagrilir."""
    _smtp_fail(sender, (fail,), exc=exc)
    r = sender._send_smtp(1, "a.example", "r@y", "K", "G", "v1", _creds())
    assert r.status == "HATA"
    assert r.channel == "smtp"
    assert f"{type(exc).__name__}: {exc}" in r.note


def test_send_smtp_hata_recipient_korunur(sender):
    _smtp_fail(sender, ("send",))
    r = sender._send_smtp(1, "a.example", "r@y.example", "K", "G", "v1", _creds())
    assert r.recipient == "r@y.example"
    assert r.domain == "a.example"


def test_send_smtp_hata_logda_hata_durumu(sender):
    _smtp_fail(sender, ("send",))
    sender._send_smtp(1, "a.example", "r@y", "K", "G", "v1", _creds())
    rows = _log_rows(sender)
    assert len(rows) == 1 and rows[0]["status"] == "HATA"


# == _send_smtp — _log her zaman ===============================================================

def test_send_smtp_basarili_log_yazar(sender):
    sender._send_smtp(42, "a.example", "r@y.example", "K", "G", "v2", _creds())
    rows = _log_rows(sender)
    assert rows == [dict(queue_id=42, domain="a.example",
                         recipient="r@y.example", status="GÖNDERİLDİ",
                         note=rows[0]["note"], variant_key="v2")]


def test_send_smtp_log_unique_guncelleme(sender):
    """ORTAM: UNIQUE(queue_id, recipient) — ayni kuyruk+aliciyi GUNCELLER."""
    sender._send_smtp(1, "a.example", "r@y", "K", "G", "v1", _creds())
    _smtp_fail(sender, ("send",))
    sender._send_smtp(1, "a.example", "r@y", "K", "G", "v1", _creds())
    rows = _log_rows(sender)
    assert len(rows) == 1
    assert rows[0]["status"] == "HATA"


def test_send_smtp_log_variant_key_kaydedilir(sender):
    sender._send_smtp(1, "a.example", "r@y", "K", "G", "variant_3", _creds())
    assert _log_rows(sender)[0]["variant_key"] == "variant_3"


@pytest.mark.parametrize("recipient", [None, ""])
def test_send_smtp_recipient_yok_log_parantez(sender, recipient):
    """ORTAM: recipient falsy -> loga '(yok)' yazilir (NOT NULL kistas)."""
    _smtp_fail(sender, ("send",))
    sender._send_smtp(1, "a.example", recipient, "K", "G", "v1", _creds())
    assert _log_rows(sender)[0]["recipient"] == "(yok)"


def test_send_smtp_unicode_govde(sender):
    """ORTAM-OGRENDI: unicode govde base64 ile kodlanir — acik metin YOK."""
    r = sender._send_smtp(1, "a.example", "r@y", "İĞÜŞÖ Konu",
                          "İĞÜŞÖ gövde", "v1", _creds())
    assert r.status == "GÖNDERİLDİ"
    giden = [x[1] for x in sender._record if x[0] == "send"][0]
    assert "Subject: İĞÜŞÖ Konu" in giden
    assert "İĞÜŞÖ gövde" not in giden  # base64'te


def test_send_smtp_kanal_smtp(sender):
    """ORTAM: _send_smtp her zaman 'smtp' kanalini isaretler."""
    _smtp_fail(sender, ("send",))
    assert sender._send_smtp(1, "d", "r", "K", "G", "v1", _creds()).channel \
        == "smtp"


# == _send_manual =============================================================================

def test_send_manual_eml_uretir(sender):
    r = sender._send_manual(9, "a.example", "r@y.example", "Konu", "Gövde",
                            "variant_2")
    assert r.status == "YAPILANDIRILMAMIŞ"
    assert r.channel == "manual"
    assert r.recipient == "r@y.example"
    assert "Hazır .eml:" in r.note
    assert "siz gönderin (kanıt loglandı)" in r.note
    dosyalar = list(sender._outbox.glob("dm_9_variant_2_a.example.eml"))
    assert len(dosyalar) == 1


def test_send_manual_eml_icerigi(sender):
    sender._send_manual(1, "a.example", "r@y.example", "Merhaba", "Gövde", "v1")
    veri = (sender._outbox / "dm_1_v1_a.example.eml").read_bytes()
    metin = veri.decode("utf-8")
    assert "To: r@y.example" in metin
    assert "Subject: Merhaba" in metin
    assert "Gövde" in metin


def test_send_manual_eml_basligi_yok(sender):
    """ORTAM: .eml'de From header'i YOK (kullanici kendi istemcisiyle gonderir)."""
    sender._send_manual(1, "a.example", "r@y.example", "K", "G", "v1")
    metin = (sender._outbox / "dm_1_v1_a.example.eml").read_bytes().decode()
    assert "From:" not in metin


def test_send_manual_dosya_uzerine_yazar(sender):
    """ORTAM: ayni queue+variant+domain -> dosya UZERINE yazilir."""
    sender._send_manual(1, "a.example", "r@y", "K", "ilk", "v1")
    sender._send_manual(1, "a.example", "r@y", "K", "ikinci", "v1")
    assert len(list(sender._outbox.glob("*.eml"))) == 1
    metin = (sender._outbox / "dm_1_v1_a.example.eml").read_bytes().decode()
    assert "ikinci" in metin


def test_send_manual_variant_dosya_adi(sender):
    sender._send_manual(5, "b.example", "r@y", "K", "G", "followup_day_3")
    assert (sender._outbox / "dm_5_followup_day_3_b.example.eml").exists()


def test_send_manual_recipient_none(sender):
    """ORTAM: recipient None -> .eml yine uretilir (To: None)."""
    r = sender._send_manual(1, "a.example", None, "K", "G", "v1")
    assert r.status == "YAPILANDIRILMAMIŞ"
    assert (sender._outbox / "dm_1_v1_a.example.eml").exists()


def test_send_manual_yazma_hatasi(sender, monkeypatch):
    """ORTAM-OGRENDI: IOError -> 'HATA' + '.eml yazılamadı' (fail-closed)."""
    boom = OSError("disk dolu")

    def _patla(yol):
        raise boom

    monkeypatch.setattr(dm_sender.Path, "write_bytes",
                        lambda self, b: _patla(self))
    r = sender._send_manual(1, "a.example", "r@y", "K", "G", "v1")
    assert r.status == "HATA"
    assert ".eml yazılamadı" in r.note
    assert "OSError: disk dolu" in r.note


def test_send_manual_log_yazar(sender):
    sender._send_manual(3, "a.example", "r@y.example", "K", "G", "v1")
    rows = _log_rows(sender)
    assert len(rows) == 1
    assert rows[0]["status"] == "YAPILANDIRILMAMIŞ"
    assert rows[0]["queue_id"] == 3


def test_send_manual_log_recipient_yok(sender):
    sender._send_manual(3, "a.example", None, "K", "G", "v1")
    assert _log_rows(sender)[0]["recipient"] == "(yok)"


def test_send_manual_hata_log_yazar(sender, monkeypatch):
    """ORTAM: hata durumunda DAHIL _log cagrilir (kanit her zaman)."""
    monkeypatch.setattr(dm_sender.Path, "write_bytes",
                        lambda self, b: (_ for _ in ()).throw(OSError("x")))
    sender._send_manual(3, "a.example", "r@y", "K", "G", "v1")
    assert _log_rows(sender)[0]["status"] == "HATA"


def test_send_manual_unicode_dosya_adi(sender):
    sender._send_manual(1, "i̇ğ.example", "r@y", "K", "G", "v1")
    assert (sender._outbox / "dm_1_v1_i̇ğ.example.eml").exists()


def test_send_manual_cok_gonderim_bagimsiz(sender):
    for i in range(5):
        sender._send_manual(i, f"d{i}.example", "r@y", "K", "G", "v1")
    assert len(list(sender._outbox.glob("*.eml"))) == 5


# == kanal secim entegrasyonu =================================================================

def test_smtp_creds_env_yoksa_none(monkeypatch):
    """ORTAM: ANSWRANK_SMTP_HOST yoksa smtp_creds None -> manual kanal."""
    monkeypatch.delenv("ANSWRANK_SMTP_HOST", raising=False)
    import os
    monkeypatch.setattr(os, "getenv", lambda k, d=None: None)
    s = DMSender.__new__(DMSender)
    assert s.smtp_creds() is None


def test_smtp_creds_env_dolu(monkeypatch):
    monkeypatch.setenv("ANSWRANK_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("ANSWRANK_SMTP_PORT", "465")
    monkeypatch.setenv("ANSWRANK_SMTP_USER", "u@b")
    monkeypatch.setenv("ANSWRANK_SMTP_PASS", "p")
    monkeypatch.setenv("ANSWRANK_SMTP_FROM_NAME", "Takım")
    s = DMSender.__new__(DMSender)
    c = s.smtp_creds()
    assert c == {"host": "smtp.test", "port": 465, "user": "u@b",
                 "pass": "p", "from_name": "Takım"}


def test_smtp_creds_port_default_587(monkeypatch):
    monkeypatch.setenv("ANSWRANK_SMTP_HOST", "smtp.test")
    monkeypatch.delenv("ANSWRANK_SMTP_PORT", raising=False)
    monkeypatch.delenv("ANSWRANK_SMTP_USER", raising=False)
    monkeypatch.delenv("ANSWRANK_SMTP_PASS", raising=False)
    monkeypatch.delenv("ANSWRANK_SMTP_FROM_NAME", raising=False)
    s = DMSender.__new__(DMSender)
    c = s.smtp_creds()
    assert c["port"] == 587
    assert c["user"] == "" and c["pass"] == ""
    assert c["from_name"] == "AnswRank"
