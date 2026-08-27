"""Tier-4 architecture inference and substitution ranking.

Every case here is drawn from the real 81-workflow library or from a bug the sweep caught, so a
failure names a workflow that regressed rather than an abstract rule.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from model_registry import infer_model_family  # noqa: E402
from workflow_architecture_inference import (  # noqa: E402
    AMBIGUOUS,
    RESOLVED,
    UNKNOWN,
    architecture_of_family,
    infer_required_architecture,
    missing_model_references,
    rank_substitution_candidates,
)


def graph(*nodes: dict) -> dict:
    return {str(i): n for i, n in enumerate(nodes)}


def node(class_type: str, **inputs) -> dict:
    return {"class_type": class_type, "inputs": inputs}


# --- the alias-shadowing bug that made every SDXL checkpoint read as SD1.5 ----------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("sdxl", "sdxl"),                       # the family KEY itself resolved to stable_diffusion
        ("sd-xl", "sdxl"),
        ("sdxl/juggernaut.safetensors", "sdxl"),
        ("sd15/realisticVision.safetensors", "stable_diffusion"),  # "sd"+digit must still match
        ("flux1-dev.safetensors", "flux"),      # version digit flush against the name
        ("wan2.2_i2v.safetensors", "wan"),
        ("ltx-2.3-22b-dev.safetensors", "ltx"),
        ("krea2_turbo_fp8_scaled.safetensors", "krea2"),
        ("Comfy-Org/Krea-2", "krea2"),
        ("juggernautXL_v9.safetensors", "unknown"),  # no token: must NOT invent a family
    ],
)
def test_family_tokens_match_on_boundaries_not_substrings(text, expected):
    assert infer_model_family(text) == expected


def test_lineage_folds_up_to_architecture():
    for lineage in ("pony", "illustrious", "noobai", "animagine"):
        assert architecture_of_family(lineage) == "sdxl"
    assert architecture_of_family("sdxl") == "sdxl"
    assert architecture_of_family("unknown") is None
    assert architecture_of_family(None) is None


# --- signal order ------------------------------------------------------------------------


def test_clip_loader_type_is_normalised_not_compared_literally():
    """A live graph carried type="Wan-2.2 T2V", which matches no hardcoded table."""
    result = infer_required_architecture(graph(node("CLIPLoader", type="Wan-2.2 T2V")))
    assert result.state == RESOLVED
    assert result.architecture == "wan"
    assert result.signals == ("clip_loader_type",)


def test_unambiguous_marker_resolves():
    result = infer_required_architecture(graph(node("EmptyLTXVLatentVideo", length=97)))
    assert (result.state, result.architecture) == (RESOLVED, "ltx")


def test_wanted_model_name_beats_latent_dimensions():
    """endercomic-v1 and simple-t2i-generator: an Illustrious (SDXL) checkpoint at width 512.

    The width>=768 rule fired for SD1.5 exactly twice in the library and was wrong both times.
    """
    g = graph(
        node("EmptyLatentImage", width=512, height=512),
        node("CheckpointLoaderSimple", ckpt_name="illustrijBTTR_v10.safetensors"),
    )
    result = infer_required_architecture(g, wanted_model="illustrijBTTR_v10.safetensors")
    assert result.state == RESOLVED
    assert result.architecture == "sdxl", "the filename must outrank the latent size"
    assert result.signals == ("wanted_model_name",)


def test_latent_dimensions_still_break_a_tie_the_name_cannot():
    g = graph(node("EmptyLatentImage", width=1080, height=1920))
    result = infer_required_architecture(g, wanted_model="nova3DCGXL_ilV70.safetensors")
    assert (result.state, result.architecture) == (RESOLVED, "sdxl")
    assert result.signals == ("latent_dimensions",)
    assert result.confidence < 0.6, "a dimensions-only answer must not look confident"


def test_no_marker_but_the_filename_names_the_architecture():
    """working-image-generator: no marker node, but it wants prefectIllustriousXL_40."""
    result = infer_required_architecture(graph(node("SaveImage")),
                                         wanted_model="prefectIllustriousXL_40.safetensors")
    assert (result.state, result.architecture) == (RESOLVED, "sdxl")


# --- the three states ---------------------------------------------------------------------


def test_ambiguous_marker_stays_ambiguous_rather_than_guessing():
    result = infer_required_architecture(graph(node("EmptySD3LatentImage", width=1024)))
    assert result.state == AMBIGUOUS
    assert result.architecture is None
    assert set(result.candidates) == {"sd3", "flux", "krea2", "lumina"}


def test_ambiguous_markers_intersect_to_narrow_the_set():
    """Two ambiguous markers narrow further than either alone -- but 2 is still not 1."""
    g = graph(node("EmptySD3LatentImage", width=1024), node("ModelSamplingSD3"))
    result = infer_required_architecture(g)
    assert result.state == AMBIGUOUS
    assert set(result.candidates) == {"sd3", "flux"}, "narrowed from 4, still not pinned"


def test_contradicting_markers_report_unknown_rather_than_picking_one():
    """{sd3,flux} intersected with {lumina,krea2} is empty. Empty evidence is not weak
    evidence -- it must not fall through to whichever marker was seen first."""
    g = graph(node("ModelSamplingSD3"), node("ModelSamplingAuraFlow"))
    result = infer_required_architecture(g)
    assert result.state == UNKNOWN
    assert result.architecture is None


def test_unknown_is_its_own_state():
    result = infer_required_architecture(graph(node("SaveImage")))
    assert result.state == UNKNOWN
    assert result.architecture is None
    assert result.candidates == ()
    assert not result.is_resolved


def test_an_unambiguous_marker_beats_a_contradicting_filename():
    g = graph(node("EmptyLTXVLatentVideo", length=97))
    result = infer_required_architecture(g, wanted_model="juggernautXL_v9.safetensors")
    assert result.architecture == "ltx"


# --- missing references -------------------------------------------------------------------


def test_missing_references_normalise_separators_and_case():
    g = graph(node("CheckpointLoaderSimple", ckpt_name="sdxl/Foo.safetensors"),
              node("UNETLoader", unet_name="wan/absent.safetensors"))
    missing = missing_model_references(g, installed=["sdxl\\foo.safetensors"])
    assert missing == ["wan/absent.safetensors"]


# --- ranking ------------------------------------------------------------------------------


CATALOG = [
    "sdxl/juggernautXL_v9.safetensors",
    "sdxl/ponyDiffusionV6XL.safetensors",
    "sdxl/hassakuXLIllustrious_v32.safetensors",
    "sd15/realisticVision.safetensors",
    "flux/flux1-dev.safetensors",
    "ltx/ltx-2.3-22b-dev.safetensors",
]


def test_lineage_is_a_preference_not_a_gate():
    ranked = rank_substitution_candidates("sdxl", "someIllustriousModel.safetensors", CATALOG)
    names = [c.name for c in ranked]
    assert len(names) == 3, "every SDXL checkpoint stays eligible"
    assert names[0] == "sdxl/hassakuXLIllustrious_v32.safetensors", "same lineage sorts first"
    assert ranked[0].lineage_match is True
    assert all(c.architecture == "sdxl" for c in ranked)


def test_ranking_excludes_other_architectures():
    ranked = rank_substitution_candidates("flux", "someFluxModel.safetensors", CATALOG)
    assert [c.name for c in ranked] == ["flux/flux1-dev.safetensors"]


def test_ranking_of_an_empty_architecture_is_empty_not_everything():
    assert rank_substitution_candidates("", "x.safetensors", CATALOG) == []
    assert rank_substitution_candidates("cogvideox", "x.safetensors", CATALOG) == []
