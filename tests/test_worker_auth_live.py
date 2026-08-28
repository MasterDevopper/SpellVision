"""The auth gate over the real TCP protocol, against a live worker.

The unit tests drive the policy in-process. These prove the other half: that the gate is actually
IN the request path and rejects before dispatch, rather than being a module nothing calls -- the
"registered the seam" failure this codebase has hit repeatedly.

The session worker runs with no token configured, which is the shipping default, so these cover the
LOCAL_TRUSTED path and the bad-token rejection. Token-bearing integration behaviour is covered by
the unit tests, which can vary the configured token freely.
"""
from __future__ import annotations


def test_a_normal_request_still_works_over_the_wire(worker_client):
    """The gate must not have broken the ordinary path."""
    messages = worker_client({"command": "ping"})
    assert messages
    assert not any(m.get("type") == "auth_error" for m in messages), messages


def test_an_unknown_token_is_rejected_before_dispatch(worker_client):
    """A token that matches nothing configured is DENIED even from loopback -- otherwise offering a
    wrong token would be strictly better than offering none."""
    messages = worker_client({"command": "ping", "auth_token": "definitely-not-the-token"})
    errors = [m for m in messages if m.get("type") == "auth_error"]
    assert errors, f"the auth gate did not fire: {messages}"
    assert errors[0]["ok"] is False
    assert "Not authorised" in errors[0]["error"]


def test_the_rejection_says_nothing_about_the_configured_token(worker_client):
    """An unauthorised caller learns whether it was the token or the command, and nothing else."""
    messages = worker_client({"command": "install_custom_node", "auth_token": "wrong"})
    errors = [m for m in messages if m.get("type") == "auth_error"]
    assert errors
    text = errors[0]["error"]
    assert "wrong" not in text.lower().replace("not authorised", "")
    assert "traceback" not in errors[0]


def test_a_rejected_request_does_not_execute_the_command(worker_client):
    """The point of gating before dispatch: install_custom_node must not run."""
    messages = worker_client({"command": "install_custom_node", "auth_token": "wrong",
                              "repo": "https://example.invalid/should-never-be-fetched"})
    assert [m for m in messages if m.get("type") == "auth_error"]
    assert not any(m.get("type") in {"node_install_ack", "job_update"} for m in messages), messages
