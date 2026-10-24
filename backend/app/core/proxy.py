"""Client address resolution behind trusted reverse proxies.

``X-Forwarded-For`` is only believed when the connecting peer is a trusted
proxy; otherwise anyone could fake their address and dodge per-address limits.
Trusted proxies may be IP addresses, CIDR networks or hostnames. Hostnames
(such as the ``caddy`` compose service) are resolved through DNS and cached,
and re-resolved when an unknown peer appears, so a restarted proxy with a new
container IP is picked up.
"""

import asyncio
import ipaddress
import socket
import time
from collections.abc import Awaitable, Callable

from starlette.requests import Request

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
Resolver = Callable[[str], Awaitable[set[IPAddress]]]


async def resolve_host(host: str) -> set[IPAddress]:
    """Resolve a hostname to its addresses; empty if it does not resolve."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return set()
    return {ipaddress.ip_address(info[4][0]) for info in infos}


def _parse_ip(value: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


class TrustedProxies:
    """The set of proxies allowed to report the client address."""

    def __init__(
        self,
        entries: list[str],
        *,
        resolver: Resolver = resolve_host,
        refresh_seconds: float = 30.0,
        min_retry_seconds: float = 5.0,
    ) -> None:
        self._networks: list[IPNetwork] = []
        self._hostnames: list[str] = []
        for entry in entries:
            try:
                self._networks.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                self._hostnames.append(entry)
        self._resolver = resolver
        self._refresh_seconds = refresh_seconds
        self._min_retry_seconds = min_retry_seconds
        self._resolved: set[IPAddress] = set()
        self._resolved_at: float | None = None

    async def _refresh(self) -> None:
        resolved: set[IPAddress] = set()
        for host in self._hostnames:
            resolved |= await self._resolver(host)
        self._resolved = resolved
        self._resolved_at = time.monotonic()

    async def is_trusted(self, address: str) -> bool:
        """Whether a connecting peer address is a trusted proxy."""
        ip = _parse_ip(address)
        if ip is None:
            return False
        if any(ip in network for network in self._networks):
            return True
        if not self._hostnames:
            return False

        age = None if self._resolved_at is None else time.monotonic() - self._resolved_at
        if age is None or age > self._refresh_seconds:
            await self._refresh()
        elif ip not in self._resolved and age >= self._min_retry_seconds:
            # Possibly a proxy that restarted with a new address.
            await self._refresh()
        return ip in self._resolved

    async def client_ip(self, request: Request) -> str:
        """The address of the client, looking through trusted proxies.

        Walks ``X-Forwarded-For`` from the right (nearest hop) and returns the
        first address that is not itself a trusted proxy.
        """
        peer = request.client.host if request.client else "unknown"
        if not await self.is_trusted(peer):
            return peer

        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        for hop in reversed(hops):
            if _parse_ip(hop) is None:
                break  # malformed header: do not trust anything to its left
            if not await self.is_trusted(hop):
                return hop
        return peer
