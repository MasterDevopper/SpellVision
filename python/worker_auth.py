"""Who is allowed to talk to the worker, and which commands they may use.

The worker protocol had no authentication of any kind. Its bind address is a single environment
variable (``SPELLVISION_WORKER_HOST``, default ``127.0.0.1``), so one setting away from a listener
on every interface — and the command surface includes ``install_custom_node`` (fetches GitHub
zipballs and runs pip), ``import_model_url`` (writes downloads to arbitrary paths), ``enqueue``
(writes to any ``output`` path) and ``comfy_workflow`` (executes arbitrary graphs). Exposed, that
is remote code execution on the workstation. Loopback was the only thing preventing it.

## The model

Two levels, because a local UI and an external integration want different things.

``LOCAL_TRUSTED``
    A connection on the loopback interface that presents no token. Full command surface. This is
    the SpellVision UI, and its behaviour is unchanged whether or not a token is configured — the
    app keeps working with no configuration, and configuring a token for SpellBound does not
    silently lock the UI out.

``INTEGRATION``
    A caller presenting the configured token. Restricted to ``INTEGRATION_COMMANDS``: generation,
    queue observation, and status. **Not** node installation, model import, credential access or
    runtime mutation. A token is deliberately not a promotion to full trust — an external program
    asking SpellVision for a character concept has no business installing custom nodes.

Anything else is denied before dispatch.

## Deployment shape (owner decision, 2026-08-28)

Loopback bind + an SSH tunnel, rather than binding to a network interface. SSH provides the
transport encryption and the first authentication factor; the token identifies the integration and
bounds what it can reach. **This protocol is plaintext** — it is fine inside a tunnel or on a
trusted wired LAN, and is not something to expose directly to an untrusted network.

Because a tunnelled connection arrives *from* ``127.0.0.1``, the source address cannot distinguish
SpellBound from the local UI. That is why the token, not the peer address, selects the level — a
caller that presents the token is *choosing* the restricted surface.

Being precise about what that buys: over a tunnel the real authentication is SSH's, and anything
already able to reach loopback can run code on this machine anyway. The token's value here is
**bounding an integration to what it should need**, so a bug in SpellBound cannot install a node
pack or overwrite a credential — and defence in depth if the bind address is ever changed.

## Fail closed

Binding anywhere other than loopback without a token configured refuses to start
(``assert_bind_is_safe``). The dangerous configuration must be the hard one to reach.
"""
from __future__ import annotations

import hmac
import ipaddress
import os
from typing import Any

# The credential name used when the token is stored in the DPAPI store rather than the environment.
TOKEN_CREDENTIAL = "worker_integration_token"
TOKEN_ENV = "SPELLVISION_WORKER_TOKEN"

# The request field carrying the token. Listed in worker_queue.SECRET_REQUEST_KEYS so it is redacted
# out of the persisted queue manifest, and never logged anywhere.
TOKEN_FIELD = "auth_token"

LOCAL_TRUSTED = "local_trusted"
INTEGRATION = "integration"
DENIED = "denied"

# What a token-bearing external caller may do. Deliberately a small, explicit list rather than
# "everything except the scary ones" -- a new command must be opted IN, so adding one cannot widen
# the remote surface by accident.
#
# Chosen for what SpellBound Engine actually needs: submit generation work, watch it, collect the
# result, and ask what the runtime supports.
INTEGRATION_COMMANDS: frozenset[str] = frozenset({
    # Submit and observe work.
    "enqueue", "queue_status",
    "cancel_queue_item", "cancel_active_queue_item", "remove_queue_item",
    # Direct generation (the non-queued path).
    "t2i", "i2i",
    # Liveness and capability discovery.
    "ping", "comfy_runtime_status", "video_family_contracts",
    # Read-only classification, so a caller can ask what a model is before requesting it.
    "classify_models",
})


def configured_token() -> str:
    """The integration token, or an empty string when none is set.

    Environment first so a service or tunnel can supply it without touching the user's store, then
    the DPAPI credential store. Never logged, never echoed in a response.
    """
    from_env = str(os.environ.get(TOKEN_ENV) or "").strip()
    if from_env:
        return from_env
    try:
        from credential_store import get_credential

        return str(get_credential(TOKEN_CREDENTIAL) or "").strip()
    except Exception:
        # A store that cannot be read must not crash the worker; it means "no token configured",
        # which on a loopback bind is the normal, working case.
        return ""


def is_loopback(host: str) -> bool:
    """Whether a bind address reaches only this machine."""
    value = str(host or "").strip()
    if not value:
        return False
    if value.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        # A hostname that is not plainly localhost cannot be assumed safe.
        return False


def assert_bind_is_safe(host: str, *, token: str | None = None) -> None:
    """Refuse to start a non-loopback listener that anyone could drive.

    Raises ``RuntimeError`` rather than warning, because the failure mode being prevented is an
    unauthenticated remote-code-execution surface, and a warning in a log nobody reads is not a
    control.
    """
    if is_loopback(host):
        return
    if str(token if token is not None else configured_token() or "").strip():
        return
    raise RuntimeError(
        f"Refusing to bind the worker to {host!r} with no integration token configured.\n"
        f"The worker protocol can install node packs, download files and execute graphs, so an "
        f"unauthenticated non-loopback listener is a remote code execution surface.\n"
        f"Either bind to 127.0.0.1 (the default, and the supported shape -- reach it over an SSH "
        f"tunnel), or set {TOKEN_ENV} / the {TOKEN_CREDENTIAL!r} credential first."
    )


def classify(request: Any, *, peer_host: str = "", token: str | None = None) -> str:
    """The access level for one request: LOCAL_TRUSTED, INTEGRATION or DENIED."""
    expected = str(token if token is not None else configured_token() or "").strip()
    presented = ""
    if isinstance(request, dict):
        presented = str(request.get(TOKEN_FIELD) or "").strip()

    if expected and presented and hmac.compare_digest(presented, expected):
        return INTEGRATION

    if presented:
        # A token was offered and did not match. Never fall through to local trust on a bad token,
        # even from loopback -- that would make a wrong token strictly better than no token.
        return DENIED

    # Loopback stays trusted whether or not a token is configured. Requiring one here would break
    # the SpellVision UI the moment an integration token was set, and it would break it silently and
    # only for the user who enabled the feature -- the worst possible time to discover it.
    #
    # This is defensible rather than lax: anything that can reach loopback already runs code on this
    # machine as some user, so the worker is not the security boundary there. The boundary is the
    # bind address, which assert_bind_is_safe holds closed.
    if is_loopback(peer_host):
        return LOCAL_TRUSTED

    return DENIED


def permits(level: str, command: str) -> bool:
    if level == LOCAL_TRUSTED:
        return True
    if level == INTEGRATION:
        return str(command or "").strip() in INTEGRATION_COMMANDS
    return False


def denial_message(level: str, command: str) -> str:
    """What to tell the caller. Says which of the two reasons applies, and never leaks the token."""
    if level == DENIED:
        return (
            "Not authorised. This worker requires a valid integration token in the "
            f"{TOKEN_FIELD!r} field for connections that present one, and accepts unauthenticated "
            "requests only from the loopback interface when no token is configured."
        )
    return (
        f"The command {command!r} is not available to integration callers. Permitted: "
        + ", ".join(sorted(INTEGRATION_COMMANDS))
        + "."
    )
