"""mainnet_verify._rpc + imap_izle._adresleri_yukle dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — urllib.request.urlopen STUBLA (monkeypatch),
GERCEK ag cagrisi YAPILMAZ; tmp_path adres-dosyasi.
"""
import io
import json
import os
import sys
import urllib.request

import pytest

sys.path.insert(0, ".")
sys.path.insert(0, "src")
from mainnet_verify import _rpc, RPCError, RPC_URL  # noqa: E402


class FakeResp:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def fake_urlopen(monkeypatch):
    calls = []

    def _u(req, timeout=None):
        calls.append((req, timeout))
        return FakeResp({"jsonrpc": "2.0", "id": 1, "result": 0x1234})

    monkeypatch.setattr(urllib.request, "urlopen", _u)
    return calls


# == _rpc: temel ==============================================================================

def test_result_donar(fake_urlopen):
    assert _rpc("eth_blockNumber", []) == 0x1234


def test_url_kullanilir(fake_urlopen):
    _rpc("m", [])
    req, _ = fake_urlopen[0]
    assert req.get_full_url() == RPC_URL


def test_payload_jsonrpc(fake_urlopen):
    _rpc("m", [])
    req, _ = fake_urlopen[0]
    data = json.loads(req.data.decode())
    assert data["jsonrpc"] == "2.0"


def test_payload_method(fake_urlopen):
    _rpc("eth_chainId", [])
    req, _ = fake_urlopen[0]
    assert json.loads(req.data.decode())["method"] == "eth_chainId"


def test_payload_params(fake_urlopen):
    _rpc("m", ["a", 1])
    req, _ = fake_urlopen[0]
    assert json.loads(req.data.decode())["params"] == ["a", 1]


def test_payload_id_bir(fake_urlopen):
    _rpc("m", [])
    req, _ = fake_urlopen[0]
    assert json.loads(req.data.decode())["id"] == 1


def test_payload_anahtar_seti(fake_urlopen):
    _rpc("m", [])
    req, _ = fake_urlopen[0]
    assert set(json.loads(req.data.decode())) == {"jsonrpc", "method",
                                                   "params", "id"}


def test_timeout_20(fake_urlopen):
    _rpc("m", [])
    _, t = fake_urlopen[0]
    assert t == 20


def test_bos_params(fake_urlopen):
    _rpc("m", [])
    req, _ = fake_urlopen[0]
    assert json.loads(req.data.decode())["params"] == []


def test_returns_dict(fake_urlopen):
    """ORTAM: out['result'] tipi neyse o."""
    assert _rpc("m", []) == 0x1234


# == _rpc: error ==============================================================================

def test_error_raises(monkeypatch):
    def _u(req, timeout=None):
        return FakeResp({"jsonrpc": "2.0", "id": 1,
                         "error": {"code": -32601, "message": "not found"}})
    monkeypatch.setattr(urllib.request, "urlopen", _u)
    with pytest.raises(RPCError):
        _rpc("eth_x", [])


def test_error_mesaj_method(monkeypatch):
    def _u(req, timeout=None):
        return FakeResp({"jsonrpc": "2.0", "id": 1, "error": "boom"})
    monkeypatch.setattr(urllib.request, "urlopen", _u)
    with pytest.raises(RPCError) as ei:
        _rpc("eth_metod", [])
    assert "eth_metod" in str(ei.value)


def test_error_mesaj_icerik(monkeypatch):
    def _u(req, timeout=None):
        return FakeResp({"jsonrpc": "2.0", "id": 1, "error": "BOOM"})
    monkeypatch.setattr(urllib.request, "urlopen", _u)
    with pytest.raises(RPCError) as ei:
        _rpc("m", [])
    assert "BOOM" in str(ei.value)


def test_error_none_raises(monkeypatch):
    def _u(req, timeout=None):
        return FakeResp({"jsonrpc": "2.0", "id": 1, "error": None})
    monkeypatch.setattr(urllib.request, "urlopen", _u)
    with pytest.raises(RPCError):
        _rpc("m", [])


def test_result_yok_keyerror(monkeypatch):
    def _u(req, timeout=None):
        return FakeResp({"jsonrpc": "2.0", "id": 1})
    monkeypatch.setattr(urllib.request, "urlopen", _u)
    with pytest.raises(KeyError):
        _rpc("m", [])


