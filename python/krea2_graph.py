"""The loader block every Krea 2 graph starts with, written once.

Four graphs build a Krea 2 render and all four open the same way -- UNETLoader, CLIPLoader,
VAELoader, two CLIPTextEncodes, ModelSamplingAuraFlow at shift 1.15 -- with identical node ids and
identical wiring:

    native_image_graphs._build_krea2_image_prompt      t2i / i2i
    krea2_regional_inpaint.build_krea2_regional_...    inpaint
    look_completion.build_krea2_t2i_graph              Character Studio
    clothes_only.build_clothes_only_krea2_graph        garment plates

Only the first passed a ``device`` to the CLIPLoader. That input is what the memory profile uses to
move the 4B text encoder to system RAM when VRAM is tight, so **the same model fitted as t2i and
OOM'd as inpaint** -- the audit's headline duplication finding, and it survived Phase 4c because the
sweep that caught hand-written device values cannot see an OMITTED one. An omission has no syntax.

What is NOT merged is the rest of the graph. The inpaint route runs sixteen nodes through
VAEEncodeForInpaint and ImageCompositeMasked and the t2i routes run ten; forcing one topology on
both would be applying a rule at the wrong level, which is the mistake this audit keeps finding.
The loader block is the part that is genuinely the same, and it is the part the defect lived in.
"""
from __future__ import annotations

from typing import Any

from comfy_graph_helpers import text_encoder_device_input

# ``Krea2.sampling_settings`` via ModelSamplingAuraFlow, multiplier 1.0. Grounded from live Comfy
# source, not from a reference workflow -- all four copies carried the same literal and agreed.
KREA2_SHIFT = 1.15

# The CLIPLoader ``type`` for this family, from CLIPLoader.INPUT_TYPES in nodes.py.
KREA2_CLIP_TYPE = "krea2"

# Node ids the block owns. Fixed rather than generated because all four graphs already used these
# exact ids, so callers keep wiring against the numbers they already reference.
UNET_ID = "1"
CLIP_ID = "2"
VAE_ID = "3"
POSITIVE_ID = "4"
NEGATIVE_ID = "6"


def krea2_loader_block(
    *,
    unet_name: str,
    clip_name: str,
    vae_name: str,
    positive: str,
    negative: str,
    request: dict[str, Any] | None = None,
    object_info: dict[str, Any] | None = None,
    clip_type: str = KREA2_CLIP_TYPE,
    shift: float = KREA2_SHIFT,
    sampling_node_id: str = "5",
) -> dict[str, Any]:
    """The five loader nodes plus the sigma-shift node, wired.

    ``sampling_node_id`` is the one thing the four callers genuinely disagreed about: the t2i graphs
    put ModelSamplingAuraFlow at ``"5"`` and the inpaint graph at ``"7"``. It is a parameter rather
    than a normalisation because renumbering a live graph changes every reference to it for no gain.

    The CLIPLoader's ``device`` comes from the shared resolver, which reads the node's own accepted
    values and falls back to the memory profile. Passing no ``object_info`` yields no device key at
    all -- the same "do not guess a vocabulary you cannot read" rule the resolver applies everywhere.
    """
    return {
        UNET_ID: {"class_type": "UNETLoader",
                  "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        CLIP_ID: {"class_type": "CLIPLoader",
                  "inputs": {"clip_name": clip_name, "type": clip_type,
                             **text_encoder_device_input(request or {}, object_info or {},
                                                         "CLIPLoader")}},
        VAE_ID: {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        POSITIVE_ID: {"class_type": "CLIPTextEncode",
                      "inputs": {"text": positive, "clip": [CLIP_ID, 0]}},
        NEGATIVE_ID: {"class_type": "CLIPTextEncode",
                      "inputs": {"text": negative, "clip": [CLIP_ID, 0]}},
        sampling_node_id: {"class_type": "ModelSamplingAuraFlow",
                           "inputs": {"model": [UNET_ID, 0], "shift": float(shift)}},
    }
