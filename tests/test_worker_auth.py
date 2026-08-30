"""Authorisation on the worker protocol.

The protocol had none. Its bind address is one environment variable away from every interface, and
the command surface includes ``install_custom_node`` (GitHub zipballs + pip), ``import_model_url``
(arbitrary write paths), ``enqueue`` (arbitrary output path) and ``comfy_workflow`` (arbitrary
graphs). Exposed, that is remote code execution on the workstation; loopback was the only control.

Deployment shape is loopback + SSH tunnel (owner decision, 2026-08-28). A tunnelled connection
ARRIVES from ``127.0.0.1``, so the peer address cannot tell SpellBound from the local UI — which is
exactly why the token, not the address, selects the access level.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

# Tree-wide property, not a call-site check: the integration surface stays a small explicit allowlist.
# Runs in the pre-commit hook -- keep it fast.
pytestmark = pytest.mark.ratchet

import worker_auth  # noqa: E402
from worker_auth import (  # noqa: E402
    DENIED,
    INTEGRATION,
    INTEGRATION_COMMANDS,
    LOCAL_TRUSTED,
    assert_bind_is_safe,
    classify,
    is_loopback,
    permits,
)

TOKEN = "s3cret-integration-token"


# --- the two levels -----------------------------------------------------------------------------


def test_the_local_ui_keeps_working_with_no_token_configured():
    """The app must not need configuring. Loopback plus no token is the everyday case."""
    assert classify({"command": "enqueue"}, peer_host="127.0.0.1", token="") == LOCAL_TRUSTED
    assert permits(LOCAL_TRUSTED, "install_custom_node") is True


def test_a_valid_token_is_an_integration_not_a_promotion_to_full_trust():
    """A token identifies an external program, and an external program asking for a character
    concept has no business installing custom nodes."""
    level = classify({"command": "enqueue", "auth_token": TOKEN}, peer_host="10.0.0.5", token=TOKEN)
    assert level == INTEGRATION
    assert permits(level, "enqueue") is True
    assert permits(level, "install_custom_node") is False
    assert permits(level, "import_model_url") is False
    assert permits(level, "save_credential") is False


def test_a_wrong_token_is_denied_even_from_loopback():
    """Never fall through to local trust on a bad token -- that would make presenting a wrong token
    strictly better than presenting none at all."""
    assert classify({"auth_token": "wrong"}, peer_host="127.0.0.1", token=TOKEN) == DENIED


def test_a_missing_token_from_a_remote_peer_is_denied():
    assert classify({"command": "ping"}, peer_host="192.168.1.50", token="") == DENIED
    assert classify({"command": "ping"}, peer_host="192.168.1.50", token=TOKEN) == DENIED


def test_the_comparison_is_constant_time():
    """A naive == leaks the token a character at a time under timing analysis."""
    import inspect

    assert "compare_digest" in inspect.getsource(worker_auth.classify)


# --- the integration surface --------------------------------------------------------------------


@pytest.mark.parametrize("command", [
    "install_custom_node", "install_comfy_manager", "import_model_url", "inspect_model_url",
    "save_credential", "clear_credential", "credential_status", "secrets_status",
    "restart_comfy_runtime", "stop_comfy_runtime", "generate_dataset", "import_workflow",
    "build_node_class_index",
])
def test_dangerous_commands_are_not_reachable_by_an_integration(command):
    assert command not in INTEGRATION_COMMANDS
    assert permits(INTEGRATION, command) is False


@pytest.mark.parametrize("command", ["enqueue", "queue_status", "t2i", "i2i", "ping"])
def test_the_commands_spellbound_needs_are_reachable(command):
    assert permits(INTEGRATION, command) is True


def test_the_integration_list_is_an_opt_in_allowlist_not_a_denylist():
    """A new worker command must not widen the remote surface merely by existing.

    Checked against the real dispatch table: everything an integration can reach is named
    explicitly, so the default for anything new is "not reachable".
    """
    from test_worker_command_audience import dispatched_commands

    known = dispatched_commands()
    assert INTEGRATION_COMMANDS <= known, "the allowlist names a command that does not exist"
    assert len(INTEGRATION_COMMANDS) < len(known) / 2, (
        "the integration surface has grown to most of the protocol; it is meant to stay a small "
        "explicit subset"
    )


# --- fail closed ----------------------------------------------------------------------------------


def test_binding_beyond_loopback_without_a_token_refuses_to_start():
    with pytest.raises(RuntimeError, match="Refusing to bind"):
        assert_bind_is_safe("0.0.0.0", token="")
    with pytest.raises(RuntimeError, match="Refusing to bind"):
        assert_bind_is_safe("192.168.1.10", token="   ")


def test_binding_beyond_loopback_is_allowed_once_a_token_exists():
    assert_bind_is_safe("0.0.0.0", token=TOKEN)


def test_loopback_never_requires_a_token():
    for host in ("127.0.0.1", "localhost", "::1"):
        assert is_loopback(host), host
        assert_bind_is_safe(host, token="")


def test_a_hostname_is_not_assumed_to_be_loopback():
    """A name that is not plainly localhost must fail safe rather than be resolved and trusted."""
    assert is_loopback("workstation.lan") is False
    assert is_loopback("") is False
    with pytest.raises(RuntimeError):
        assert_bind_is_safe("workstation.lan", token="")


# --- the token itself -------------------------------------------------------------------------------


def test_the_token_is_redacted_out_of_the_persisted_queue_manifest():
    """An enqueued request carries the token, and the manifest is plain JSON on disk."""
    from worker_queue import SECRET_REQUEST_KEYS, redact_secrets

    assert worker_auth.TOKEN_FIELD in SECRET_REQUEST_KEYS
    cleaned = redact_secrets({"command": "enqueue", "auth_token": TOKEN, "prompt": "a cat"})
    assert cleaned["auth_token"] == "<redacted>"
    assert cleaned["prompt"] == "a cat"


def test_the_denial_message_never_contains_the_token():
    for level in (DENIED, INTEGRATION):
        assert TOKEN not in worker_auth.denial_message(level, "install_custom_node")


def test_the_token_can_live_in_the_dpapi_store():
    from credential_store import KNOWN_KEYS

    assert worker_auth.TOKEN_CREDENTIAL in KNOWN_KEYS


def test_an_unreadable_credential_store_means_no_token_rather_than_a_crash(monkeypatch):
    """On a loopback bind, "no token" is the normal working case; it must not take the worker down."""
    monkeypatch.delenv(worker_auth.TOKEN_ENV, raising=False)
    import credential_store

    def explode(*args, **kwargs):
        raise OSError("store unreadable")

    monkeypatch.setattr(credential_store, "get_credential", explode)
    assert worker_auth.configured_token() == ""


def test_the_environment_token_wins_over_the_store(monkeypatch):
    monkeypatch.setenv(worker_auth.TOKEN_ENV, "from-env")
    assert worker_auth.configured_token() == "from-env"


def test_configuring_a_token_does_not_lock_the_local_ui_out():
    """The regression this policy got wrong on the first attempt.

    An earlier version required a token from everyone once one was configured, so enabling
    SpellBound access would have broken the SpellVision UI -- silently, and only for the user who
    turned the feature on. Loopback is trusted whether or not a token exists.
    """
    assert classify({"command": "enqueue"}, peer_host="127.0.0.1", token=TOKEN) == LOCAL_TRUSTED
    assert classify({"command": "install_custom_node"}, peer_host="127.0.0.1", token=TOKEN) == LOCAL_TRUSTED


def test_a_tunnelled_caller_presenting_the_token_chooses_the_restricted_surface():
    """SpellBound reaches loopback through the SSH tunnel, so it could omit the token and get full
    trust. Presenting it is what bounds the integration -- protection against a bug in SpellBound
    rather than against an attacker who already has shell on this machine."""
    assert classify({"auth_token": TOKEN}, peer_host="127.0.0.1", token=TOKEN) == INTEGRATION
    assert permits(INTEGRATION, "install_custom_node") is False
