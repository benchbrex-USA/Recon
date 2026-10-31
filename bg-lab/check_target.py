#!/usr/bin/env python3
"""Shared authorization gate for BG Lab exploit scripts.

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

Lab rule (mirrors bg-recon and the security-tools skill): exploit scripts
default to private/loopback targets only. A public IP or public DNS name
requires an explicit --allow-external flag — the caller's acknowledgment that
the target is owned or written-scope authorized.
"""
from __future__ import annotations

import ipaddress
import re
import socket


class UnauthorizedTarget(Exception):
    pass


def resolve(target: str) -> list[str]:
    target = target.strip().strip("[]")
    target = re.sub(r"^[a-z]+://", "", target, flags=re.IGNORECASE).split("/")[0]
    target = target.split(":")[0]
    try:
        infos = socket.getaddrinfo(target, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnauthorizedTarget(f"cannot resolve {target!r}: {exc}") from exc
    ips: list[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    return ips


def assert_authorized(target: str, allow_external: bool = False) -> list[str]:
    """Return resolved IPs or raise UnauthorizedTarget."""
    ips = resolve(target)
    if not ips:
        raise UnauthorizedTarget(f"{target!r} resolved to nothing")
    local = all(
        (lambda a: a.is_loopback or a.is_private)(ipaddress.ip_address(ip))
        for ip in ips
    )
    if local or allow_external:
        return ips
    raise UnauthorizedTarget(
        f"{target} resolves to public address(es) {', '.join(ips)}. "
        "Pass --allow-external ONLY for systems you own or hold written scope for."
    )
