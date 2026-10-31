"""
File Overview: Server-side request forgery (SSRF) guard for user-supplied webhook URLs.

All Functions/Classes:
- UnsafeUrlError: Raised with a client-safe reason when a URL must not be called.
- assert_public_https_url: Require https and a hostname that resolves only to public addresses.

The check runs when a rule is created and again before every delivery (a hostname can be
re-pointed after creation). Redirects are not followed by the webhook client.

Endpoints/APIs: DNS resolution only.

Database Tables: None
"""
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeUrlError(ValueError):
    pass


def assert_public_https_url(url: str, allow_private: bool = False) -> None:
    """Raise UnsafeUrlError unless url is https and every resolved address is publicly routable.

    Blocking (DNS); call through asyncio.to_thread from async code.
    """
    parts = urlsplit(str(url))
    if parts.scheme != "https" and not allow_private:
        raise UnsafeUrlError("Webhook URL must use https")
    if parts.scheme not in ("https", "http"):
        raise UnsafeUrlError("Webhook URL must be http(s)")
    host = parts.hostname
    if not host:
        raise UnsafeUrlError("Webhook URL has no host")
    if allow_private:
        return

    try:
        infos = socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise UnsafeUrlError(f"Webhook host '{host}' does not resolve")

    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global or address.is_multicast:
            raise UnsafeUrlError(f"Webhook host '{host}' resolves to a non-public address")
