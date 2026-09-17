"""The ten kinds the Models page tabs are built from, and what "undetermined" means.

This vocabulary shipped TWICE. `worker_service._KIND_VOCABULARY` answered `classify_models` and
mapped the classifier's `"unknown"` to `"other"`; `refresh._kind_and_family` wrote the
classifier's RAW `model_type` into the sidecar. So one weight was `kind: "other"` when the Models
page asked and `kind: "unknown"` when it read the sidecar beside the file, and
`placement.KIND_SUBDIRS` has an entry for neither -- the two-resolvers-for-one-question defect
`placement.py`'s own docstring opens by citing, reproduced one module over.

`normalise_family` is the other half, and it is the one with teeth. The classifier answers
`family="unknown"` -- a TRUTHY string -- for a weight it cannot place. A truthy family suppresses
the `table:family-default` floor in `recommended.build` (`seed_for("unknown")` is `{}`), so a
model nobody could classify silently received no defaults at all, which is the opposite of what
the floor exists for. An undetermined family is None.
"""
from __future__ import annotations

# The classifier's own _L1_TYPE_CATEGORY vocabulary plus "other". A path that classifies as
# nothing gets "other" rather than being filed under checkpoints: a wrong tab is worse than an
# honest one.
KIND_VOCABULARY: dict[str, str] = {
    "checkpoint": "checkpoint",
    "diffusion_model": "diffusion_model",
    "lora": "lora",
    "vae": "vae",
    "text_encoder": "text_encoder",
    "clip_vision": "clip_vision",
    "embedding": "embedding",
    "upscaler": "upscaler",
    "controlnet": "controlnet",
    "style_model": "style_model",
    "video_stack": "other",
    "unknown": "other",
}

KINDS: frozenset[str] = frozenset(KIND_VOCABULARY.values())

# What the classifier says when it could not place the weight. None means the same thing and is
# what every consumer here tests for.
_UNDETERMINED_FAMILIES = frozenset({"", "unknown", "none", "null"})


def normalise_kind(model_type: object) -> str:
    """The tab vocabulary. Anything unrecognised is `other`, never a guess."""
    return KIND_VOCABULARY.get(str(model_type or "").strip().lower(), "other")


def normalise_family(family: object) -> str | None:
    """The registry family, or None when nothing determined one."""
    text = str(family or "").strip()
    return None if text.lower() in _UNDETERMINED_FAMILIES else text
