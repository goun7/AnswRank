"""x402_servis._olcum_rate_limit_ok dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (FakeRequest + time.monotonic monkeypatch, dis cagri YOK).
K3 guvenlik: ayni IP'den saniyede 1 istek — rate-limit.
"""
import os
import sys
import time

import pytest

# G47: sester SDK PyPI-de ( sester==0.7.5, CI-de-kurulu);
# yalnizca-yerel-gelistirme-icin yedek-yol ( CI-de-YOK).
sys.path.insert(0, os.environ.get(
    "MESH_SESTER_ROOT", "/home/gokun/projects/01_unicorn/63-Sester"))
sys.path.insert(0, ".")
os.environ.setdefault("UNPUMP_TREASURY_EOA", "0x" + "a" * 40)
os.environ.setdefault("UNPUMP_SELLER_SECRET", "test-seller-secret")
os.environ.setdefault("ANSWRANK_SELLER_SECRET", "test-answrank-secret")
import x402_servis as xs  # noqa: E402

BASE = 1000.0


class FakeClient:
    def __init__(self, host):
        self.host = host


class FakeReq:
    def __init__(self, host="1.2.3.4"):
        self.client = FakeClient(host)


class Clock:
    """Fake time.monotonic — BASE'den baslar, += ile ilerler."""

    def __init__(self):
        self.t = BASE


@pytest.fixture()
def clk(monkeypatch):
    c = Clock()
    monkeypatch.setattr(time, "monotonic", lambda: c.t)
    return c


@pytest.fixture()
def clear_olcum(monkeypatch):
    monkeypatch.setattr(xs, "_OLCUM_IP", {})
    return xs._OLCUM_IP


# == temel ===================================================================================

def test_ilk_istek_ok(clear_olcum, clk):
    assert xs._olcum_rate_limit_ok(FakeReq()) is True


def test_ayni_ip_aralik_icinde_red(clear_olcum, clk):
    assert xs._olcum_rate_limit_ok(FakeReq()) is True
    clk.t += 0.5
    assert xs._olcum_rate_limit_ok(FakeReq()) is False


def test_ayni_ip_aralik_disinda_ok(clear_olcum, clk):
    assert xs._olcum_rate_limit_ok(FakeReq()) is True
    clk.t += 1.0
    assert xs._olcum_rate_limit_ok(FakeReq()) is True


def test_tam_sinirda_ok(clear_olcum, clk):
    """tam 1.0s (>= min-aralik 1.0) -> OK."""
    xs._olcum_rate_limit_ok(FakeReq())
    clk.t += 1.0
    assert xs._olcum_rate_limit_ok(FakeReq()) is True


def test_sinir_altinda_red(clear_olcum, clk):
    xs._olcum_rate_limit_ok(FakeReq())
    clk.t += 0.999
    assert xs._olcum_rate_limit_ok(FakeReq()) is False


def test_bir_saniye_ustunde_ok(clear_olcum, clk):
    xs._olcum_rate_limit_ok(FakeReq())
    clk.t += 1.001
    assert xs._olcum_rate_limit_ok(FakeReq()) is True


# == coklu istek =============================================================================

def test_uc_istek_aralikla(clear_olcum, clk):
    assert xs._olcum_rate_limit_ok(FakeReq()) is True
    clk.t += 1.0
    assert xs._olcum_rate_limit_ok(FakeReq()) is True
    clk.t += 1.0
    assert xs._olcum_rate_limit_ok(FakeReq()) is True


def test_uc_arka_arkaya_biri_ok(clear_olcum, clk):
    assert xs._olcum_rate_limit_ok(FakeReq()) is True
    assert xs._olcum_rate_limit_ok(FakeReq()) is False
    assert xs._olcum_rate_limit_ok(FakeReq()) is False


def test_uzun_bekleme_sonrasi_ok(clear_olcum, clk):
    xs._olcum_rate_limit_ok(FakeReq())
    clk.t += 500.0
    assert xs._olcum_rate_limit_ok(FakeReq()) is True


# == IP-izolasyonu ===========================================================================

