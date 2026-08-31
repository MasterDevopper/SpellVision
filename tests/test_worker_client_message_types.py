"""Every worker response type the UI relies on must be registered in worker_client.

The failure this guards is silent and reassuring: an unregistered type is wrapped in a
``client_warning`` envelope whose own ``ok`` is **True**, with the real payload buried under
``raw``. A caller reading ``ok`` sees success and an empty result. That is exactly how the model
picker reported "everything is already installed" while the worker had just returned 112
substitution candidates.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import worker_client  # noqa: E402


def normalize(payload):
    return worker_client.normalize_worker_message(payload, None)[0]


def _all_registered_types() -> set[str]:
    """Every registered type, collected from the module rather than from a hand-written list.

    The old version of this test named two sets, so the other fourteen were unverified -- the same
    scoping bug that let nine emitted types go unregistered in the first place.
    """
    return {
        value
        for name, value in vars(worker_client).items()
        if name.endswith("_MESSAGE_TYPES") and isinstance(value, set)
        for value in value
    }


@pytest.mark.parametrize("message_type", sorted(_all_registered_types()))
def test_new_response_types_pass_through_unwrapped(message_type):
    payload = {"type": message_type, "ok": True, "offers": [{"wanted": "a.safetensors"}]}
    result = normalize(payload)
    assert result["type"] == message_type, "must not be wrapped in client_warning"
    assert result.get("offers") == [{"wanted": "a.safetensors"}], "the payload must survive intact"


def test_an_unregistered_type_is_reported_as_a_failure():
    """The envelope used to report ok: TRUE regardless of the payload.

    That default is what made every instance of this class silent -- the model picker showing
    "everything is already installed" over 112 candidates, and an authorisation refusal arriving at
    the UI as a success. Registering the known types fixes today; this flag is what makes the NEXT
    unregistered type loud, which is what rule 7 was always trying to buy.
    """
    result = normalize({"type": "totally_new_type", "ok": False, "error": "boom"})
    assert result["type"] == "client_warning"
    assert result["ok"] is False, "an unknown type is a failure of this client to understand the worker"
    assert result["unknown_type"] == "totally_new_type", "the message must name what it did not know"
    assert result["raw"]["ok"] is False, "the original payload is still carried"


def test_an_auth_refusal_is_not_reported_as_success():
    """The sharpest instance. auth_error was emitted by every command's authorisation gate and
    registered nowhere, so a refusal reached the UI inside an ok: true envelope."""
    result = normalize({"type": "auth_error", "ok": False, "error": "not authorised"})
    assert result["type"] == "auth_error", "must not be wrapped"
    assert result["ok"] is False


def test_every_command_the_ui_sends_has_its_response_type_registered():
    """A command reachable from the UI whose response type is unregistered is a live trap."""
    for command, message_type in [
        ("resolve_missing_models", "model_resolution_offers"),
        ("download_status", "download_status"),
        ("start_download", "download_ack"),
        ("cancel_download", "download_ack"),
    ]:
        assert command in worker_client.CONTROL_COMMANDS, f"{command} is not a control command"
        assert normalize({"type": message_type, "ok": True})["type"] == message_type, (
            f"{command} returns {message_type}, which is not registered"
        )
