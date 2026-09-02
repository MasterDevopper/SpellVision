#pragma once

// GENERATED FILE -- DO NOT EDIT BY HAND.
//
// Rendered from MODEL_FAMILIES in python/model_registry.py by
//     scripts/dev/generate_family_license_table.py
// and re-rendered + compared on every pytest run by tests/test_family_license_surfaced.py,
// so this copy cannot drift from the registry. Edit the registry, then regenerate.
//
// It exists because the model card grid is built from a disk scan and paints before any
// worker round trip could answer; a licence badge that arrives late is a licence badge that
// is absent when it matters. The predecessor of this table was two family names hardcoded in
// C++ and matched as SUBSTRINGS -- true of animagine, animatediff and animation, and silently
// false for any non-commercial family the registry gains after it was written.
//
// `aliases` is pipe-separated, and lookup is by EXACT key or EXACT alias (see FamilyLicense.cpp),
// mirroring resolve_model_capabilities. Never by substring: that is the defect this replaces.

namespace spellvision::assets::generated
{

struct FamilyLicenseRow
{
    const char *key;
    const char *aliases;      // pipe-separated, may be empty
    bool commercialUse;
    const char *licenseNote;  // may be empty
};

inline constexpr FamilyLicenseRow kFamilyLicenseTable[] = {
    {"anima", "anima-base|anima-preview|cosmos-anima", false, "CircleStone Labs Non-Commercial License + NVIDIA Open Model License (Cosmos-Predict2 derivative). Non-commercial; point user to official source, do not auto-download or bundle."},
    {"cogvideox", "cogvideo|cog-video-x", true, ""},
    {"flux", "black-forest-labs-flux", true, ""},
    {"hunyuan_video", "hunyuan|hunyuanvideo|hyvideo", false, "Tencent Hunyuan Community License (non-commercial). Badge and warn on commercial-use flows; do not auto-download or bundle."},
    {"illustrious", "illustrious|illustri|illustriousxl", true, ""},
    {"krea2", "krea-2|krea_2|krea2-raw|krea2-turbo|krea-2-raw|krea-2-turbo", true, "Krea 2 Community License + Acceptable Use Policy. Official bases: krea/Krea-2-Raw (default, ~52 steps CFG 3.5) and krea/Krea-2-Turbo (speed lane, 8 steps CFG 0). Comfy-Org/Krea-2 is the ungated ComfyUI pack (diffusion_models + qwen3vl_4b + qwen_image_vae). LoRAs are user variants \xE2\x80\x94 enabled, never required, not family-installed."},
    {"ltx", "ltx-video|ltxv|ltx-2|ltx-2.3", true, ""},
    {"lumina", "lumina-2|lumina2|lumina-image-2|lumina_image_2", true, ""},
    {"mochi", "mochi-1", true, ""},
    {"pixart", "pixart-sigma|pixart-alpha|pixart_sigma|pixartsigma", true, ""},
    {"pony", "pony|ponydiffusion|pony-diffusion|ponyxl", true, ""},
    {"sd3", "stable-diffusion-3", true, ""},
    {"sdxl", "sd-xl|stable-diffusion-xl", true, ""},
    {"stable_diffusion", "sd|sd15|sd1.5|stable-diffusion", true, ""},
    {"unknown", "", true, ""},
    {"wan", "wan2|wan2.1|wan2.2|wan-video", true, ""},
    {"z_image", "z-image|zimage|z-image-turbo|z_image_turbo|z-image-omni", true, ""},
};

// The row a family key that is in no row falls back to. The registry answers an unrecognised
// family with MODEL_FAMILIES["unknown"] (resolve_model_capabilities), so C++ carries no
// default of its own -- it uses the registry's.
inline constexpr const char *kFamilyLicenseFallbackKey = "unknown";

} // namespace spellvision::assets::generated
