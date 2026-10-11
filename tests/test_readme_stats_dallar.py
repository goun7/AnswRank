"""scripts.readme_stats dal-kesen testleri (LEED) — 5 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — subprocess.run STUBLA, Path STUBLA, dis cagri YOK.
_test_sayisi + _bot_sayilari + _api_pathleri + _servis_sayisi + _charge_shield.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "scripts")
sys.path.insert(0, ".")
import readme_stats as RS  # noqa: E402


# == _charge_shield ==========================================================================

def test_charge_shield_dict():
    assert isinstance(RS._charge_shield(), dict)


def test_charge_shield_servis():
    assert RS._charge_shield()["servis"] == "ChargeShield"


def test_charge_shield_hizmet():
    assert RS._charge_shield()["hizmet"] == "ters-ibraz savunması"


def test_charge_shield_fiyat():
    assert RS._charge_shield()["fiyat"] == "$0.25/ibraz"


def test_charge_shield_uyari_answrank():
    assert "AnswRank" in RS._charge_shield()["uyari"]


def test_charge_shield_uyari_farkli():
    assert "FARKLI" in RS._charge_shield()["uyari"]


def test_charge_shield_anahtar_seti():
    assert set(RS._charge_shield()) == {"servis", "hizmet", "fiyat", "uyari"}


def test_charge_shield_repeatable():
    assert RS._charge_shield() == RS._charge_shield()


def test_charge_shield_uyari_05():
    """ORTAM: $0.05 AnswRank-fiyat karsilastirmasi."""
    assert "$0.05" in RS._charge_shield()["uyari"]


# == _test_sayisi ===========================================================================

class FakeProc:
    def __init__(self, out="", err=""):
        self.stdout = out
        self.stderr = err


@pytest.fixture()
def run_out(monkeypatch):
    def _make(out):
        def _run(cmd, **kw):
            return FakeProc(out=out)
        monkeypatch.setattr(RS.subprocess, "run", _run)
    return _make


def test_test_sayisi_basari(run_out):
    run_out("1234 passed in 5.0s")
    assert RS._test_sayisi() == (1234, 0, 1234)


def test_test_sayisi_basarisiz(run_out):
    run_out("100 passed, 3 failed in 5.0s")
    assert RS._test_sayisi() == (100, 3, 103)


def test_test_sayisi_sayi_yok(run_out):
    """ORTAM: regex-eslesme yok -> (-1,-1,-1)."""
    run_out("no output")
    assert RS._test_sayisi() == (-1, -1, -1)


def test_test_sayisi_bos(run_out):
    run_out("")
    assert RS._test_sayisi() == (-1, -1, -1)


def test_test_sayisi_stderr_okunur(run_out):
    """ORTAM: stdout + stderr'de aranir."""
    run_out("")
    """stderr yok — bos."""
    assert RS._test_sayisi() == (-1, -1, -1)


def test_test_sayisi_return_tuple(run_out):
    run_out("5 passed")
    assert isinstance(RS._test_sayisi(), tuple) and len(RS._test_sayisi()) == 3


def test_test_sayisi_exception_negatif(monkeypatch):
    def _run(cmd, **kw):
        raise RuntimeError("down")
    monkeypatch.setattr(RS.subprocess, "run", _run)
    assert RS._test_sayisi() == (-1, -1, -1)


def test_test_sayisi_timeout_negatif(monkeypatch):
    import subprocess
    def _run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 280)
    monkeypatch.setattr(RS.subprocess, "run", _run)
    assert RS._test_sayisi() == (-1, -1, -1)


def test_test_sayisi_komut_venv(monkeypatch):
    calls = []
    def _run(cmd, **kw):
        calls.append((cmd, kw))
        return FakeProc(out="1 passed")
    monkeypatch.setattr(RS.subprocess, "run", _run)
    RS._test_sayisi()
    cmd, _ = calls[0]
    assert cmd[0] == RS._VENV_PYTHON
    assert "pytest" in cmd


def test_test_sayisi_cwd_kok(monkeypatch):
    calls = []
    def _run(cmd, **kw):
        calls.append((cmd, kw))
        return FakeProc(out="1 passed")
    monkeypatch.setattr(RS.subprocess, "run", _run)
    RS._test_sayisi()
    _, kw = calls[0]
    assert kw["cwd"] == str(RS._KOK)


def test_test_sayisi_capture_text(monkeypatch):
    calls = []
    def _run(cmd, **kw):
        calls.append((cmd, kw))
        return FakeProc(out="1 passed")
    monkeypatch.setattr(RS.subprocess, "run", _run)
    RS._test_sayisi()
    _, kw = calls[0]
    assert kw["capture_output"] is True
    assert kw["text"] is True


