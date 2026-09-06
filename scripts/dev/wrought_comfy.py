"""The ComfyUI transport and the two graphs every Wrought script submits.

Extracted from generate_wrought_dataset.py so the suit edit (Lane A), the asset plates (Lane B) and
the reference-sheet test submit through ONE builder. The reference graph is the core's own
Krea 2 style-reference template with the identity path kept and the style LoRA left out:
`TextEncodeQwenImageEditPlus(clip, vae, image1, prompt)` carries the reference latents into the
conditioning, `FluxKontextMultiReferenceLatentMethod(index_timestep_zero)` selects the core's
`ref_latents_method` for the Krea 2 forward. Grounded from
`comfyui_workflow_templates_json/templates/image_krea2_turbo_int8_image_style_reference.json`
on core v0.34.0, 2026-09-05 -- never from memory (Doc 50 rule 2).

Frames are fetched over HTTP (`/view`) and never read from a disk path: a disk path resolves on the
machine running THIS script, and pointing the harness at spellnode would copy the LOCAL output
directory's stale renders without an error (banked 1eb2c56).
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))
from comfy_prompt_client import _http_get_json, _upload_comfy_image  # noqa: E402

UNET = "loxsUtopicWorldKrea2_v10Quants.safetensors"
CLIP = "qwen3vl_4b_fp8_scaled.safetensors"
VAE = "qwen_image_vae.safetensors"
STEPS, CFG, SHIFT = 52, 3.5, 1.15
# Measured 2026-09-06 (evidence/v2_reference_edit_probes_2026-09-06.jpg): Utopic cannot consume
# reference tokens without Krea's own style-reference LoRA -- without it, the reference-edit
# forward decodes as a latent checkerboard; with it at strength 1.0, the edit holds cleanly.
REFERENCE_LORA = "krea2_style_reference.safetensors"


@dataclass
class Endpoint:
    api: str = "http://127.0.0.1:8188"

    def submit(self, graph: dict) -> str:
        body = json.dumps({"prompt": graph, "client_id": "sv-wrought-v2"}).encode()
        request = urllib.request.Request(f"{self.api}/prompt", data=body,
                                         headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(request, timeout=120).read())["prompt_id"]

    def wait(self, prompt_id: str, timeout_s: int = 900) -> list[str]:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            entry = (_http_get_json(self.api, f"/history/{prompt_id}", timeout=30) or {}).get(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("completed"):
                    return [i["filename"] for o in entry.get("outputs", {}).values()
                            for i in o.get("images", [])]
                if status.get("status_str") == "error":
                    return []
            time.sleep(2.0)
        return []

    def fetch(self, filename: str) -> bytes:
        url = f"{self.api}/view?filename={urllib.parse.quote(filename)}&type=output"
        with urllib.request.urlopen(url, timeout=180) as response:
            return response.read()

    def free_ram_gb(self) -> float:
        try:
            return _http_get_json(self.api, "/system_stats", timeout=15)["system"]["ram_free"] / 2**30
        except Exception:
            return -1.0

    def upload(self, path: Path) -> str:
        """Push a local plate into the endpoint's input folder; returns the name LoadImage takes."""
        return _upload_comfy_image(self.api, str(path))["name"]

    def upload_reference(self, path: Path, max_side: tuple[int, int] = (768, 1088)) -> str:
        """Push a plate in AS A REFERENCE -- downscaled first, never upscaled.

        Measured 2026-09-06: the reference-edit path is constrained to roughly 1 MP -- a 2.1 MP
        reference gave artifacts even with the LoRA's siblings loaded (`REFERENCE_LORA`), a <=1 MP
        one held clean. `Image.thumbnail` only shrinks, so a plate already under the cap round-trips
        unchanged. Saved beside the source as `<stem>_ref.png` rather than overwriting it -- the
        full-resolution plate stays on disk for the record/gate to read.
        """
        path = Path(path)
        image = Image.open(path)
        image.thumbnail(max_side)
        ref_path = path.with_name(f"{path.stem}_ref.png")
        image.save(ref_path)
        return _upload_comfy_image(self.api, str(ref_path))["name"]


def _base(positive: str, negative: str, seed: int, prefix: str, width: int, height: int,
          steps: int, cfg: float, unet: str | None, shift: float) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet or UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "krea2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": shift}},
        "7": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["5", 0], "seed": seed, "steps": steps, "cfg": cfg,
                         "sampler_name": "euler", "scheduler": "simple", "positive": ["4", 0],
                         "negative": ["6", 0], "latent_image": ["7", 0], "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }


