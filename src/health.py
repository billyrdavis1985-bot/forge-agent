"""
health.py — dead-man's switch.

Pings healthchecks.io (or any compatible endpoint) at run start, success, and
failure. If the timer stops firing, or runs start failing silently, the check
goes red and you get told. Without this, an unattended agent can be dead for a
week before you notice.

Design rule: monitoring must NEVER break the thing it monitors. Every ping is
best-effort with a short timeout, and all network errors are swallowed.
Configure via HEALTHCHECK_URL env var; absent = pings disabled, no-op.
"""

from __future__ import annotations

import os
import urllib.request

_TIMEOUT = 5


def _ping(suffix: str = "", payload: str | None = None) -> None:
    base = os.environ.get("HEALTHCHECK_URL", "").strip()
    if not base:
        return  # monitoring not configured; silently disabled
    url = base.rstrip("/") + suffix
    try:
        data = payload.encode("utf-8")[:10_000] if payload else None
        urllib.request.urlopen(url, data=data, timeout=_TIMEOUT)
    except Exception:
        pass  # never let a monitoring failure affect the run


def start() -> None:
    _ping("/start")


def success(summary: str | None = None) -> None:
    _ping("", summary)


def failure(reason: str | None = None) -> None:
    _ping("/fail", reason)
