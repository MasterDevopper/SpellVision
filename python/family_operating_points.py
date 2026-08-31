"""Per-family generation OPERATING POINTS -- tuning data + resolver (Phase 1, Wan-first).

GROUND TRUTH, NOT GUESSES. Every value here is empirically validated by a real render on the
target hardware (RTX 5090) -- the "why" is recorded per operating point below. This is the single
worker-owned source of truth that:
  * the video/image builders resolve blank/`auto` sampling params from (see ``resolve_family_defaults``),
    replacing the scattered inline ``req.get("steps") or 20`` literals; and
  * Phase 3 will ship to the UI (via the family-contract status payload) to drive a fast/quality
    selector and auto-populate the LoRA stack.

MANIFEST-AS-DATA (modeled on ``model_dependency_manifest.py``): adding a family or an operating point
is a NEW ROW here, not new code. A family may declare ANY SUBSET of params -- an image family may
only set ``steps``/``cfg``. The resolver treats a missing key as "not set", so the builder's own
inline literal still covers it (last-resort safety net during the phased migration).

Schema (per family):
    default_operating_point : str            -- used when the request names none (preserves today's behavior)
    operating_points        : {name: params}
        steps        : int
        cfg          : float
        sampler      : str
        scheduler    : str
        shift        : float
        lora         : {"accel": bool, "high"?: filename, "low"?: filename}
                       -- DECLARATIVE. Phase 3 auto-populates the UI's LoRA stack from this; the
                          builder does NOT auto-inject LoRAs (that would surprise a user who did not
                          add them). This pass records it, nothing consumes it yet.
        acceleration : {"type": "teacache" | "lora" | "none", ...}
                       -- DECLARATIVE. "quality" wants TeaCache once the standalone node is installed;
                          it degrades safely to no-op today via the selector fix (commit 19c26af).

Resolver precedence (per param): explicit request value  >  operating-point table value  >  absent
(the caller's own literal). A blank / "" / "auto" sampler|scheduler counts as "not provided" -- that
is exactly what the UI's "auto" sends (normalizeAutoValue -> ""), so it resolves from the table here
instead of from a builder's inline preference tuple.
"""
from __future__ import annotations

import logging
from typing import Any


# Lightx2v 4-step distill LoRAs for the Wan 2.2 A14B dual-noise MoE, PER TASK VARIANT.
#
# The t2v pair is validated live: ~6.3x sampling vs the 28-step baseline, coherent output.
# The i2v pair is its exact sibling -- same publisher, same rank 64, same 4-step distill, same
# naming -- and is NOT separately timed here. It is declared because the alternative was worse, not
# because a number was measured for it: **do not quote 6.3x for i2v.**
#
# Why per-variant at all. The dual-noise builder serves both t2v and i2v, and already refuses a
# mixed expert pair -- "must be the same task variant (both t2v, or both i2v) -- a mixed pair
# renders off-model". That guard was applied to the CHECKPOINTS and not to the LoRAs, so selecting
# the fast operating point on an i2v job injected the t2v accel pair: the identical off-model
# failure the guard exists to prevent, one layer down, with the correct pair sitting on disk beside
# it. A rule applied at one layer and not the next is this audit's whole subject.
#
# The variant keys replace the flat `high`/`low` rather than sitting beside them. A flat pair left
# in place as a "default" would keep working for t2v and keep being wrong for i2v, which is the
# failure mode -- an unmigrated reader must break loudly, not quietly pick the t2v pair.
_WAN_LIGHTX2V = {
    "t2v": {
        "high": "wan2.2_t2v_A14b_high_noise_lora_rank64_lightx2v_4step_1217.safetensors",
        "low": "wan2.2_t2v_A14b_low_noise_lora_rank64_lightx2v_4step_1217.safetensors",
    },
    "i2v": {
        "high": "wan2.2_i2v_A14b_high_noise_lora_rank64_lightx2v_4step_1022.safetensors",
        "low": "wan2.2_i2v_A14b_low_noise_lora_rank64_lightx2v_4step_1022.safetensors",
    },
}


def accel_loras_for(params: dict[str, Any] | None, command: Any) -> dict[str, str]:
    """The accel LoRA pair an operating point declares FOR THIS COMMAND, or {} if it declares none.

    Returns ``{}`` -- never a fallback to another variant -- when the point declares accel LoRAs but
    not for this command. A caller that gets ``{}`` must run without them, which is a slow render;
    substituting the other variant's pair is a wrong render that looks like a working one, and Doc 19
    forbids the silent substitution of a model either way.
    """
    lora = (params or {}).get("lora") or {}
    if not lora.get("accel"):
        return {}
    pair = lora.get(str(command or "").strip().lower()) or {}
    return {k: str(v) for k, v in pair.items() if str(v or "").strip()}