def test_garbage_json_raises(monkeypatch):
    class R:
        def read(self):
            return b"not-json"
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=None: R())
    with pytest.raises(json.JSONDecodeError):
        _rpc("m", [])


def test_url_error_propagates(monkeypatch):
    def _u(req, timeout=None):
        raise urllib.error.URLError("down")
    monkeypatch.setattr(urllib.request, "urlopen", _u)
    with pytest.raises(urllib.error.URLError):
        _rpc("m", [])


def test_timeout_propagates(monkeypatch):
    import socket
    def _u(req, timeout=None):
        raise socket.timeout("t")
    monkeypatch.setattr(urllib.request, "urlopen", _u)
    with pytest.raises(TimeoutError):
        _rpc("m", [])


# == _rpc: cesitli =============================================================================

def test_post_yapar(fake_urlopen):
    _rpc("m", [])
    req, _ = fake_urlopen[0]
    assert req.data is not None


def test_repeatable(fake_urlopen):
    assert _rpc("m", []) == _rpc("m", [])


def test_iki_cagri(fake_urlopen):
    _rpc("a", [])
    _rpc("b", [])
    assert len(fake_urlopen) == 2


def test_params_dict(fake_urlopen):
    _rpc("m", [{"x": 1}])
    req, _ = fake_urlopen[0]
    assert json.loads(req.data.decode())["params"] == [{"x": 1}]


def test_params_turkce(fake_urlopen):
    _rpc("m", ["Türkçe"])
    req, _ = fake_urlopen[0]
    assert json.loads(req.data.decode())["params"] == ["Türkçe"]


@pytest.mark.parametrize("params", [[], [1], ["a", "b"], [{}], [None, True]])
def test_params_matrix(fake_urlopen, params):
    _rpc("m", params)
    req, _ = fake_urlopen[0]
    assert json.loads(req.data.decode())["params"] == params


def test_result_dict(monkeypatch):
    def _u(req, timeout=None):
        return FakeResp({"jsonrpc": "2.0", "id": 1,
                         "result": {"block": 1}})
    monkeypatch.setattr(urllib.request, "urlopen", _u)
    assert _rpc("m", []) == {"block": 1}


def test_result_none(monkeypatch):
    def _u(req, timeout=None):
        return FakeResp({"jsonrpc": "2.0", "id": 1, "result": None})
    monkeypatch.setattr(urllib.request, "urlopen", _u)
    assert _rpc("m", []) is None


# == _adresleri_yukle ==========================================================================

sys.path.insert(0, ".")
import imap_izle  # noqa: E402


def test_dosya_yok_bos(monkeypatch):
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", "/yok/yok.txt")
    assert imap_izle._adresleri_yukle() == []


def test_bos_dosya(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == []


def test_tek_adres(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("0xabc\n", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == ["0xabc"]


def test_strip_yapar(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("  0xabc  \n", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == ["0xabc"]


def test_cok_adres(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("0xa\n0xb\n0xc\n", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == ["0xa", "0xb", "0xc"]


def test_bos_satir_atlanir(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("0xa\n\n0xb\n", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == ["0xa", "0xb"]


def test_yorum_atlanir(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("# yorum\n0xa\n", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == ["0xa"]


def test_bosluk_satir_atlanir(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("   \n0xa\n", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == ["0xa"]


def test_turkce_adres(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("Türkçe-adres\n", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == ["Türkçe-adres"]


def test_emoji_adres(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("🤖\n", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == ["🤖"]


def test_son_satir_newline_yok(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("0xa", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == ["0xa"]


def test_returns_list(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("0xa\n", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert isinstance(imap_izle._adresleri_yukle(), list)


def test_sadece_yorumlar(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("# a\n# b\n", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == []


def test_karisik(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("# baslik\n\n  0xa  \n0xb\n\n# son\n", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == ["0xa", "0xb"]


def test_repeatable(tmp_path, monkeypatch):
    p = tmp_path / "a.txt"
    p.write_text("0xa\n", encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert imap_izle._adresleri_yukle() == imap_izle._adresleri_yukle()


@pytest.mark.parametrize("n", [1, 3, 10])
def test_adres_sayisi(tmp_path, monkeypatch, n):
    p = tmp_path / "a.txt"
    p.write_text("\n".join(f"0x{i}" for i in range(n)) + "\n",
                 encoding="utf-8")
    monkeypatch.setattr(imap_izle, "ADRES_DOSYASI", str(p))
    assert len(imap_izle._adresleri_yukle()) == n
