"""Can this job run on THAT ComfyUI? Three checks in cost order, each able to say why not.

The transport to a second box was proven live on 2026-09-01 against the 3090 Ti: a 904-class
``/object_info`` over the wire and a 1.28 MB PNG back through ``/view``, first try. What was never
proven is that a job *would run there*, and both ways it fails are silent:

* a model the cockpit offered is simply not on that machine -- its ComfyUI walks its own model
  directories -- and ``/prompt`` answers 400 naming a node the user never chose;
* a node class the graph uses belongs to a pack installed here and not there.

So this module is the gate, and it FAILS CLOSED with a NAME. "Cannot run there" tells a user
nothing; "SpellNode does not have loxsUtopicWorldKrea2_v20Quants.safetensors" tells them what to
copy.

## Why health is ``/system_stats`` and never a model listing

ComfyUI's ``folder_paths`` walks its model directories to answer a filename list. On a Linux node
whose models arrive over CIFS, the research recorded ``cifs_wait_for_server_reconnect`` stalling a
ComfyUI start for minutes when the share's host was down -- so a health check built on a model
listing hangs exactly in the state the health check exists to detect, and reports nothing.
``/system_stats`` touches no model directory. It runs first, on its own short timeout, and the
later checks never run if it fails.

## Why ``/models/{folder}`` and not only ``/object_info``

``GET /models/{folder}`` (upstream since 2024-08/09, so present on the v0.34.0 core) returns
``folder_paths.get_filename_list`` for one category -- kilobytes, against ``/object_info``'s 6.76 MB
on this core. It is the primary. ``/object_info`` is consulted only on a miss, because it is the
AUTHORITY on two things the folder route cannot answer: whether an input is a catalogued file at
all, and which catalogue a given loader actually reads. When it is consulted, its combo is read
through ``comfy_graph_helpers``' one reader, which knows both live shapes -- the core publishes the
legacy ``[[choices], {}]`` and the V3 ``["COMBO", {"options": [...]}]`` at the same time, and a
reader that knows one returns ``[]`` for the other, which every caller would read as "no
constraint" rather than as "I could not tell".
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable

from comfy_graph_helpers import _comfy_input_declares_combo, _sv_comfy_input_choices
from comfy_prompt_client import _comfy_object_info, _normalized_model_name, http_get_json_status

log = logging.getLogger(__name__)

# Which ``/models/{folder}`` a loader input is served from. Ordered: the first folder the endpoint
# answers 200 for wins. A name absent from this table is not assumed to be a model -- it falls
# through to /object_info, which is the only thing that knows.
INPUT_FOLDERS: dict[str, tuple[str, ...]] = {
    "ckpt_name": ("checkpoints",),
    "unet_name": ("diffusion_models", "unet"),
    "gguf_name": ("unet", "diffusion_models"),
    "lora_name": ("loras",),
    "vae_name": ("vae",),
    # The core renamed this category and kept the old name working; ask for both rather than
    # picking the one that happens to be right on the box in front of us.
    "clip_name": ("text_encoders", "clip"),
    "clip_name1": ("text_encoders", "clip"),
    "clip_name2": ("text_encoders", "clip"),
    "text_encoder": ("text_encoders", "clip"),
    "control_net_name": ("controlnet",),
    "style_model_name": ("style_models",),
    "clip_vision_name": ("clip_vision",),
    "upscale_model_name": ("upscale_models",),
    "model_name": ("upscale_models",),
    "ipadapter_file": ("ipadapter",),
    "instantid_file": ("instantid",),
}

_MODELS_CACHE: dict[tuple[str, str], list[str] | None] = {}
_MODELS_LOCK = threading.Lock()


def forget_endpoint(api_url: str) -> None:
    """Drop this endpoint's cached model listings. Tests and any restart path call it."""
    root = str(api_url or "").rstrip("/")
    with _MODELS_LOCK:
        for key in [k for k in _MODELS_CACHE if k[0] == root]:
            _MODELS_CACHE.pop(key, None)


