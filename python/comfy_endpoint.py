"""The one place that decides which ComfyUI to talk to.

Before this, 26 sites across 12 modules each resolved the endpoint their own way, and they did not
agree:

* ``comfy_prompt_client`` read ``COMFY_API_URL`` then ``SPELLVISION_COMFY_URL`` — but only in one
  of its two resolvers; the other skipped ``SPELLVISION_COMFY_URL`` entirely.
* ``comfy_bootstrap`` used a different pair of variables altogether
  (``SPELLVISION_COMFY_HOST`` + ``SPELLVISION_COMFY_PORT``).
* ``ltx_requeue_draft_submission`` used a fifth name, ``SPELLVISION_COMFY_ENDPOINT``.
* ``clothes_only`` and ``look_completion`` hardcoded ``http://127.0.0.1:8188`` as a module constant
  and read no environment at all.

So pointing SpellVision at a ComfyUI on another machine — the second-render-box idea — would have
moved *some* paths and silently left others on localhost. A health check would report success from
the remote host while generation ran locally. That is the same "looks correct while being wrong"
shape as the inert sampler dropdown, and it is why this is one resolver rather than a tidy-up.

## Precedence

Highest to lowest, first non-empty wins:

1. ``req["comfy_api_url"]`` — an explicit per-request override.
2. ``req["comfy_host"]`` / ``req["comfy_port"]`` — the per-request pair the worker already accepted.
3. ``COMFY_API_URL``
4. ``SPELLVISION_COMFY_URL``
5. ``SPELLVISION_COMFY_ENDPOINT``
6. ``SPELLVISION_COMFY_HOST`` + ``SPELLVISION_COMFY_PORT``
7. ``http://127.0.0.1:8188``

Every previously-used name is still honoured, so nothing that worked stops working — they just all
feed one chain now instead of four. New configuration should use ``COMFY_API_URL``.

Not to be confused with ``SPELLVISION_COMFY``, which is the ComfyUI **install directory**
(``runtime_paths``), not the HTTP endpoint. The two are independent: a remote endpoint has no local
install path.
"""
from __future__ import annotations

import os
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8188
DEFAULT_ENDPOINT = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"

# In precedence order. Kept as data so the ordering is inspectable and testable rather than buried
# in an `or` chain that has to be read carefully to be trusted.
ENDPOINT_ENV_VARS = ("COMFY_API_URL", "SPELLVISION_COMFY_URL", "SPELLVISION_COMFY_ENDPOINT")
HOST_ENV_VAR = "SPELLVISION_COMFY_HOST"
PORT_ENV_VAR = "SPELLVISION_COMFY_PORT"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize(url: str) -> str:
    """A bare host:port becomes a URL; a trailing slash is dropped.

    ``COMFY_API_URL=otherbox:8188`` is the obvious thing to type and used to produce a URL urllib
    rejects, so it is accepted rather than punished.
    """
    text = _clean(url).rstrip("/")
    if not text:
        return ""
    if "://" not in text:
        text = f"http://{text}"
    return text


def comfy_endpoint(req: Any = None) -> str:
    """The ComfyUI base URL for this request, e.g. ``http://127.0.0.1:8188``. Never empty."""
    if isinstance(req, dict):
        explicit = _normalize(req.get("comfy_api_url") or req.get("comfy_endpoint"))
        if explicit:
            return explicit
        host = _clean(req.get("comfy_host"))
        if host:
            port = _clean(req.get("comfy_port")) or str(DEFAULT_PORT)
            return _normalize(f"{host}:{port}")

    for name in ENDPOINT_ENV_VARS:
        found = _normalize(os.environ.get(name))
        if found:
            return found

    host = _clean(os.environ.get(HOST_ENV_VAR))
    port = _clean(os.environ.get(PORT_ENV_VAR))
    if host or port:
        return _normalize(f"{host or DEFAULT_HOST}:{port or DEFAULT_PORT}")

    return DEFAULT_ENDPOINT


def comfy_host(req: Any = None) -> str:
    """Host portion of the resolved endpoint, for callers that need the pair rather than a URL."""
    from urllib.parse import urlparse

    parsed = urlparse(comfy_endpoint(req))
    return parsed.hostname or DEFAULT_HOST


def comfy_port(req: Any = None) -> int:
    from urllib.parse import urlparse

    parsed = urlparse(comfy_endpoint(req))
    try:
        return int(parsed.port or DEFAULT_PORT)
    except (TypeError, ValueError):
        return DEFAULT_PORT


def is_local_endpoint(req: Any = None) -> bool:
    """Whether the resolved ComfyUI runs on this machine.

    Load-bearing for anything that manages the ComfyUI *process* or reads its *files*: starting,
    stopping, installing node packs into ``custom_nodes/``, or reading an output from disk are all
    meaningless against a remote endpoint. A caller that manages the install must check this rather
    than assume co-location, which every such call site previously did.
    """
    host = comfy_host(req).lower()
    if host in {"localhost", DEFAULT_HOST, "::1", "0.0.0.0"}:
        return True
    import ipaddress

    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
