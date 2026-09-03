"""Clothes-only plates for Character Studio shrink-wrap (Doc 44).

Produces isolated garment stills (white/empty bg). This is NOT a cooked wearable.
Stills→mesh / garment_cook stay Degraded.
"""
from __future__ import annotations

from comfy_endpoint import comfy_endpoint

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping

from request_payload import bounded_option
from comfy_graph_helpers import sampling_for, stated_seed, vae_decode_node
from krea2_graph import krea2_loader_block

log = logging.getLogger("spellvision.clothes_only")

CONTRACT = "spellvision.clothes-only.v1"
REQUIRED_VIEWS = ("front", "side", "back")
ALLOWED_DUMMIES = ("none", "whbs")
UTOPIC_QUANTS_UNET = "loxsUtopicWorldKrea2_v10Quants.safetensors"
DEFAULT_CLIP = "qwen3vl_4b_fp8_scaled.safetensors"
DEFAULT_VAE = "qwen_image_vae.safetensors"
BODY_VERTS_REQUIRED = 14517

# Lock 051 — never a jet-black mannequin or short doll hair.
WHBS_DUMMY_IDENTITY = (
    "the same specific woman as lock 051, deep warm brown skin, "
    "voluminous wavy white hair with sky-blue tips, icy blue eyes, "
    "strong brow, sharp jaw, gold hoop earrings, fierce expression, "
    "muscular hourglass figure, defined waist, "
    "very full heavy breasts, very wide hips, thick muscular thighs"
)

_VIEW_CAMERA = {
    "front": "front orthographic view, facing camera, garment facing viewer",
    "side": "true side orthographic view, profile, left side, garment in profile",
    "back": "back orthographic view, rear, garment seen from behind",
}

_PRODUCT_NEGATIVE = (
    "person, model, mannequin, dummy, face, second face, hands, feet, body, "
    "busy background, textured background, studio set, text, watermark, logo, "
    "label, hanger clutter, extra garments, bodysuit, catsuit, unitard, sheer, "
    "transparent, nude, 3d render, blender, octane, photoreal catalog, "
    "studio product photo, cgi, hard surface, official style lora"
)
_WHBS_NEGATIVE = (
    "second face, extra face, extra person, livestock head, splice, "
    "busy background, textured background, text, watermark, logo, "
    "bodysuit, catsuit, unitard, sheer, transparent, nude, maxi dress substitution, "
    "cropped at waist, missing feet, missing hips, 3d render, blender, octane, "
    "product catalog, official style lora, darkbrush, retroanime"
)


class ClothesOnlyError(ValueError):
    """Request cannot honestly produce clothes-only plates."""


def garment_slug(garment: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(garment or "").strip().lower())
    text = text.strip("-")
    return text or "garment"


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = re.split(r"[\n,]", value)
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        parts = [str(item) for item in value]
    else:
        parts = []
    return [item.strip() for item in parts if str(item).strip()]


def parse_views(value: Any, *, default_if_missing: bool = True) -> list[str]:
    if value is None:
        if default_if_missing:
            return list(REQUIRED_VIEWS)
        raise ClothesOnlyError("at least one view is required")
    views = [item.lower() for item in _as_list(value)]
    if not views:
        raise ClothesOnlyError("at least one view is required")
    unknown = [view for view in views if view not in REQUIRED_VIEWS]
    if unknown:
        raise ClothesOnlyError(f"unsupported views: {unknown}; allowed={list(REQUIRED_VIEWS)}")
    seen: list[str] = []
    for view in views:
        if view not in seen:
            seen.append(view)
    return seen


def parse_dummy(value: Any) -> str:
    dummy = str(value or "none").strip().lower()
    if dummy not in ALLOWED_DUMMIES:
        raise ClothesOnlyError(f"dummy must be 'whbs' or 'none', got {value!r}")
    return dummy


def validate_clothes_only_request(request: Mapping[str, Any]) -> tuple[str, list[str], str]:
    garment = str(
        request.get("garment")
        or request.get("garment_text")
        or request.get("prompt")
        or ""
    ).strip()
    if not garment:
        raise ClothesOnlyError("garment is required")
    views = parse_views(request.get("views"))
    if not views:
        raise ClothesOnlyError("at least one view is required")
    dummy = parse_dummy(request.get("dummy"))
    return garment, views, dummy


def canvas_for_dummy(dummy: str) -> tuple[int, int]:
    dummy = parse_dummy(dummy)
    if dummy == "whbs":
        return 768, 1344
    return 1024, 1024