# --- results ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Refusal:
    """A named reason. ``missing`` is what a user has to go and put on the machine."""

    check: str            # health | models | nodes
    code: str             # machine-readable
    detail: str           # one sentence, names the endpoint and the thing
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapabilityReport:
    endpoint: str
    label: str = ""
    ok: bool = False
    checks_run: tuple[str, ...] = ()
    refusals: tuple[Refusal, ...] = ()
    health: dict[str, Any] = field(default_factory=dict)

    def missing_models(self) -> tuple[str, ...]:
        return tuple(m for r in self.refusals if r.check == "models" for m in r.missing)

    def missing_classes(self) -> tuple[str, ...]:
        return tuple(m for r in self.refusals if r.check == "nodes" for m in r.missing)

    def where(self) -> str:
        return self.label or self.endpoint

    def explain(self) -> str:
        if self.ok:
            return f"{self.where()} can run this job."
        if not self.refusals:
            return f"{self.where()} was not checked."
        return " ".join(r.detail for r in self.refusals)

    def payload(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "label": self.label,
            "ok": self.ok,
            "checks_run": list(self.checks_run),
            "message": self.explain(),
            "health": dict(self.health),
            "refusals": [
                {"check": r.check, "code": r.code, "detail": r.detail, "missing": list(r.missing)}
                for r in self.refusals
            ],
        }


# --- check 1: health ----------------------------------------------------------------------------

def endpoint_health(api_url: str, *, timeout_sec: float = 5.0) -> dict[str, Any]:
    """``GET /system_stats``. Touches no model directory, so a dead model share cannot hide a
    dead endpoint behind it."""
    root = str(api_url or "").rstrip("/")
    try:
        status, payload = http_get_json_status(root, "/system_stats", timeout=float(timeout_sec))
    except Exception as exc:
        return {"ok": False, "endpoint": root, "error": f"{type(exc).__name__}: {exc}"}
    if status >= 400 or not isinstance(payload, dict):
        return {"ok": False, "endpoint": root, "status": status, "error": f"HTTP {status} from /system_stats"}
    system = payload.get("system") if isinstance(payload.get("system"), dict) else {}
    return {
        "ok": True,
        "endpoint": root,
        "status": status,
        "comfyui_version": system.get("comfyui_version"),
        "system_stats": payload,
    }


# --- check 2: models ----------------------------------------------------------------------------

def model_references(prompt: dict[str, Any]) -> list[tuple[str, str, str]]:
    """``(class_type, input_name, value)`` for every name-shaped loader input in the graph."""
    refs: list[tuple[str, str, str]] = []
    for node in (prompt or {}).values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "").strip()
        inputs = node.get("inputs")
        if not class_type or not isinstance(inputs, dict):
            continue
        for input_name, value in inputs.items():
            if input_name not in INPUT_FOLDERS:
                continue
            if isinstance(value, str) and value.strip():
                refs.append((class_type, str(input_name), value.strip()))
    return refs


def _folder_listing(api_url: str, folder: str, *, timeout_sec: float) -> list[str] | None:
    """The endpoint's own ``get_filename_list`` for one category. ``None`` = it could not say."""
    key = (api_url, folder)
    with _MODELS_LOCK:
        if key in _MODELS_CACHE:
            return _MODELS_CACHE[key]
    try:
        status, payload = http_get_json_status(api_url, f"/models/{folder}", timeout=float(timeout_sec))
        names = [str(n) for n in payload] if status == 200 and isinstance(payload, list) else None
    except Exception as exc:
        log.warning("endpoint_capability: /models/%s on %s failed: %s", folder, api_url, exc)
        names = None
    with _MODELS_LOCK:
        _MODELS_CACHE[key] = names
    return names


def check_models(
    prompt: dict[str, Any],
    api_url: str,
    *,
    timeout_sec: float = 15.0,
    object_info_timeout_sec: float = 30.0,
) -> tuple[list[str], list[str]]:
    """``(missing, unverifiable)``. Both refuse -- "I could not find out" is not a pass."""
    root = str(api_url or "").rstrip("/")
    refs = model_references(prompt)
    if not refs:
        return [], []

    object_info: dict[str, Any] | None = None
    object_info_error: str | None = None

    def _object_info() -> dict[str, Any] | None:
        nonlocal object_info, object_info_error
        if object_info is None and object_info_error is None:
            try:
                object_info = _comfy_object_info(root, budget_sec=float(object_info_timeout_sec))
            except Exception as exc:
                object_info_error = f"{type(exc).__name__}: {exc}"
        return object_info

    missing: list[str] = []
    unverifiable: list[str] = []
    for class_type, input_name, value in refs:
        wanted = _normalized_model_name(value)
        listings = [_folder_listing(root, f, timeout_sec=timeout_sec) for f in INPUT_FOLDERS[input_name]]
        if any(ns is not None and wanted in {_normalized_model_name(n) for n in ns} for ns in listings):
            continue

        # Either the folder route said no, or it could not answer. /object_info is the authority on
        # both remaining questions: is this input catalogued at all, and does the catalogue hold it.
        info = _object_info()
        if info is None:
            if value not in unverifiable:
                unverifiable.append(value)
            continue
        if not _comfy_input_declares_combo(info, class_type, input_name):
            # No combo means this is not a catalogued file input on this endpoint (a free string,
            # or a class that does not declare it). Calling that "missing" would refuse graphs over
            # inputs that are not files.
            continue
        choices = _sv_comfy_input_choices(info, class_type, input_name)
        if wanted in {_normalized_model_name(c) for c in choices}:
            continue
        if value not in missing:
            missing.append(value)
    return missing, unverifiable


