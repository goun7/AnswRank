"""probe.MiniProbe._is_internal (check) dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-3: socket.getaddrinfo stub — gercek DNS/ag YAPILMADI.
"""
import asyncio

import pytest

from answrank.probe.miniprobe import MiniProbe


class _Addr(tuple):
    pass


def _fake_resolver(mapping):
    def res(host, port=None):
        host = host.strip("[]").rstrip(".")
        if host in mapping:
            return [(0, 0, 0, 0, (mapping[host], 0))]
        raise OSError("DNS yok")
    return res


# -- localhost literalleri ---------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_localhost_true(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", _fake_resolver({}))
    assert await MiniProbe._is_internal("localhost") is True


@pytest.mark.asyncio
async def test_dot_localhost_true(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", _fake_resolver({}))
    assert await MiniProbe._is_internal("sub.localhost") is True


@pytest.mark.asyncio
async def test_ipv6_bracketed_localhost(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", _fake_resolver({}))
    assert await MiniProbe._is_internal("[::1]") is True


@pytest.mark.asyncio
async def test_trailing_dot_stripped(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", _fake_resolver({}))
    assert await MiniProbe._is_internal("localhost.") is True


# -- private/loopback IP'leri ---------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_private_ip_10(monkeypatch):
    assert await MiniProbe._is_internal("10.0.0.1") is True


@pytest.mark.asyncio
async def test_private_ip_172(monkeypatch):
    assert await MiniProbe._is_internal("172.16.0.1") is True


@pytest.mark.asyncio
async def test_private_ip_192(monkeypatch):
    assert await MiniProbe._is_internal("192.168.1.1") is True


@pytest.mark.asyncio
async def test_loopback_ip(monkeypatch):
    assert await MiniProbe._is_internal("127.0.0.1") is True


@pytest.mark.asyncio
async def test_ipv6_loopback(monkeypatch):
    assert await MiniProbe._is_internal("::1") is True


@pytest.mark.asyncio
async def test_link_local(monkeypatch):
    assert await MiniProbe._is_internal("169.254.1.1") is True


@pytest.mark.asyncio
async def test_reserved(monkeypatch):
    assert await MiniProbe._is_internal("240.0.0.1") is True


@pytest.mark.asyncio
async def test_multicast(monkeypatch):
    assert await MiniProbe._is_internal("224.0.0.1") is True


@pytest.mark.asyncio
async def test_unspecified(monkeypatch):
    assert await MiniProbe._is_internal("0.0.0.0") is True


# -- public ---------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_public_ip_false(monkeypatch):
    assert await MiniProbe._is_internal("8.8.8.8") is False


@pytest.mark.asyncio
async def test_public_domain_false(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo",
                        _fake_resolver({"example.com": "8.8.8.8"}))
    assert await MiniProbe._is_internal("example.com") is False


# -- DNS cozulemeyen ---------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unresolvable_false(monkeypatch):
    """Cozumsuz DNS SSRF degildir."""
    monkeypatch.setattr("socket.getaddrinfo", _fake_resolver({}))
    assert await MiniProbe._is_internal("bogus.invalid") is False


# -- domain private'a cozulurse ---------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_domain_resolves_private_true(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo",
                        _fake_resolver({"internal.example": "10.1.1.1"}))
    assert await MiniProbe._is_internal("internal.example") is True


@pytest.mark.asyncio
async def test_domain_resolves_public_false(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo",
                        _fake_resolver({"ok.example": "1.2.3.4"}))
    assert await MiniProbe._is_internal("ok.example") is False


@pytest.mark.asyncio
async def test_multiple_addrs_one_private_true(monkeypatch):
    def res(host, port=None):
        return [(0, 0, 0, 0, ("8.8.8.8", 0)),
                (0, 0, 0, 0, ("192.168.0.1", 0))]
    monkeypatch.setattr("socket.getaddrinfo", res)
    assert await MiniProbe._is_internal("multi.example") is True


@pytest.mark.asyncio
async def test_multiple_addrs_all_public_false(monkeypatch):
    def res(host, port=None):
        return [(0, 0, 0, 0, ("1.2.3.4", 0)),
                (0, 0, 0, 0, ("8.8.4.4", 0))]
    monkeypatch.setattr("socket.getaddrinfo", res)
    assert await MiniProbe._is_internal("multi2.example") is False


# -- bozuk addr girdisi ---------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_ip_addr_returns_true(monkeypatch):
    def res(host, port=None):
        return [(0, 0, 0, 0, ("not-an-ip", 0))]
    monkeypatch.setattr("socket.getaddrinfo", res)
    assert await MiniProbe._is_internal("weird.example") is True


# -- bad_ip birim ---------------------------------------------------------------------------------

def test_bad_ip_private():
    import ipaddress
    assert MiniProbe._bad_ip(ipaddress.ip_address("10.0.0.1")) is True


def test_bad_ip_public():
    import ipaddress
    assert MiniProbe._bad_ip(ipaddress.ip_address("8.8.8.8")) is False


def test_bad_ip_loopback():
    import ipaddress
    assert MiniProbe._bad_ip(ipaddress.ip_address("127.0.0.1")) is True


# -- tekrar ---------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repeatable(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo",
                        _fake_resolver({"example.com": "8.8.8.8"}))
    a = await MiniProbe._is_internal("example.com")
    b = await MiniProbe._is_internal("example.com")
    assert a == b is False


@pytest.mark.asyncio
async def test_returns_bool(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", _fake_resolver({}))
    assert isinstance(await MiniProbe._is_internal("localhost"), bool)
