"""answrank.probe.miniprobe dal-kesen testleri (LEED) — 1 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — ag/fetch YOK, sadece classmethod fabrikasi.
MiniProbe._rejected.
"""
import pytest

from answrank.probe.miniprobe import MiniProbe, MiniProbeResult, _UNMEASURED


# == _rejected ==============================================================================

@pytest.mark.parametrize("host, reason", [
    ("a.example", "WAF 403"),
    ("b.example", "Cloudflare challenge"),
    ("1.2.3.4", "timeout"),
    ("x.example", "bağlantı reddedildi"),
])
def test_rejected_temel_alanlar(host, reason):
    r = MiniProbe._rejected(host, reason)
    assert isinstance(r, MiniProbeResult)
    assert r.domain == host
    assert r.bots_line == reason
    assert r.robots_line == f"{_UNMEASURED} (taranmadı)"
    assert r.llms_line == f"{_UNMEASURED} (taranmadı)"


def test_rejected_verdict_giris_reddedildi():
    r = MiniProbe._rejected("a.example", "x")
    assert r.verdict == "GİRİŞ REDDEDİLDİ"


def test_rejected_measured_false():
    """ORTAM: measured=False — bu bir OLCUM degil, erisim-reddi kaydidir."""
    assert MiniProbe._rejected("a.example", "x").measured is False


def test_rejected_probed_sifir():
    assert MiniProbe._rejected("a.example", "x").probed == 0


def test_rejected_blocked_bots_bos():
    assert MiniProbe._rejected("a.example", "x").blocked_bots == []


def test_rejected_robots_ve_llms_ayni_metin():
    r = MiniProbe._rejected("a.example", "x")
    assert r.robots_line == r.llms_line


def test_rejected_unmeasured_sabiti():
    assert _UNMEASURED == "ÖLÇÜLEMEDİ"
    assert "(taranmadı)" in MiniProbe._rejected("a.example", "x").robots_line


@pytest.mark.parametrize("reason", ["", "WAF 403", "çok uzun " * 30,
                                    "emoji 🔥 reddi", "TR karakterli: İĞÜŞÖ"])
def test_rejected_reason_korunur(reason):
    """ORTAM: reason bots_line'a aynen yazilir — hicbir normalizasyon YOK."""
    assert MiniProbe._rejected("a.example", reason).bots_line == reason


@pytest.mark.parametrize("host", ["", "a.example", "https://b.example",
                                  "İSTANBUL.example", "sub.domain.example",
                                  "8.8.8.8", "[::1]"])
def test_rejected_host_korunur(host):
    """ORTAM: host domain'e aynen yazilir; scheme/unicode normalizasyon YOK."""
    assert MiniProbe._rejected(host, "x").domain == host


def test_rejected_optional_alanlar_none():
    r = MiniProbe._rejected("a.example", "x")
    assert r.robots_status is None
    assert r.llms_status is None


def test_rejected_bot_statuses_bos():
    assert MiniProbe._rejected("a.example", "x").bot_statuses == {}


def test_rejected_classmethod_siniftan_cagrilir():
    """ORTAM: @classmethod — instance'siz cagrilabilir."""
    assert MiniProbe._rejected("a.example", "x").verdict == "GİRİŞ REDDEDİLDİ"


def test_rejected_ile_olcum_farkli():
    """ORTAM-ANATOMI: olcum sonucu measured=True iken _rejected hep False."""
    ok = MiniProbeResult(domain="a.example", robots_line="İZİNLİ",
                         llms_line="VAR", bots_line="3/3", blocked_bots=[],
                         probed=3, verdict="TEMİZ", measured=True)
    red = MiniProbe._rejected("a.example", "WAF")
    assert ok.measured is True and red.measured is False
    assert ok.verdict != red.verdict


def test_rejected_db_kaydi_olcmeme_garantisi():
    """ORTAM-OGRENDI: 'GİRİX REDDEDİLDİ' yerine 'GİRİŞ REDDEDİLDİ' —
    save_miniprobe_leads bu verdict'i atlar (E7 huni kapisi)."""
    assert MiniProbe._rejected("a.example", "x").verdict != "GİRİX REDDEDİLDİ"


@pytest.mark.parametrize("n", range(5))
def test_rejected_tekrar_uretilebilir(n):
    """Her cagri ayni yapida yeni nesne doner (state YOK)."""
    a = MiniProbe._rejected("a.example", "WAF")
    b = MiniProbe._rejected("a.example", "WAF")
    assert a.model_dump() == b.model_dump()
    assert a is not b


def test_rejected_model_dump_serilestirme():
    r = MiniProbe._rejected("a.example", "WAF 403")
    d = r.model_dump()
    assert d["domain"] == "a.example"
    assert d["verdict"] == "GİRİŞ REDDEDİLDİ"
    assert d["measured"] is False
    assert d["probed"] == 0