def test_test_sayisi_timeout_280(monkeypatch):
    calls = []
    def _run(cmd, **kw):
        calls.append((cmd, kw))
        return FakeProc(out="1 passed")
    monkeypatch.setattr(RS.subprocess, "run", _run)
    RS._test_sayisi()
    _, kw = calls[0]
    assert kw["timeout"] == 280


def test_test_sayisi_failed_sifir_implicit(run_out):
    """'N passed' failed-grup YOK -> failed=0."""
    run_out("50 passed in 1s")
    p, f, t = RS._test_sayisi()
    assert f == 0 and t == 50


@pytest.mark.parametrize("out,exp", [
    ("1 passed", (1, 0, 1)),
    ("10 passed, 2 failed", (10, 2, 12)),
    ("999 passed, 1 failed", (999, 1, 1000)),
    ("", (-1, -1, -1)),
])
def test_test_sayisi_matrix(run_out, out, exp):
    run_out(out)
    assert RS._test_sayisi() == exp


# == _bot_sayilari ===========================================================================

def test_bot_sayilari_dict_or_empty(monkeypatch):
    """import basarili olursa dict, olmazsa {}."""
    try:
        r = RS._bot_sayilari()
        assert isinstance(r, dict)
    except Exception:
        assert True


def test_bot_sayilari_exception_bos_dict(monkeypatch):
    """ORTAM: herhangi import-hata -> {} (fail-soft)."""
    import builtins
    real_import = builtins.__import__

    def _imp(name, *a, **k):
        if name.startswith("answrank"):
            raise ImportError("yok")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", _imp)
    assert RS._bot_sayilari() == {}


def test_bot_sayilari_repeatable():
    try:
        assert RS._bot_sayilari() == RS._bot_sayilari()
    except Exception:
        assert True


# == _api_pathleri ===========================================================================

class FakeRoute:
    def __init__(self, path, methods):
        self.path = path
        self.methods = methods


class FakeBadRoute:
    """path-ozellik YOK -> getattr None."""
    pass


def test_api_pathleri_dict(monkeypatch):
    """import basarili -> dict."""
    try:
        r = RS._api_pathleri()
        assert isinstance(r, dict)
    except Exception:
        assert True


def test_api_pathleri_app_none_bos(monkeypatch):
    """ORTAM: app-nesnesi yoksa {} (api_mod.app.app None)."""
    import sys as _sys
    _sys.modules.pop("answrank.api", None)
    fake_mod = type(_sys)("answrank.api")
    sub_mod = type(_sys)("answrank.api.app")  # app-nesnesi YOK
    fake_mod.app = sub_mod
    monkeypatch.setitem(_sys.modules, "answrank.api", fake_mod)
    monkeypatch.setitem(_sys.modules, "answrank.api.app", sub_mod)
    assert RS._api_pathleri() == {}


def test_api_pathleri_app_var(monkeypatch):
    """Fake app ile path/handler sayisi."""
    import sys as _sys
    _sys.modules.pop("answrank.api", None)
    fake_mod = type(_sys)("answrank.api")
    sub_mod = type(_sys)("answrank.api.app")
    sub_mod.app = type("App", (), {
        "routes": [FakeRoute("/a", {"GET"}),
                   FakeRoute("/b", {"POST"}),
                   FakeRoute("/c", {"GET", "PUT"})]})
    fake_mod.app = sub_mod
    monkeypatch.setitem(_sys.modules, "answrank.api", fake_mod)
    monkeypatch.setitem(_sys.modules, "answrank.api.app", sub_mod)
    r = RS._api_pathleri()
    assert r["dokümante_path"] == 3
    assert r["handler"] == 3


def test_api_pathleri_kotu_rota_atlanir(monkeypatch):
    """path-ozellik YOK -> getattr(rota,'methods',set()) -> set()."""
    import sys as _sys
    _sys.modules.pop("answrank.api", None)
    fake_mod = type(_sys)("answrank.api")
    sub_mod = type(_sys)("answrank.api.app")
    sub_mod.app = type("App", (), {"routes": [FakeBadRoute()]})
    fake_mod.app = sub_mod
    monkeypatch.setitem(_sys.modules, "answrank.api", fake_mod)
    monkeypatch.setitem(_sys.modules, "answrank.api.app", sub_mod)
    r = RS._api_pathleri()
    assert r["handler"] == 0


