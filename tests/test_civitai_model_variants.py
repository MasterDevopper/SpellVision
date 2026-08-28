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
