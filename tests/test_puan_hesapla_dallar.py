"""uret_rapor.puan_hesapla dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (dis cagri YOK).
"""
import copy
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uret_rapor as U  # noqa: E402

_ROBOTS = {"robots.txt": {"var": True}, "sitemap.xml": {"var": True}}
_YAP = {"schema_org": True, "open_graph": True, "meta_aciklama": True,
        "h1_sayisi": 2, "title_uzunlugu": 50, "lang": "tr"}
_TEMEL = {"erisilebilir": True, "https_var": True}


def _all():
    return (copy.deepcopy(_TEMEL), copy.deepcopy(_ROBOTS),
            copy.deepcopy(_YAP))


# -- mukemmel ---------------------------------------------------------------------------------

def test_all_checks_100():
    assert U.puan_hesapla(*_all()) == 100


def test_returns_int():
    assert isinstance(U.puan_hesapla(*_all()), int)


def test_min_cap_100():
    """min(100, p)."""
    t, r, y = _all()
    y["extra"] = True
    assert U.puan_hesapla(t, r, y) == 100


# -- hicbiri yok ---------------------------------------------------------------------------------

def test_zero_when_nothing():
    assert U.puan_hesapla({}, _ROBOTS_NO(), _YAP_NO()) == 0


def _ROBOTS_NO():
    return {"robots.txt": {"var": False}, "sitemap.xml": {"var": False}}


def _YAP_NO():
    return {"schema_org": False, "open_graph": False, "meta_aciklama": False,
            "h1_sayisi": 0, "title_uzunlugu": 0, "lang": "belirtilmemis"}


def test_zero_empty_dicts():
    """nested key yok -> KeyError (get degil)."""
    with pytest.raises(KeyError):
        U.puan_hesapla({},
                       {"robots.txt": {}, "sitemap.xml": {}},
                       {})


# -- bireysel-katklar ---------------------------------------------------------------------------------

def test_erisilebilir_10():
    t, r, y = _all(); _zero(t, r, y)
    t["erisilebilir"] = True
    assert U.puan_hesapla(t, r, y) == 10


def test_https_var_10():
    t, r, y = _all(); _zero(t, r, y)
    t["https_var"] = True
    assert U.puan_hesapla(t, r, y) == 10


def test_robots_txt_15():
    t, r, y = _all(); _zero(t, r, y)
    r["robots.txt"]["var"] = True
    assert U.puan_hesapla(t, r, y) == 15


def test_sitemap_15():
    t, r, y = _all(); _zero(t, r, y)
    r["sitemap.xml"]["var"] = True
    assert U.puan_hesapla(t, r, y) == 15


def test_schema_org_15():
    t, r, y = _all(); _zero(t, r, y)
    y["schema_org"] = True
    assert U.puan_hesapla(t, r, y) == 15


def test_open_graph_10():
    t, r, y = _all(); _zero(t, r, y)
    y["open_graph"] = True
    assert U.puan_hesapla(t, r, y) == 10


def test_meta_aciklama_10():
    t, r, y = _all(); _zero(t, r, y)
    y["meta_aciklama"] = True
    assert U.puan_hesapla(t, r, y) == 10


def test_h1_5():
    t, r, y = _all(); _zero(t, r, y)
    y["h1_sayisi"] = 1
    assert U.puan_hesapla(t, r, y) == 5


def test_title_30_5():
    t, r, y = _all(); _zero(t, r, y)
    y["title_uzunlugu"] = 30
    assert U.puan_hesapla(t, r, y) == 5


def test_lang_5():
    t, r, y = _all(); _zero(t, r, y)
    y["lang"] = "en"
    assert U.puan_hesapla(t, r, y) == 5


def _zero(t, r, y):
    t["erisilebilir"] = False
    t["https_var"] = False
    r["robots.txt"]["var"] = False
    r["sitemap.xml"]["var"] = False
    y["schema_org"] = False
    y["open_graph"] = False
    y["meta_aciklama"] = False
    y["h1_sayisi"] = 0
    y["title_uzunlugu"] = 0
    y["lang"] = "belirtilmemis"


# -- esikler ---------------------------------------------------------------------------------

def test_h1_zero_no_points():
    t, r, y = _all(); _zero(t, r, y)
    y["h1_sayisi"] = 0
    assert U.puan_hesapla(t, r, y) == 0


def test_title_below_30_no_points():
    t, r, y = _all(); _zero(t, r, y)
    y["title_uzunlugu"] = 29
    assert U.puan_hesapla(t, r, y) == 0


def test_title_exactly_30_points():
    t, r, y = _all(); _zero(t, r, y)
    y["title_uzunlugu"] = 30
    assert U.puan_hesapla(t, r, y) == 5


def test_lang_belirtilmemis_no_points():
    t, r, y = _all(); _zero(t, r, y)
    y["lang"] = "belirtilmemis"
    assert U.puan_hesapla(t, r, y) == 0


def test_lang_none_no_points():
    """yap.get('lang') None → 'belirtilmemis' degil → +5?"""
    t, r, y = _all(); _zero(t, r, y)
    y["lang"] = None
    assert U.puan_hesapla(t, r, y) == 5


def test_lang_missing_key_no_points():
    """get('lang') → None → not in ('belirtilmemis',) → +5?"""
    t, r, y = _all(); _zero(t, r, y)
    del y["lang"]
    assert U.puan_hesapla(t, r, y) == 5


# -- toplam ---------------------------------------------------------------------------------

def test_partial_30():
    t, r, y = _all(); _zero(t, r, y)
    t["erisilebilir"] = True
    t["https_var"] = True
    r["robots.txt"]["var"] = True
    assert U.puan_hesapla(t, r, y) == 35


def test_minus_5_from_100():
    t, r, y = _all()
    y["lang"] = "belirtilmemis"
    assert U.puan_hesapla(t, r, y) == 95


def test_yap_only_45():
    t, r, y = _all(); _zero(t, r, y)
    y["schema_org"] = True
    y["open_graph"] = True
    y["meta_aciklama"] = True
    assert U.puan_hesapla(t, r, y) == 35


def test_robots_only_30():
    t, r, y = _all(); _zero(t, r, y)
    r["robots.txt"]["var"] = True
    r["sitemap.xml"]["var"] = True
    assert U.puan_hesapla(t, r, y) == 30


# -- truthiness ---------------------------------------------------------------------------------

def test_erisilebilir_truthy():
    t, r, y = _all(); _zero(t, r, y)
    t["erisilebilir"] = 1
    assert U.puan_hesapla(t, r, y) == 10


def test_https_var_empty_string_no_points():
    t, r, y = _all(); _zero(t, r, y)
    t["https_var"] = ""
    assert U.puan_hesapla(t, r, y) == 0


def test_schema_org_none_no_points():
    t, r, y = _all(); _zero(t, r, y)
    y["schema_org"] = None
    assert U.puan_hesapla(t, r, y) == 0


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable():
    a = U.puan_hesapla(*_all())
    b = U.puan_hesapla(*_all())
    assert a == b == 100


def test_independent_calls():
    t, r, y = _all()
    U.puan_hesapla(t, r, y)
    assert U.puan_hesapla(t, r, y) == 100
