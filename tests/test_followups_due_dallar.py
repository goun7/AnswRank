"""crm.dm_sender.followups_due dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: tmp_path SQLite + sentetik kayıtlar.
"""
import sqlite3
from datetime import date, timedelta

import pytest

from answrank.crm.dm_sender import DMSender


def _db(tmp_path, rows):
    """dm_send_log tablosu + kayıtlar."""
    path = str(tmp_path / "test.db")
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE dm_send_log ("
        "queue_id TEXT, domain TEXT, recipient TEXT, "
        "sent_at TEXT, variant_key TEXT, status TEXT)")
    for r in rows:
        db.execute(
            "INSERT INTO dm_send_log VALUES (?,?,?,?,?,?)", r)
    db.commit()
    db.close()
    return path


def _row(qid, days_ago, status="GÖNDERİLDİ", variant="variant_1",
          domain="a.com", recipient="x@a.com"):
    sent = (date.today() - timedelta(days=days_ago)).isoformat()
    return (qid, domain, recipient, sent, variant, status)


@pytest.fixture
def sender(tmp_path):
    return DMSender(_db(tmp_path, []))


# -- temel ---------------------------------------------------------------------------------

def test_empty_returns_list(sender):
    assert sender.followups_due() == []


def test_returns_list_of_dicts(tmp_path):
    rows = [_row("q1", 3)]
    s = DMSender(_db(tmp_path, rows))
    due = s.followups_due()
    assert isinstance(due, list)
    assert all(isinstance(d, dict) for d in due)


# -- 3 gun esigi ---------------------------------------------------------------------------------

def test_day_3_included(tmp_path):
    s = DMSender(_db(tmp_path, [_row("q1", 3)]))
    assert len(s.followups_due()) == 1


def test_day_3_key(tmp_path):
    s = DMSender(_db(tmp_path, [_row("q1", 3)]))
    assert s.followups_due()[0]["key"] == "followup_day_3"


def test_day_3_gun(tmp_path):
    s = DMSender(_db(tmp_path, [_row("q1", 3)]))
    assert s.followups_due()[0]["gun"] == 3


def test_day_4_still_3(tmp_path):
    """3-7 arasi hep gun=3."""
    s = DMSender(_db(tmp_path, [_row("q1", 5)]))
    assert s.followups_due()[0]["gun"] == 3


def test_day_2_excluded(tmp_path):
    s = DMSender(_db(tmp_path, [_row("q1", 2)]))
    assert s.followups_due() == []


def test_day_0_excluded(tmp_path):
    s = DMSender(_db(tmp_path, [_row("q1", 0)]))
    assert s.followups_due() == []


# -- 7 gun esigi ---------------------------------------------------------------------------------

def test_day_7_included(tmp_path):
    s = DMSender(_db(tmp_path, [_row("q1", 7)]))
    assert len(s.followups_due()) == 1


def test_day_7_key(tmp_path):
    s = DMSender(_db(tmp_path, [_row("q1", 7)]))
    assert s.followups_due()[0]["key"] == "followup_day_7"


def test_day_7_gun(tmp_path):
    s = DMSender(_db(tmp_path, [_row("q1", 7)]))
    assert s.followups_due()[0]["gun"] == 7


def test_day_30_still_7(tmp_path):
    s = DMSender(_db(tmp_path, [_row("q1", 30)]))
    assert s.followups_due()[0]["gun"] == 7


# -- alanlar ---------------------------------------------------------------------------------

def test_queue_id_preserved(tmp_path):
    s = DMSender(_db(tmp_path, [_row("my-q", 7)]))
    assert s.followups_due()[0]["queue_id"] == "my-q"


def test_domain_preserved(tmp_path):
    s = DMSender(_db(tmp_path, [_row("q1", 7, domain="ornek.com")]))
    assert s.followups_due()[0]["domain"] == "ornek.com"


def test_recipient_preserved(tmp_path):
    s = DMSender(_db(tmp_path, [_row("q1", 7, recipient="kişi@b.com")]))
    assert s.followups_due()[0]["recipient"] == "kişi@b.com"


# -- durum filtresi ---------------------------------------------------------------------------------

def test_only_sent_and_unconfigured(tmp_path):
    """status IN ('GÖNDERİLDİ','YAPILANDIRILMAMIŞ')."""
    rows = [_row("g1", 7), _row("y1", 7, status="YAPILANDIRILMAMIŞ"),
            _row("h1", 7, status="BASARISIZ"),
            _row("h2", 7, status="GÖNDERİLDİ_BEKLEMEDE")]
    s = DMSender(_db(tmp_path, rows))
    assert len(s.followups_due()) == 2


def test_basarisiz_excluded(tmp_path):
    s = DMSender(_db(tmp_path, [_row("q1", 7, status="BASARISIZ")]))
    assert s.followups_due() == []


def test_unconfigured_included(tmp_path):
    s = DMSender(_db(tmp_path,
                     [_row("q1", 3, status="YAPILANDIRILMAMIŞ")]))
    assert len(s.followups_due()) == 1


# -- variant filtresi ---------------------------------------------------------------------------------

def test_other_variant_excluded(tmp_path):
    s = DMSender(_db(tmp_path,
                     [_row("q1", 7, variant="variant_2")]))
    assert s.followups_due() == []


def test_variant_1_only(tmp_path):
    rows = [_row("a", 7, variant="variant_1"),
            _row("b", 7, variant="variant_2"),
            _row("c", 7, variant="test")]
    s = DMSender(_db(tmp_path, rows))
    assert len(s.followups_due()) == 1


# -- coklu + hata dayanikliligi ---------------------------------------------------------------------------------

def test_multiple_due(tmp_path):
    rows = [_row("a", 3), _row("b", 7), _row("c", 10)]
    s = DMSender(_db(tmp_path, rows))
    assert len(s.followups_due()) == 3


def test_sorted_by_insertion(tmp_path):
    rows = [_row("a", 10), _row("b", 3)]
    s = DMSender(_db(tmp_path, rows))
    keys = [d["key"] for d in s.followups_due()]
    assert keys[0] == "followup_day_7"


def test_bad_date_skipped(tmp_path):
    rows = [_row("q1", 3), ("q2", "a.com", "x", "gecersiz", "variant_1",
                            "GÖNDERİLDİ")]
    s = DMSender(_db(tmp_path, rows))
    assert len(s.followups_due()) == 1


def test_null_date_skipped(tmp_path):
    rows = [_row("q1", 3), ("q2", "a.com", "x", None, "variant_1",
                            "GÖNDERİLDİ")]
    s = DMSender(_db(tmp_path, rows))
    assert len(s.followups_due()) == 1


def test_datetime_format_ok(tmp_path):
    """sent_at ISO8601 tam zaman damgasi (ilk 10 karakter)."""
    from datetime import datetime
    sent = (datetime.now() - timedelta(days=7)).isoformat()
    rows = [("q1", "a.com", "x", sent, "variant_1", "GÖNDERİLDİ")]
    s = DMSender(_db(tmp_path, rows))
    assert len(s.followups_due()) == 1
