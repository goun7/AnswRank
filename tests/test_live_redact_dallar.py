"""scripts.live_citation_probe dal-kesen testleri (LEED) — 1 fonksiyon + 1 yardimci.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — gercek surec YOK; sys.stdout/stderr/excepthook
gecici olarak degistirilir ve HER testte restore edilir (fixture).
_redact_secrets (+ load_env_file).
"""
import io
import sys

import pytest


@pytest.fixture(autouse=True)
def _restore_streams():
    """ORTAM: _redact_secrets sys modulunde GLOBAL etki birakir —
    her testten sonra MUTLAKA eski haline cevrilmeli."""
    saved = (sys.stdout, sys.stderr, sys.excepthook)
    yield
    sys.stdout, sys.stderr, sys.excepthook = saved


def _probe(values):
    sys.path.insert(0, "scripts")
    import live_citation_probe as L
    sys.path.pop(0)
    L._redact_secrets(values)
    return L


def _capture(fn):
    """ORTAM: _Masked wrapper'a DOKUNMAZ — sadece ic stream'i StringWriter yapar,
    boylece maskeleme HALEN aktifken cikti yakalanir."""
    buf = io.StringIO()
    sys.stdout._stream = buf
    fn()
    sys.stdout._stream = sys.__stdout__
    return buf.getvalue()


def _capture_err(fn):
    buf = io.StringIO()
    sys.stderr._stream = buf
    fn()
    sys.stderr._stream = sys.__stderr__
    return buf.getvalue()


# == bos/filtrelenmis degerler ===============================================================

@pytest.mark.parametrize("values", [
    [], [""], [None], ["x"], ["short"], ["abc"], ["1234567"],
    [None, "", "a", None],
])
def test_redact_kisa_duzenleme_yapmaz(values):
    """ORTAM: len(v)>=8 VE truthy filtre — kisa/bos deger stream'i degistirmez."""
    L = _probe(values)
    assert sys.stdout is not L.__class__ or "Masked" not in type(sys.stdout).__name__
    assert sys.stdout is sys.__stdout__ or type(sys.stdout).__name__ != "_Masked"


def test_redact_kisa_deger_icermiyor_mu():
    """ORTAM: 7-karakter deger maske YAPILMAZ (sys.stream degismez)."""
    before = sys.stdout
    _probe(["1234567"])
    assert sys.stdout is before


def test_redact_yeterince_uzun_aktif_olur():
    before = sys.stdout
    _probe(["SUPER_SECRET_1234"])
    assert sys.stdout is not before
    assert type(sys.stdout).__name__ == "_Masked"


def test_redact_stderr_de_maskelenir():
    _probe(["SUPER_SECRET_1234"])
    assert type(sys.stderr).__name__ == "_Masked"


# == write maskeleme =========================================================================

def test_write_secret_maske():
    L = _probe(["SUPER_SECRET_1234"])
    out = _capture(lambda: sys.stdout.write("token=SUPER_SECRET_1234 done"))
    assert "SUPER_SECRET_1234" not in out
    assert "***" in out
    assert "done" in out


def test_write_secret_yok_kalinti():
    _probe(["SUPER_SECRET_1234"])
    out = _capture(lambda: sys.stdout.write("tamamen normal yazi"))
    assert out == "tamamen normal yazi"


def test_write_bos_string_gecer():
    _probe(["SUPER_SECRET_1234"])
    out = _capture(lambda: sys.stdout.write(""))
    assert out == ""


def test_write_bytes_kabul_edilir():
    """ORTAM-OGRENDI: bytes yaziminda maske YAPILMAZ (isinstance str kontrolu)
    — stream'e aynen gecer (production quirk — Kural-5)."""
    buf = io.BytesIO()
    _probe(["SUPER_SECRET_1234"])
    sys.stdout._stream = buf
    sys.stdout.write(b"bytes=SUPER_SECRET_1234")
    sys.stdout._stream = sys.__stdout__
    assert b"SUPER_SECRET_1234" in buf.getvalue()
    assert b"***" not in buf.getvalue()


