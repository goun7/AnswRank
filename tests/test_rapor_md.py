"""rapor_md AEO delta-rapor markdown testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: sentetik ölçüm dict'leri.

Gerçek snapshot formatı:
  alt_puanlar = {isim: {"puan": float}}
  siralama = {"sorgular": [{sorgu, position, bulundu}]}
  _fmt float → "70.0"; _fmt_delta → "+15.0"
"""
import sys

import pytest

sys.path.insert(0, ".")
sys.path.insert(0, "izleyici")
sys.path.insert(0, "../../01_unicorn/63-Sester")

from izleyici.delta import rapor_md, hesapla  # noqa: E402


def _olcum(domain="example.com", tarih="2026-10-08", puan=70,
           alt=None, sorgular=None):
    return {
        "domain": domain,
        "tarih": tarih,
        "ai_alinti_puani": puan,
        "alt_puanlar": alt if alt is not None else {
            "net_lik": {"puan": 60}, "derinlik": {"puan": 65}},
        "siralama": {"sorgular": sorgular if sorgular is not None else [
            {"sorgu": "test sorgu", "position": 5, "bulundu": True}]},
    }


def _sorgu(ad, position=5, bulundu=True):
    return {"sorgu": ad, "position": position, "bulundu": bulundu}


@pytest.fixture
def yeni():
    return _olcum()


# -- temel yapı ---------------------------------------------------------------------------

def test_returns_string(yeni):
    assert isinstance(rapor_md(None, yeni), str)


def test_starts_with_heading(yeni):
    assert rapor_md(None, yeni).startswith("# AEO Delta Raporu")


def test_contains_domain(yeni):
    assert "example.com" in rapor_md(None, yeni)


def test_ends_with_newline(yeni):
    assert rapor_md(None, yeni).endswith("\n")


def test_report_length(yeni):
    assert len(rapor_md(None, yeni)) > 100


# -- ilk ölçüm ---------------------------------------------------------------------------

def test_first_measurement_baseline(yeni):
    md = rapor_md(None, yeni)
    assert "ilk ölçüm — taban çizgisi" in md


def test_subsequent_measurement_no_baseline(yeni):
    eski = _olcum(tarih="2026-10-01")
    md = rapor_md(eski, _olcum())
    assert "taban çizgisi" not in md


def test_shows_both_dates(yeni):
    eski = _olcum(tarih="2026-10-01")
    md = rapor_md(eski, _olcum(tarih="2026-10-08"))
    assert "2026-10-01" in md and "2026-10-08" in md


def test_missing_old_date_uses_dash(yeni):
    md = rapor_md(None, yeni)
    assert "—" in md


# -- puan ---------------------------------------------------------------------------

def test_score_line(yeni):
    md = rapor_md(None, yeni)
    assert "**AI Alıntı Puanı:" in md


def test_score_shows_values(yeni):
    eski = _olcum(puan=60)
    md = rapor_md(eski, _olcum(puan=75))
    assert "60.0" in md and "75.0" in md


def test_score_improvement_delta(yeni):
    eski = _olcum(puan=60)
    md = rapor_md(eski, _olcum(puan=75))
    assert "+15.0" in md


def test_score_decline_delta(yeni):
    eski = _olcum(puan=80)
    md = rapor_md(eski, _olcum(puan=70))
    assert "-10.0" in md


def test_score_no_change_delta(yeni):
    eski = _olcum(puan=70)
    md = rapor_md(eski, _olcum(puan=70))
    assert "+0.0" in md


def test_score_decimal(yeni):
    eski = _olcum(puan=60.4)
    md = rapor_md(eski, _olcum(puan=67.9))
    assert "+7.5" in md


def test_first_measurement_score_dash(yeni):
    """eski=None → puan eski '—'."""
    md = rapor_md(None, yeni)
    assert "→ 70.0" in md


# -- alt puanlar tablosu ---------------------------------------------------------------------------

def test_subscore_table_header(yeni):
    md = rapor_md(None, yeni)
    assert "| Alt puan | Önce | Sonra | Δ |" in md


def test_subscore_names_present(yeni):
    md = rapor_md(None, yeni)
    assert "net_lik" in md and "derinlik" in md


def test_subscore_separator(yeni):
    md = rapor_md(None, yeni)
    assert "|---|---|---|---|" in md


def test_subscore_values_formatted(yeni):
    md = rapor_md(None, yeni)
    assert "60.0" in md and "65.0" in md


def test_multiple_subscores(yeni):
    y = _olcum(alt={"a": {"puan": 1}, "b": {"puan": 2}, "c": {"puan": 3}})
    md = rapor_md(None, y)
    assert md.count("\n| ") >= 4


