"""dm_sender.send dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: temp SQLite + OUTBOX_DIR monkeypatch + smtplib stub.
"""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from answrank.crm.dm_sender import DMSender, SendResult

_PROSPECTS = """
CREATE TABLE IF NOT EXISTS prospects (
    id TEXT PRIMARY KEY, brand_name TEXT NOT NULL,
    sector TEXT NOT NULL, city TEXT NOT NULL, website_url TEXT,
    contact_person TEXT, platform TEXT, status TEXT DEFAULT 'lead',
    domain_ref TEXT, country TEXT, phone TEXT, email TEXT,
    source_url TEXT, verified_at TEXT, http_status INTEGER,
    robots_status INTEGER, contact_source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""

_DMLOG = """
CREATE TABLE IF NOT EXISTS dm_send_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, queue_id INTEGER NOT NULL,
    domain TEXT NOT NULL, recipient TEXT NOT NULL,
    status TEXT NOT NULL, note TEXT NOT NULL, sent_at TEXT NOT NULL,
    variant_key TEXT NOT NULL DEFAULT 'variant_1',
    UNIQUE(queue_id, recipient));
"""


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    p = str(tmp_path / "dm.db")
    db = sqlite3.connect(p)
    db.executescript(_PROSPECTS)
    db.executescript(_DMLOG)
    db.commit()
    db.close()
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    monkeypatch.setattr("answrank.crm.dm_sender.OUTBOX_DIR", outbox)
    return p, outbox


def _seed(p, email="a@ornek.com", status="lead",
          url="https://ornek.com", pid="p1"):
    db = sqlite3.connect(p)
    db.execute(
        "INSERT INTO prospects(id, brand_name, sector, city,"
        " status, website_url, email) VALUES (?,?,?,?,?,?,?)",
        (pid, "Brand", "Tech", "Istanbul", status, url, email))
    db.commit()
    db.close()


def _seed_sent(p, queue_id, recipient, status="GÖNDERİLDİ"):
    db = sqlite3.connect(p)
    db.execute(
        "INSERT INTO dm_send_log(queue_id, domain, recipient,"
        " status, note, sent_at) VALUES (?,?,?,?,?,?)",
        (queue_id, "ornek.com", recipient, status, "n", "2026-01-01"))
    db.commit()
    db.close()


def _rows(p, tbl="dm_send_log"):
    db = sqlite3.connect(p)
    try:
        return db.execute(f"SELECT * FROM {tbl}").fetchall()
    finally:
        db.close()


def _no_smtp(monkeypatch):
    monkeypatch.setattr(DMSender, "smtp_creds",
                        lambda self: None)


def _with_smtp(monkeypatch):
    monkeypatch.setattr(DMSender, "smtp_creds",
                        lambda self: {
                            "host": "smtp.test", "port": 587,
                            "user": "u", "pass": "s",
                            "from_name": "Bot"})


def _no_smtp_lib(monkeypatch):
    """smtplib.SMTP stub — gercek sunucu YOK."""
    class _Srv:
        def __init__(self, *a, **k):
            self.args = a

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def send_message(self, msg):
            self.msg = msg

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr("answrank.crm.dm_sender.smtplib",
                        type("M", (), {"SMTP": _Srv}))


# -- HEDEF_YOK ---------------------------------------------------------------------------------

def test_no_recipient_hedef_yok(tmpdb, monkeypatch):
    p, _ = tmpdb
    _no_smtp(monkeypatch)
    r = DMSender(db_path=p).send(1, "ornek.com", "s", "b", "v")
    assert r.status == "HEDEF_YOK"


def test_no_recipient_none(tmpdb, monkeypatch):
    p, _ = tmpdb
    _no_smtp(monkeypatch)
    r = DMSender(db_path=p).send(1, "yok.com", "s", "b", "v")
    assert r.recipient is None


def test_hedef_yok_logged(tmpdb, monkeypatch):
    p, _ = tmpdb
    _no_smtp(monkeypatch)
    DMSender(db_path=p).send(1, "ornek.com", "s", "b", "v")
    assert len(_rows(p)) == 1


def test_hedef_yok_queue_id_kept(tmpdb, monkeypatch):
    p, _ = tmpdb
    _no_smtp(monkeypatch)
    r = DMSender(db_path=p).send(77, "ornek.com", "s", "b", "v")
    assert r.queue_id == 77


def test_hedef_yok_domain_kept(tmpdb, monkeypatch):
    p, _ = tmpdb
    _no_smtp(monkeypatch)
    r = DMSender(db_path=p).send(1, "ornek.com", "s", "b", "v")
    assert r.domain == "ornek.com"


def test_hedef_yok_variant_logged(tmpdb, monkeypatch):
    p, _ = tmpdb
    _no_smtp(monkeypatch)
    DMSender(db_path=p).send(1, "ornek.com", "s", "b", "v2")
    row = _rows(p)[0]
    assert row[7] == "v2"


# -- TEKRAR ---------------------------------------------------------------------------------

def test_already_sent_tekrar(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _seed_sent(p, 1, "a@ornek.com")
    _no_smtp(monkeypatch)
    r = DMSender(db_path=p).send(1, "ornek.com", "s", "b", "v")
    assert r.status == "TEKRAR"


def test_tekrar_recipient_returned(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _seed_sent(p, 1, "a@ornek.com")
    _no_smtp(monkeypatch)
    r = DMSender(db_path=p).send(1, "ornek.com", "s", "b", "v")
    assert r.recipient == "a@ornek.com"


def test_tekrar_logged(tmpdb, monkeypatch):
    """ON CONFLICT(queue_id,recipient) -> satir guncellenir."""
    p, _ = tmpdb
    _seed(p)
    _seed_sent(p, 1, "a@ornek.com")
    _no_smtp(monkeypatch)
    DMSender(db_path=p).send(1, "ornek.com", "s", "b", "v")
    assert len(_rows(p)) == 1


def test_different_queue_not_tekrar(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _seed_sent(p, 1, "a@ornek.com")
    _no_smtp(monkeypatch)
    r = DMSender(db_path=p).send(2, "ornek.com", "s", "b", "v")
    assert r.status == "YAPILANDIRILMAMIŞ"


def test_yapilandirilmamis_counts_tekrar(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _seed_sent(p, 1, "a@ornek.com", "YAPILANDIRILMAMIŞ")
    _no_smtp(monkeypatch)
    r = DMSender(db_path=p).send(1, "ornek.com", "s", "b", "v")
    assert r.status == "TEKRAR"


def test_hata_status_not_tekrar(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _seed_sent(p, 1, "a@ornek.com", "HATA")
    _no_smtp(monkeypatch)
    r = DMSender(db_path=p).send(1, "ornek.com", "s", "b", "v")
    assert r.status == "YAPILANDIRILMAMIŞ"


def test_dropped_status_not_tekrar(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _seed_sent(p, 1, "a@ornek.com", "DROPPED")
    _no_smtp(monkeypatch)
    r = DMSender(db_path=p).send(1, "ornek.com", "s", "b", "v")
    assert r.status == "YAPILANDIRILMAMIŞ"


# -- MANUAL ---------------------------------------------------------------------------------

def test_manual_when_no_smtp(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _no_smtp(monkeypatch)
    r = DMSender(db_path=p).send(1, "ornek.com", "s", "b", "v")
    assert r.status == "YAPILANDIRILMAMIŞ"


def test_manual_writes_eml(tmpdb, monkeypatch):
    p, outbox = tmpdb
    _seed(p)
    _no_smtp(monkeypatch)
    DMSender(db_path=p).send(1, "ornek.com", "Konu", "Govde", "v")
    files = list(outbox.glob("dm_1_v_*.eml"))
    assert len(files) == 1


def test_manual_eml_has_recipient(tmpdb, monkeypatch):
    p, outbox = tmpdb
    _seed(p)
    _no_smtp(monkeypatch)
    DMSender(db_path=p).send(1, "ornek.com", "K", "G", "v")
    content = list(outbox.glob("*.eml"))[0].read_bytes()
    assert b"a@ornek.com" in content


def test_manual_eml_has_subject(tmpdb, monkeypatch):
    p, outbox = tmpdb
    _seed(p)
    _no_smtp(monkeypatch)
    DMSender(db_path=p).send(1, "ornek.com", "OZEL-KONU", "G", "v")
    content = list(outbox.glob("*.eml"))[0].read_bytes()
    assert b"OZEL-KONU" in content


def test_manual_eml_has_body(tmpdb, monkeypatch):
    p, outbox = tmpdb
    _seed(p)
    _no_smtp(monkeypatch)
    DMSender(db_path=p).send(1, "ornek.com", "K", "OZEL-GOVDE", "v")
    content = list(outbox.glob("*.eml"))[0].read_bytes()
    assert b"OZEL-GOVDE" in content


def test_manual_logged(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _no_smtp(monkeypatch)
    DMSender(db_path=p).send(1, "ornek.com", "K", "G", "v")
    assert len(_rows(p)) == 1


def test_manual_no_smtp_connection(tmpdb, monkeypatch):
    p, outbox = tmpdb
    _seed(p)
    _no_smtp(monkeypatch)
    DMSender(db_path=p).send(1, "ornek.com", "K", "G", "v")
    # .eml uretildi, SMTP denenmedi
    assert list(outbox.glob("*.eml"))


# -- SMTP ---------------------------------------------------------------------------------

def test_smtp_success(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _with_smtp(monkeypatch)
    _no_smtp_lib(monkeypatch)
    r = DMSender(db_path=p).send(1, "ornek.com", "K", "G", "v")
    assert r.status == "GÖNDERİLDİ"


def test_smtp_logged(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _with_smtp(monkeypatch)
    _no_smtp_lib(monkeypatch)
    DMSender(db_path=p).send(1, "ornek.com", "K", "G", "v")
    assert len(_rows(p)) == 1


def test_smtp_no_eml(tmpdb, monkeypatch):
    p, outbox = tmpdb
    _seed(p)
    _with_smtp(monkeypatch)
    _no_smtp_lib(monkeypatch)
    DMSender(db_path=p).send(1, "ornek.com", "K", "G", "v")
    assert list(outbox.glob("*.eml")) == []


def test_smtp_error_fail_closed(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _with_smtp(monkeypatch)

    class _Boom:
        def __init__(self, *a, **k):
            raise ConnectionRefusedError("yok")

    monkeypatch.setattr("answrank.crm.dm_sender.smtplib",
                        type("M", (), {"SMTP": _Boom}))
    r = DMSender(db_path=p).send(1, "ornek.com", "K", "G", "v")
    assert r.status == "HATA"


def test_smtp_error_still_logged(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _with_smtp(monkeypatch)

    class _Boom:
        def __init__(self, *a, **k):
            raise ConnectionRefusedError("yok")

    monkeypatch.setattr("answrank.crm.dm_sender.smtplib",
                        type("M", (), {"SMTP": _Boom}))
    DMSender(db_path=p).send(1, "ornek.com", "K", "G", "v")
    assert len(_rows(p)) == 1


def test_smtp_recipient_returned(tmpdb, monkeypatch):
    p, _ = tmpdb
    _seed(p)
    _with_smtp(monkeypatch)
    _no_smtp_lib(monkeypatch)
    r = DMSender(db_path=p).send(1, "ornek.com", "K", "G", "v")
    assert r.recipient == "a@ornek.com"


# -- recipient_for ---------------------------------------------------------------------------------

def test_recipient_found(tmpdb):
    p, _ = tmpdb
    _seed(p)
    assert DMSender(db_path=p).recipient_for("ornek.com") == \
        "a@ornek.com"


def test_recipient_substring_match(tmpdb):
    p, _ = tmpdb
    _seed(p, url="https://sub.ornek.com/path")
    assert DMSender(db_path=p).recipient_for("ornek.com") == \
        "a@ornek.com"


def test_recipient_no_email(tmpdb):
    p, _ = tmpdb
    db = sqlite3.connect(p)
    db.execute("INSERT INTO prospects(id, brand_name, sector,"
               " city, status, website_url) VALUES (?,?,?,?,?,?)",
               ("p2", "B", "T", "I", "lead", "https://ornek.com"))
    db.commit()
    db.close()
    assert DMSender(db_path=p).recipient_for("ornek.com") is None


def test_recipient_wrong_status(tmpdb):
    p, _ = tmpdb
    _seed(p, status="won")
    assert DMSender(db_path=p).recipient_for("ornek.com") is None


def test_recipient_no_match(tmpdb):
    p, _ = tmpdb
    _seed(p)
    assert DMSender(db_path=p).recipient_for("baska.com") is None


# -- channel ---------------------------------------------------------------------------------

def test_channel_manual(tmpdb, monkeypatch):
    p, _ = tmpdb
    _no_smtp(monkeypatch)
    assert DMSender(db_path=p).channel() == "manual"


def test_channel_smtp(tmpdb, monkeypatch):
    p, _ = tmpdb
    _with_smtp(monkeypatch)
    assert DMSender(db_path=p).channel() == "smtp"


def test_send_result_is_dataclass():
    import dataclasses
    assert dataclasses.is_dataclass(SendResult)
