"""Credentials must not reach the on-disk queue manifest.

The manifest is plain JSON, written on every state change and kept across restarts, so anything in
a `request_snapshot` is persisted verbatim. No credential-bearing command is enqueued today --
import_workflow, start_download and civitai_variants are control commands that never touch the
queue -- so this is defence in depth. It is here because the failure mode is silent and permanent:
the day someone enqueues a command carrying a key, the key lands in a file and nothing reports it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from worker_queue import SECRET_REQUEST_KEYS, redact_secrets  # noqa: E402


def test_known_credential_keys_are_replaced():
    payload = {"command": "t2i", "civitai_api_key": "sk-secret", "hf_token": "hf_secret",
               "prompt": "a cat"}
    redacted = redact_secrets(payload)
    assert redacted["civitai_api_key"] == "<redacted>"
    assert redacted["hf_token"] == "<redacted>"
    assert redacted["prompt"] == "a cat", "non-secret values must survive untouched"


def test_matching_is_case_insensitive():
    assert redact_secrets({"Civitai_API_Key": "s"})["Civitai_API_Key"] == "<redacted>"
    assert redact_secrets({"AUTHORIZATION": "Bearer s"})["AUTHORIZATION"] == "<redacted>"


def test_nested_structures_are_walked():
    payload = {"outer": {"inner": {"api_key": "s"}}, "list": [{"hf_token": "s"}, "plain"]}
    redacted = redact_secrets(payload)
    assert redacted["outer"]["inner"]["api_key"] == "<redacted>"
    assert redacted["list"][0]["hf_token"] == "<redacted>"
    assert redacted["list"][1] == "plain"


def test_the_original_is_not_mutated():
    """The worker still needs the real value; only the persisted copy is redacted."""
    payload = {"civitai_api_key": "sk-secret"}
    redact_secrets(payload)
    assert payload["civitai_api_key"] == "sk-secret"


def test_non_dict_input_passes_through():
    assert redact_secrets("plain") == "plain"
    assert redact_secrets(7) == 7
    assert redact_secrets(None) is None


def test_the_secret_key_set_covers_what_this_repo_actually_sends():
    """Every credential name the worker protocol carries must be in the set, or it persists."""
    for name in ("civitai_api_key", "hf_token"):
        assert name in SECRET_REQUEST_KEYS