FAMILY_OPERATING_POINTS: dict[str, dict[str, Any]] = {
    "wan": {
        "default_operating_point": "quality",
        "operating_points": {
            # 28-step full model. The validated CLEAN config from the noise diagnosis: the noisy render
            # was 28-step-no-LoRA at cfg 7 / dpmpp_2m / sgm_uniform; euler + simple + cfg ~4 at full
            # steps is coherent. TeaCache is the intended accelerant here, but the standalone node is
            # not installed -- the acceleration slot is DECLARATIVE and degrades to no-op (19c26af).
            "quality": {
                "steps": 28,
                "cfg": 4.0,
                "sampler": "euler",
                "scheduler": "simple",
                "shift": 5.0,
                "lora": {"accel": False},
                "acceleration": {"type": "teacache", "profile": "balanced"},
            },
            # Lightx2v 4-step config. Measured live at ~6.3x sampling vs the 28-step baseline with a
            # coherent frame. cfg 1 + 4 steps + the accel LoRAs (high -> high expert, low -> low, by the
            # builder's filename routing). TeaCache is deliberately "none" -- redundant at 4 steps.
            "fast": {
                "steps": 4,
                "cfg": 1.0,
                "sampler": "euler",
                "scheduler": "simple",
                "shift": 5.0,
                "lora": {"accel": True, **_WAN_LIGHTX2V},
                "acceleration": {"type": "none"},
            },
        },
    },

    # ===================================================================================================
    # Phase 2a -- VIDEO builder defaults, LIFTED VERBATIM from inline literals. These are a pure
    # centralization (no value changed). Keyed by BUILDER CONFIG identity (a family may have several
    # builders with different baselines), not by contract-family. Each carries its provenance honestly.
    # Consumed via operating_point_params(<key>, "default"): each builder keeps its own verbatim
    # request-alias read and uses the table only to supply the default value (so alias handling is
    # unchanged -- these builders' aliases diverge from resolve_family_defaults's fixed set).
    # ===================================================================================================

    # _build_native_wan_core_video_prompt (single-model Wan native-core graph).
    "wan_core": {
        "default_operating_point": "default",
        "operating_points": {
            # TESTED -- ACCEPTABLE (2026-07-12). A/B'd live against euler/simple/cfg-4 (single-model
            # Wan 2.1, i2v, 16 steps, seed-matched, same prompt/model/res): CURRENT defaults
            # (dpmpp_2m/sgm_uniform/cfg-5) and the blueprint-aligned alternative BOTH render clean and
            # coherent -- no noise/grain in either. KEPT AS-IS. Notes: the split-sampler concern does
            # NOT apply here -- wan_core is single-model with NO expert swap, so dpmpp_2m's history
            # discontinuity (a dual-noise-specific problem across the mid-chain model swap) is a non-issue.
            # euler appeared faster, but the speed edge was CONFOUNDED by run order (A always ran first,
            # uncounterbalanced) -- suggestive, not measured. Values unchanged.
            "default": {
                "steps": 30, "cfg": 5.0, "sampler": "dpmpp_2m", "scheduler": "sgm_uniform", "shift": 5.0,
            },
        },
    },

    # _build_native_wan_split_video_prompt (WanVideoWrapper / WanVideoSampler). No sampler literal
    # (the wrapper sampler is scheduler-driven); carries denoise.
    "wan_wrapper": {
        "default_operating_point": "default",
        "operating_points": {
            # Lifted verbatim from _build_native_wan_split_video_prompt inline literals.
            # NOT validated by render; provenance unknown.
            "default": {
                "steps": 30, "cfg": 6.0, "scheduler": "unipc", "shift": 5.0, "denoise": 1.0,
            },
        },
    },

    # _native_video_kwargs (diffusers WanPipeline path -- pipeline kwargs, not a Comfy graph).
    "wan_diffusers": {
        "default_operating_point": "default",
        "operating_points": {
            # Lifted verbatim from _native_video_kwargs inline literals.
            # NOT validated by render; provenance unknown.
            "default": {"steps": 30, "cfg": 5.0},
        },
    },

    # _build_native_hunyuan_video_prompt. NOTE: the builder's shift=7.0 is a HARDCODED CONSTANT (not a
    # req-fallback), so it stays hardcoded in the builder and is only RECORDED here for provenance --
    # routing it would make req["shift"] override it, a behavior change. Only steps/cfg are routed.
    "hunyuan_video": {
        "default_operating_point": "default",
        "operating_points": {
            # Lifted verbatim from _build_native_hunyuan_video_prompt inline literals.
            # NOT validated by render; provenance unknown. shift 7.0 is declarative here (builder keeps it hardcoded).
            "default": {"steps": 20, "cfg": 6.0, "shift": 7.0},
        },
    },

    # _build_native_mochi_video_prompt (Genmo Mochi-1 T2V native graph, build-order #5). GROUNDED from the
    # official ComfyUI Mochi blueprint: KSampler with a REAL cfg (Mochi is NOT distilled). steps/cfg routed;
    # sampler euler / scheduler simple are PINNED (grounded, recorded only -- hardcoded in the builder).
    "mochi": {
        "default_operating_point": "default",
        "operating_points": {
            "default": {
                "steps": 30,               # routed -- GROUNDED (full Mochi wants ~30)
                "cfg": 4.5,                # routed -- GROUNDED (Mochi real-cfg sweet spot); NOT pinned
                "sampler": "euler",        # PINNED / recorded only -- GROUNDED
                "scheduler": "simple",     # PINNED / recorded only -- GROUNDED
            },
        },
    },

    # _build_native_split_video_prompt -- the UNKNOWN-FAMILY CATCH-ALL fallback (any family that isn't
    # wan/hunyuan/ltx inherits this). Keyed by config identity, not a real family.
    "native_split_generic": {
        "default_operating_point": "default",
        "operating_points": {
            # REASONED defaults (retuned 2026-07-12), NOT render-validated. This is the unknown-family
            # catch-all -- no specific model can be tested against it, so these values CANNOT be render-
            # validated; they are chosen to match the shape of every VALIDATED video config rather than
            # the old lifted-verbatim literals (which were an unexplained outlier):
            #   cfg 4.5  -- 7.0 was the value that produced the diagnosed NOISY Wan render; every
            #              validated config sits far lower. 4.5 keeps headroom without over-guiding.
            #   sampler euler -- history-free, split-safe. dpmpp_2m is 2nd-order multistep whose
            #              correction breaks across this builder's mid-chain model swap.
            #   scheduler simple -- the video-blueprint standard (karras is image-oriented).
            #   shift 5.0 -- aligns with Wan's validated shift (8.0 was an unexplained outlier).
            "default": {
                "steps": 30,
                "cfg": 4.5,
                "sampler": "euler", "scheduler": "simple", "shift": 5.0, "denoise": 1.0,
            },
        },
    },

    # ===================================================================================================
    # Phase 2b -- IMAGE builder defaults. Provenance is DIFFERENTIATED: GROUNDED (official config /
    # render-proven, per the builder comments) vs lifted-verbatim (provenance unknown). PINNED params
    # (a baked/ignored cfg, hardcoded sampler/scheduler/shift) are RECORDED here for visibility but stay
    # HARDCODED in the builder -- routing them would newly let a request override a grounded pin (same
    # discipline as hunyuan shift=7 in 2a). ONLY the plain-fallback params (marked "routed") are wired.
    # ===================================================================================================

    # _build_flux_image_prompt. GROUNDED: Flux uses distilled guidance -- the KSampler cfg is PINNED 1.0
    # and the cockpit cfg maps to FluxGuidance.guidance (default 3.5 = Flux sweet spot, in
    # _flux_guidance_from_request). sampler/scheduler are hardcoded euler/simple. Only steps is routed.
    "flux_image": {
        "default_operating_point": "default",
        "operating_points": {
            "default": {
                "steps": 20,               # routed -- lifted verbatim (provenance unknown)
                "cfg": 1.0,                # PINNED / recorded only -- GROUNDED (KSampler cfg; Flux uses guidance, not cfg)
                "guidance_default": 3.5,   # recorded only -- GROUNDED (_flux_guidance_from_request fallback, Flux sweet spot)
                "sampler": "euler",        # PINNED / recorded only -- GROUNDED
                "scheduler": "simple",     # PINNED / recorded only -- GROUNDED
            },
        },
    },

    # _build_pixart_image_prompt. steps/cfg routed (PixArt uses REAL cfg); sampler/scheduler pinned.
    "pixart_image": {
        "default_operating_point": "default",
        "operating_points": {
            "default": {
                "steps": 20,               # routed -- lifted verbatim (provenance unknown)
                "cfg": 4.5,                # routed -- lifted verbatim (provenance unknown); real CFG
                "sampler": "euler",        # PINNED / recorded only
                "scheduler": "normal",     # PINNED / recorded only
            },
        },
    },

    # _build_lumina_image_prompt. steps/cfg routed; shift 6.0 GROUNDED (official Lumina 2.0 sigma regime,
    # render-proven) recorded only; sampler/scheduler pinned.
    "lumina_image": {
        "default_operating_point": "default",
        "operating_points": {
            "default": {
                "steps": 30,               # routed -- lifted verbatim (provenance unknown)
                "cfg": 4.0,                # routed -- lifted verbatim (provenance unknown); real cfg
                "shift": 6.0,              # PINNED / recorded only -- GROUNDED (official sigma shift, render-proven at shift 6 / res_multistep)
                "sampler": "res_multistep",# PINNED / recorded only -- GROUNDED
                "scheduler": "normal",     # PINNED / recorded only
            },
        },
    },

    # _build_zimage_image_prompt. GROUNDED official Turbo config. steps 4 routed (the fallback; the
    # <1 / >16 -> 4 CLAMP stays inline). cfg 1.0 is PINNED (baked-in; cockpit cfg IGNORED) and shift 3.0
    # is grounded -- both recorded only, hardcoded in the builder. sampler/scheduler pinned.
    "zimage_image": {
        "default_operating_point": "default",
        "operating_points": {
            "default": {
                "steps": 4,                # routed -- GROUNDED (official Turbo 4 NFE, render-proven)
                "cfg": 1.0,                # PINNED, cockpit IGNORED / recorded only -- GROUNDED (distilled Turbo, baked cfg)
                "shift": 3.0,              # PINNED / recorded only -- GROUNDED (render-proven clean)
                "sampler": "res_multistep",# PINNED / recorded only -- GROUNDED
                "scheduler": "simple",     # PINNED / recorded only -- GROUNDED
            },
        },
    },

    # _build_anima_image_prompt. steps/cfg routed (cfg is NOT pinned -- mapped, request-overridable);
    # sampler/scheduler pinned. No shift node.
    "anima_image": {
        "default_operating_point": "default",
        "operating_points": {
            "default": {
                "steps": 30,               # routed -- lifted verbatim (provenance unknown)
                "cfg": 4.0,                # routed -- lifted verbatim (provenance unknown); mapped, NOT pinned
                "sampler": "er_sde",       # PINNED / recorded only
                "scheduler": "simple",     # PINNED / recorded only
            },
        },
    },

    # Official Raw is the default quality lane. Turbo is the speed-lane UNET, not a required LoRA.
    # Owner-proven 2026-08-17: raw UNET + optional user LoRAs. LoRAs are enabled, never required.
    # Grounded on the blueprint Comfy-Org ships beside the checkpoint
    # (sd3.5-t2i-fp8-scaled-workflow.json): 30 steps, cfg 5.45, euler / sgm_uniform. These are the
    # model author's own numbers, and they are NOT overridden by the one-image-per-sampler
    # comparison run when this family landed -- heun and dpmpp_2m both looked cleaner on a single
    # render each, which is an impression. Krea 2's default moved only after three measured pairs
    # with the sampler as the sole variable, and the same bar applies here before this changes.
    "sd3_image": {
        "default_operating_point": "default",
        "operating_points": {
            "default": {
                "steps": 30,
                "cfg": 5.45,
                "sampler": "euler",
                "scheduler": "sgm_uniform",
            },
        },
    },

    "krea2_image": {
        "default_operating_point": "raw",
        "operating_points": {
            # sampler: er_sde, chosen by RENDER COMPARISON 2026-08-28, not by copying the
            # reference workflow. Three pairs (two prompts at raw 52/3.5, one at turbo 8/1.0),
            # identical seed/steps/cfg/scheduler with the sampler as the only variable. er_sde
            # resolved fine high-frequency structure markedly better every time -- legible
            # graduation ticks and coordinate grid on an astrolabe where euler smeared them, and a
            # net whose mesh could be counted knot by knot where euler produced a haze.
            #
            # Cost is nil: the one clean timing pair (both with the model already resident) was
            # 56.5s euler vs 56.2s er_sde. The turbo pair's 34.5s/6.0s split is NOT a speed claim --
            # the euler run there included a checkpoint reload.
            #
            # Corroborating, but not the reason: the Krea 2 reference workflow samples with er_sde,
            # and SpellVision's own anima family already defaults to it.
            "raw": {
                "steps": 52,
                "cfg": 3.5,
                "sampler": "er_sde",
                "scheduler": "simple",
                "lora": {"accel": False},
            },
            # Official turbo snap: 8 / CFG 1. Owner 2026-08-18: CFG 0 is not
            # a look anyone wants (hands/text leak). CFG 1 is the model default.
            # Sequential turbo stills can still collapse (face ok → side 2D).
            # Verified separately at 8 steps rather than assumed from the raw result: the same
            # comparison at turbo's operating point favoured er_sde too (crisper net mesh and rope
            # braid, more resolved background).
            "turbo": {
                "steps": 8,
                "cfg": 1.0,
                "sampler": "er_sde",
                "scheduler": "simple",
                "lora": {"accel": False},
            },
        },
    },
}