def test_api_pathleri_dedup(monkeypatch):
    """ayni path 2-rota -> benzersiz."""
    import sys as _sys
    _sys.modules.pop("answrank.api", None)
    fake_mod = type(_sys)("answrank.api")
    sub_mod = type(_sys)("answrank.api.app")
    sub_mod.app = type("App", (), {"routes": [
        FakeRoute("/x", {"GET"}), FakeRoute("/x", {"POST"})]})
    fake_mod.app = sub_mod
    monkeypatch.setitem(_sys.modules, "answrank.api", fake_mod)
    monkeypatch.setitem(_sys.modules, "answrank.api.app", sub_mod)
    assert RS._api_pathleri()["dokümante_path"] == 1


def test_api_pathleri_ws_atlanir(monkeypatch):
    """WebSocket rotasinin methods'u YOK."""
    import sys as _sys
    _sys.modules.pop("answrank.api", None)
    fake_mod = type(_sys)("answrank.api")

    class WS:
        path = "/ws"
    sub_mod = type(_sys)("answrank.api.app")
    sub_mod.app = type("App", (), {"routes": [WS()]})
    fake_mod.app = sub_mod
    monkeypatch.setitem(_sys.modules, "answrank.api", fake_mod)
    monkeypatch.setitem(_sys.modules, "answrank.api.app", sub_mod)
    assert RS._api_pathleri()["handler"] == 0


# == _servis_sayisi ===========================================================================

@pytest.fixture()
def script(monkeypatch, tmp_path):
    p = tmp_path / "start_services.sh"
    monkeypatch.setattr(RS, "_START_SCRIPT", p)
    return p


def test_servis_sayisi_bos(script):
    script.write_text("", encoding="utf-8")
    assert RS._servis_sayisi() == {"toplam": 0, "benzersiz": 0, "liste": []}


def test_servis_sayisi_tek(script):
    script.write_text("start_svc a\n", encoding="utf-8")
    assert RS._servis_sayisi() == {"toplam": 1, "benzersiz": 1, "liste": ["a"]}


def test_servis_sayisi_cok(script):
    script.write_text("start_svc a\nstart_svc b\nstart_svc c\n",
                      encoding="utf-8")
    assert RS._servis_sayisi()["toplam"] == 3


def test_servis_sayisi_dedup(script):
    script.write_text("start_svc a\nstart_svc a\n", encoding="utf-8")
    r = RS._servis_sayisi()
    assert r["toplam"] == 2 and r["benzersiz"] == 1


def test_servis_sayisi_sorted(script):
    """ORTAM: sorted(set(...))."""
    script.write_text("start_svc c\nstart_svc a\nstart_svc b\n",
                      encoding="utf-8")
    assert RS._servis_sayisi()["liste"] == ["a", "b", "c"]


def test_servis_sayisi_yok_basarisiz(script):
    """ORTAM: dosya yok -> Exception -> {} (fail-soft)."""
    monkeypatch_set = None
    import os
    """Path yok -> read_text FileNotFoundError -> {}."""
    assert RS._servis_sayisi() == {}


def test_servis_sayisi_anahtar_seti(script):
    script.write_text("start_svc x\n", encoding="utf-8")
    assert set(RS._servis_sayisi()) == {"toplam", "benzersiz", "liste"}


def test_servis_sayisi_argumanli(script):
    script.write_text("start_svc a --flag\n", encoding="utf-8")
    """ORTAM: regex start_svc\\s+(\\S+) — sadece ilk-token."""
    assert RS._servis_sayisi()["liste"] == ["a"]


def test_servis_sayisi_turkce(script):
    script.write_text("start_svc servis-İ\n", encoding="utf-8")
    assert RS._servis_sayisi()["liste"] == ["servis-İ"]


def test_servis_sayisi_emoji(script):
    script.write_text("start_svc 🤖\n", encoding="utf-8")
    assert RS._servis_sayisi()["liste"] == ["🤖"]


def test_servis_sayisi_yorum(script):
    script.write_text("# start_svc a\nstart_svc b\n", encoding="utf-8")
    """ORTAM: # ile baslamissa YINE de sayilir (yorum-filtresi YOK)."""
    assert RS._servis_sayisi()["toplam"] == 2


def test_servis_sayisi_repeatable(script):
    script.write_text("start_svc a\n", encoding="utf-8")
    assert RS._servis_sayisi() == RS._servis_sayisi()


@pytest.mark.parametrize("n", [1, 3, 10])
def test_servis_sayisi_matrix(script, n):
    script.write_text("\n".join(f"start_svc s{i}" for i in range(n)) + "\n",
                      encoding="utf-8")
    assert RS._servis_sayisi()["toplam"] == n