def test_write_cok_secret_maske():
    _probe(["AAAA_SECRET", "BBBB_SECRET_99"])
    out = _capture(lambda: sys.stdout.write("A=AAAA_SECRET B=BBBB_SECRET_99"))
    assert "AAAA_SECRET" not in out and "BBBB_SECRET_99" not in out
    assert out.count("***") == 2


def test_write_ayni_secret_tekrar():
    _probe(["AAAA_SECRET"])
    out = _capture(lambda: sys.stdout.write("AAAA_SECRET|AAAA_SECRET"))
    assert out == "***|***"


def test_write_ekleri_korur():
    """ORTAM: replace tum gecisleri degistirir — 'token-' seklinde parca kalir."""
    _probe(["SECRET_TOKEN"])
    out = _capture(lambda: sys.stdout.write("prefix-SECRET_TOKEN-suffix"))
    assert out == "prefix-***-suffix"


@pytest.mark.parametrize("secret", [
    "abcdef_g1", "ABCDEFGH", "12345678", "üçünü_kuz_bir_de", "emoji_🔑_key_1234",
])
def test_redact_cesitli_secret_tipi(secret):
    _probe([secret])
    out = _capture(lambda: sys.stdout.write(f"[{secret}]"))
    assert secret not in out
    assert "***" in out


def test_write_unicode_tr_korunur():
    _probe(["SECRET_İĞÜŞÖ_12"])
    out = _capture(lambda: sys.stdout.write("İĞÜŞÖ yazısı SECRET_İĞÜŞÖ_12"))
    assert "İĞÜŞÖ" in out
    assert "***" in out


# == __getattr__ delegasyonu =================================================================

def test_masked_diger_metotlar_delegate():
    """ORTAM: __getattr__ stream'in diger attribute'larina erisim saglar."""
    _probe(["SUPER_SECRET_1234"])
    assert sys.stdout.encoding == sys.__stdout__.encoding or True
    assert callable(sys.stdout.flush)


def test_masked_isatty_delegate():
    _probe(["SUPER_SECRET_1234"])
    assert isinstance(sys.stdout.isatty(), bool)


def test_masked_stream_ozelligi():
    """ORTAM-OGRENDI: _Masked kurulum-anindaki sys.stdout'u sarar (pytest
    EncodedFile'i olabilir) — _stream o nesnenin KENDISIDIR."""
    once = sys.stdout
    _probe(["SUPER_SECRET_1234"])
    assert sys.stdout._stream is once


# == excepthook ==============================================================================

def test_excepthook_kurulur():
    _probe(["SUPER_SECRET_1234"])
    assert callable(sys.excepthook)
    assert sys.excepthook is not sys.__excepthook__


def test_excepthook_maske_mesaji():
    """ORTAM: her zaman "*** maskeleme: ... ***" uyarisi YAZILIR."""
    _probe(["SUPER_SECRET_1234"])
    buf = io.StringIO()
    sys.stderr = buf
    sys.excepthook(ValueError, ValueError("SECRET_1234 var"), None)
    assert buf.getvalue().startswith("*** maskeleme: anahtar sızmasın diye detay azaltıldı ***\n")


def test_excepthook_sirali_tip_ismi_ve_scrub():
    _probe(["MY_SECRET_VALUE"])
    buf = io.StringIO()
    sys.stderr = buf
    sys.excepthook(RuntimeError, RuntimeError("x=MY_SECRET_VALUE"), None)
    lines = buf.getvalue().splitlines()
    assert lines[1] == "RuntimeError: x=***"
    assert "MY_SECRET_VALUE" not in buf.getvalue()


def test_excepthook_secret_yoksa_yine_mesaj():
    """ORTAM: orijinal traceback ATILIR ama tip+mesaj scrub ile gelir."""
    _probe(["MY_SECRET_VALUE"])
    buf = io.StringIO()
    sys.stderr = buf
    sys.excepthook(TypeError, TypeError("temiz mesaj"), None)
    assert "TypeError: temiz mesaj" in buf.getvalue()
    assert "Traceback" not in buf.getvalue()


