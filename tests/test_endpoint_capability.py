"""Before a job is sent to a machine, that machine has to be able to run it -- and say why not.

W6 lets a job be queued on a second box. The recorded live run against the 3090 Ti (2026-09-01)
proved the *transport* works: a 904-class ``/object_info`` came back over the wire and a 1.28 MB PNG
came back through ``/view``, first try. Nothing proved the job would RUN there, and the two failure
modes that follow are both silent:

* the node has a different model set (its ComfyUI walks its own model dirs, not ours), so a
  checkpoint the cockpit offers is simply absent and ComfyUI answers with a 400 naming a node the
  user never chose;
* the node has a different node-pack set, so a class in the graph does not exist there.

So the gate is three checks in cost order, each of which must be able to name what was missing.
"Cannot run there" is not an answer a user can act on; "SpellNode does not have
loxsUtopicWorldKrea2_v20Quants.safetensors" is.

**Health is ``/system_stats`` and never a model listing.** The research recorded
``cifs_wait_for_server_reconnect`` stalling a ComfyUI start when the model share's host was down,
and ComfyUI's ``folder_paths`` walks its model directories to answer a filename list. A health
check built on a model listing therefore hangs exactly when the node is in the state the health
check exists to detect. ``test_a_hung_model_listing_does_not_hang_the_health_check`` is that fact.

Everything here runs against a stdlib HTTP server stood up in-process. The real ComfyUI on :8188 is
never touched.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

import endpoint_capability as cap  # noqa: E402


# --- a fake ComfyUI ---------------------------------------------------------------------------

def _combo(options: list[str]) -> list:
    return [list(options), {}]


def _v3_combo(options: list[str]) -> list:
    """The other shape the same core publishes. A reader that knows one is wrong half the time."""
    return ["COMBO", {"options": list(options)}]


DEFAULT_OBJECT_INFO = {
    "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": _combo(["sdxl/base.safetensors"])}}},
    "LoraLoader": {"input": {"required": {"lora_name": _v3_combo(["style/house.safetensors"])}}},
    "CLIPTextEncode": {"input": {"required": {"text": ["STRING", {}]}}},
    "KSampler": {"input": {"required": {"seed": ["INT", {}]}}},
    "VAEDecode": {"input": {"required": {}}},
    "SaveImage": {"input": {"required": {}}},
}

DEFAULT_MODELS = {
    "checkpoints": ["sdxl/base.safetensors"],
    "loras": ["style/house.safetensors"],
}


class FakeComfy:
    """A ComfyUI-shaped HTTP server. Every knob is a failure mode the gate has to name."""

    def __init__(self) -> None:
        self.object_info = json.loads(json.dumps(DEFAULT_OBJECT_INFO))
        self.models = dict(DEFAULT_MODELS)
        self.models_delay_sec = 0.0
        self.system_stats = {"system": {"comfyui_version": "0.34.0"}, "devices": []}
        self.hits: list[str] = []
        self._httpd: HTTPServer | None = None
        self._url = ""

    # -- lifecycle
    def start(self) -> "FakeComfy":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802 - stdlib naming
                outer.hits.append(self.path)
                if self.path == "/system_stats":
                    return self._json(200, outer.system_stats)
                if self.path == "/object_info":
                    return self._json(200, outer.object_info)
                if self.path.startswith("/models/"):
                    if outer.models_delay_sec:
                        time.sleep(outer.models_delay_sec)
                    folder = self.path[len("/models/"):]
                    if folder not in outer.models:
                        return self._json(404, {"error": "unknown folder"})
                    return self._json(200, outer.models[folder])
                return self._json(404, {"error": "not found"})

            def _json(self, status: int, payload):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # keep pytest output clean
                pass

        self._httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self._url = f"http://127.0.0.1:{self._httpd.server_port}"
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    @property
    def url(self) -> str:
        # Survives stop(): the offline test needs the address of a server that is no longer there.
        assert self._url
        return self._url


@pytest.fixture
def comfy():
    server = FakeComfy().start()
    cap.forget_endpoint(server.url)
    try:
        yield server
    finally:
        cap.forget_endpoint(server.url)
        server.stop()


PROMPT = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdxl/base.safetensors"}},
    "2": {"class_type": "LoraLoader", "inputs": {"lora_name": "style/house.safetensors", "strength_model": 0.8}},
    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat"}},
    "4": {"class_type": "KSampler", "inputs": {"seed": 1}},
    "5": {"class_type": "VAEDecode", "inputs": {}},
    "6": {"class_type": "SaveImage", "inputs": {}},
}


# --- the three checks -------------------------------------------------------------------------

def test_a_healthy_endpoint_with_everything_present_passes(comfy):
    report = cap.check_endpoint(PROMPT, comfy.url)
    assert report.ok, report.explain()
    assert report.refusals == ()
    assert [c for c in report.checks_run] == ["health", "models", "nodes"]


def test_an_offline_endpoint_refuses_naming_health(comfy):
    comfy.stop()
    report = cap.check_endpoint(PROMPT, comfy.url, health_timeout_sec=2.0)
    assert not report.ok
    assert [r.check for r in report.refusals] == ["health"]
    assert "health" in report.explain().lower()
    # Cost order: nothing more expensive was attempted once health failed.
    assert report.checks_run == ("health",)


def test_a_missing_checkpoint_refuses_naming_the_file(comfy):
    comfy.models["checkpoints"] = ["sdxl/something-else.safetensors"]
    comfy.object_info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = _combo(
        ["sdxl/something-else.safetensors"]
    )
    report = cap.check_endpoint(PROMPT, comfy.url)
    assert not report.ok
    assert [r.check for r in report.refusals] == ["models"]
    assert "sdxl/base.safetensors" in report.explain()
    assert report.missing_models() == ("sdxl/base.safetensors",)


def test_a_missing_lora_is_found_through_the_v3_combo_shape(comfy):
    """The core publishes both combo shapes at once; a reader that knows one is wrong for the other."""
    comfy.models.pop("loras")  # no /models/loras -> fall back to /object_info
    comfy.object_info["LoraLoader"]["input"]["required"]["lora_name"] = _v3_combo(["style/other.safetensors"])
    report = cap.check_endpoint(PROMPT, comfy.url)
    assert not report.ok
    assert report.missing_models() == ("style/house.safetensors",)


def test_a_missing_node_class_refuses_naming_the_class(comfy):
    del comfy.object_info["VAEDecode"]
    report = cap.check_endpoint(PROMPT, comfy.url)
    assert not report.ok
    assert [r.check for r in report.refusals] == ["nodes"]
    assert "VAEDecode" in report.explain()
    assert report.missing_classes() == ("VAEDecode",)


def test_a_hung_model_listing_does_not_hang_the_health_check(comfy):
    """A dead CIFS mount is what makes a model listing hang, and it is the state health must report."""
    comfy.models_delay_sec = 30.0
    started = time.monotonic()
    health = cap.endpoint_health(comfy.url, timeout_sec=5.0)
    elapsed = time.monotonic() - started
    assert health["ok"], health
    assert elapsed < 3.0, f"health took {elapsed:.1f}s -- it touched a model listing"
    assert comfy.hits == ["/system_stats"]


def test_a_hung_model_listing_refuses_rather_than_blocking(comfy):
    """Fail closed also covers "could not find out": an unanswerable listing is not a pass."""
    comfy.models_delay_sec = 10.0
    started = time.monotonic()
    report = cap.check_endpoint(PROMPT, comfy.url, models_timeout_sec=1.0, object_info_timeout_sec=1.0)
    elapsed = time.monotonic() - started
    assert not report.ok
    assert elapsed < 8.0, f"the gate blocked for {elapsed:.1f}s on a listing it gave 1s"
    assert [r.check for r in report.refusals] == ["models"]


# --- fail-closed shape ------------------------------------------------------------------------

def test_an_unreadable_prompt_refuses_rather_than_passing_vacuously():
    """An empty graph has nothing missing. That must not read as "yes, it can run there"."""
    report = cap.check_endpoint({}, "http://127.0.0.1:9")
    assert not report.ok
    assert "no graph" in report.explain().lower() or "empty" in report.explain().lower()


def test_an_input_the_endpoint_publishes_no_catalog_for_is_not_called_missing(comfy):
    """`model_name` on a node with a free-string input is not a model reference.

    /object_info's combo is the authority on whether an input is a catalogued file at all. Treating
    every name-shaped input as a model would refuse graphs for files that are not files.
    """
    comfy.object_info["SomeNode"] = {"input": {"required": {"model_name": ["STRING", {}]}}}
    prompt = dict(PROMPT)
    prompt["7"] = {"class_type": "SomeNode", "inputs": {"model_name": "not-a-file"}}
    report = cap.check_endpoint(prompt, comfy.url)
    assert report.ok, report.explain()


def test_the_payload_is_serialisable_and_names_the_endpoint(comfy):
    comfy.models["checkpoints"] = []
    comfy.object_info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = _combo([])
    report = cap.check_endpoint(PROMPT, comfy.url)
    payload = report.payload()
    assert json.loads(json.dumps(payload))["endpoint"] == comfy.url
    assert payload["ok"] is False
    assert payload["refusals"][0]["missing"]


# --- the worker command -----------------------------------------------------------------------

def test_the_command_answers_for_an_explicit_endpoint_and_prompt(comfy):
    import endpoint_commands

    reply = endpoint_commands.handle_endpoint_capability_command({
        "command": "endpoint_capability",
        "comfy_api_url": comfy.url,
        "prompt": PROMPT,
    })
    assert reply["type"] == "endpoint_capability"
    assert reply["ok"] is True
    assert reply["endpoint"] == comfy.url


def test_the_command_refuses_with_a_reason_a_user_can_act_on(comfy):
    import endpoint_commands

    comfy.models["checkpoints"] = []
    comfy.object_info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = _combo([])
    reply = endpoint_commands.handle_endpoint_capability_command({
        "comfy_api_url": comfy.url,
        "prompt": PROMPT,
        "endpoint_label": "SpellNode",
    })
    assert reply["ok"] is False
    assert "SpellNode" in reply["message"]
    assert "sdxl/base.safetensors" in reply["message"]


def test_the_command_refuses_without_a_graph():
    import endpoint_commands

    reply = endpoint_commands.handle_endpoint_capability_command({"comfy_api_url": "http://127.0.0.1:9"})
    assert reply["ok"] is False
    assert reply["type"] == "endpoint_capability"
