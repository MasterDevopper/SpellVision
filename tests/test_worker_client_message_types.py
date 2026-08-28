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


@pytest.mark.parametrize(
    "message_type",
    sorted(worker_client.MODEL_RESOLUTION_MESSAGE_TYPES | worker_client.DOWNLOAD_MESSAGE_TYPES),
)
def test_new_response_types_pass_through_unwrapped(message_type):
    payload = {"type": message_type, "ok": True, "offers": [{"wanted": "a.safetensors"}]}
    result = normalize(payload)
    assert result["type"] == message_type, "must not be wrapped in client_warning"
    assert result.get("offers") == [{"wanted": "a.safetensors"}], "the payload must survive intact"


def test_an_unregistered_type_is_wrapped_and_that_envelope_is_the_hazard():
    """Pinning the hazard itself, so the reason the registration matters stays visible."""
    result = normalize({"type": "totally_new_type", "ok": False, "error": "boom"})
    assert result["type"] == "client_warning"
    assert result["ok"] is True, "the envelope reports success regardless of the payload"
    assert result["raw"]["ok"] is False


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
