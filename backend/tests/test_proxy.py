"""Tests for client address resolution behind trusted proxies."""

import ipaddress

import pytest
from starlette.requests import Request

from app.core.proxy import IPAddress, TrustedProxies, resolve_host


def make_request(peer: str, forwarded_for: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded_for.encode())] if forwarded_for else []
    return Request({"type": "http", "client": (peer, 50000), "headers": headers})


class FakeDNS:
    """Resolver whose answers can change, counting lookups."""

    def __init__(self, records: dict[str, set[str]]) -> None:
        self.records = records
        self.lookups = 0

    async def __call__(self, host: str) -> set[IPAddress]:
        self.lookups += 1
        return {ipaddress.ip_address(a) for a in self.records.get(host, set())}


class TestIsTrusted:
    @pytest.mark.parametrize(
        ("entries", "peer", "expected"),
        [
            (["10.0.0.5"], "10.0.0.5", True),
            (["10.0.0.5"], "10.0.0.6", False),
            (["172.16.0.0/12"], "172.18.0.3", True),
            (["172.16.0.0/12"], "192.168.1.1", False),
            (["::1"], "::1", True),
            ([], "127.0.0.1", False),
            (["10.0.0.5"], "not-an-ip", False),
        ],
    )
    async def test_addresses_and_networks(
        self, entries: list[str], peer: str, expected: bool
    ) -> None:
        assert await TrustedProxies(entries).is_trusted(peer) is expected

    async def test_hostname_is_resolved(self) -> None:
        dns = FakeDNS({"caddy": {"172.18.0.9"}})
        proxies = TrustedProxies(["caddy"], resolver=dns)

        assert await proxies.is_trusted("172.18.0.9")
        assert not await proxies.is_trusted("172.18.0.10")

    async def test_unresolvable_hostname_trusts_nothing(self) -> None:
        proxies = TrustedProxies(["caddy"], resolver=FakeDNS({}))

        assert not await proxies.is_trusted("172.18.0.9")

    async def test_resolution_is_cached(self) -> None:
        dns = FakeDNS({"caddy": {"172.18.0.9"}})
        proxies = TrustedProxies(["caddy"], resolver=dns)

        for _ in range(5):
            await proxies.is_trusted("172.18.0.9")
            await proxies.is_trusted("203.0.113.1")

        assert dns.lookups == 1

    async def test_proxy_with_new_address_is_picked_up(self) -> None:
        dns = FakeDNS({"caddy": {"172.18.0.9"}})
        proxies = TrustedProxies(["caddy"], resolver=dns, min_retry_seconds=0)
        assert await proxies.is_trusted("172.18.0.9")

        dns.records["caddy"] = {"172.18.0.20"}  # proxy container restarted

        assert await proxies.is_trusted("172.18.0.20")
        assert not await proxies.is_trusted("172.18.0.9")

    async def test_real_dns_resolves_localhost(self) -> None:
        assert ipaddress.ip_address("127.0.0.1") in await resolve_host("localhost")

    async def test_real_dns_unknown_host_resolves_to_nothing(self) -> None:
        # .invalid is reserved and never resolves (RFC 2606).
        assert await resolve_host("no-such-proxy.invalid") == set()


class TestClientIP:
    proxies = TrustedProxies(["10.0.0.5"])

    async def test_direct_connection_uses_peer(self) -> None:
        assert await self.proxies.client_ip(make_request("203.0.113.1")) == "203.0.113.1"

    async def test_untrusted_peer_cannot_spoof(self) -> None:
        request = make_request("203.0.113.1", forwarded_for="198.51.100.7")

        assert await self.proxies.client_ip(request) == "203.0.113.1"

    async def test_trusted_proxy_reports_client(self) -> None:
        request = make_request("10.0.0.5", forwarded_for="198.51.100.7")

        assert await self.proxies.client_ip(request) == "198.51.100.7"

    async def test_uses_nearest_untrusted_hop(self) -> None:
        # A client-supplied value on the left is ignored; the proxy appended the real one.
        request = make_request("10.0.0.5", forwarded_for="1.2.3.4, 198.51.100.7")

        assert await self.proxies.client_ip(request) == "198.51.100.7"

    async def test_skips_chained_trusted_proxies(self) -> None:
        proxies = TrustedProxies(["10.0.0.0/24"])
        request = make_request("10.0.0.5", forwarded_for="198.51.100.7, 10.0.0.6")

        assert await proxies.client_ip(request) == "198.51.100.7"

    @pytest.mark.parametrize("header", ["", "garbage", "198.51.100.7, garbage"])
    async def test_missing_or_malformed_header_falls_back_to_peer(self, header: str) -> None:
        request = make_request("10.0.0.5", forwarded_for=header or None)

        assert await self.proxies.client_ip(request) == "10.0.0.5"