# --- check 3: node classes -----------------------------------------------------------------------

def graph_classes(prompt: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    for node in (prompt or {}).values():
        if isinstance(node, dict):
            name = str(node.get("class_type") or "").strip()
            if name and name not in seen:
                seen.append(name)
    return seen


def check_node_classes(
    prompt: dict[str, Any],
    api_url: str,
    *,
    timeout_sec: float = 30.0,
    pinned_contract: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], str | None]:
    """``(absent_classes, breaking_contract_findings, error)`` against that endpoint's schema.

    The ``/object_info`` fetch is the one in ``comfy_prompt_client``, cached per ``api_url`` -- so
    two endpoints keep two schemas rather than one overwriting the other.
    """
    root = str(api_url or "").rstrip("/")
    try:
        info = _comfy_object_info(root, budget_sec=float(timeout_sec))
    except Exception as exc:
        return [], [], f"{type(exc).__name__}: {exc}"
    absent = [c for c in graph_classes(prompt) if c not in info]

    findings: list[str] = []
    if pinned_contract:
        from comfy_node_contract import contract_for_classes, diff_contract

        live = contract_for_classes(info, pinned_contract.get("classes", {}).keys())
        findings = [str(f) for f in diff_contract(pinned_contract, live).breaking]
    return absent, findings, None


# --- the gate -------------------------------------------------------------------------------------

def check_endpoint(
    prompt: dict[str, Any],
    api_url: str,
    *,
    label: str = "",
    health_timeout_sec: float = 5.0,
    models_timeout_sec: float = 15.0,
    object_info_timeout_sec: float = 30.0,
    pinned_contract: dict[str, Any] | None = None,
) -> CapabilityReport:
    root = str(api_url or "").rstrip("/")
    where = label or root
    if not isinstance(prompt, dict) or not graph_classes(prompt):
        return CapabilityReport(
            endpoint=root, label=label, ok=False, checks_run=(),
            refusals=(Refusal("graph", "no_graph", "There is no graph to check, so no endpoint can be cleared to run it."),),
        )

    health = endpoint_health(root, timeout_sec=health_timeout_sec)
    if not health.get("ok"):
        return CapabilityReport(
            endpoint=root, label=label, ok=False, checks_run=("health",), health=health,
            refusals=(Refusal(
                "health", "unreachable",
                f"{where} did not answer a health check on /system_stats: {health.get('error')}.",
            ),),
        )

    refusals: list[Refusal] = []
    missing, unverifiable = check_models(
        prompt, root, timeout_sec=models_timeout_sec, object_info_timeout_sec=object_info_timeout_sec,
    )
    if missing:
        refusals.append(Refusal(
            "models", "models_absent",
            f"{where} does not have {_and_list(missing)}.",
            tuple(missing),
        ))
    if unverifiable:
        refusals.append(Refusal(
            "models", "models_unverifiable",
            f"{where} could not be asked whether it has {_and_list(unverifiable)}; refusing rather than guessing.",
            tuple(unverifiable),
        ))
    if refusals:
        return CapabilityReport(endpoint=root, label=label, ok=False, checks_run=("health", "models"),
                                health=health, refusals=tuple(refusals))

    absent, findings, error = check_node_classes(
        prompt, root, timeout_sec=object_info_timeout_sec, pinned_contract=pinned_contract,
    )
    if error:
        refusals.append(Refusal("nodes", "schema_unreadable",
                                f"{where} would not return its node schema: {error}."))
    if absent:
        refusals.append(Refusal("nodes", "classes_absent",
                                f"{where} has no node class {_and_list(absent)}.", tuple(absent)))
    if findings:
        refusals.append(Refusal("nodes", "contract_drift",
                                f"{where} answers a different node API: {'; '.join(findings)}.",
                                tuple(findings)))

    return CapabilityReport(
        endpoint=root, label=label, ok=not refusals,
        checks_run=("health", "models", "nodes"), health=health, refusals=tuple(refusals),
    )


def _and_list(values: Iterable[str]) -> str:
    items = [str(v) for v in values]
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " and " + items[-1]
