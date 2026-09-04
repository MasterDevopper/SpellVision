"""Generate a four-view character reference sheet, on the stack a locked plate was made with.

Third of three: **generate** -> `prepare_reference_sheet.py` (pad and centre) ->
`check_reference_sheet.py` (verify against the contract). The contract is SpellBound-Engine's
`CHARACTER_IMAGE_INPUT_SPEC_2026-08-07.md`; the stages are in
`CONCEPT_TO_ASSET_PIPELINE_2026-09-04.md`.

Worked end to end on orc-002, whose recipe was recovered from the locked plate's embedded ComfyUI
graph -- krea2 `loxsUtopicWorldKrea2_v10BF16` + qwen3vl CLIP + qwen_image VAE, AuraFlow shift 1.15,
euler/simple, 52 steps, cfg 3.5. The constants below are that character; the STRUCTURE is the reusable
part, and it is four hard-won things:

1. **A concept plate's prompt is not a sheet's prompt, and one clause proves it.** The plate
   negatived "flat lighting" -- correct for a cinematic key light, and the exact opposite of what a
   reference sheet needs. Left in, the sampler fights the constraint the sheet exists to satisfy.

2. **THE WARDROBE WAS CARRYING THE SILHOUETTE.** The plate said only "strong build, full heavy
   breasts, thick thighs" and let a corset cinch the waist and pauldrons square the shoulders. Strip
   the armour for a minimal set and the body reverts to the model's prior -- soft and straight-sided,
   which is what the owner's own PICK.md rejects by name ("fit hourglass / Bible body band -- not
   plus-size dump, not skinny stick"). Once the costume is gone the shape has to be STATED, because
   it was never in the prompt. Same lesson as the MMD de-costume finding, running the other way.

3. **Describe a profile by its CONSEQUENCES, not its angle.** "Turned ninety degrees, side profile
   view" produced a 3/4, because that is where the training mass sits. One eye, one ear, nose and
   tusk in silhouette, shoulders stacked, far limbs hidden -- that produced a true orthographic side.

4. **Then fix duplication with GEOMETRY, not negatives.** The same profile language also produced a
   MIRRORED PAIR, and negatives did not stop it: the vocabulary describing an orthographic view is
   the vocabulary of a reference SHEET, an image that contains several views. A profile subject is
   ~330 px wide, so a 1216 px canvas has room for a second figure and the model uses it. Narrowing
   the profile canvas to 832 ended it -- and incidentally fixed cross-view centring.

Margin is deliberately NOT attempted here. Two rounds of prompt work at ~200 s each could not buy
5% whitespace; `prepare_reference_sheet.py` pads it exactly, afterwards, in milliseconds.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path("C:/Users/xXste/Code_Projects/SpellVision")
sys.path.insert(0, str(REPO / "python"))
from comfy_prompt_client import _http_get_json  # noqa: E402

API = "http://127.0.0.1:8188"
UNET = "loxsUtopicWorldKrea2_v10BF16.safetensors"
CLIP = "qwen3vl_4b_fp8_scaled.safetensors"
VAE = "qwen_image_vae.safetensors"
# 1216x1728 rather than 1008x1792. The first pass at 9:16 produced a correct A-pose whose HANDS
# reached the frame edge (left margin 0.0%, bottom 0.7%): a tall narrow canvas has no room for arms
# held away from the body, and the A-pose is not negotiable -- it is what keeps limbs separable for
# the fuse. Widening the canvas is the fix; cropping the pose would trade a checkable constraint for
# an uncheckable one.
W, H, SEED, STEPS, CFG = 1216, 1728, 1002, 52, 3.5

# Per-view canvas WIDTH. The profile description finally produced a true side view -- one eye, one
# ear, tusk in silhouette, shoulders stacked -- and simultaneously produced TWO of her, side by side.
# Negatives did not stop it, and that makes sense: the vocabulary that describes an orthographic
# reference view is the vocabulary of a reference SHEET, which is an image containing several views.
#
# The fix is geometric rather than semantic. A profile subject is ~330 px wide; in a 1216 px canvas
# there is room for a second figure, and the model uses it. Height stays 1728 for every view so the
# raw cross-view scale comparison remains meaningful.
VIEW_WIDTH = {"front": 1216, "back": 1216, "left": 832, "right": 832}

# The character, unchanged from the locked plate: the identity clauses and the WROUGHT style law.
# The plate said only "strong build, full heavy breasts, thick thighs" and let the ARMOUR do the
# rest: a corset and belt cinched the waist, pauldrons squared the shoulders. Strip the wardrobe for
# a minimal set and that silhouette goes with it -- the first regeneration drifted soft and
# straight-sided, which is precisely what PICK.md rejects by name ("fit hourglass / Bible body band
# -- not plus-size dump, not skinny stick").
#
# Same lesson as the MMD de-costume finding, running the other way: there, clothing WAS the
# silhouette of an imported body; here, clothing WAS the silhouette of a generated one. Once it is
# removed the shape has to be stated, because it was never in the prompt.
IDENTITY = (
    "wrought style, female orc, green skin, attractive face, "
    "athletic hourglass figure, broad shoulders, muscular defined arms, "
    "narrow cinched waist with visible abdominal definition, wide flared hips, "
    "full heavy breasts, thick powerful thighs, strong glutes, "
    "long black braids, battle scars"
)
STYLE = (
    "grounded stylized realism, WROUGHT style, physically based materials, "
    "controlled saturation, detailed material surfaces"
)
# The reference-sheet clauses: minimal wardrobe, whole body, neutral stance, flat light, plain ground.
SHEET = (
    "plain black sports bra and plain short fitted shorts, bare arms, bare legs, barefoot, "
    "full body shot from head to toe, entire figure visible, both feet fully visible, "
    "standing straight, symmetrical A-pose with arms held away from the sides, "
    "feet shoulder width apart, plain seamless light grey studio backdrop, "
    "even soft frontal studio lighting, no harsh shadows, orthographic character reference sheet, "
    "wide framing with generous empty margin on all sides, clear empty space above the head and "
    "below the feet, hands well inside the frame, whole figure small in the centre of the frame"
)
# "exact left side profile view" made the model draw a MIRRORED PAIR facing each other -- it read
# the phrase as a turnaround sheet rather than one view of one person. Two figures is fatal to a
# fuse, so every view now says "one" explicitly and the negative refuses duplicates.
VIEWS = {
    "front": "one single figure alone, facing the camera directly, front view",
    "back": "one single figure alone, seen from directly behind, back view, facing away from camera",
    # "turned ninety degrees, side profile view" produced a 3/4. Diffusion models drift toward 3/4
    # because that is where the training mass sits, so the profile has to be described by its
    # CONSEQUENCES -- one eye, one ear, the nose breaking the silhouette, the far arm hidden behind
    # the near one -- rather than by the angle, which the model treats as a suggestion.
    "left": ("one single figure alone, strict orthographic left side view, body perpendicular to "
             "the camera, head turned fully to face the left edge of the frame, nose and chin and "
             "tusk in sharp silhouette against the background, only one eye visible, only one ear "
             "visible, shoulders stacked one directly behind the other, far arm and far leg hidden "
             "behind the near arm and near leg, spine and buttocks profile clearly readable"),
    "right": ("one single figure alone, strict orthographic right side view, body perpendicular to "
              "the camera, head turned fully to face the right edge of the frame, nose and chin and "
              "tusk in sharp silhouette against the background, only one eye visible, only one ear "
              "visible, shoulders stacked one directly behind the other, far arm and far leg hidden "
              "behind the near arm and near leg, spine and buttocks profile clearly readable"),
}
NEGATIVE = (
    "plastic skin, oversaturated, cartoon, anime, blurry, deformed hands, extra limbs, text, "
    "watermark, ugly, deformed face, asymmetric eyes, flat chest, small breasts, skinny hips, "
    "narrow hips, thin thighs, "
    # Both ends of PICK.md's band, negated: the drift can go either way and did.
    "soft belly, shapeless torso, straight waist, undefined waist, no waist, "
    "overweight, plus size, obese, skinny, scrawny, undefined muscles, "
    # framing + wardrobe negatives, which the concept plate did not need
    "cropped, close up, portrait crop, cut off feet, cut off head, out of frame, zoomed in, "
    "heavy armor, armor plates, cloak, cape, dress, long coat, "
    "dramatic shadows, rim light, vignette, dark background, busy background, props, weapons, "
    "figure filling the frame, touching the edge of the frame, hands at the edge, tight crop, "
    "two people, multiple figures, duplicate, mirrored pair, twins, side by side, "
    "turnaround sheet, multiple views, split image, collage, reflection, "
    "three quarter view, 3/4 view, angled view, torso turned toward the viewer, "
    "chest facing camera, hips facing camera, both eyes visible, both ears visible, "
    "looking at the camera, twisted spine, contrapposto"
)


def build(view: str) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "krea2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": f"{IDENTITY}, {VIEWS[view]}, {SHEET}, {STYLE}", "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["2", 0]}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1.15}},
        "7": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": VIEW_WIDTH.get(view, W), "height": H, "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["5", 0], "seed": SEED, "steps": STEPS, "cfg": CFG,
                         "sampler_name": "euler", "scheduler": "simple",
                         "positive": ["4", 0], "negative": ["6", 0],
                         "latent_image": ["7", 0], "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage",
               "inputs": {"images": ["9", 0], "filename_prefix": f"002_minimal_{view}"}},
    }


def run(view: str) -> dict:
    graph = build(view)
    started = time.perf_counter()
    body = json.dumps({"prompt": graph, "client_id": "sv-002-regen"}).encode()
    request = urllib.request.Request(f"{API}/prompt", data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        prompt_id = json.loads(urllib.request.urlopen(request, timeout=120).read())["prompt_id"]
    except urllib.error.HTTPError as exc:
        return {"view": view, "outcome": "rejected", "detail": exc.read()[:600].decode("replace")}
    for _ in range(2400):
        entry = (_http_get_json(API, f"/history/{prompt_id}", timeout=30) or {}).get(prompt_id)
        if entry:
            status = entry.get("status", {})
            if status.get("completed"):
                files = [i["filename"] for o in entry.get("outputs", {}).values()
                         for i in o.get("images", [])]
                return {"view": view, "outcome": "ok", "files": files,
                        "seconds": round(time.perf_counter() - started, 1)}
            if status.get("status_str") == "error":
                return {"view": view, "outcome": "error",
                        "detail": json.dumps(status.get("messages", []))[:600]}
        time.sleep(1.0)
    return {"view": view, "outcome": "timeout"}


if __name__ == "__main__":
    wanted = sys.argv[1:] or ["front"]
    for v in wanted:
        row = run(v)
        print(json.dumps(row))
        sys.stdout.flush()