def test_subscore_delta(yeni):
    eski = _olcum(alt={"x": {"puan": 50}})
    md = rapor_md(eski, _olcum(alt={"x": {"puan": 55}}))
    assert "+5.0" in md


def test_subscore_sorted(yeni):
    """alt_puanlar sorted() ile alfabetik gelir."""
    y = _olcum(alt={"zeta": {"puan": 1}, "alfa": {"puan": 2}})
    md = rapor_md(None, y)
    assert md.index("alfa") < md.index("zeta")


# -- sorgu tablosu ---------------------------------------------------------------------------

def test_query_table_header(yeni):
    md = rapor_md(None, yeni)
    assert "| Sorgu | Önce | Sonra | Olay |" in md


def test_query_names_present(yeni):
    y = _olcum(sorgular=[_sorgu("fiyat listesi", 3)])
    md = rapor_md(None, y)
    assert "fiyat listesi" in md


def test_query_position_shown(yeni):
    y = _olcum(sorgular=[_sorgu("q", 7)])
    md = rapor_md(None, y)
    assert "| 7 |" in md


# -- olay işaretleri ---------------------------------------------------------------------------

def test_event_improved(yeni):
    eski = _olcum(sorgular=[_sorgu("q", 8)])
    y = _olcum(sorgular=[_sorgu("q", 3)])
    assert "↑" in rapor_md(eski, y)


def test_event_improvement_rank_delta(yeni):
    eski = _olcum(sorgular=[_sorgu("q", 8)])
    y = _olcum(sorgular=[_sorgu("q", 3)])
    md = rapor_md(eski, y)
    assert "↑ +5 sıra" in md


def test_event_declined(yeni):
    eski = _olcum(sorgular=[_sorgu("q", 3)])
    y = _olcum(sorgular=[_sorgu("q", 8)])
    assert "↓" in rapor_md(eski, y)


def test_event_decline_rank_delta(yeni):
    eski = _olcum(sorgular=[_sorgu("q", 3)])
    y = _olcum(sorgular=[_sorgu("q", 8)])
    md = rapor_md(eski, y)
    assert "↓ -5 sıra" in md


def test_event_entered(yeni):
    eski = _olcum(sorgular=[_sorgu("q", None, False)])
    y = _olcum(sorgular=[_sorgu("q", 5)])
    md = rapor_md(eski, y)
    assert "★" in md and "ilk 10'a girdi" in md


def test_event_left(yeni):
    eski = _olcum(sorgular=[_sorgu("q", 5)])
    y = _olcum(sorgular=[_sorgu("q", None, False)])
    md = rapor_md(eski, y)
    assert "⚠" in md and "ilk 10'dan çıktı" in md


def test_event_none_empty(yeni):
    eski = _olcum(sorgular=[_sorgu("q", 5)])
    y = _olcum(sorgular=[_sorgu("q", 5)])
    md = rapor_md(eski, y)
    assert "| q |" in md


def test_new_query_appears(yeni):
    eski = _olcum(sorgular=[])
    y = _olcum(sorgular=[_sorgu("yeni q", 2)])
    assert "yeni q" in rapor_md(eski, y)


def test_disappeared_query_absent(yeni):
    """Sadece q2 taranır — kaybolan sorgu listede ÇIKMAZ."""
    eski = _olcum(sorgular=[_sorgu("kaybolan", 2)])
    y = _olcum(sorgular=[])
    md = rapor_md(eski, y)
    assert "kaybolan" not in md


def test_multiple_queries(yeni):
    y = _olcum(sorgular=[_sorgu("a", 1), _sorgu("b", 2), _sorgu("c", 3)])
    md = rapor_md(None, y)
    assert md.count("\n| ") >= 4


# -- hesapla entegrasyonu ---------------------------------------------------------------------------

def test_uses_hesapla(yeni):
    d = hesapla(None, yeni)
    assert d["domain"] in rapor_md(None, yeni)


def test_empty_queries(yeni):
    y = _olcum(sorgular=[])
    md = rapor_md(None, y)
    assert "| Sorgu |" in md


def test_missing_subscores(yeni):
    y = _olcum(alt={})
    assert isinstance(rapor_md(None, y), str)


def test_none_old_measurement(yeni):
    assert isinstance(rapor_md(None, yeni), str)


def test_missing_siralama(yeni):
    """siralama anahtarı yok → boş sorgu listesi."""
    y = _olcum()
    del y["siralama"]
    assert isinstance(rapor_md(None, y), str)
