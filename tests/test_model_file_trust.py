"""Loading a model must not be able to run code, and our safety here is SOMEBODY ELSE'S default.

Doc 28's security gate reads "Model-file trust | Prefer `.safetensors`; pickle formats gated +
documented". Measured on this box before writing anything:

| | |
|---|---|
| `.safetensors` under the model root | **702** |
| pickle formats (`.pt` / `.pth` / `.bin`) | **10** |
| `torch.load` calls in SpellVision's own tree | **0** |

And every loader in the stack that reads those ten already refuses to unpickle arbitrary objects:

* `comfy/utils.py` -> `torch.load(..., weights_only=True)`
* `UpscaleModelLoader` -> `comfy.utils.load_torch_file(model_path, safe_load=True)` -- which matters
  here, because `4x-UltraSharp.pth` is the Auto pick for the upscale tier, i.e. the pickle file the
  product reaches for by default
* `diffusers/models/model_loading_utils.py` -> `weights_only=True`
* torch itself has defaulted `weights_only=True` since 2.6; this box runs 2.10

**So the gate is already met, and nothing recorded it.** The deliverable is therefore evidence and a
regression guard, NOT a warning badge: telling a user to fear a `.pth` whose loader cannot execute
it is theatre, and theatre in a security surface is worse than silence because it spends attention
that a real warning will later need.

What is genuinely fragile is that all four facts above are third-party defaults. A torch downgrade,
a diffusers change, or a ComfyUI patch could flip any of them without a line changing in this repo,
and nothing would notice. That is what these tests are for.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

PICKLE_SUFFIXES = (".pt", ".pth", ".bin", ".ckpt")


def test_torch_refuses_to_unpickle_by_default() -> None:
    """`weights_only` defaults to True from torch 2.6. If a downgrade ever flips it back, every
    pickle checkpoint on disk becomes an execution path again."""
    torch = pytest.importorskip("torch")
    signature = inspect.signature(torch.load)
    default = signature.parameters["weights_only"].default
    assert default is not False, (
        f"torch {torch.__version__} defaults torch.load(weights_only={default!r}). Loading a "
        "pickle checkpoint can then execute arbitrary code, and 10 such files sit under the model "
        "root -- including 4x-UltraSharp.pth, the upscale tier's Auto pick."
    )


def test_diffusers_asks_for_weights_only() -> None:
    """The worker's own image path loads checkpoints through diffusers."""
    loading = pytest.importorskip("diffusers.models.model_loading_utils")
    source = inspect.getsource(loading)
    assert "weights_only" in source, (
        "diffusers no longer names weights_only in model_loading_utils; the single-file loader may "
        "be unpickling. Re-read it before trusting a .ckpt."
    )


def test_the_comfy_core_loads_checkpoints_with_weights_only() -> None:
    """ComfyUI is a separate process with its own venv, so its default is not ours to set -- but it
    reads the same files, and it is the loader for every native family."""
    from comfy_root import LIVE_COMFY  # noqa: PLC0415

    utils = Path(LIVE_COMFY) / "comfy" / "utils.py"
    if not utils.is_file():
        pytest.skip(f"the live ComfyUI core is not on this machine ({utils})")
    source = utils.read_text(encoding="utf-8", errors="replace")
    assert "weights_only=True" in source, (
        "comfy/utils.py no longer loads with weights_only=True. Every native family reads its "
        "checkpoint through it, and 10 pickle-format files sit under the model root."
    )


def test_the_upscale_loader_does_not_bypass_it() -> None:
    """`UpscaleModelLoader` is the one that matters most: the tier's Auto pick is a `.pth`, so this
    is the pickle the product loads by DEFAULT rather than only when a user chooses one."""
    from comfy_root import LIVE_COMFY  # noqa: PLC0415

    node = Path(LIVE_COMFY) / "comfy_extras" / "nodes_upscale_model.py"
    if not node.is_file():
        pytest.skip(f"the live ComfyUI core is not on this machine ({node})")
    source = node.read_text(encoding="utf-8", errors="replace")
    assert "safe_load=True" in source, (
        "UpscaleModelLoader no longer passes safe_load=True, so an upscale model is unpickled. The "
        "upscale tier's Auto pick is 4x-UltraSharp.pth."
    )
