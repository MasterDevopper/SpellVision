"""Commands that manage the local ComfyUI install must refuse when the endpoint is remote.

Starting or stopping the process, and installing node packs into this machine's ``custom_nodes/``,
are meaningless against a ComfyUI running elsewhere — the pack would land in a tree that endpoint
never reads.

This is the same failure the stale ``SPELLVISION_COMFY`` env var caused: it pointed at the rollback
install, so Install Manager and Install Selected Node would have operated on a tree nothing reads
**and reported success**. Before ``comfy_endpoint.is_local_endpoint()`` there was no way to tell.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import worker_tcp  # noqa: E402
from worker_tcp import LOCAL_INSTALL_COMMANDS  # noqa: E402

REMOTE = {"comfy_api_url": "http://gpubox:8188"}


def test_the_guarded_set_is_exactly_the_install_managing_commands():
    """Named explicitly rather than pattern-matched, so a new command is a deliberate decision."""
    assert LOCAL_INSTALL_COMMANDS == {
        "start_comfy_runtime", "stop_comfy_runtime", "restart_comfy_runtime",
        "ensure_comfy_runtime", "install_comfy_manager", "install_custom_node",
        "install_recommended_video_nodes",
    }


@pytest.mark.parametrize("command", sorted(LOCAL_INSTALL_COMMANDS))
def test_each_is_refused_against_a_remote_endpoint(command, worker_client):
    """Over the real protocol, so this proves the guard is in the request path."""
    messages = worker_client({"command": command, **REMOTE})
    refusals = [m for m in messages if m.get("action") == command and m.get("ok") is False]
    assert refusals, f"{command} was not refused against a remote endpoint: {messages}"

    refusal = refusals[0]
    assert refusal["endpoint_is_local"] is False
    assert "gpubox" in refusal["endpoint"]
    # The message has to say what to do, not just that something is wrong.
    assert "gpubox" in refusal["error"]
    assert "COMFY_API_URL" in refusal["error"]


@pytest.mark.parametrize("command", ["comfy_runtime_status", "comfy_manager_status", "queue_status"])
def test_read_only_status_commands_are_not_blocked(command, worker_client):
    """Status is legitimate against a remote endpoint -- it asks the endpoint, it does not manage a
    local tree. Over-guarding would break the remote case this exists to enable."""
    messages = worker_client({"command": command, **REMOTE})
    blocked = [m for m in messages
               if m.get("action") == command and m.get("endpoint_is_local") is False]
    assert not blocked, f"{command} should not be gated on locality: {messages}"


def test_generation_is_not_blocked_against_a_remote_endpoint(worker_client):
    """The whole point of a remote endpoint is to render on it."""
    messages = worker_client({"command": "ping", **REMOTE})
    assert not any(m.get("endpoint_is_local") is False for m in messages), messages


def test_a_local_endpoint_leaves_the_commands_reachable(worker_client):
    """The guard must not fire in the default configuration."""
    messages = worker_client({"command": "comfy_runtime_status"})
    assert not any(m.get("endpoint_is_local") is False for m in messages), messages
