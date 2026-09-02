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

import atexit
import hmac
import ipaddress
import json
import os
import secrets
import tempfile
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
# Loopback, no token, and no (or a missing) session secret while one is enforced. May only `ping`.
# This is what a probe, an adopting launcher, and another Windows account's process all look like
# before the secret has been read -- the first two go on to read it; the third cannot.
LOCAL_PROBE = "local_probe"

# --- The session secret --------------------------------------------------------------------------
#
# Loopback is not a per-user boundary. A second, unprivileged Windows account on a shared PC -- or
# any sandboxed process that can open a TCP socket -- reaches 127.0.0.1:8765 exactly as the
# SpellVision user does, and LOCAL_TRUSTED handed it install_custom_node (pip + an arbitrary GitHub
# repo), start_download with the victim's stored Civitai/HF keys, set_credential, and every write
# path the integration schema now refuses to integration callers. The old docstring's defence --
# "anything that can reach loopback already runs code on this machine" -- holds for the SAME user,
# not across users. v1.0 ships to arbitrary machines, some of them shared.
#
# The boundary that exists on every OS is the filesystem ACL. So the worker generates a secret per
# launch and writes it to a file only the launching user can read; a client proves it is the same
# user by reading that file and presenting the secret. The worker owns the secret rather than the
# UI, because the UI does not always spawn the worker -- run_ui.ps1 starts the backend separately
# and the UI ADOPTS it -- and a secret passed through a child environment would never reach an
# adopting parent. A file at a location both sides compute independently reaches everyone.
#
# Unauthenticated loopback keeps exactly one command, ping, so probes and the adopt path still work.

SESSION_FIELD = "session_secret"
SESSION_SECRET_ENV = "SPELLVISION_WORKER_SESSION_SECRET"   # a launcher may supply the value
SESSION_FILE_ENV = "SPELLVISION_WORKER_SESSION_FILE"       # a harness may relocate the file
PROBE_COMMANDS: frozenset[str] = frozenset({"ping"})

_ACTIVE_SESSION_SECRET = ""   # set by establish_session() in the worker process


def session_file_path(port: int | str | None = None) -> Path:
    """Where the running worker on ``port`` publishes its session secret.

    Keyed by port so a test worker on a free port and the app's worker on 8765 never overwrite
    each other. Overridable by SESSION_FILE_ENV so a harness can put it in a temp directory.
    """
    configured = str(os.environ.get(SESSION_FILE_ENV) or "").strip()
    if configured:
        return Path(configured).expanduser()
    from app_paths import app_data_dir

    if port is None:
        port = os.environ.get("SPELLVISION_WORKER_PORT", "8765")
    return app_data_dir() / f"worker_session_{port}.json"


def read_session_secret(port: int | str | None = None) -> str:
    """What a CLIENT presents. The environment first so a launcher can hand it down; then the file
    the worker wrote. Empty when neither exists -- the client then gets LOCAL_PROBE and a refusal
    that names the file, which is the right outcome for a client that cannot read it."""
    from_env = str(os.environ.get(SESSION_SECRET_ENV) or "").strip()
    if from_env:
        return from_env
    try:
        payload = json.loads(session_file_path(port).read_text(encoding="utf-8"))
        return str(payload.get("secret") or "").strip()
    except (OSError, ValueError, AttributeError):
        return ""


def configured_session_secret() -> str:
    """What the WORKER enforces. The one it established at startup; else the environment; else
    nothing -- and nothing means the session gate is off, which is the state of every unit test that
    calls classify() directly and of any worker started outside main()."""
    if _ACTIVE_SESSION_SECRET:
        return _ACTIVE_SESSION_SECRET
    return str(os.environ.get(SESSION_SECRET_ENV) or "").strip()


def establish_session(port: int | str) -> Path:
    """Generate (or adopt from the environment) this launch's secret and publish it to the session
    file with a user-only ACL. Called once by worker_service.main() before the socket binds.

    Fails CLOSED: if the file cannot be written the worker does not start. The alternative --
    starting with the gate off -- would silently restore the cross-account exposure on exactly the
    machines whose permissions are unusual enough to hit this, and say nothing.
    """
    global _ACTIVE_SESSION_SECRET
    secret = str(os.environ.get(SESSION_SECRET_ENV) or "").strip() or secrets.token_hex(32)
    path = session_file_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Written to a sibling temp file, ACL-narrowed, then moved into place, so no reader ever sees a
    # world-readable moment or a half-written file.
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"secret": secret, "port": int(port), "pid": os.getpid()}, fh)
        from credential_store import _restrict_acl

        if not _restrict_acl(tmp):
            raise RuntimeError(
                f"Could not restrict the worker session file {path} to the current user. Refusing "
                f"to start: without that ACL the session secret is readable by other accounts and "
                f"the loopback boundary it enforces does not exist."
            )
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    _ACTIVE_SESSION_SECRET = secret

    def _cleanup() -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    atexit.register(_cleanup)
    return path


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


def classify(request: Any, *, peer_host: str = "", token: str | None = None,
             session: str | None = None) -> str:
    """The access level for one request: LOCAL_TRUSTED, INTEGRATION, LOCAL_PROBE or DENIED.

    ``token`` and ``session`` exist so tests can pin what is configured without touching the
    environment or the filesystem; production callers pass neither.
    """
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

    if not is_loopback(peer_host):
        return DENIED

    # Loopback. Whether that is enough depends on whether this worker established a session.
    expected_session = str(session if session is not None else configured_session_secret() or "").strip()
    if not expected_session:
        # No session gate: a worker started outside main(), or a unit test calling classify()
        # directly. Loopback alone is trusted, as it always was. main() always establishes one, so
        # the shipped worker is never in this state.
        return LOCAL_TRUSTED

    presented_session = ""
    if isinstance(request, dict):
        presented_session = str(request.get(SESSION_FIELD) or "").strip()
    if presented_session and hmac.compare_digest(presented_session, expected_session):
        return LOCAL_TRUSTED
    if presented_session:
        # A wrong secret is never better than none -- same rule as a wrong token.
        return DENIED
    return LOCAL_PROBE


def permits(level: str, command: str) -> bool:
    if level == LOCAL_TRUSTED:
        return True
    if level == INTEGRATION:
        return str(command or "").strip() in INTEGRATION_COMMANDS
    if level == LOCAL_PROBE:
        return str(command or "").strip() in PROBE_COMMANDS
    return False


def denial_message(level: str, command: str) -> str:
    """What to tell the caller. Says which reason applies, and never leaks the token or secret."""
    if level == DENIED:
        return (
            "Not authorised. This worker requires a valid integration token in the "
            f"{TOKEN_FIELD!r} field for connections that present one, and a valid "
            f"{SESSION_FIELD!r} for local callers when a session is enforced."
        )
    if level == LOCAL_PROBE:
        return (
            f"The command {command!r} requires this launch's session secret in the "
            f"{SESSION_FIELD!r} field. The worker publishes it to {session_file_path()} for the "
            f"user that started it; a client that cannot read that file is not that user. "
            f"Unauthenticated local callers may only: " + ", ".join(sorted(PROBE_COMMANDS)) + "."
        )
    return (
        f"The command {command!r} is not available to integration callers. Permitted: "
        + ", ".join(sorted(INTEGRATION_COMMANDS))
        + "."
    )
