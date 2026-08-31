"""One Civitai model id can hold variants for several different architectures.

Every fixture below is the real API shape, recorded from
``/api/v1/models/2842735`` ("Vintage Mix by AK") and ``/api/v1/models/2863718`` ("KreaWood").
The first has six versions spanning five architectures; the second has one.

The bug this guards: a model-page URL names no version, and the resolver used ``versions[0]``.
Pasting the Vintage Mix link handed you the **Flux** LoRA whatever your workflow needed, and it
downloaded fine with a plausible filename -- nothing looked wrong at any point.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from model_sources import (  # noqa: E402
    AmbiguousCivitaiModel,
    civitai_base_model_architecture,
    model_variants,
    precision_candidates,
    precision_disputes,
    recommend_across_variants,
    recommend_file,
    select_variant,
)


def version(vid, name, base_model, filename, size_kb=223111.9):
    return {
        "id": vid, "name": name, "baseModel": base_model,
        "files": [{"name": filename, "sizeKB": size_kb, "primary": True,
                   "downloadUrl": f"https://civitai.com/api/download/models/{vid}"}],
    }


# Recorded verbatim from the live API.
VINTAGE_MIX = {
    "name": "Vintage Mix by AK", "type": "LORA",
    "modelVersions": [
        version(3227643, "Flux.1 D v2", "Flux.1 D", "Vintage_Mix_Flux_v2_epoch_5.safetensors", 19075.8),
        version(3239224, "ZIT v2", "ZImageTurbo", "Vintage_Mix_ZIT_epoch_8.safetensors", 166142.1),
        version(3251139, "Pony v1", "Pony", "Vintage_Mix_Pony_epoch_10.safetensors"),
        version(3209248, "Krea 2 v1", "Krea 2", "Vintage Mix Krea2 v1.safetensors", 223231.4),
        version(3234746, "SDXL v1", "SDXL 1.0", "Vintage_Mix_SDXL_epoch_10.safetensors"),
        version(3213776, "Illustrious v1", "Illustrious", "Vintage_Mix_ill_epoch_10.safetensors"),
    ],
}

KREAWOOD = {
    "name": "KreaWood", "type": "LORA",
    "modelVersions": [version(3235102, "V1", "Krea 2", "KreaWood_E10.safetensors", 223231.4)],
}


# --- baseModel is the signal, the filename is not ------------------------------------------


@pytest.mark.parametrize(
    "base_model, architecture",
    [
        ("SDXL 1.0", "sdxl"),
        ("Pony", "sdxl"),          # lineage folds up
        ("Illustrious", "sdxl"),   # so does this one
        ("Flux.1 D", "flux"),
        ("ZImageTurbo", "z_image"),
        ("Krea 2", "krea2"),       # written with a SPACE; the registry alias is "krea-2"
    ],
)
def test_civitai_base_model_maps_onto_our_architecture_axis(base_model, architecture):
    assert civitai_base_model_architecture(base_model) == architecture


def test_an_unmappable_or_empty_base_model_is_none_not_a_guess():
    assert civitai_base_model_architecture("") is None
    assert civitai_base_model_architecture("Some Future Model") is None


def test_the_filename_convention_is_not_reliable_enough_to_infer_from():
    """Five variants follow Vintage_Mix_<FAMILY>_epoch_N; the Krea 2 one does not."""
    variants = model_variants(VINTAGE_MIX)
    krea = next(v for v in variants if v.base_model == "Krea 2")
    assert krea.filename == "Vintage Mix Krea2 v1.safetensors"
    assert "_epoch_" not in krea.filename
    assert krea.architecture == "krea2", "baseModel still resolves it correctly"


# --- variant extraction ---------------------------------------------------------------------


def test_variants_carry_what_a_choice_needs():
    variants = model_variants(VINTAGE_MIX)
    assert len(variants) == 6
    assert {v.architecture for v in variants} == {"sdxl", "flux", "z_image", "krea2"}

    flux = next(v for v in variants if v.version_id == "3227643")
    assert flux.version_name == "Flux.1 D v2"
    assert flux.filename == "Vintage_Mix_Flux_v2_epoch_5.safetensors"
    assert flux.download_url.endswith("/3227643")
    assert "Flux.1 D" in flux.describe() and "19 MB" in flux.describe()


def test_a_version_with_no_files_or_no_id_is_skipped_not_half_built():
    payload = {"modelVersions": [
        {"id": 1, "name": "ok", "baseModel": "SDXL 1.0", "files": []},
        {"name": "no id", "baseModel": "Pony", "files": []},
        "not a dict",
    ]}
    variants = model_variants(payload)
    assert [v.version_id for v in variants] == ["1"]
    assert variants[0].filename == "", "an absent file must not fabricate a name"


# --- selection ------------------------------------------------------------------------------


def test_a_unique_architecture_match_selects_that_variant():
    variants = model_variants(VINTAGE_MIX)
    chosen = select_variant(variants, "flux")
    assert chosen is not None and chosen.version_id == "3227643"


def test_several_matches_select_nothing_because_architecture_cannot_decide():
    """Pony, Illustrious and SDXL 1.0 all fold to sdxl. Picking one would hand an Illustrious
    render a Pony LoRA."""
    variants = model_variants(VINTAGE_MIX)
    assert select_variant(variants, "sdxl") is None


def test_no_preference_and_no_match_both_select_nothing():
    variants = model_variants(VINTAGE_MIX)
    assert select_variant(variants, None) is None
    assert select_variant(variants, "") is None
    assert select_variant(variants, "ltx") is None


def test_a_single_version_model_is_never_ambiguous():
    variants = model_variants(KREAWOOD)
    assert len(variants) == 1
    assert variants[0].architecture == "krea2"


# --- the refusal ------------------------------------------------------------------------------


def test_the_ambiguity_error_lists_every_variant_so_a_choice_is_possible():
    variants = model_variants(VINTAGE_MIX)
    exc = AmbiguousCivitaiModel("2842735", variants, preferred_architecture="sdxl")
    text = str(exc)
    assert "2842735" in text and "6 versions" in text
    for v in variants:
        assert v.version_name in text
        assert v.base_model in text
    assert "sdxl" in text, "the unmet preference is stated, not hidden"
    assert len(exc.variants) == 6


# --- precision variants: one filename, several files ----------------------------------------


def _file(fid, name, size_gb, fp, primary=False):
    return {"id": fid, "name": name, "sizeKB": size_gb * 1048576, "primary": primary,
            "downloadUrl": f"https://civitai.com/api/download/models/1?fileId={fid}",
            "metadata": {"format": "SafeTensor", "fp": fp}}


# Recorded from Civitai model 2823011, "Lox's Utopic World | Krea 2".
LOX_V1_BF16 = {"modelVersions": [{
    "id": 3184548, "name": "V1.0 BF16", "baseModel": "Krea 2",
    "files": [
        _file(3065550, "loxsUtopicWorldKrea2_v10BF16.safetensors", 23.88, "bf16", primary=True),
        _file(3070099, "loxsUtopicWorldKrea2_v10BF16_txt.safetensors", 4.88, "fp8_scaled"),
        {"id": 3070200, "name": "loxsUtopicWorldKrea2_v10BF16.json", "sizeKB": 40.0,
         "downloadUrl": "https://civitai.com/api/download/models/1?fileId=3070200", "metadata": {}},
        _file(3070170, "qwen_image_vae.safetensors", 0.24, "bf16"),
        _file(3065135, "loxsUtopicWorldKrea2_v10BF16.safetensors", 11.94, "fp8"),
    ],
}]}


def test_a_filename_is_not_a_key_inside_a_version():
    """The bf16 and the fp8 of this checkpoint have the SAME filename. Picking by name fetches
    whichever happens to come first."""
    variant = model_variants(LOX_V1_BF16)[0]
    same_name = [f for f in variant.files
                 if f.name == "loxsUtopicWorldKrea2_v10BF16.safetensors"]
    assert len(same_name) == 2
    assert {f.precision for f in same_name} == {"bf16", "fp8"}
    assert len({f.file_id for f in same_name}) == 2, "ids are what distinguish them"


def test_precision_variants_exclude_the_bundled_companions():
    """A version bundles its text encoder, VAE and workflow .json next to the checkpoint."""
    variant = model_variants(LOX_V1_BF16)[0]
    assert {f.precision for f in variant.precision_variants()} == {"bf16", "fp8"}
    companions = {f.name for f in variant.companion_files()}
    assert companions == {"loxsUtopicWorldKrea2_v10BF16_txt.safetensors",
                          "qwen_image_vae.safetensors"}
    assert all(f.is_weights for f in variant.companion_files())
    assert not any(f.name.endswith(".json") for f in variant.weight_files())


def test_the_recommendation_is_never_a_companion_file():
    """A naive "highest precision that fits" recommended the 0.24 GB bf16 VAE as the model to
    download: it is bf16, it is weights, and it fits any card."""
    variant = model_variants(LOX_V1_BF16)[0]
    for vram in (32.0, 12.0, None):
        chosen = recommend_file(variant.files, vram_gb=vram)
        assert chosen is not None
        assert chosen.name != "qwen_image_vae.safetensors", f"recommended the VAE at vram={vram}"


def test_the_recommendation_respects_vram_headroom():
    variant = model_variants(LOX_V1_BF16)[0]
    assert recommend_file(variant.precision_variants(), vram_gb=32.0).precision == "bf16"
    # 12 GB * 0.8 leaves 9.6 GB, so neither fits -- recommend the smallest and let the caller say so.
    assert recommend_file(variant.precision_variants(), vram_gb=12.0).precision == "fp8"


def test_with_no_vram_figure_it_recommends_the_highest_precision():
    """Guessing a card is worse than not guessing; the size is shown for the user to read."""
    variant = model_variants(LOX_V1_BF16)[0]
    assert recommend_file(variant.precision_variants(), vram_gb=None).precision == "bf16"


def test_the_primary_file_is_chosen_among_WEIGHTS():
    """files[0] is frequently a companion -- the real V1.0 Quants version lists the VAE first."""
    payload = {"modelVersions": [{
        "id": 1, "name": "V", "baseModel": "Krea 2",
        "files": [_file(1, "qwen_image_vae.safetensors", 0.24, "bf16"),
                  _file(2, "checkpoint.safetensors", 12.5, "int8", primary=True)],
    }]}
    assert model_variants(payload)[0].filename == "checkpoint.safetensors"


# --- the precision axis is sometimes the VERSION axis -------------------------------------------
#
# Recorded verbatim from Civitai model 2726029, "Krea 2 Turbo Official Comfy-Org Checkpoints":
# six versions, one file each, one precision each. The live tests covering this skip when Civitai
# is unreachable, so the reasoning is pinned here, where it always runs.


def _one_file_version(vid, name, file_dict):
    return {"id": vid, "name": name, "baseModel": "Krea 2", "files": [file_dict]}


COMFY_ORG_KREA2 = {"name": "Krea 2 Turbo Official Comfy-Org Checkpoints (Krea2)", "modelVersions": [
    _one_file_version(3091481, "krea2_turbo_int8_convrot",
                      _file(2971089, "krea2TurboOfficialComfy_krea2TurboInt8.safetensors",
                            12.57, "bf16", primary=True)),
    _one_file_version(3147780, "krea2_raw_int8_convrot",
                      _file(3028456, "krea2TurboOfficialComfy_krea2RawInt8Convrot.safetensors",
                            12.57, "int8", primary=True)),
    _one_file_version(3064584, "krea2_turbo_bf16",
                      _file(2943406, "krea2TurboOfficialComfy_krea2TurboBf16.safetensors",
                            24.48, "bf16", primary=True)),
    _one_file_version(3064297, "krea2_turbo_fp8",
                      _file(2943083, "krea2TurboOfficialComfy_krea2TurboFp8.safetensors",
                            12.24, "fp8", primary=True)),
    _one_file_version(3064149, "krea2_turbo_mxfp8",
                      _file(2942890, "krea2TurboOfficialComfy_krea2TurboMxfp8.safetensors",
                            12.6, "fp8", primary=True)),
    _one_file_version(3064058, "krea2_turbo_nvfp4",
                      _file(2942742, "krea2TurboOfficialComfy_krea2TurboNvfp4.safetensors",
                            7.15, "nf4", primary=True)),
]}

# Model 2823011, "Lox's Utopic World | Krea 2" -- the OTHER shape, precisions inside a version, with
# the author's ordering putting V2.0 ahead of V1.0.
LOX_FULL = {"name": "Lox's Utopic World | Krea 2", "modelVersions": [
    {"id": 3238520, "name": "V2.0 BF16", "baseModel": "Krea 2", "files": [
        _file(3121213, "loxsUtopicWorldKrea2_v20BF16.safetensors", 23.88, "bf16", primary=True)]},
    {"id": 3262504, "name": "V2.0 Quants", "baseModel": "Krea 2", "files": [
        _file(3146156, "loxsUtopicWorldKrea2_v20Quants.safetensors", 7.15, "nvfp4", primary=True),
        _file(3146121, "loxsUtopicWorldKrea2_v20Quants.safetensors", 12.25, "int8"),
        _file(3145988, "loxsUtopicWorldKrea2_v20Quants.safetensors", 11.94, "fp8")]},
    {"id": 3213747, "name": "V1.0 Quants", "baseModel": "Krea 2", "files": [
        _file(3095542, "loxsUtopicWorldKrea2_v10Quants.safetensors", 12.57, "int8", primary=True),
        _file(3095805, "loxsUtopicWorldKrea2_v10Quants.safetensors", 7.61, "nvfp4")]},
]}


def _chosen(model, vram_gb):
    """The (version, file) a model-wide recommendation lands on."""
    variants = model_variants(model)
    picked = recommend_across_variants(variants, vram_gb)
    assert picked is not None
    version_id, file_id = picked
    version = next(v for v in variants if v.version_id == version_id)
    file = next(f for _, f in precision_candidates(variants) if f.file_id == file_id)
    return version, file


def test_exactly_one_row_is_marked_across_the_whole_model():
    """The defect this replaced. The mark was computed PER VERSION, and this model gives each
    precision its own version -- so every version held one file, every file was the best in its
    version, and all six rows came back "recommended for your GPU". Measured 6 of 6. A star on
    every row is a star that says nothing, while looking like guidance."""
    variants = model_variants(COMFY_ORG_KREA2)
    candidates = precision_candidates(variants)
    assert len(candidates) == 6
    for vram in (32.0, 16.0, 8.0, None):
        picked = recommend_across_variants(variants, vram)
        assert picked is not None
        marked = [1 for v, f in candidates if (v.version_id, f.file_id) == picked]
        assert len(marked) == 1, f"{len(marked)} rows marked at vram={vram}"


def test_the_recommendation_follows_the_card():
    """A recommendation returning the same file for a 12 GB card and a 32 GB one is not a
    recommendation. That was the state: a cross-version candidate set collapsed to the first
    primary file, and the VRAM budget was never consulted at all."""
    assert _chosen(COMFY_ORG_KREA2, 32.0)[1].size_gb == pytest.approx(24.48, abs=0.01)
    small = _chosen(COMFY_ORG_KREA2, 12.0)[1]
    assert small.size_gb == pytest.approx(7.15, abs=0.01)
    assert small.size_gb <= 12.0 * 0.8


# Recorded verbatim from Civitai model 573152, "LUSTIFY! [NSFW checkpoint]", version "v10
# (Krea 2)". SEVEN files, one filename: three declare bf16 at 24.48 GB and two declare bf16 at
# 12.25 GB. They cannot all be bf16 -- 12.25 is half of 24.48, which is what fp8 costs.
LUSTIFY_V10_KREA2 = {"name": "LUSTIFY! [NSFW checkpoint]", "modelVersions": [
    {"id": 3112728, "name": "v10 (Krea 2)", "baseModel": "Krea 2", "files": [
        _file(2997637, "lustifyNSFWCheckpoint_v10Krea2.safetensors", 11.94, "fp8", primary=True),
        _file(2996235, "lustifyNSFWCheckpoint_v10Krea2.safetensors", 12.25, "bf16"),
        _file(3015314, "lustifyNSFWCheckpoint_v10Krea2.safetensors", 24.48, "bf16"),
        _file(3015315, "lustifyNSFWCheckpoint_v10Krea2.safetensors", 24.48, "bf16"),
        _file(2997070, "lustifyNSFWCheckpoint_v10Krea2.safetensors", 12.25, "bf16"),
    ]},
]}


def test_a_declared_precision_that_contradicts_its_size_is_disputed():
    """``metadata.fp`` is a field an uploader types, and here it is wrong five ways in one version:
    the same filename is published at 24.48 GB and at 12.25 GB, both declared bf16. Half the bytes
    is what fp8 costs, so the 12.25 GB rows are 8-bit files wearing a 16-bit label -- and believing
    the label makes them "the highest precision available"."""
    disputes = precision_disputes(model_variants(LUSTIFY_V10_KREA2))
    assert set(disputes) == {"2996235", "2997070"}, "the two half-size rows claiming bf16"
    assert "8-bit" in disputes["2996235"]
    assert "bf16" in disputes["2996235"]


def test_a_disputed_row_is_never_recommended_but_is_still_offered():
    """Marked, never hidden -- it may be exactly the file the user wants, and dropping it would be
    the silent substitution this module exists to prevent."""
    variants = model_variants(LUSTIFY_V10_KREA2)
    disputes = precision_disputes(variants)
    for vram in (32.0, 24.0, 16.0, 12.0, None):
        _, file = _chosen(LUSTIFY_V10_KREA2, vram)
        assert file.file_id not in disputes, f"recommended a disputed row at vram={vram}"
    offered = {f.file_id: f for _, f in precision_candidates(variants)}
    for file_id in disputes:
        assert file_id in offered
        assert offered[file_id].download_url


def test_a_self_consistent_model_reports_no_dispute():
    """The check has to be quiet on correct metadata or it is noise. Every Lox row agrees."""
    assert precision_disputes(model_variants(LOX_FULL)) == {}


def test_an_fp16_alongside_an_fp32_is_not_a_mislabel():
    """fp32 is 32 bits, not "the top class". Folding it into 16 made every honest
    fp16-alongside-fp32 pair look like a mislabel -- the fp16 is half the fp32's size, so anchored
    on a 16-bit fp32 it measured 8-bit. That was 2 of the 5 flags in the corpus sweep, on SD1.5
    checkpoints where 3.97 GB fp32 + 1.99 GB fp16 is simply the normal shipping pair."""
    payload = {"modelVersions": [{"id": 1, "name": "V", "baseModel": "SD 1.5", "files": [
        _file(1, "ckpt.safetensors", 3.97, "fp32", primary=True),
        _file(2, "ckpt.safetensors", 1.99, "fp16"),
    ]}]}
    assert precision_disputes(model_variants(payload)) == {}


def test_the_comparison_never_crosses_a_version_boundary():
    """The scope error this was measured out of.

    Run across a model's VERSIONS the same code flagged **121 of 1101 candidates (11%)** over the
    100 most-downloaded Civitai checkpoints -- almost none of them mislabels. A model's versions
    routinely span different architectures and parameter counts (Pony Diffusion V6 XL carries a
    1.99 GB file and a 6.46 GB file, both honestly fp16), so a size ratio between versions measures
    the architecture, not the precision. Per version it flags 3 of 1101 (0.27%), and those are
    real.

    The cost is stated rather than hidden: a model publishing one precision per version -- model
    2726029 does exactly that, and its ``krea2_turbo_int8_convrot`` really does declare bf16 at
    12.57 GB against a 24.48 GB bf16 -- has nothing to compare within a version, so this reports
    nothing. "Cannot tell" is the honest answer there, not a weaker check.
    """
    assert precision_disputes(model_variants(COMFY_ORG_KREA2)) == {}

    # The same numbers arranged inside ONE version ARE caught -- given a majority to measure
    # against. Two files alone that contradict each other are a tie, not a verdict: nothing says
    # which of them is the mislabelled one, so a third agreeing file is what breaks it.
    same_numbers = {"modelVersions": [{"id": 1, "name": "V", "baseModel": "Krea 2", "files": [
        _file(1, "krea2.safetensors", 24.48, "bf16", primary=True),
        _file(2, "krea2.safetensors", 24.48, "bf16"),
        _file(3, "krea2.safetensors", 12.57, "bf16"),
    ]}]}
    assert set(precision_disputes(model_variants(same_numbers))) == {"3"}

    two_only = {"modelVersions": [{"id": 1, "name": "V", "baseModel": "Krea 2", "files": [
        _file(1, "krea2.safetensors", 24.48, "bf16", primary=True),
        _file(2, "krea2.safetensors", 12.57, "bf16"),
    ]}]}
    assert precision_disputes(model_variants(two_only)) == {}, "a two-way tie names no culprit"


def test_a_model_whose_metadata_disagrees_with_itself_reports_nothing():
    """Two files, same size, two different declarations, no majority either way. Naming a culprit
    here would be picking a winner among mutually inconsistent metadata -- a guess wearing a
    verdict's clothes. "Cannot tell" is one of the three states."""
    payload = {"modelVersions": [{"id": 1, "name": "V", "baseModel": "Krea 2", "files": [
        _file(1, "a.safetensors", 10.0, "bf16", primary=True),
        _file(2, "a.safetensors", 10.0, "fp8"),
    ]}]}
    assert precision_disputes(model_variants(payload)) == {}