# Hard per-family allow-lists (Doc 27 §2.2). Unused KSampler entries do not appear.
FAMILY_SAMPLER_ALLOWLISTS: dict[str, dict[str, tuple[str, ...]]] = {
    "wan": {
        "samplers": ("euler", "dpmpp_2m", "uni_pc"),
        "schedulers": ("simple", "sgm_uniform", "normal"),
    },
    "hunyuan_video": {
        "samplers": ("euler", "dpmpp_2m"),
        "schedulers": ("simple", "normal"),
        # euler/simple is what _build_native_hunyuan_video_prompt patches into KSamplerSelect and
        # BasicScheduler, and what the render-proven run used (Doc 28, frame-0 MAE 5.55). The
        # alphabetical fallback advertised dpmpp_2m/normal instead -- a default the graph could not
        # produce, since it ignored the request entirely until the sampler was wired through.
        "default_sampler": "euler",
        "default_scheduler": "simple",
    },
    "mochi": {
        "samplers": ("euler",),
        "schedulers": ("simple",),
    },
    # LTX-2.3. All three names verified present in the live KSamplerSelect options on core
    # v0.27.0 before being listed here. The two _cfg_pp variants are the template's own stage-1 and
    # stage-2 defaults; plain euler is the safe generic.
    #
    # schedulers is DELIBERATELY EMPTY: neither LTX template exposes a scheduler input -- both
    # drive sigmas through ManualSigmas -- so there is nothing to choose. An empty tuple here says
    # "this family has no scheduler", which is different from having no entry at all, and that
    # distinction is the whole reason LTX previously showed the cockpit nothing.
    "ltx": {
        "samplers": ("euler_ancestral_cfg_pp", "euler_cfg_pp", "euler"),
        "schedulers": (),
        # LTX is TEMPLATE-DRIVEN and deliberately has no FAMILY_OPERATING_POINTS row -- steps and
        # cfg live in the shipped graph and a cockpit value is ignored for the distilled route
        # (the builder warns and pins the guiders at 1). The sampler IS overridable, so the default
        # is declared here: it is the stage-1 patch default in
        # native_video_graphs._build_native_ltx_two_stage_prompt (node 4831).
        "default_sampler": "euler_ancestral_cfg_pp",
    },
    "flux_image": {
        "samplers": ("euler", "euler_ancestral"),
        "schedulers": ("simple", "normal"),
    },
    "pixart_image": {
        "samplers": ("euler", "dpmpp_2m"),
        "schedulers": ("normal", "simple"),
    },
    "lumina_image": {
        "samplers": ("res_multistep", "euler"),
        "schedulers": ("normal", "simple"),
    },
    "zimage_image": {
        "samplers": ("res_multistep", "euler"),
        "schedulers": ("simple",),
    },
    "anima_image": {
        "samplers": ("er_sde", "euler"),
        "schedulers": ("simple", "normal"),
    },
    "krea2_image": {
        # er_sde is what the Krea 2 reference workflow samples with, and without it here a user who
        # imports that workflow cannot reproduce it -- the allow-list would filter out the author's
        # own choice. Verified present in the live KSampler sampler_name list (63 entries), and
        # anima_image, the closest sibling family, already offers exactly this pair.
        #
        # Both are selectable, and er_sde is now also the DEFAULT -- settled by the render
        # comparison recorded on the operating points below, after the measurement first exposed
        # that no native image builder read the requested sampler at all.
        "samplers": ("euler", "er_sde"),
        "schedulers": ("simple", "normal"),
    },
    "sd3_image": {
        # SD3 is FLOW-MATCHING, so this list is not sdxl's with a different default -- copying that
        # was rejected explicitly when the family had no row. Every entry was submitted to the live
        # KSampler against the real checkpoint and produced a distinct, coherent 1024x1024 image
        # (mean absolute difference 28-40 per channel between samplers, so the choice genuinely
        # applies). Schedulers stay at the two the blueprint and ComfyUI's SD3 docs use; karras is
        # deliberately absent, because reshaping a sigma schedule is meaningless for a model that
        # does not have one.
        "samplers": ("euler", "heun", "dpmpp_2m", "res_multistep"),
        "schedulers": ("sgm_uniform", "simple"),
    },
    "sdxl": {
        "samplers": ("euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde", "ddim"),
        "schedulers": ("normal", "karras", "simple", "sgm_uniform"),
        # Declared, because the fallback below is alphabetical and "ddim" sorts first. That fallback
        # WAS the shipped default here, and through the pony / illustrious / stable_diffusion / sd
        # aliases it was the default on 112 checkpoints -- chosen by sort order, by nobody.
        #
        # Measured on this box (LuxuriousPrisma_v30, 1024x1024, 30 steps, cfg 7, seed 20260830,
        # sampler the only variable, each applied from a genuinely stock scheduler):
        #
        #   ddim / karras         DDIMScheduler                    3.6s  reference
        #   dpmpp_2m / karras     DPMSolverMultistepScheduler      3.6s  MAD 42.94
        #   euler / normal        EulerDiscreteScheduler           3.6s  MAD  7.33
        #   euler_ancestral       EulerAncestralDiscreteScheduler  3.6s  MAD 55.45
        #   dpmpp_2m_sde / karras NOT APPLIED -- no mapping        3.6s  MAD  7.33 (stock euler)
        #
        # Two things that measurement settled beyond the choice itself. The old default's SCHEDULER
        # half never applied: DDIMScheduler does not accept use_karras_sigmas, so from_config raised
        # TypeError and the retry dropped it -- "ddim + karras" rendered ddim with no karras, and the
        # config confirmed use_karras_sigmas false. And dpmpp_2m_sde, offered in this very tuple, had
        # no scheduler mapping at all: it rendered whatever scheduler was already loaded (MAD
        # identical to plain euler). Both are fixed alongside this.
        #
        # dpmpp_2m + karras is the pair the SDXL community standardised on, it is the one that
        # genuinely applies (use_karras_sigmas verified true), and it costs nothing in wall clock.
        "default_sampler": "dpmpp_2m",
        "default_scheduler": "karras",
    },
}

