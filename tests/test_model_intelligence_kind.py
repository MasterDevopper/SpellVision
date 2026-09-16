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
    """Assert the VALUE. `kind in KINDS` was a tautology over `KIND_VOCABULARY.get(x, "other")`:
    every input produces a member of KINDS, so a stub answering "checkpoint" for everything
    passed under a name promising the opposite."""
    reply = _classify_reply(
        worker_client({"command": "classify_models", "paths": ["C:/somewhere/mystery.bin"]})
    )
    assert reply["classifications"][0]["kind"] == "other"


def test_the_sidecar_and_the_page_answer_the_same_kind():
    """One vocabulary. It used to be declared in worker_service and re-derived in refresh."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
    from model_intelligence import kinds

    assert set(kinds.KINDS) == KINDS
    assert kinds.normalise_kind("unknown") == "other"
    assert kinds.normalise_kind("video_stack") == "other"
    assert kinds.normalise_family("unknown") is None
    assert kinds.normalise_family("sdxl") == "sdxl"
