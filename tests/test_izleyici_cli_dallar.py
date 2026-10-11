"""izleyici.cli dal-kesen testleri (LEED) — 5 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — gercek ag/dosya YOK; takip/kosu/delta modulleri
SimpleNamespace ile STUBLA, dosyalar tmp_path'te.
_cmd_add + _cmd_list + _cmd_remove + _cmd_run + _cmd_delta.
"""
import sys
from types import SimpleNamespace

import pytest

from izleyici import cli


def _mod(**attrs):
    m = SimpleNamespace(**attrs)
    return m


@pytest.fixture
def fs(monkeypatch):
    """ORTAM: cli'nin import ettigi 3 modulu saf-in-memory stub'lar."""
    state = {"takip": {}, "snaplar": [], "son_iki": (None, None), "rapor": "# delta\n"}

    def _ekle(domain, sorgular=None, yol=None):
        state["takip"][domain] = {"sorgular": sorgular or [],
                                  "eklenme": "2026-01-01"}
        return state["takip"]

    def _cikar(domain, yol=None):
        return state["takip"].pop(domain, None) is not None

    mods = {
        "takip": _mod(
            ekle=_ekle,
            cikar=_cikar,
            yukle=lambda yol=None: dict(state["takip"]),
            normalle=lambda d: d.strip().lower().rstrip("/"),
            kapsamda=lambda yol, kok: yol,
            HERE="/repo",
            IZLE_KOK="/repo/olcumler/izleyici",
        ),
        "kosu": _mod(
            kos=lambda domainler=None, olc_fn=None, api_key=None,
                  sorgular_fn=None, kaydet_fn=None: list(state["snaplar"]),
            son_iki_snapshot=lambda domain: state["son_iki"],
        ),
        "delta": _mod(rapor_md=lambda eski, yeni: state["rapor"]),
    }
    for name, mod in mods.items():
        monkeypatch.setattr(cli, name, mod)
    return state


def _add(domain, sorgular=None):
    return cli._cmd_add(SimpleNamespace(domain=domain, sorgular=sorgular))


# == _cmd_add =================================================================================

def test_add_basit(fs, capsys):
    rc = _add("A.example")
    assert rc == 0
    assert "takip eklendi: a.example (0 sorgu)" in capsys.readouterr().out
    assert "A.example" in fs["takip"]


def test_add_normalle_gosterim(fs, capsys):
    rc = _add("HTTPS://B.example/")
    assert rc == 0
    assert "b.example" in capsys.readouterr().out


def test_add_sorgu_dosyasi(fs, tmp_path, monkeypatch, capsys):
    f = tmp_path / "s.txt"
    f.write_text("  dişçi \n\n implant \n", encoding="utf-8")
    cli.takip.kapsamda = lambda yol, kok: str(f)
    rc = _add("A.example", str(f))
    assert rc == 0
    assert fs["takip"]["A.example"]["sorgular"] == ["dişçi", "implant"]
    assert "(2 sorgu)" in capsys.readouterr().out


def test_add_sorgu_dosyasi_bos(fs, tmp_path):
    f = tmp_path / "b.txt"
    f.write_text("\n  \n", encoding="utf-8")
    cli.takip.kapsamda = lambda yol, kok: str(f)
    rc = _add("A.example", str(f))
    assert rc == 0
    assert fs["takip"]["A.example"]["sorgular"] == []


def test_add_path_traversal_reddeder(fs, capsys, monkeypatch):
    """ORTAM: kapsamda ValueError -> stderr 'hata:' + rc=1 (güvenlik kapısı)."""

    def _dis(yol, kok):
        raise ValueError("proje kökü dışında: %s" % yol)

    monkeypatch.setattr(cli.takip, "kapsamda", _dis)
    rc = _add("A.example", "/etc/passwd")
    assert rc == 1
    err = capsys.readouterr().err
    assert err.startswith("hata: ")
    assert "proje kökü dışında" in err
    assert fs["takip"] == {}