_FAMILY_SAMPLING_ALIASES: dict[str, str] = {
    "flux": "flux_image",
    "pixart": "pixart_image",
    "lumina": "lumina_image",
    "zimage": "zimage_image",
    "z-image": "zimage_image",
    # The REGISTRY KEY is "z_image" (model_registry.MODEL_FAMILIES), and it was the one spelling
    # missing here -- so the family could not resolve its own tuned defaults or sampler allowlist
    # by name. Only native_image_graphs worked, because it passes the literal "zimage_image".
    # Every other caller silently got nothing.
    "z_image": "zimage_image",
    "anima": "anima_image",
    "sd3": "sd3_image",
    "sd-3": "sd3_image",
    "sd_3": "sd3_image",
    "krea2": "krea2_image",
    "krea-2": "krea2_image",
    "krea_2": "krea2_image",
    "hunyuan": "hunyuan_video",
    "pony": "sdxl",
    "illustrious": "sdxl",
    "stable_diffusion": "sdxl",
    "sd": "sdxl",
}


# Sampling params the resolver fills. Request-key aliases per logical param (worker request-schema
# knowledge lives here, not in the data table). String params treat "" / "auto" as "not provided".
_SAMPLING_PARAMS: tuple[str, ...] = ("steps", "cfg", "sampler", "scheduler", "shift")
_STRING_PARAMS = frozenset({"sampler", "scheduler"})
_REQUEST_ALIASES: dict[str, tuple[str, ...]] = {
    "steps": ("steps",),
    "cfg": ("cfg", "guidance_scale"),
    "sampler": ("video_sampler", "sampler"),
    "scheduler": ("video_scheduler", "scheduler"),
    "shift": ("shift", "model_sampling_shift"),
}


