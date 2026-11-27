"""Anti-SSRF outbound URL & redirect IP validator + safe XML guard for SAQA."""
from __future__ import annotations

import ipaddress
import re
import socket
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_XML_DANGEROUS_RE = re.compile(r"<!(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


def is_private_or_metadata_ip(ip_str: str) -> bool:
    """Return True if an IP literal falls in loopback, private RFC1918, link-local (169.254/16), or reserved space."""
    try:
        addr = ipaddress.ip_address(ip_str.strip("[]"))
    except ValueError:
        return False
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def host_is_private_or_local(hostname: str, *, resolve_dns: bool = False) -> bool:
    """Check whether a hostname is loopback, an IP literal in private/metadata space, or resolves to one."""
    host = hostname.strip().lower().strip("[]")
    if not host:
        return True
    if host in _LOOPBACK_HOSTS or host.endswith(".localhost") or host.endswith(".internal"):
        return True
    if is_private_or_metadata_ip(host):
        return True
    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            for info in infos:
                resolved_ip = str(info[4][0])
                if is_private_or_metadata_ip(resolved_ip):
                    return True
        except OSError:
            return False
    return False


def validate_safe_outbound_url(
    url: str,
    *,
    allow_private: bool = False,
    resolve_dns: bool = False,
    label: str = "target",
) -> str:
    """Validate HTTP(S) URL without embedded credentials and optionally block SSRF private/metadata targets."""
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid {label} URL: {url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} URL must not contain embedded credentials")
    if not allow_private and host_is_private_or_local(parsed.hostname, resolve_dns=resolve_dns):
        raise ValueError(
            f"SSRF blocked: {label} host {parsed.hostname!r} targets private, loopback, or cloud-metadata address space"
        )
    return cleaned


def safe_parse_xml(xml_text: str) -> ET.Element:
    """Parse XML safely by rejecting DOCTYPE/ENTITY declarations (prevents XXE & Billion Laughs)."""
    if _XML_DANGEROUS_RE.search(xml_text):
        raise ValueError("Unsafe XML rejected: DOCTYPE and ENTITY declarations are disallowed")
    return ET.fromstring(xml_text)  # noqa: S314