def t2i_graph(positive: str, negative: str, seed: int, prefix: str, width: int, height: int,
              steps: int = STEPS, cfg: float = CFG, unet: str | None = None,
              shift: float = SHIFT) -> dict:
    g = _base(positive, negative, seed, prefix, width, height, steps, cfg, unet, shift)
    g["4"] = {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["2", 0]}}
    return g


def reference_edit_graph(positive: str, negative: str, seed: int, prefix: str, width: int,
                         height: int, reference_name: str, steps: int = STEPS, cfg: float = CFG,
                         unet: str | None = None, shift: float = SHIFT,
                         lora: str | None = REFERENCE_LORA) -> dict:
    """Same character, new instruction: the reference plate rides the conditioning.

    `lora` defaults to Krea's own on-disk style-reference LoRA (`REFERENCE_LORA`). Measured
    2026-09-06 (four probes on the Lane A smoke pair,
    `evidence/v2_reference_edit_probes_2026-09-06.jpg`): Utopic without this LoRA cannot consume
    the reference tokens and decodes a latent checkerboard; Krea's own RAW checkpoint was also
    probed and merely copies the reference instead of editing it. Utopic + the LoRA at strength
    1.0, paired with a reference downscaled through `Endpoint.upload_reference`, is the one
    combination that edits cleanly. Pass `lora=None` to omit the node (the pre-probe shape).
    """
    g = _base(positive, negative, seed, prefix, width, height, steps, cfg, unet, shift)
    g["11"] = {"class_type": "LoadImage", "inputs": {"image": reference_name}}
    g["4"] = {"class_type": "TextEncodeQwenImageEditPlus",
              "inputs": {"clip": ["2", 0], "vae": ["3", 0], "image1": ["11", 0], "prompt": positive}}
    g["12"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
               "inputs": {"conditioning": ["4", 0], "reference_latents_method": "index_timestep_zero"}}
    g["8"]["inputs"]["positive"] = ["12", 0]
    if lora:
        g["13"] = {"class_type": "LoraLoaderModelOnly",
                   "inputs": {"model": ["1", 0], "lora_name": lora, "strength_model": 1.0}}
        g["5"]["inputs"]["model"] = ["13", 0]
    return g


def img2img_graph(positive: str, negative: str, seed: int, prefix: str, init_name: str,
                  denoise: float, steps: int = STEPS, cfg: float = CFG, unet: str | None = None,
                  shift: float = SHIFT, reference_name: str | None = None,
                  lora: str | None = REFERENCE_LORA) -> dict:
    """The skin plate is the init latent: same body, new surface.

    `init_name` is the FULL-SIZE upload of the skin plate (`Endpoint.upload`), VAE-encoded and
    handed to the KSampler as `latent_image` with `denoise` < 1 -- the silhouette survives by
    construction because the sampler starts from it. With `reference_name` (the <=1 MP
    `upload_reference` copy) the reference conditioning of `reference_edit_graph` rides on top
    (nodes 11/4/12 + the LoRA); without it the positive is a plain CLIPTextEncode and no LoRA.
    """
    if not (0 < denoise <= 1):
        raise ValueError(f"denoise must be in (0, 1]: {denoise}")
    # width/height are irrelevant here -- node "7" (EmptySD3LatentImage) is built by _base only to
    # be deleted below, replaced by the VAE-encoded init latent.
    g = _base(positive, negative, seed, prefix, 8, 8, steps, cfg, unet, shift)
    del g["7"]
    g["15"] = {"class_type": "LoadImage", "inputs": {"image": init_name}}
    g["14"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["15", 0], "vae": ["3", 0]}}
    g["8"]["inputs"]["latent_image"] = ["14", 0]
    g["8"]["inputs"]["denoise"] = float(denoise)
    if reference_name:
        g["11"] = {"class_type": "LoadImage", "inputs": {"image": reference_name}}
        g["4"] = {"class_type": "TextEncodeQwenImageEditPlus",
                  "inputs": {"clip": ["2", 0], "vae": ["3", 0], "image1": ["11", 0], "prompt": positive}}
        g["12"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
                   "inputs": {"conditioning": ["4", 0], "reference_latents_method": "index_timestep_zero"}}
        g["8"]["inputs"]["positive"] = ["12", 0]
        if lora:
            g["13"] = {"class_type": "LoraLoaderModelOnly",
                       "inputs": {"model": ["1", 0], "lora_name": lora, "strength_model": 1.0}}
            g["5"]["inputs"]["model"] = ["13", 0]
    else:
        g["4"] = {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["2", 0]}}
    return g


def render(endpoint: Endpoint, graph: dict, target: Path) -> bool:
    files = endpoint.wait(endpoint.submit(graph))
    if not files:
        return False
    target.write_bytes(endpoint.fetch(files[0]))
    return True