def test_farkli_ip_bagimsiz(clear_olcum, clk):
    assert xs._olcum_rate_limit_ok(FakeReq("1.1.1.1")) is True
    assert xs._olcum_rate_limit_ok(FakeReq("2.2.2.2")) is True


def test_farkli_ip_arka_arkaya_ok(clear_olcum, clk):
    assert xs._olcum_rate_limit_ok(FakeReq("1.1.1.1")) is True
    assert xs._olcum_rate_limit_ok(FakeReq("2.2.2.2")) is True
    assert xs._olcum_rate_limit_ok(FakeReq("3.3.3.3")) is True


def test_ayni_ip_ikinci_red(clear_olcum, clk):
    assert xs._olcum_rate_limit_ok(FakeReq("9.9.9.9")) is True
    assert xs._olcum_rate_limit_ok(FakeReq("9.9.9.9")) is False


def test_ip_karisik(clear_olcum, clk):
    assert xs._olcum_rate_limit_ok(FakeReq("A")) is True
    assert xs._olcum_rate_limit_ok(FakeReq("B")) is True
    clk.t += 0.4
    assert xs._olcum_rate_limit_ok(FakeReq("A")) is False
    assert xs._olcum_rate_limit_ok(FakeReq("B")) is False
    clk.t += 1.0
    assert xs._olcum_rate_limit_ok(FakeReq("A")) is True
    assert xs._olcum_rate_limit_ok(FakeReq("B")) is True


def test_ipv6(clear_olcum, clk):
    assert xs._olcum_rate_limit_ok(FakeReq("::1")) is True
    assert xs._olcum_rate_limit_ok(FakeReq("::1")) is False


# == client-hatasi ===========================================================================

def test_client_none_ip_isaret(clear_olcum, clk):
    class R:
        client = None
    assert xs._olcum_rate_limit_ok(R()) is True
    clk.t += 0.5
    assert xs._olcum_rate_limit_ok(R()) is False


def test_client_exception_ip_isaret(clear_olcum, clk):
    class BadClient:
        @property
        def host(self):
            raise RuntimeError("bad")

    class R:
        client = BadClient()
    assert xs._olcum_rate_limit_ok(R()) is True


def test_client_none_str(clear_olcum, clk):
    assert xs._olcum_rate_limit_ok(FakeReq(None)) is True
    clk.t += 0.5
    assert xs._olcum_rate_limit_ok(FakeReq(None)) is False


def test_bilinmeyen_ip_isaret_kullanilir(clear_olcum, clk):
    class R:
        client = None
    xs._olcum_rate_limit_ok(R())
    assert "?" in xs._OLCUM_IP


def test_isaret_ip_ayri_tutulur(clear_olcum, clk):
    class R:
        client = None
    xs._olcum_rate_limit_ok(R())
    xs._olcum_rate_limit_ok(FakeReq("?"))
    assert len(xs._OLCUM_IP) == 1


# == durum ====================================================================================

def test_ip_kaydedilir(clear_olcum, clk):
    xs._olcum_rate_limit_ok(FakeReq("5.5.5.5"))
    assert "5.5.5.5" in clear_olcum


def test_ip_zaman_stamped(clear_olcum, clk):
    xs._olcum_rate_limit_ok(FakeReq("5.5.5.5"))
    assert clear_olcum["5.5.5.5"] == BASE


def test_red_zaman_guncellenmez(clear_olcum, clk):
    xs._olcum_rate_limit_ok(FakeReq("5.5.5.5"))
    clk.t += 0.5
    xs._olcum_rate_limit_ok(FakeReq("5.5.5.5"))
    assert clear_olcum["5.5.5.5"] == BASE


def test_returns_bool(clear_olcum, clk):
    assert isinstance(xs._olcum_rate_limit_ok(FakeReq()), bool)


def test_ip_str_coerce(clear_olcum, clk):
    """str(client.host) — int host -> str."""
    class R:
        client = FakeClient(65535)
    assert xs._olcum_rate_limit_ok(R()) is True


@pytest.mark.parametrize("n", range(1, 6))
def test_ilk_n_ip_hepsi_ok(clear_olcum, clk, n):
    for i in range(n):
        assert xs._olcum_rate_limit_ok(FakeReq(f"ip{i}")) is True
