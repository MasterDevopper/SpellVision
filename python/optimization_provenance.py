"""What build produced this render.

Every render already writes ``generation_time_sec`` into its sidecar; none of the 59 keys in
``video_history.jsonl`` records which ComfyUI build, attention backend or fast-math flag produced
that number. The only published A/B on this project (Doc 55, sage vs SDPA on krea2) is
distinguishable solely because a human typed ``t4_sage`` and ``t4_sdpa`` into two output filenames
-- and the archive holds a third arm nobody mentioned, ``t4_sage_queue_3d2236390c95`` at 159.27s,
fifteen minutes before the quoted 120.72s sage run. The published ~3% delta is smaller than the
variance between two runs of the SAME arm. A number without its arm is not evidence.

The arm is read from the RUNNING process's argv via ``GET /system_stats``, never from what the
launcher intended: the Qt sage probe fails open to SDPA on a cold first launch
(``RuntimeProfile.cpp:307``), so intent and reality have diverged here before. Config files and
launch scripts describe what was ASKED for; only the live process describes what actually ran.

Attention flags are mutually exclusive in ComfyUI's ``cli_args.py`` -- if more than one somehow
shows up in a captured argv, both are recorded rather than one being silently preferred, because
picking one would be inventing certainty a bare argv scan does not have.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.request
from datetime import datetime
from typing import Any, Sequence

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 5.0

# `--fast` with no names enables every one of these (comfy/cli_args.py PerformanceFeature, per
# t4-research.md #1). A bare flag must be expanded to the actual set, not repeated as "--fast",
# or two renders that enabled different subsets would read as identical.
ALL_FAST_FEATURES = ("fp16_accumulation", "fp8_matrix_mult", "cublas_ops", "autotune")

# Flag -> backend name. Order matters only for the ambiguous-multiple-flags case, where the
# recorded order should be stable rather than dict-iteration-order-by-accident.
_ATTENTION_FLAG_TO_BACKEND = (
    ("--use-sage-attention", "sage"),
    ("--use-flash-attention", "flash"),
    ("--use-ck-attention", "ck"),
    ("--use-split-cross-attention", "split"),
    ("--use-quad-cross-attention", "quad"),
    ("--use-pytorch-cross-attention", "sdpa"),
)

# These four disable DynamicVRAM entirely (comfy_launch_policy.py's INERT_UNDER_DYNAMIC_VRAM);
# --disable-dynamic-vram is the direct flag. `--lowvram` is deliberately absent: its own help text
# says it does nothing while DynamicVRAM is on, so it does not change what actually ran.
_DYNAMIC_VRAM_DISABLING_FLAGS = frozenset({
    "--disable-dynamic-vram", "--novram", "--highvram", "--gpu-only", "--cpu",
})


def attention_from_argv(argv: Sequence[str]) -> str:
    """The attention backend the running process was launched with.

    No flag present means SDPA -- ComfyUI's own default when nothing is passed. More than one flag
    present (should not happen; cli_args treats them as mutually exclusive) is recorded as every
    match joined with "+" rather than guessing which one won.
    """
    argv = list(argv)
    found = [backend for flag, backend in _ATTENTION_FLAG_TO_BACKEND if flag in argv]
    if not found:
        return "sdpa"
    if len(found) == 1:
        return found[0]
    return "+".join(found)


def fast_from_argv(argv: Sequence[str]) -> list[str]:
    """Named `--fast` features, expanded from a bare flag to the full set it turns on."""
    argv = list(argv)
    try:
        index = argv.index("--fast")
    except ValueError:
        return []
    names: list[str] = []
    for token in argv[index + 1:]:
        if token.startswith("-"):
            break
        names.append(token)
    return names if names else list(ALL_FAST_FEATURES)


def dynamic_vram_from_argv(argv: Sequence[str]) -> bool:
    """DynamicVRAM is on by default on this core; only specific flags turn it off."""
    argv = list(argv)
    return not any(flag in argv for flag in _DYNAMIC_VRAM_DISABLING_FLAGS)


def reserve_vram_from_argv(argv: Sequence[str]) -> float | None:
    """The GB passed to ``--reserve-vram``, or ``None`` when the flag was not given."""
    argv = list(argv)
    try:
        index = argv.index("--reserve-vram")
    except ValueError:
        return None
    if index + 1 >= len(argv):
        return None
    try:
        return float(argv[index + 1])
    except (TypeError, ValueError):
        return None


def _cuda_from_torch_version(version: str | None) -> str | None:
    """``"2.10.0+cu128"`` -> ``"12.8"``. The last digit is always the minor version."""
    if not version:
        return None
    match = re.search(r"\+cu(\d{2,})", str(version))
    if not match:
        return None
    digits = match.group(1)
    return f"{digits[:-1]}.{digits[-1]}"


def _unknown_block(probed_at: str, error: str | None = None) -> dict[str, Any]:
    """The block a render still needs when the probe itself failed.

    A render must remain recordable when ComfyUI is unreachable (the diffusers-only routes never
    launch it at all) -- but it must not claim SDPA, or any other default it did not read.
    """
    return {
        "comfy_version": None,
        "comfy_argv": [],
        "attention_backend": "unknown",
        "fast_flags": [],
        "dynamic_vram": None,
        "reserve_vram_gb": None,
        "torch": None,
        "cuda": None,
        "python": None,
        "packages": {"sageattention": None, "triton": None, "comfy_kitchen": None, "comfy_aimdo": None},
        "probed_at": probed_at,
        "probe_error": error,
    }


class _UrllibOpener:
    """The real transport. Injectable so tests never touch a socket."""

    def open(self, request: Any, timeout: float | None = None) -> Any:
        return urllib.request.urlopen(request, timeout=timeout)


_DEFAULT_OPENER = _UrllibOpener()

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
# Same rationale as comfy_prompt_client's _OBJECT_INFO_TTL_SEC: a render should not pay an HTTP
# round trip for its own metadata, but a restart (or a launch-policy change) must not go unnoticed
# for longer than this.
_CACHE_TTL_SEC = 60.0


def invalidate_optimization_provenance(reason: str = "") -> None:
    """Drop the cached probe. Call after any ComfyUI restart, mirroring invalidate_comfy_object_info."""
    with _CACHE_LOCK:
        had = bool(_CACHE)
        _CACHE.clear()
    if had:
        log.warning("Invalidated cached optimization provenance%s", f": {reason}" if reason else "")


def _resolve_url(api_url: str | None) -> str:
    if api_url:
        return str(api_url).rstrip("/")
    from comfy_endpoint import comfy_endpoint

    return comfy_endpoint().rstrip("/")


def _fetch_system_stats(url: str, opener: Any, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{url}/system_stats",
        headers={"Accept": "application/json", "User-Agent": "SpellVision/1.0"},
    )
    response = opener.open(request, timeout=timeout)
    try:
        body = response.read()
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
    return json.loads(body.decode("utf-8"))


def _probe_uncached(url: str, opener: Any, timeout: float) -> dict[str, Any]:
    probed_at = datetime.now().isoformat()
    try:
        payload = _fetch_system_stats(url, opener, timeout)
    except Exception as exc:  # noqa: BLE001 -- a probe failure must never crash a render
        log.warning("optimization provenance probe failed (%s): %s", url, exc)
        return _unknown_block(probed_at, str(exc))

    system = payload.get("system") if isinstance(payload, dict) else None
    system = system if isinstance(system, dict) else {}
    raw_argv = system.get("argv")
    argv = [str(item) for item in raw_argv] if isinstance(raw_argv, list) else []
    raw_packages = system.get("comfy_package_versions")
    packages = raw_packages if isinstance(raw_packages, dict) else {}
    torch_version = system.get("pytorch_version")

    return {
        "comfy_version": system.get("comfyui_version"),
        "comfy_argv": argv,
        "attention_backend": attention_from_argv(argv) if argv else "unknown",
        "fast_flags": fast_from_argv(argv),
        "dynamic_vram": dynamic_vram_from_argv(argv) if argv else None,
        "reserve_vram_gb": reserve_vram_from_argv(argv),
        "torch": torch_version,
        "cuda": _cuda_from_torch_version(torch_version),
        "python": system.get("python_version"),
        "packages": {
            "sageattention": packages.get("sageattention"),
            "triton": packages.get("triton") or packages.get("triton-windows"),
            "comfy_kitchen": packages.get("comfy-kitchen"),
            "comfy_aimdo": packages.get("comfy-aimdo"),
        },
        "probed_at": probed_at,
        "probe_error": None,
    }


def probe(
    api_url: str | None = None,
    *,
    opener: Any = None,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """What the running ComfyUI process was actually launched with.

    Cached per resolved URL with a short TTL (see ``_CACHE_TTL_SEC``); a caller passing an
    explicit ``opener`` -- always a test -- bypasses the cache so repeated probes in the same
    process never see a stale fake response.
    """
    resolved = _resolve_url(api_url)
    use_cache = opener is None
    if use_cache and not force_refresh:
        with _CACHE_LOCK:
            entry = _CACHE.get(resolved)
        if entry and (time.monotonic() - entry[0]) < _CACHE_TTL_SEC:
            return entry[1]

    active_opener = opener if opener is not None else _DEFAULT_OPENER
    block = _probe_uncached(resolved, active_opener, timeout)
    if use_cache:
        with _CACHE_LOCK:
            _CACHE[resolved] = (time.monotonic(), block)
    return block
