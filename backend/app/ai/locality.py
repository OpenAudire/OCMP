"""Where a provider runs: what counts as local, and what needs a warning (ADR 042)."""

import ipaddress

from httpx import URL, InvalidURL

from app.models.ai_settings import DataLocation
from app.services.authorization import InvalidRequestError

_LOCAL_SUFFIXES = (".local", ".internal", ".lan", ".home.arpa", ".localhost")


def is_local_host(host: str) -> bool:
    """Whether a host name is on this machine or a private network.

    True for localhost, loopback and private IP addresses, names without a dot (Docker
    service names such as ``ollama``) and names ending in ``.local``, ``.internal`` or
    ``.lan``. Public addresses and ordinary domain names are not local.
    """
    host = host.strip("[]").lower().rstrip(".")
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host or host.endswith(_LOCAL_SUFFIXES)
    return address.is_loopback or address.is_private or address.is_link_local


def normalise_base_url(value: str, location: DataLocation) -> str:
    """A clean base URL without a trailing slash.

    Raises:
        InvalidRequestError: If it is not an http(s) address, carries a password, query or
            fragment, uses plain http for a non-local provider, or claims to be local while
            pointing at a public address.
    """
    text = value.strip()
    try:
        url = URL(text)
    except InvalidURL:
        raise InvalidRequestError("The address is not valid.") from None
    if url.scheme not in ("http", "https") or not url.host:
        raise InvalidRequestError("The address must start with http:// or https://.")
    if url.userinfo or url.query or url.fragment:
        raise InvalidRequestError("The address cannot hold a password, query or fragment.")
    local_host = is_local_host(url.host)
    if location is DataLocation.LOCAL and not local_host:
        raise InvalidRequestError(
            "A provider can only be marked local when its address is on this server or a "
            "private network (localhost, a private IP address, or a name without dots)."
        )
    if url.scheme == "http" and not local_host:
        raise InvalidRequestError("Use https:// for a provider that is not on a private network.")
    return text.rstrip("/")
