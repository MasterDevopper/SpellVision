"""The tiling switch had nowhere to land.

``enable_vae_tiling`` is inserted into EVERY request the cockpit builds. Eleven image decode sites
wrote a bare ``VAEDecode`` node literal, so on every image route the answer "yes, tile" went
nowhere. The video side had the mirror-image problem: hunyuan and mochi hardcoded
``VAEDecodeTiled``, which is the same decision taken away from the user rather than offered -- a
request setting the flag to false could not turn it off.

Decode-side memory is the lever that matters here. The FP8 measurement established that peak VRAM is
driven by activations and VAE decode rather than by weights, which is why a quantized checkpoint
bought only ~1.5 GB where "large headroom" had been assumed.

**No speed or memory claim is attached to tiling.** Doc 50 rule 1 says a heuristic ships with a
number, and there is no measurement for tiled image decode on this box. So nothing decides to tile
on the user's behalf: tiling is a CONTROL, and a family that wants it on by default has to DECLARE
that (``default_tiled=True``) rather than reach it by omitting a call. What was wrong was never the
absence of a default -- it was that the switch was unreachable.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from comfy_graph_helpers import vae_decode_node  # noqa: E402

TILED_INFO = {
    "VAEDecode": {"input": {"required": {"samples": ["LATENT"], "vae": ["VAE"]}}},
    "VAEDecodeTiled": {"input": {"required": {
        "samples": ["LATENT"], "vae": ["VAE"],
        "tile_size": ["INT", {"default": 512}],
        "overlap": ["INT", {"default": 64}],
        "temporal_size": ["INT", {"default": 64}],
        "temporal_overlap": ["INT", {"default": 8}],
    }}},
}
UNTILED_CORE = {"VAEDecode": {"input": {"required": {"samples": ["LATENT"], "vae": ["VAE"]}}}}

SAMPLES = ["8", 0]
VAE = ["3", 0]


def _decode(req, info=TILED_INFO, **kwargs):
    return vae_decode_node(req, info, samples=SAMPLES, vae=VAE, **kwargs)


# --- the switch reaches the graph ---------------------------------------------------------------

def test_the_default_is_untiled_and_nothing_decides_otherwise() -> None:
    """No heuristic. There is no measurement for tiled image decode, so nothing infers one."""
    assert _decode({})["class_type"] == "VAEDecode"


def test_asking_for_tiling_produces_the_tiled_node() -> None:
    node = _decode({"enable_vae_tiling": True})
    assert node["class_type"] == "VAEDecodeTiled"
    assert node["inputs"]["samples"] == SAMPLES and node["inputs"]["vae"] == VAE


def test_a_declaring_family_tiles_and_can_still_be_turned_off() -> None:
    """hunyuan and mochi hardcoded VAEDecodeTiled. They needed the headroom at video frame counts,
    which is a fine reason to default it on -- and not a reason the user cannot say no."""
    assert _decode({}, default_tiled=True)["class_type"] == "VAEDecodeTiled"
    assert _decode({"enable_vae_tiling": False}, default_tiled=True)["class_type"] == "VAEDecode"
    assert _decode({"enable_vae_tiling": True}, default_tiled=True)["class_type"] == "VAEDecodeTiled"


def test_an_absent_key_is_not_a_stated_false() -> None:
    """The distinction that makes `default_tiled` work at all: a request that never mentions tiling
    takes the family's declaration, while one that says false overrides it."""
    assert _decode({}, default_tiled=True)["class_type"] == "VAEDecodeTiled"
    assert _decode({"enable_vae_tiling": None}, default_tiled=True)["class_type"] == "VAEDecodeTiled"
    assert _decode({"enable_vae_tiling": 0}, default_tiled=True)["class_type"] == "VAEDecode"


# --- sizing comes from the node ------------------------------------------------------------------

def test_the_sizing_defaults_are_read_from_the_node(caplog) -> None:
    node = _decode({"enable_vae_tiling": True})
    assert node["inputs"]["tile_size"] == 512
    assert node["inputs"]["overlap"] == 64
    assert node["inputs"]["temporal_size"] == 64
    assert node["inputs"]["temporal_overlap"] == 8


def test_a_stated_tile_size_wins() -> None:
    node = _decode({"enable_vae_tiling": True, "vae_tile_tile_size": 768})
    assert node["inputs"]["tile_size"] == 768


def test_an_input_the_node_does_not_declare_is_not_sent() -> None:
    """Adding a key a node does not declare is a 400 -- an older core's VAEDecodeTiled has no
    temporal inputs at all."""
    older = {"VAEDecodeTiled": {"input": {"required": {
        "samples": ["LATENT"], "vae": ["VAE"], "tile_size": ["INT", {"default": 512}]}}}}
    node = _decode({"enable_vae_tiling": True}, info=older)
    assert set(node["inputs"]) == {"samples", "vae", "tile_size"}


# --- a core without the node ---------------------------------------------------------------------

def test_a_core_without_the_tiled_node_renders_untiled_and_says_so(caplog) -> None:
    """Refusing would be worse than decoding untiled: the user asked for less memory, not for no
    picture. Saying nothing would be worse still -- they would believe tiling was in effect."""
    import logging

    with caplog.at_level(logging.WARNING):
        node = _decode({"enable_vae_tiling": True}, info=UNTILED_CORE)
    assert node["class_type"] == "VAEDecode"
    assert any("VAEDecodeTiled" in r.getMessage() for r in caplog.records)


def test_an_empty_object_info_still_produces_a_usable_node() -> None:
    """Builders are called with {} in several tests, and a decode is not optional."""
    assert vae_decode_node({}, {}, samples=SAMPLES, vae=VAE)["class_type"] == "VAEDecode"
    assert vae_decode_node({"enable_vae_tiling": True}, {},
                           samples=SAMPLES, vae=VAE)["class_type"] == "VAEDecodeTiled"


# --- every builder goes through it ----------------------------------------------------------------

def test_no_builder_still_writes_a_decode_literal() -> None:
    """The sweep owns this tree-wide; asserted here so the rule's subject stays visible in the file
    that explains it. The two exemptions are the resolver naming the classes it chooses between."""
    sys.path.insert(0, str(ROOT / "tests"))
    from sweeps import exemptions, rules

    rule = [r for r in rules.ALL_RULES if r.name == "latent-decode-through-one-resolver"][0]
    exempt = exemptions.EXEMPT[rule.name]
    unexplained = [str(v) for v in rule.run() if v.site not in exempt]
    assert not unexplained, unexplained


@pytest.mark.parametrize("module", [
    "native_image_graphs", "clothes_only", "look_completion",
    "krea2_regional_inpaint", "qwen_image_edit_graph",
])
def test_every_image_builder_imports_the_resolver(module: str) -> None:
    source = (ROOT / "python" / f"{module}.py").read_text(encoding="utf-8")
    assert "vae_decode_node" in source, f"{module} still decodes on its own"
