"""Loopback is not a per-user boundary. A file only one user can read is.

Security audit finding 2, 2026-09-01. ``classify`` granted LOCAL_TRUSTED -- all 113 commands,
including install_custom_node (pip + an arbitrary GitHub repo), start_download with the stored
Civitai/HF keys, and set_credential -- on the peer address alone. On Windows, loopback is shared by
every account on the machine. A second, unprivileged user on a family PC reached the worker exactly
as the SpellVision user did. The old defence ("anything on loopback already runs code here") holds
for the SAME user, not across users, and v1.0 ships to machines that are shared.

Now the worker generates a secret per launch and publishes it to a user-only file; a client proves
it is the same user by presenting it. Unauthenticated loopback keeps one command, ``ping``, so the
UI's probe and the adopt path still work.

Two lanes here. The classification lane pins ``classify``/``permits`` with the session pinned by
argument, so it needs no worker. The live lane (``needs_worker``, derived from the fixture) proves
the shipped worker actually enforces it over the wire: the fixture presents the secret and gets
everything; a raw socket that presents nothing gets a pong and then a refusal.
"""
from __future__ import annotations

import json
import os
import socket
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import worker_auth  # noqa: E402
from worker_auth import (  # noqa: E402
    DENIED,
    INTEGRATION,
    LOCAL_PROBE,
    LOCAL_TRUSTED,
    PROBE_COMMANDS,
    SESSION_FIELD,
    SESSION_FILE_ENV,
    SESSION_SECRET_ENV,
    classify,
    denial_message,
    permits,
    read_session_secret,
    session_file_path,
)

SECRET = "a" * 64
TOKEN = "integration-token"


# --- classification with a session enforced -----------------------------------------------------

def test_loopback_with_the_right_secret_is_fully_trusted() -> None:
    assert classify({SESSION_FIELD: SECRET}, peer_host="127.0.0.1", token="", session=SECRET) == LOCAL_TRUSTED


def test_loopback_with_no_secret_is_a_probe_not_trusted() -> None:
    """The regression, stated exactly: peer address alone no longer buys the full surface."""
    assert classify({"command": "install_custom_node"}, peer_host="127.0.0.1", token="", session=SECRET) == LOCAL_PROBE


def test_loopback_with_the_wrong_secret_is_denied_not_demoted() -> None:
    """A wrong secret is never better than none -- the same rule as a wrong token. Demoting to
    LOCAL_PROBE would let a guesser keep guessing under the guise of a probe."""
    assert classify({SESSION_FIELD: "b" * 64}, peer_host="127.0.0.1", token="", session=SECRET) == DENIED


def test_a_probe_may_ping_and_nothing_else() -> None:
    assert permits(LOCAL_PROBE, "ping") is True
    for command in ("queue_status", "enqueue", "t2i", "install_custom_node", "set_credential",
                    "start_download", "comfy_runtime_status", "classify_models"):
        assert permits(LOCAL_PROBE, command) is False, command


def test_the_probe_set_is_exactly_ping() -> None:
    """Widening this is a deliberate decision, not a side effect."""
    assert PROBE_COMMANDS == frozenset({"ping"})


def test_a_remote_peer_is_denied_regardless_of_secret() -> None:
    """The secret proves same-user on THIS machine. It is not a network credential; the integration
    token is, and it selects a different tier."""
    assert classify({SESSION_FIELD: SECRET}, peer_host="192.168.1.50", token="", session=SECRET) == DENIED


def test_the_integration_token_still_selects_its_tier_ahead_of_the_session() -> None:
    req = {"auth_token": TOKEN, SESSION_FIELD: SECRET}
    assert classify(req, peer_host="127.0.0.1", token=TOKEN, session=SECRET) == INTEGRATION


def test_a_wrong_token_is_denied_even_with_the_right_session() -> None:
    req = {"auth_token": "wrong", SESSION_FIELD: SECRET}
    assert classify(req, peer_host="127.0.0.1", token=TOKEN, session=SECRET) == DENIED


# --- no session enforced: the legacy shape, kept for direct callers -------------------------------

def test_with_no_session_configured_loopback_is_trusted_as_before(monkeypatch) -> None:
    """Every existing unit test that calls classify() directly relies on this. main() always
    establishes a session, so the SHIPPED worker is never in this state -- see the live lane."""
    monkeypatch.delenv(SESSION_SECRET_ENV, raising=False)
    monkeypatch.setattr(worker_auth, "_ACTIVE_SESSION_SECRET", "")
    assert classify({}, peer_host="127.0.0.1", token="") == LOCAL_TRUSTED


# --- the messages ------------------------------------------------------------------------------