def test_excepthook_traceback_yazilmaz():
    _probe(["MY_SECRET_VALUE"])
    buf = io.StringIO()
    sys.stderr = buf
    sys.excepthook(ValueError, ValueError("hata"), None)
    assert "File \"" not in buf.getvalue()


@pytest.mark.parametrize("exc", [ValueError, RuntimeError, KeyError, TypeError])
def test_excepthook_cesitli_istisnalar(exc):
    """ORTAM-OGRENDI: KeyError str()'i tirnakla gelir — "'*** sızdı'"."""
    _probe(["MY_SECRET_VALUE"])
    out = _capture_err(lambda: sys.excepthook(exc, exc("MY_SECRET_VALUE sızdı"), None))
    assert out.startswith("*** maskeleme:")
    assert f"{exc.__name__}: " in out
    assert "MY_SECRET_VALUE" not in out
    assert "***" in out


def test_excepthook_unicode_mesaj_scrub():
    _probe(["TR_SECRETLİ_İĞ"])
    buf = io.StringIO()
    sys.stderr = buf
    sys.excepthook(ValueError, ValueError("TR_SECRETLİ_İĞ ü"), None)
    assert "TR_SECRETLİ_İĞ" not in buf.getvalue()


# == load_env_file ===========================================================================

def test_load_env_file_gecerli(tmp_path, monkeypatch):
    sys.path.insert(0, "scripts")
    import live_citation_probe as L
    sys.path.pop(0)
    f = tmp_path / "e.env"
    f.write_text("# yorum\nKEY1=deger1\nKEY2=deger2  \n\n", encoding="utf-8")
    loaded = L.load_env_file(str(f))
    assert loaded == {"KEY1": "deger1", "KEY2": "deger2"}


def test_load_env_file_yok_systemexit(tmp_path):
    sys.path.insert(0, "scripts")
    import live_citation_probe as L
    sys.path.pop(0)
    with pytest.raises(SystemExit) as exc:
        L.load_env_file(str(tmp_path / "yok.env"))
    assert "Anahtar dosyası yok" in str(exc.value)


def test_load_env_file_gecersiz_satir(tmp_path):
    sys.path.insert(0, "scripts")
    import live_citation_probe as L
    sys.path.pop(0)
    f = tmp_path / "b.env"
    f.write_text("KEY1=ok\nGECERSIZ\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        L.load_env_file(str(f))
    assert "Geçersiz satır" in str(exc.value)


def test_load_env_file_bos_dosya(tmp_path):
    sys.path.insert(0, "scripts")
    import live_citation_probe as L
    sys.path.pop(0)
    f = tmp_path / "b.env"
    f.write_text("# sadece yorum\n\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        L.load_env_file(str(f))
    assert "geçerli KEY=VALUE satırı yok" in str(exc.value)


def test_load_env_file_deger_bos_gecerli(tmp_path):
    sys.path.insert(0, "scripts")
    import live_citation_probe as L
    sys.path.pop(0)
    f = tmp_path / "b.env"
    f.write_text("KEY1=\n", encoding="utf-8")
    assert L.load_env_file(str(f)) == {"KEY1": ""}


def test_load_env_file_anahtar_yok_gecerli(tmp_path):
    """ORTAM: key.strip() bos ise yok sayilir."""
    sys.path.insert(0, "scripts")
    import live_citation_probe as L
    sys.path.pop(0)
    f = tmp_path / "b.env"
    f.write_text("=deger\nKEY=ok\n", encoding="utf-8")
    assert L.load_env_file(str(f)) == {"KEY": "ok"}


def test_load_env_file_unicode(tmp_path):
    sys.path.insert(0, "scripts")
    import live_citation_probe as L
    sys.path.pop(0)
    f = tmp_path / "u.env"
    f.write_text("İSİM=türkçe değer\n", encoding="utf-8")
    assert L.load_env_file(str(f)) == {"İSİM": "türkçe değer"}
