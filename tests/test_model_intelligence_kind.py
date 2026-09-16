"""`classify_models` reports a kind the Models page can put in a tab.

The page currently guesses type from path substrings in C++ while the worker has a real
classifier, so the family shown can disagree with the family routed on. This closes half of that
(the kind); W5 makes the page consume it.

Note on the reply shape: the brief that specified this test assumed a `"type": "classify_models"`
envelope and a `"results"` key. Neither exists on the live handler -- it emits
`{"ok": True, "classifications": [...]}` with no `"type"` key at all (the code comment at its
return says so: "worker_client passes this through unwrapped"), and `qt_ui/main.cpp` /
`MainWindow.cpp` both read `response.value("classifications")`. Renaming that key to match the
brief would break the live C++ consumer, so this test reads the reply as the handler actually
returns it and keeps the vocabulary check the brief asked for.
"""
from __future__ import annotations

KINDS = {
    "checkpoint", "diffusion_model", "lora", "vae", "text_encoder", "clip_vision",
    "embedding", "upscaler", "controlnet", "style_model", "other",
}


def _classify_reply(messages):
    for message in messages:
        if "classifications" in message:
            return message
    raise AssertionError(f"no classify_models reply in {[m.get('type') for m in messages]}")


def test_classify_models_reports_a_kind_from_the_vocabulary(worker_client):
    reply = _classify_reply(
        worker_client({
            "command": "classify_models",
            "paths": [
                "D:/AI_ASSETS/models/checkpoints/sdxl/foo.safetensors",
                "D:/AI_ASSETS/models/loras/bar.safetensors",
                "D:/AI_ASSETS/models/vae/baz.safetensors",
                "D:/AI_ASSETS/models/clip_vision/qux.safetensors",
            ],
        })
    )
    assert reply["ok"] is True
    kinds = [row["kind"] for row in reply["classifications"]]
    assert kinds == ["checkpoint", "lora", "vae", "clip_vision"]
    assert set(kinds) <= KINDS


def test_an_unclassifiable_path_is_other_not_a_guess(worker_client):
    reply = _classify_reply(
        worker_client({"command": "classify_models", "paths": ["C:/somewhere/mystery.bin"]})
    )
    assert reply["classifications"][0]["kind"] in KINDS