def test_the_probe_refusal_names_the_file_and_never_the_secret(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(SESSION_FILE_ENV, str(tmp_path / "s.json"))
    message = denial_message(LOCAL_PROBE, "queue_status")
    assert "queue_status" in message
    assert str(tmp_path / "s.json") in message, "the caller must learn WHERE the secret lives"
    assert SECRET not in message


def test_the_denied_message_never_contains_a_secret() -> None:
    assert SECRET not in denial_message(DENIED, "anything")


# --- the file ----------------------------------------------------------------------------------

def test_the_session_file_is_keyed_by_port(monkeypatch) -> None:
    monkeypatch.delenv(SESSION_FILE_ENV, raising=False)
    assert session_file_path(8765).name == "worker_session_8765.json"
    assert session_file_path(51234).name == "worker_session_51234.json"


def test_the_session_file_lives_where_the_credential_store_does(monkeypatch) -> None:
    """One per-user directory, computed once (app_paths). If these diverged, the UI would read
    under one spelling while the worker wrote under another, and every request would be refused."""
    monkeypatch.delenv(SESSION_FILE_ENV, raising=False)
    from app_paths import app_data_dir
    import credential_store

    assert session_file_path(8765).parent == app_data_dir()
    assert credential_store.default_store_path().parent == app_data_dir()


def test_establish_session_writes_a_user_only_file_and_arms_the_gate(monkeypatch, tmp_path) -> None:
    path = tmp_path / "session.json"
    monkeypatch.setenv(SESSION_FILE_ENV, str(path))
    monkeypatch.delenv(SESSION_SECRET_ENV, raising=False)
    monkeypatch.setattr(worker_auth, "_ACTIVE_SESSION_SECRET", "")

    written = worker_auth.establish_session(50000)
    assert written == path and path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["secret"]) == 64 and payload["port"] == 50000 and payload["pid"] == os.getpid()
    # Armed in-process: a loopback request without it is now a probe.
    assert classify({}, peer_host="127.0.0.1", token="") == LOCAL_PROBE
    assert classify({SESSION_FIELD: payload["secret"]}, peer_host="127.0.0.1", token="") == LOCAL_TRUSTED
    # And the client-side reader finds the same value.
    assert read_session_secret(50000) == payload["secret"]
    if sys.platform != "win32":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_launcher_may_supply_the_secret_through_the_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(SESSION_FILE_ENV, str(tmp_path / "s.json"))
    monkeypatch.setenv(SESSION_SECRET_ENV, SECRET)
    monkeypatch.setattr(worker_auth, "_ACTIVE_SESSION_SECRET", "")
    worker_auth.establish_session(50001)
    assert json.loads((tmp_path / "s.json").read_text())["secret"] == SECRET
    assert read_session_secret(50001) == SECRET


def test_the_secret_is_redacted_from_persisted_state() -> None:
    from worker_queue import SECRET_REQUEST_KEYS, redact_secrets

    assert SESSION_FIELD in SECRET_REQUEST_KEYS
    assert redact_secrets({SESSION_FIELD: SECRET, "prompt": "x"})[SESSION_FIELD] != SECRET


def test_the_secret_is_dropped_from_the_request_after_classification() -> None:
    source = (ROOT / "python" / "worker_tcp.py").read_text(encoding="utf-8")
    assert "req.pop(worker_auth.SESSION_FIELD, None)" in source


def test_main_establishes_the_session_before_binding() -> None:
    source = (ROOT / "python" / "worker_service.py").read_text(encoding="utf-8")
    body = source[source.index("def main() -> None:"):]
    assert body.index("establish_session(port)") < body.index("ThreadedTCPServer((host, port)")


# --- the live lane: the shipped worker enforces it over the wire ----------------------------------

def _raw(host: str, port: int, payload: dict, timeout: float = 15.0) -> list[dict]:
    out: list[dict] = []
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        sock.shutdown(socket.SHUT_WR)
        buf = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
    for line in buf.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def test_live_the_fixture_client_presents_the_secret_and_gets_the_full_surface(worker_client) -> None:
    messages = worker_client({"command": "queue_status"})
    assert messages and messages[0].get("type") != "auth_error", messages


def test_live_a_bare_local_socket_may_ping(worker_service) -> None:
    messages = _raw(worker_service["host"], worker_service["port"], {"command": "ping"})
    assert messages and messages[0].get("type") != "auth_error", messages


def test_live_a_bare_local_socket_is_refused_everything_else(worker_service) -> None:
    """Another account's process, or any client that could not read the file, looks exactly like
    this. It learns which command was refused and where the secret lives -- and nothing else."""
    messages = _raw(worker_service["host"], worker_service["port"], {"command": "queue_status"})
    assert messages and messages[0].get("type") == "auth_error", messages
    assert messages[0].get("ok") is False
    assert "session_secret" in messages[0].get("error", "")


def test_live_a_wrong_secret_is_denied(worker_service) -> None:
    messages = _raw(worker_service["host"], worker_service["port"],
                    {"command": "ping", SESSION_FIELD: "not-the-secret"})
    assert messages and messages[0].get("type") == "auth_error", messages


def test_live_the_session_file_was_published_where_the_fixture_said(worker_service) -> None:
    path = Path(worker_service["session_file"])
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["port"] == worker_service["port"]