def _family_row(family: Any) -> dict[str, Any]:
    key = str(family or "").strip().lower()
    if key in FAMILY_OPERATING_POINTS:
        return FAMILY_OPERATING_POINTS[key]
    alias = _FAMILY_SAMPLING_ALIASES.get(key)
    if alias and alias in FAMILY_OPERATING_POINTS:
        return FAMILY_OPERATING_POINTS[alias]
    return {}


def default_operating_point(family: Any) -> str:
    """The operating point used when the request names none. "" for an unknown family."""
    return str(_family_row(family).get("default_operating_point") or "").strip()


def operating_point_params(family: Any, operating_point: Any) -> dict[str, Any]:
    """The FULL raw params for one operating point (steps/cfg/.../lora/acceleration), or {} if the
    family or operating point is unknown. Phase 3 reads lora/acceleration from here."""
    points = _family_row(family).get("operating_points", {})
    return dict(points.get(str(operating_point or "").strip(), {}))


def _request_override(req: dict[str, Any], param: str) -> Any:
    """The explicit request value for a logical param, or None if the request didn't provide one.
    Mirrors the old ``req.get(..) or <lit>`` semantics: a string "" / "auto" and a falsy number (0)
    both count as "not provided"."""
    for key in _REQUEST_ALIASES.get(param, ()):
        val = req.get(key)
        if val is None:
            continue
        if param in _STRING_PARAMS:
            text = str(val).strip()
            if not text or text.lower() == "auto":
                continue
            return text
        try:
            num: Any = int(val) if param == "steps" else float(val)
        except (TypeError, ValueError):
            continue
        if num:  # falsy 0 -> not provided (matches the old `or <literal>`)
            return num
    return None