def test_add_ekle_valueerror(fs, capsys, monkeypatch):
    """ORTAM: takip.ekle ValueError (geçersiz domain) -> hata + rc=1."""

    def _boom(domain, sorgular=None, yol=None):
        raise ValueError("geçersiz alan adı")

    monkeypatch.setattr(cli.takip, "ekle", _boom)
    rc = _add("!!")
    assert rc == 1
    assert "geçersiz alan adı" in capsys.readouterr().err


def test_add_sorgular_none_ekle_none_gecer(fs):
    """ORTAM: sorgular bos -> takip.ekle(domain, None) (falsy None gecer)."""
    rc = _add("A.example", None)
    assert rc == 0
    assert "A.example" in fs["takip"]


def test_add_unicode_domain(fs, capsys):
    rc = _add("İĞÜŞÖ.example")
    assert rc == 0
    out = capsys.readouterr().out
    assert "i̇ğüşö.example" in out


# == _cmd_list ================================================================================

def test_list_bos(fs, capsys):
    rc = cli._cmd_list(SimpleNamespace())
    assert rc == 0
    assert "takip listesi boş" in capsys.readouterr().out


def test_list_dolu(fs, capsys):
    fs["takip"] = {
        "b.example": {"sorgular": ["x", "y"], "eklenme": "2026-01-02"},
        "a.example": {"sorgular": [], "eklenme": "2026-01-01"},
    }
    rc = cli._cmd_list(SimpleNamespace())
    assert rc == 0
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if l]
    assert lines[0].startswith("a.example")
    assert lines[1].startswith("b.example")
    assert "sorgu=2" in lines[1]
    assert "eklenme=2026-01-02" in lines[1]


def test_list_sirali(fs, capsys):
    """ORTAM: sorted(t.items()) — alfabetik sira."""
    fs["takip"] = {"z.example": {"sorgular": []}, "a.example": {"sorgular": []}}
    cli._cmd_list(SimpleNamespace())
    out = capsys.readouterr().out
    assert out.index("a.example") < out.index("z.example")


def test_list_eklenme_yoksa_soru_isareti(fs, capsys):
    fs["takip"] = {"a.example": {"sorgular": []}}
    cli._cmd_list(SimpleNamespace())
    assert "eklenme=?" in capsys.readouterr().out


# == _cmd_remove ==============================================================================

def test_remove_var(fs, capsys):
    fs["takip"] = {"a.example": {"sorgular": []}}
    rc = cli._cmd_remove(SimpleNamespace(domain="a.example"))
    assert rc == 0
    assert capsys.readouterr().out.strip() == "çıkarıldı"
    assert fs["takip"] == {}


def test_remove_yok(fs, capsys):
    rc = cli._cmd_remove(SimpleNamespace(domain="yok.example"))
    assert rc == 1
    assert capsys.readouterr().out.strip() == "takip listesinde değil"


def test_remove_unicode(fs, capsys):
    fs["takip"] = {"i̇ğ.example": {"sorgular": []}}
    rc = cli._cmd_remove(SimpleNamespace(domain="İĞ.example"))
    assert rc == 1
    fs["takip"] = {"i̇ğ.example": {"sorgular": []}}
    rc = cli._cmd_remove(SimpleNamespace(domain="i̇ğ.example"))
    assert rc == 0


# == _cmd_run =================================================================================