def build_clothes_only_prompt(
    garment: str,
    views: Iterable[str] | None = None,
    dummy: str = "none",
) -> dict[str, Any]:
    garment = str(garment or "").strip()
    if not garment:
        raise ClothesOnlyError("garment is required")
    dummy = parse_dummy(dummy)
    view_list = parse_views(views)
    width, height = canvas_for_dummy(dummy)
    view_payload: dict[str, dict[str, str]] = {}
    for view in view_list:
        camera = _VIEW_CAMERA[view]
        if dummy == "none":
            prompt = (
                f"wrought style, painted volume, cinematic game still, materials and key light, "
                f"isolated {garment}, no body, no model, no mannequin, "
                f"floating garment, dark studio, black backdrop, key light, "
                f"painted concept plate, not a 3d render, {camera}, "
                f"separable clothing piece, opaque fabric, recreate the real garment, hips-length "
                f"silhouette honest to the garment"
            )
            negative = _PRODUCT_NEGATIVE
        else:
            prompt = (
                f"wrought style, cinematic game still, painted volume, materials and key light, "
                f"full body, entire figure, head to toe, feet visible, standing T-pose, "
                f"{WHBS_DUMMY_IDENTITY}, "
                f"wearing opaque {garment} over black briefs, clothes on, fully opaque fabric, "
                f"no sheer, no nipple show-through, hips visible, dark studio, key light, "
                f"{camera}, single identity, no second face"
            )
            negative = _WHBS_NEGATIVE
        view_payload[view] = {"prompt": prompt, "negative": negative, "view": view}
    return {
        "garment": garment,
        "dummy": dummy,
        "width": width,
        "height": height,
        "views": view_payload,
    }