def resolve_operating_point(family: Any, requested: Any) -> str:
    """Validate a REQUESTED operating_point name against a family; return the effective name.

    Blank/absent request -> the family's default_operating_point. A non-blank request that names a point
    the family does NOT define -> ``log.warning`` + fall back to the default (a bad operating point must
    NEVER kill a render -- a safe, visible fallback beats raising, chosen deliberately). Unknown family
    (no table row) -> the requested value passes through unchanged (there is nothing to validate against;
    the builder's own literals cover it).

    This is the VALIDATION layer, kept SEPARATE from ``resolve_family_defaults`` (which stays a pure
    name->params lookup: an unknown name there still returns ``{}`` passthrough). Callers validate here
    first, then resolve params with the returned valid name -- so an unknown op never reaches the params
    resolver as unknown, and the passthrough contract of ``resolve_family_defaults`` is preserved."""
    row = _family_row(family)
    points = row.get("operating_points", {})
    default = str(row.get("default_operating_point") or "").strip()
    req_op = str(requested or "").strip()
    if not req_op:
        return default
    if req_op in points:
        return req_op
    if points:  # known family, unknown point -> warn + fall back (never raise)
        logging.warning(
            "Unknown operating_point %r for family %r; falling back to the default %r "
            "(valid points: %s). The render proceeds with the default operating point.",
            req_op, str(family or ""), default or "<none>", sorted(points),
        )
        return default
    return req_op  # unknown family -> passthrough (the builder's own literals cover it)