def test_run_api_key_yok(fs, capsys, monkeypatch):
    monkeypatch.setattr(sys, "modules", {**sys.modules})
    import types as _t
    motor = _t.SimpleNamespace(env_oku=lambda: {},
                               ENV_DOSYASI=".env")
    monkeypatch.setitem(sys.modules, "ai_gorunurluk", motor)
    rc = cli._cmd_run(SimpleNamespace(domain="a.example"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "SERPER_API_KEY bulunamadı" in err
    assert ".env" in err


def test_run_basarili(fs, capsys, monkeypatch):
    import types as _t
    motor = _t.SimpleNamespace(env_oku=lambda: {"SERPER_API_KEY": "k"},
                               ENV_DOSYASI=".env")
    monkeypatch.setitem(sys.modules, "ai_gorunurluk", motor)
    fs["snaplar"] = [{"domain": "a.example", "puan": 82.5, "snapshot": "s1"},
                     {"domain": "b.example", "puan": 71, "snapshot": "s2"}]
    rc = cli._cmd_run(SimpleNamespace(domain="a.example"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "a.example  puan=82.5  snapshot=s1" in out
    assert "b.example  puan=71  snapshot=s2" in out


def test_run_domain_none_hepsi(fs, monkeypatch):
    """ORTAM: domain yoksa kosu.kos(domainler=None) — takipli HEPSI."""
    import types as _t
    gorulen = {}
    motor = _t.SimpleNamespace(env_oku=lambda: {"SERPER_API_KEY": "k"},
                               ENV_DOSYASI=".env")
    monkeypatch.setitem(sys.modules, "ai_gorunurluk", motor)
    def _kayit(domainler=None, **kw):
        gorulen["domainler"] = domainler
        return []

    cli.kosu.kos = _kayit
    cli._cmd_run(SimpleNamespace(domain=None))
    assert gorulen["domainler"] is None


def test_run_domain_verildi(fs, monkeypatch):
    import types as _t
    gorulen = {}
    motor = _t.SimpleNamespace(env_oku=lambda: {"SERPER_API_KEY": "k"},
                               ENV_DOSYASI=".env")
    monkeypatch.setitem(sys.modules, "ai_gorunurluk", motor)
    def _kayit(domainler=None, **kw):
        gorulen["domainler"] = domainler
        return []

    cli.kosu.kos = _kayit
    cli._cmd_run(SimpleNamespace(domain="a.example"))
    assert gorulen["domainler"] == ["a.example"]


def test_run_api_key_bos_string(fs, capsys, monkeypatch):
    """ORTAM: api_key '' -> falsy -> hata (Kural-5 fail-closed)."""
    import types as _t
    motor = _t.SimpleNamespace(env_oku=lambda: {"SERPER_API_KEY": ""},
                               ENV_DOSYASI=".env")
    monkeypatch.setitem(sys.modules, "ai_gorunurluk", motor)
    rc = cli._cmd_run(SimpleNamespace(domain="a.example"))
    assert rc == 1


def test_run_snap_bos(fs, capsys, monkeypatch):
    import types as _t
    motor = _t.SimpleNamespace(env_oku=lambda: {"SERPER_API_KEY": "k"},
                               ENV_DOSYASI=".env")
    monkeypatch.setitem(sys.modules, "ai_gorunurluk", motor)
    fs["snaplar"] = []
    rc = cli._cmd_run(SimpleNamespace(domain="a.example"))
    assert rc == 0
    assert capsys.readouterr().out == ""


# == _cmd_delta ===============================================================================

def test_delta_yetersiz_snapshot(fs, capsys):
    fs["son_iki"] = (None, None)
    rc = cli._cmd_delta(SimpleNamespace(domain="a.example", dosya=False))
    assert rc == 1
    assert "≥2 snapshot gerekli" in capsys.readouterr().err


def test_delta_stdout(fs, capsys):
    fs["son_iki"] = ({"puan": 70}, {"puan": 75, "tarih": "2026-01-02"})
    fs["rapor"] = "# RAPOR\nfark var\n"
    rc = cli._cmd_delta(SimpleNamespace(domain="a.example", dosya=False))
    assert rc == 0
    assert capsys.readouterr().out == "# RAPOR\nfark var\n"


def test_delta_dosya_yazar(fs, tmp_path, capsys, monkeypatch):
    fs["son_iki"] = ({"puan": 70}, {"puan": 75, "tarih": "2026-01-02"})
    fs["rapor"] = "# RAPOR\n"
    kok = tmp_path / "izleyici"
    monkeypatch.setattr(cli.takip, "IZLE_KOK", str(kok))
    monkeypatch.setattr(cli.takip, "normalle", lambda d: "a.example")
    rc = cli._cmd_delta(SimpleNamespace(domain="A.example", dosya=True))
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("a.example-2026-01-02-delta.md")
    with open(out, encoding="utf-8") as f:
        assert f.read() == "# RAPOR\n"


def test_delta_dosya_tarih_yoksa_son(fs, tmp_path, capsys, monkeypatch):
    """ORTAM: yeni.get('tarih','son') — tarih yoksa 'son' kullanilir."""
    fs["son_iki"] = ({"puan": 70}, {"puan": 75})
    kok = tmp_path / "izleyici"
    monkeypatch.setattr(cli.takip, "IZLE_KOK", str(kok))
    monkeypatch.setattr(cli.takip, "normalle", lambda d: "a.example")
    rc = cli._cmd_delta(SimpleNamespace(domain="a.example", dosya=True))
    assert rc == 0
    assert capsys.readouterr().out.strip().endswith("a.example-son-delta.md")


def test_delta_raporlar_dizini_olusturulur(fs, tmp_path, monkeypatch):
    """ORTAM: os.makedirs(exist_ok=True) — raporlar/ alt dizini yaratilir."""
    fs["son_iki"] = ({"puan": 70}, {"puan": 75, "tarih": "t1"})
    kok = tmp_path / "izleyici"
    monkeypatch.setattr(cli.takip, "IZLE_KOK", str(kok))
    monkeypatch.setattr(cli.takip, "normalle", lambda d: "a.example")
    cli._cmd_delta(SimpleNamespace(domain="a.example", dosya=True))
    assert (kok / "raporlar").is_dir()


def test_delta_eski_none_yeni_var(fs, capsys):
    """ORTAM: eski None olabilir (ilk snapshot) — rapor yine uretilir."""
    fs["son_iki"] = (None, {"puan": 75, "tarih": "t1"})
    fs["rapor"] = "ilk\n"
    rc = cli._cmd_delta(SimpleNamespace(domain="a.example", dosya=False))
    assert rc == 0
    assert capsys.readouterr().out == "ilk\n"


# == main entegrasyon (argparse) ==============================================================

def test_main_add_arguman_baglama(monkeypatch):
    """ORTAM: 'add' subparser'i _cmd_add'a bagli."""
    cagrilan = {}

    def _kayit(a):
        cagrilan["d"] = a.domain
        return 0

    monkeypatch.setattr(cli, "_cmd_add", _kayit)
    rc = cli.main(["add", "a.example"])
    assert rc == 0
    assert cagrilan["d"] == "a.example"


def test_main_komut_zorunlu():
    """ORTAM: subparsers required=True — komutsuz SystemExit."""
    with pytest.raises(SystemExit):
        cli.main([])


def test_main_list_baglama(monkeypatch):
    monkeypatch.setattr(cli, "_cmd_list", lambda a: 0)
    assert cli.main(["list"]) == 0

def test_main_add_sorgular_flagi(monkeypatch):
    gordu = {}
    monkeypatch.setattr(cli, "_cmd_add",
                        lambda a: gordu.update(s=a.sorgular) or 0)
    cli.main(["add", "a.example", "--sorgular", "q.txt"])
    assert gordu["s"] == "q.txt"


def test_main_remove_baglama(monkeypatch):
    monkeypatch.setattr(cli, "_cmd_remove", lambda a: 1)
    assert cli.main(["remove", "x.example"]) == 1


def test_main_delta_dosya_flagi(monkeypatch):
    gordu = {}
    monkeypatch.setattr(cli, "_cmd_delta",
                        lambda a: gordu.setdefault("d", a.dosya) or 0)
    cli.main(["delta", "a.example", "--dosya"])
    assert gordu["d"] is True


def test_main_run_domain_optzinal(monkeypatch):
    gordu = {}
    monkeypatch.setattr(cli, "_cmd_run",
                        lambda a: gordu.setdefault("d", a.domain) or 0)
    cli.main(["run"])
    assert gordu["d"] is None