def test_the_recommendation_stays_in_the_version_the_author_put_first():
    """Ranking on size alone crossed a version boundary for 0.32 GB: V1.0's 12.57 GB int8 beat
    V2.0's 12.25 GB int8, so the larger file bought an older model. Civitai returns versions in the
    author's own order and the dialog lists them that way, so the first is the current one."""
    version, file = _chosen(LOX_FULL, 16.0)
    assert version.version_name == "V2.0 Quants"
    assert file.size_gb == pytest.approx(12.25, abs=0.01)


def test_recommend_file_still_narrows_a_raw_single_version_list():
    """``recommend_file`` is the single-VERSION primitive and callers hand it raw file lists, which
    include the bundled text encoder and VAE. Narrowing to the checkpoint's own precisions has to
    happen exactly once, and at this level: doing it again across versions would collapse a
    six-file cross-version choice down to one file, which is the bug that made a 12 GB card and a
    32 GB card get the same answer."""
    variant = model_variants(LOX_V1_BF16)[0]
    companions = {"loxsUtopicWorldKrea2_v10BF16_txt.safetensors", "qwen_image_vae.safetensors"}
    for vram in (32.0, 12.0, 6.0, None):
        chosen = recommend_file(variant.files, vram_gb=vram)
        assert chosen is not None
        assert chosen.name not in companions, f"recommended a companion at vram={vram}"