def _object_info_choices(object_info: dict[str, Any] | None, input_name: str) -> set[str] | None:
    if not object_info:
        return None
    node = object_info.get("KSampler") or object_info.get("KSamplerAdvanced") or {}
    required = ((node.get("input") or {}).get("required") or {})
    raw = required.get(input_name)
    if not isinstance(raw, list) or not raw:
        return None
    first = raw[0]
    if not isinstance(first, list):
        return None
    return {str(item).strip() for item in first if str(item).strip()}


def family_sampling_choices(family: Any, *, object_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """Hard allow-list ∩ operating-point pins ∩ optional live KSampler choices."""
    resolved = _FAMILY_SAMPLING_ALIASES.get(str(family or "").strip().lower(), str(family or "").strip().lower())
    allow = FAMILY_SAMPLER_ALLOWLISTS.get(resolved, {})
    samplers = set(allow.get("samplers", ()))
    schedulers = set(allow.get("schedulers", ()))

    default_name = default_operating_point(resolved) or default_operating_point(family)
    table = operating_point_params(resolved, default_name) or operating_point_params(family, default_name)
    default_sampler = str(table.get("sampler") or "").strip()
    default_scheduler = str(table.get("scheduler") or "").strip()
    if default_sampler:
        samplers.add(default_sampler)
    if default_scheduler:
        schedulers.add(default_scheduler)
    for params in _family_row(resolved).get("operating_points", {}).values():
        if params.get("sampler"):
            samplers.add(str(params["sampler"]))
        if params.get("scheduler"):
            schedulers.add(str(params["scheduler"]))

    live_samplers = _object_info_choices(object_info, "sampler_name")
    live_schedulers = _object_info_choices(object_info, "scheduler")
    if live_samplers is not None:
        samplers &= live_samplers
        if default_sampler and default_sampler in live_samplers:
            samplers.add(default_sampler)
    if live_schedulers is not None:
        schedulers &= live_schedulers
        if default_scheduler and default_scheduler in live_schedulers:
            schedulers.add(default_scheduler)

    # A TEMPLATE-DRIVEN family (LTX) has no operating-point row by design -- its steps and cfg live
    # in the shipped graph and a cockpit value is ignored -- but its sampler IS overridable. Without
    # a row there is no `sampler` to take a default from, and falling through to sorted()[0] below
    # advertised "euler" while the template actually patches "euler_ancestral_cfg_pp". The allowlist
    # may therefore name its own default, which is the only place that fact can live for such a
    # family.
    if not default_sampler:
        default_sampler = str(allow.get("default_sampler") or "").strip()
    if not default_scheduler:
        default_scheduler = str(allow.get("default_scheduler") or "").strip()

    sampler_source = "operating_point" if table.get("sampler") else (
        "allowlist" if default_sampler else "")
    scheduler_source = "operating_point" if table.get("scheduler") else (
        "allowlist" if default_scheduler else "")

    # Last resort: alphabetical. Deliberately after the allowlist default, so a declared default is
    # never silently outranked by whatever happens to sort first.
    #
    # Reported rather than hidden. This fallback is not wrong in itself -- an unknown family with a
    # live KSampler list has to start somewhere -- but it is wrong as a SHIPPED default, and for
    # four families it was one. `_assert_every_family_declares_a_default` below turns that into an
    # import-time refusal for the families this repo owns; `default_source` is how any other caller,
    # and the UI, can tell a chosen default from a sorted one.
    if not default_sampler and samplers:
        default_sampler = sorted(samplers)[0]
        sampler_source = "alphabetical"
    if not default_scheduler and schedulers:
        default_scheduler = sorted(schedulers)[0]
        scheduler_source = "alphabetical"

    return {
        "samplers": sorted(samplers, key=lambda name: (name != default_sampler, name)),
        "schedulers": sorted(schedulers, key=lambda name: (name != default_scheduler, name)),
        "default_sampler": default_sampler,
        "default_scheduler": default_scheduler,
        "default_sampler_source": sampler_source or "none",
        "default_scheduler_source": scheduler_source or "none",
    }


def _assert_every_family_declares_a_default() -> None:
    """Refuse to import with a family whose default was picked by sort order.

    The plan's phrasing for this class of defect is "make the fallback refuse, then measure". A
    family that reaches the alphabetical branch is not configured; it merely has an allowlist whose
    first entry happens to be plausible. Four families shipped that way, and the one people saw most
    -- sdxl, via pony/illustrious/stable_diffusion/sd -- advertised a pair whose scheduler half could
    not even apply.

    Runs at import so a new allowlist entry cannot be added without deciding what its default is.
    A family whose sampler list is EMPTY is exempt: there is nothing to default to, and an empty
    table is an honest statement that this family has no choice to offer (LTX's schedulers are the
    shipped example).
    """
    undeclared: list[str] = []
    for key in sorted(FAMILY_SAMPLER_ALLOWLISTS):
        choices = family_sampling_choices(key)
        if choices.get("default_sampler_source") == "alphabetical":
            undeclared.append(f"{key}.default_sampler")
        if choices.get("default_scheduler_source") == "alphabetical":
            undeclared.append(f"{key}.default_scheduler")
    if undeclared:
        raise RuntimeError(
            "These families would ship a default chosen by sort order rather than by anyone: "
            + ", ".join(undeclared)
            + ". Declare default_sampler/default_scheduler in FAMILY_SAMPLER_ALLOWLISTS, or pin it "
            "on the family's operating point. If the value is not known yet, measure it -- do not "
            "let sorted()[0] decide what 112 checkpoints render with."
        )


_assert_every_family_declares_a_default()


def family_sampling_snapshot() -> dict[str, Any]:
    keys = set(FAMILY_SAMPLER_ALLOWLISTS) | set(_FAMILY_SAMPLING_ALIASES)
    return {key: family_sampling_choices(key) for key in sorted(keys)}


def family_operating_points_payload(family: Any) -> dict[str, Any]:
    """UI-facing operating-point block for a CONTRACT family, shipped in the family-contract status
    payload so a selector can be rendered GENERICALLY: the UI shows one entry per operating point (or
    none for a family with no row) and never needs to know a family name.

    Family-vs-route resolution (a real design decision -- see the pass report): this table is keyed BOTH
    by contract family (``wan`` = the dual-noise flagship, the only Wan route where fast/quality actually
    exist) AND by route-specific builder-config identity (``wan_core`` / ``wan_wrapper`` / ``wan_diffusers``
    -- single-point internal configs). A Wan request can route to any of those depending on the stack, but
    this payload deliberately ships the FAMILY-keyed CANONICAL set (dual-noise for Wan). The route-specific
    single-point configs are internal and are NOT surfaced as selectable points (they carry only a
    'default' anyway). Accepted consequence: the UI offers fast/quality for Wan; if a specific request
    actually routes to the single-model ``wan_core`` path, operating_point has no fast/quality effect there
    (that route has one config). That is inherent to a per-FAMILY (not per-request-stack) status payload.

    Returns ``{default_operating_point: str, operating_points: [{name, params, lora, acceleration}]}``,
    where ``params`` is the sampling params (everything except the declarative lora/acceleration blocks).
    Empty ``operating_points`` for a family with no table row (LTX is template-driven; cogvideox/mochi
    have none) -> the UI shows no selector."""
    row = _family_row(family)
    points: list[dict[str, Any]] = []
    for name, params in row.get("operating_points", {}).items():
        points.append({
            "name": name,
            "params": {k: v for k, v in params.items() if k not in ("lora", "acceleration")},
            "lora": dict(params.get("lora", {})),
            "acceleration": dict(params.get("acceleration", {})),
        })
    return {
        "default_operating_point": str(row.get("default_operating_point") or "").strip(),
        "operating_points": points,
        **family_sampling_choices(family),
    }


def resolve_family_defaults(family: Any, operating_point: Any, req: dict[str, Any]) -> dict[str, Any]:
    """Effective sampling params for a request. Per param: explicit request value > operating-point
    table value > absent (caller's own literal). A blank/""/"auto" sampler|scheduler resolves from the
    table. Absent/blank operating_point -> the family's default_operating_point (so a normal request
    with no operating_point is unchanged). Unknown family/operating point -> only whatever the request
    itself supplied (empty otherwise), so the builder's literals still cover everything. Validate a
    request-supplied operating_point with ``resolve_operating_point`` FIRST (warn+fallback) and pass the
    returned name here -- this function does NOT warn (it stays a pure lookup)."""
    op = str(operating_point or "").strip() or default_operating_point(family)
    table = operating_point_params(family, op)
    effective: dict[str, Any] = {}
    for param in _SAMPLING_PARAMS:
        override = _request_override(req, param)
        if override is not None:
            effective[param] = override
        elif param in table:
            effective[param] = table[param]
    return effective
