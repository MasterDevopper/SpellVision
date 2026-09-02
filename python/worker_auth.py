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
from pathlib import Path
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


# --- What a permitted command may CARRY --------------------------------------------------------
#
# INTEGRATION_COMMANDS bounds which commands a token holder may run. It did not bound what those
# commands could be told to do, and three request fields the permitted commands honour without
# restriction turned the "generation only" tier into arbitrary local file read and write:
#
#   comfy_api_url   point the worker at any host -- ensure_running accepts anything answering 200
#   input_image     _upload_comfy_image reads ANY local file (only is_file() is checked) and POSTs
#                   it to that host
#   output          _download_comfy_asset writes whatever that host's /view returns to that path
#
# So one i2i request could upload ~/.ssh/id_rsa to an attacker and write the attacker's bytes into
# the Startup folder -- exactly the "install a pack / overwrite a credential" class the tier was
# written to exclude, reached through the commands it allows. The command name was the wrong unit
# of authorisation; the request schema is the right one.

# Fields that choose WHICH machine, WHICH install, or WHERE on this disk the worker reads or
# writes. An integration caller may ask for a render; it may not choose any of these. Refused,
# not stripped: silently dropping a field changes what the caller asked for while reporting
# success, which is the failure shape this whole audit exists to remove.
INTEGRATION_FORBIDDEN_FIELDS: frozenset[str] = frozenset({
    # Which ComfyUI answers. A caller that can move this can receive every upload and author every
    # download.
    "comfy_api_url", "comfy_endpoint", "comfy_host", "comfy_port",
    # Which install and which interpreter. comfy_runtime_status honours comfy_root and mkdirs
    # under it; that is an arbitrary directory creation plus a filesystem oracle.
    "comfy_root", "python_executable",
    # Arbitrary local READS. comfy_workflow POSTs the JSON at workflow_path to the endpoint;
    # classify_models opens every entry in paths and returns str(exc) -- an existence oracle.
    # workflow_profile_path and compiled_prompt_path are the aliases the same readers accept
    # (comfy_prompt_client:821, worker_service:1225) -- found by the tree-wide test, not the audit.
    "workflow_path", "profile_path", "workflow_profile_path", "compiled_prompt_path", "paths",
    # Arbitrary local roots that other writes are resolved against. models_root is read by the
    # upscaler branch in image_runners (currently unreachable -- realesrgan is not installed --
    # and gated anyway, because "unreachable today" is a property of the venv, not the code).
    "cache_root", "install_root", "dataset_root", "output_root", "metadata_output", "models_root",
})

# Local files a generation may READ. For an integration caller each must sit under the integration
# root; a ComfyUI-side name (input_image_comfy_name) is not a local path and is not checked here.
INTEGRATION_LOCAL_INPUT_FIELDS: frozenset[str] = frozenset({
    "input_image", "mask", "mask_image", "inpaint_mask",
    "video_input_image", "input_keyframe", "keyframe_image", "source_image",
    "reference_image", "control_image",
})

# The task an integration caller may put on the queue. `enqueue` is a wrapper; the wrapped command
# is what runs, and QueueManager.enqueue admits comfy_workflow (arbitrary graphs plus a local JSON
# read) and every video route, none of which INTEGRATION_COMMANDS lists. Same opt-in rule as that
# list: widening this is one deliberate line, never a side effect of adding a queue route.
INTEGRATION_QUEUE_TASKS: frozenset[str] = frozenset({"t2i", "i2i"})

INTEGRATION_ROOT_ENV = "SPELLVISION_INTEGRATION_ROOT"


def integration_root() -> Path:
    """The one directory an integration caller may read inputs from and write outputs into.

    Configurable so a deployment can put it on a share the integration also mounts; defaults to a
    subtree of the worker's own state root so that with no configuration at all the boundary still
    exists.
    """
    configured = str(os.environ.get(INTEGRATION_ROOT_ENV) or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    from worker_durable_state import worker_state_root

    return (worker_state_root() / "integration").resolve()


def _is_within(candidate: Any, root: Path) -> bool:
    """Whether ``candidate`` resolves to ``root`` or somewhere beneath it.

    Resolved on both sides so ``..`` segments, symlinks and drive-relative forms cannot slip a path
    out of the root while still looking like it starts with the root's text.
    """
    try:
        resolved = Path(str(candidate)).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    try:
        resolved.relative_to(root)
        return True
    except ValueError:
        return False


def _queued_task(req: dict[str, Any]) -> str:
    """Mirror of QueueManager.enqueue's own key precedence, so the two cannot disagree about which
    field names the task."""
    for key in ("task_command", "generation_command", "task"):
        value = str(req.get(key) or "").strip().lower()
        if value:
            return value
    return ""


def request_violations(level: str, command: str, req: Any) -> list[str]:
    """Why an INTEGRATION request must be refused. Empty when it is acceptable.

    Applied AFTER ``permits`` said the command itself is allowed. LOCAL_TRUSTED requests are never
    inspected here -- the local UI legitimately sets every one of these fields.

    Each reason names the field, so an integration author learns what to change rather than only
    that something was refused. None of them echoes the field's value: an output path or an input
    path is itself information about this machine.
    """
    if level != INTEGRATION or not isinstance(req, dict):
        return []
    out: list[str] = []

    for field in sorted(INTEGRATION_FORBIDDEN_FIELDS):
        if field in req and req.get(field) not in (None, ""):
            out.append(f"{field!r} is not accepted from integration callers")

    if str(command or "").strip() == "enqueue":
        task = _queued_task(req)
        if task not in INTEGRATION_QUEUE_TASKS:
            out.append(
                f"enqueue of task {task or '<missing>'!r} is not available to integration callers; "
                f"permitted: {', '.join(sorted(INTEGRATION_QUEUE_TASKS))}"
            )

    root = integration_root()
    output = req.get("output")
    if output not in (None, "") and not _is_within(output, root):
        out.append(f"'output' must be under the integration root ({INTEGRATION_ROOT_ENV})")
    for field in sorted(INTEGRATION_LOCAL_INPUT_FIELDS):
        value = req.get(field)
        if value not in (None, "") and not _is_within(value, root):
            out.append(f"{field!r} must be a file under the integration root ({INTEGRATION_ROOT_ENV})")
    return out


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