def clothes_dest(request: Mapping[str, Any]) -> Path:
    explicit = str(request.get("dest") or request.get("output_dir") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    runtime_root = Path(
        str(request.get("runtime_root") or Path(__file__).resolve().parents[1])
    ).expanduser()
    character_id = garment_slug(
        str(request.get("character_id") or request.get("project") or "character_01")
    )
    slug = garment_slug(str(request.get("garment") or request.get("garment_text") or "garment"))
    return runtime_root / "runtime" / "characters" / character_id / "garments" / slug


def prepare_clothes_dest(request: Mapping[str, Any]) -> Path:
    garment, views, dummy = validate_clothes_only_request(
        {
            **dict(request),
            "garment": request.get("garment") or request.get("garment_text") or "garment",
            "views": request.get("views") or list(REQUIRED_VIEWS),
            "dummy": request.get("dummy") or "none",
        }
    )
    dest = clothes_dest({**dict(request), "garment": garment})
    dest.mkdir(parents=True, exist_ok=True)
    queue = _as_list(request.get("queue") or request.get("remaining"))
    notes = dest / "notes.txt"
    notes.write_text(
        "\n".join(
            [
                f"contract: {CONTRACT}",
                f"garment: {garment}",
                f"slug: {dest.name}",
                f"dummy: {dummy}",
                "wrap_dummy: whbs",
                f"views: {', '.join(views)}",
                f"pieces: {garment}",
                f"queue: {', '.join(queue) if queue else '(none)'}",
                f"body_verts_required: {BODY_VERTS_REQUIRED}",
                "cook: Degraded — clothes plates only, shrink-wrap scaffold, not a cooked wearable",
                "blocked_on: stills_to_mesh, garment_cook",
                "identity: frozen female.glb 14517; TRELLIS/UltraShape are not identity",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return dest


def build_clothes_only_krea2_graph(
    *,
    prompt: str,
    negative: str,
    width: int,
    height: int,
    unet_name: str = UTOPIC_QUANTS_UNET,
    clip_name: str = DEFAULT_CLIP,
    vae_name: str = DEFAULT_VAE,
    seed: int = 7,
    steps: int = 52,
    cfg: float = 3.5,
    filename_prefix: str = "clothes_only",
    # The cockpit sends `enable_vae_tiling` on every request and these builders take exploded
    # scalars rather than the request, so the switch had nowhere to land. Optional and defaulted so
    # every existing call keeps working; the live callers thread it.
    request: dict[str, Any] | None = None,
    object_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Native Krea2 T2I. Class types match live UNETLoader+CLIPLoader(type=krea2)+VAELoader."""
    # Was a hardcoded euler/simple. The cockpit sends its sampler row on every request and
    # this route dropped it -- and for krea2 the measured default is er_sde, settled by render
    # comparison on 2026-08-28, so these graphs rendered with a sampler the family's own
    # measurement had rejected while the cockpit route used the winner.
    _sampler, _scheduler = sampling_for(
        "krea2", request or {}, object_info or {}, "euler", "simple")
    width = max(256, int(width) - (int(width) % 16))
    height = max(256, int(height) - (int(height) % 16))
    return {
        **krea2_loader_block(
            unet_name=unet_name, clip_name=clip_name, vae_name=vae_name,
            positive=prompt, negative=negative,
            request=request, object_info=object_info,
        ),
        "7": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["5", 0],
                "seed": int(seed),
                "steps": max(1, int(steps)),
                "cfg": float(cfg) if float(cfg) > 0 else 1.0,
                "sampler_name": _sampler,
                "scheduler": _scheduler,
                "positive": ["4", 0],
                "negative": ["6", 0],
                "latent_image": ["7", 0],
                "denoise": 1.0,
            },
        },
        "9": vae_decode_node(request or {}, object_info or {}, samples=["8", 0], vae=["3", 0]),
        "10": {
            "class_type": "SaveImage",
            "inputs": {"images": ["9", 0], "filename_prefix": filename_prefix},
        },
    }


def _comfy_url(request: Mapping[str, Any]) -> str:
    # Resolved per call rather than snapshotted at import: comfy_endpoint already honours
    # request["comfy_api_url"], and a module-level constant would freeze whatever the environment
    # happened to be when this module was first imported.
    return str(request.get("comfy_url") or comfy_endpoint(request)).rstrip("/")


def _http_json(url: str, payload: dict[str, Any] | None = None, timeout: float = 60.0) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="GET" if payload is None else "POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else {}


def resolve_krea2_unet_name(object_info: Mapping[str, Any], model_path: str) -> str:
    preferred = Path(str(model_path or UTOPIC_QUANTS_UNET)).name
    choices: list[str] = []
    try:
        from comfy_graph_helpers import _sv_comfy_input_choices

        choices = list(_sv_comfy_input_choices(object_info, "UNETLoader", "unet_name"))
    except Exception:
        choices = []
    if preferred in choices:
        return preferred
    for name in choices:
        if preferred.lower() in name.lower() or name.endswith(preferred):
            return name
    for name in choices:
        lowered = name.lower()
        if "utopic" in lowered and "quant" in lowered:
            return name
    if choices:
        return choices[0]
    return preferred


def _download_comfy_image(api_url: str, image: Mapping[str, Any], dest: Path) -> Path:
    filename = str(image.get("filename") or "")
    if not filename:
        raise ClothesOnlyError("Comfy completed but returned no filename")
    subfolder = str(image.get("subfolder") or "")
    folder_type = str(image.get("type") or "output")
    query = f"filename={urllib.parse.quote(filename)}&type={urllib.parse.quote(folder_type)}"
    if subfolder:
        query += f"&subfolder={urllib.parse.quote(subfolder)}"
    url = f"{api_url}/view?{query}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        dest.write_bytes(resp.read())
    return dest


def _poll_history(api_url: str, prompt_id: str, timeout_sec: float = 900.0) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            history = _http_json(f"{api_url}/history/{prompt_id}", timeout=30.0)
        except Exception as exc:
            log.warning("clothes_only history poll failed: %s", exc)
            time.sleep(2.0)
            continue
        entry = history.get(prompt_id) if isinstance(history, dict) else None
        if isinstance(entry, dict) and entry.get("outputs"):
            return entry
        time.sleep(2.0)
    raise ClothesOnlyError(f"Comfy prompt {prompt_id} timed out")


def _first_history_image(history: Mapping[str, Any]) -> dict[str, Any]:
    outputs = history.get("outputs") or {}
    if not isinstance(outputs, dict):
        raise ClothesOnlyError("Comfy history has no outputs")
    for node in outputs.values():
        if not isinstance(node, dict):
            continue
        images = node.get("images") or []
        if images:
            return images[0]
    raise ClothesOnlyError("Comfy completed but produced no image")


def _unet_from_request(request: Mapping[str, Any]) -> str:
    model = str(request.get("model") or request.get("unet") or UTOPIC_QUANTS_UNET)
    name = Path(model).name
    return name or UTOPIC_QUANTS_UNET


def run_clothes_only(request: Mapping[str, Any], on_submitted: Any = None) -> dict[str, Any]:
    """Render the garment plates.

    ``on_submitted(api_url, prompt_id)`` is called the instant ComfyUI accepts a graph, before the
    history poll below blocks. It is how the job that owns this work learns the prompt id, and
    therefore the only way a cancel can reach across the process boundary and stop the render
    instead of merely stopping SpellVision from watching it.

    Each view is a separate prompt, so the callback fires once per view and the job accumulates one
    cancel hook per outstanding render.
    """
    garment, views, dummy = validate_clothes_only_request(request)
    dest = prepare_clothes_dest({**dict(request), "garment": garment, "views": views, "dummy": dummy})
    built = build_clothes_only_prompt(garment, views=views, dummy=dummy)
    queue = _as_list(request.get("queue") or request.get("remaining"))
    dry_run = bool(request.get("dry_run"))
    plates: dict[str, str] = {}
    prompt_ids: dict[str, str] = {}
    graphs: dict[str, dict[str, Any]] = {}
    unet_name = _unet_from_request(request)
    # stated_seed, not `or 7`: zero is a legal seed (KSampler declares min 0) and a value people
    # type deliberately, so `or` made the one seed most likely to be typed unsayable -- it rendered
    # as 7. The absent-default is unchanged.
    _stated_seed = stated_seed(request, "seed")
    seed = 7 if _stated_seed is None else _stated_seed
    steps = bounded_option(request, "steps", 52)
    cfg = float(request.get("cfg") if request.get("cfg") is not None else 3.5)

    object_info: dict[str, Any] = {}
    api_url = _comfy_url(request)
    if not dry_run:
        try:
            object_info = _http_json(f"{api_url}/object_info", timeout=30.0)
            unet_name = resolve_krea2_unet_name(object_info, unet_name)
        except Exception as exc:
            raise ClothesOnlyError(f"Comfy :8188 object_info unavailable: {exc}") from exc
        for class_type in ("UNETLoader", "CLIPLoader", "VAELoader", "EmptySD3LatentImage", "KSampler"):
            if class_type not in object_info:
                raise ClothesOnlyError(f"live Comfy is missing class_type {class_type}")

    for index, view in enumerate(views):
        view_spec = built["views"][view]
        plate_path = dest / f"{view}.png"
        prefix = f"clothes_only_{dest.name}_{dummy}_{view}"
        graph = build_clothes_only_krea2_graph(
            request=request,
            object_info=object_info,
            prompt=view_spec["prompt"],
            negative=view_spec["negative"],
            width=int(built["width"]),
            height=int(built["height"]),
            unet_name=unet_name,
            seed=seed + index,
            steps=steps,
            cfg=cfg,
            filename_prefix=prefix,
        )
        graphs[view] = graph
        plates[view] = str(plate_path)
        if dry_run:
            continue
        log.warning("clothes_only submit %s dummy=%s dest=%s", view, dummy, dest)
        submitted = _http_json(f"{api_url}/prompt", {"prompt": graph}, timeout=60.0)
        prompt_id = str(submitted.get("prompt_id") or submitted.get("promptId") or "")
        if not prompt_id:
            raise ClothesOnlyError(f"Comfy /prompt returned no prompt_id for {view}: {submitted!r}")
        prompt_ids[view] = prompt_id
        if callable(on_submitted):
            try:
                on_submitted(api_url, prompt_id)
            except Exception:
                # Bookkeeping must never turn an accepted submission into a failed render.
                pass
        history = _poll_history(api_url, prompt_id)
        image = _first_history_image(history)
        _download_comfy_image(api_url, image, plate_path)
        if not plate_path.is_file() or plate_path.stat().st_size < 32:
            raise ClothesOnlyError(f"{view} plate was not written: {plate_path}")

    job = {
        "contract": CONTRACT,
        "command": "clothes_only",
        "garment": garment,
        "slug": dest.name,
        "dummy": dummy,
        "wrap_dummy": "whbs",
        "views": list(views),
        "queue": queue,
        "dest": str(dest),
        "plates": plates,
        "width": built["width"],
        "height": built["height"],
        "unet": unet_name,
        "dry_run": dry_run,
        "cook_complete": False,
        "blocked_on": ["stills_to_mesh", "garment_cook"],
        "body_verts_required": BODY_VERTS_REQUIRED,
        "prompt_ids": prompt_ids,
        "prompts": {view: built["views"][view]["prompt"] for view in views},
    }
    (dest / "clothes_only_job.json").write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "command": "clothes_only",
        "garment": garment,
        "dummy": dummy,
        "views": list(views),
        "queue": queue,
        "dest": str(dest),
        "plates": plates,
        "prompt_ids": prompt_ids,
        "graphs": graphs if dry_run else {view: "submitted" for view in views},
        "cook_complete": False,
        "blocked_on": ["stills_to_mesh", "garment_cook"],
        "output": plates.get(views[0], str(dest)),
        "output_path": plates.get(views[0], str(dest)),
    }


def run_clothes_only_job(req: dict[str, Any], emitter: Any, job: Any, active_job: Any) -> dict[str, Any]:
    """Worker dispatch entry. Fail closed. Never claims cook is done."""
    from worker_service_state import JobState, complete_job, transition_job

    if emitter is not None and job is not None:
        transition_job(job, JobState.STARTING)
        emitter.status(job, "clothes_only: preparing dest")
        emitter.emit_job_update(job)
        transition_job(job, JobState.RUNNING)
    from comfy_prompt_client import track_comfy_prompt

    payload = run_clothes_only(
        req,
        on_submitted=(
            (lambda api_url, prompt_id: track_comfy_prompt(active_job, api_url, prompt_id))
            if active_job is not None else None
        ),
    )
    if emitter is not None:
        emitter.status(job, f"clothes_only dest {payload['dest']}")
    if job is not None:
        complete_job(job, payload)
        if emitter is not None:
            emitter.emit_job_update(job)
    return payload
