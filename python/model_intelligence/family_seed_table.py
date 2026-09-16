"""Published per-family defaults -- the floor under every model.

These come from official model cards and the ComfyUI workflow templates (sources recorded in
docs/superpowers/specs/2026-09-15-t2-t6-research/t3-t5-metadata-research.md section 5). They are
the WEAKEST source in `recommended`: anything a specific model says about itself wins.

This table is deliberately separate from `family_operating_points.FAMILY_OPERATING_POINTS`, which
is what the app RENDERS with and is tuned by our own render comparisons. This one is what the
model's publisher SAYS. W2 reconciles them; conflating them here would erase the distinction
between a measured choice and a published one.
"""
from __future__ import annotations

from typing import Any

SEED_TABLE: dict[str, dict[str, Any]] = {
    "sdxl": {"steps": 30, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras",
             "width": 1024, "height": 1024},
    "flux": {"steps": 20, "cfg": 1.0, "guidance": 3.5, "sampler": "euler", "scheduler": "simple",
             "width": 1024, "height": 1024},
    "krea2": {"steps": 52, "cfg": 3.5, "sampler": "er_sde", "scheduler": "simple",
              "width": 1024, "height": 1024},
    "krea2:turbo": {"steps": 8, "cfg": 1.0, "sampler": "er_sde", "scheduler": "simple",
                    "width": 1024, "height": 1024},
    "z_image": {"steps": 9, "cfg": 1.0, "shift": 3.0, "sampler": "res_multistep",
                "scheduler": "simple", "width": 1024, "height": 1024},
    "sd3": {"steps": 28, "cfg": 4.0, "sampler": "euler", "scheduler": "simple",
            "width": 1024, "height": 1024},
    "pixart": {"steps": 20, "cfg": 4.5, "sampler": "dpmpp_2m", "scheduler": "karras",
               "width": 1024, "height": 1024},
    "lumina": {"steps": 40, "cfg": 4.0, "shift": 6.0, "sampler": "euler", "scheduler": "simple",
               "width": 1024, "height": 1024},
    "anima": {"steps": 30, "cfg": 4.5, "sampler": "er_sde", "scheduler": "simple",
              "width": 1024, "height": 1024},
    "wan": {"steps": 20, "cfg": 3.5, "shift": 5.0, "sampler": "euler", "scheduler": "simple",
            "width": 832, "height": 480, "frames": 81, "fps": 16},
    "ltx": {"steps": 8, "cfg": 1.0, "sampler": "euler", "width": 832, "height": 480,
            "frames": 97, "fps": 24},
    "hunyuan_video": {"steps": 20, "cfg": 1.0, "guidance": 6.0, "shift": 7.0, "sampler": "euler",
                      "scheduler": "simple", "width": 720, "height": 1280, "frames": 129, "fps": 24},
    "mochi": {"steps": 64, "cfg": 4.5, "width": 848, "height": 480, "frames": 84, "fps": 30},
}

_ALIASES = {
    "krea-2": "krea2", "krea_2": "krea2", "pony": "sdxl", "illustrious": "sdxl",
    "stable_diffusion": "sdxl", "sd": "sdxl", "sd2": "sdxl", "zimage": "z_image",
    "z-image": "z_image", "hunyuan": "hunyuan_video", "ltxv": "ltx", "flux3": "flux",
}


def seed_for(family: str | None, variant: str | None = None) -> dict[str, Any]:
    """Published defaults for a family (and optional variant), or {} when unknown."""
    key = str(family or "").strip().lower()
    key = _ALIASES.get(key, key)
    if variant:
        specific = SEED_TABLE.get(f"{key}:{str(variant).strip().lower()}")
        if specific:
            return dict(specific)
    return dict(SEED_TABLE.get(key, {}))
