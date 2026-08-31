"""One VRAM reading, and it says where it came from.

Ten places read GPU memory and they do not measure the same thing:

    torch in the WORKER process        image_runners, native_runners, worker_runtime,
                                       memory_optimization -- correct for diffusers, where the model
                                       really is in this process
    nvidia-smi subprocess              download_commands, for total VRAM when sizing a download
    NVML v2 in Qt                      GpuMemoryProbe, the live telemetry readout
    the literal 0.0                    four native/ComfyUI result payloads

The last row is the defect. On a native route the model is in ComfyUI's process, so asking torch in
the worker returns approximately nothing -- and those four sites wrote ``0.0`` into
``cuda_allocated_gb``, a field every other route fills with a real measurement. A zero that means
"not measured here" is indistinguishable from a zero that means "used no memory", and it is
presented as the latter. History rows, the bottom bar and any future budget check all read that
field.

So a reading carries its SOURCE, and "not measured" is ``None`` rather than zero. The distinction is
the whole point of the module: a number with no provenance cannot be compared against another number
with no provenance, which is how "31.4 GB peak" and "23.62 GB" ended up in the same table during the
FP8 measurement when one of them was a cached run that never sampled.

ComfyUI publishes real numbers at ``/system_stats`` -- ``vram_total``, ``vram_free`` and their torch
counterparts, for the process actually holding the weights -- so the native routes have an honest
answer available; they were simply not asking.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

_BYTES_PER_GB = 1024 ** 3

# What a reading describes. Kept as data because it travels with the numbers into result payloads
# and history, where the reader is no longer near the code that took it.
SOURCE_WORKER_TORCH = "torch:worker"
SOURCE_COMFY_STATS = "comfyui:/system_stats"
SOURCE_REMOTE = "remote:hosted-api"
SOURCE_UNAVAILABLE = "unavailable"

_MEASURES = {
    SOURCE_WORKER_TORCH: "the worker process's own torch allocator",
    SOURCE_COMFY_STATS: "the ComfyUI process holding the weights",
    SOURCE_REMOTE: "no local GPU -- the render ran on a hosted service",
    SOURCE_UNAVAILABLE: "nothing -- no reading could be taken",
}


@dataclass(frozen=True)
class VramReading:
    """A GPU memory reading. ``None`` means not measured, and never zero.

    ``allocated_gb`` / ``reserved_gb`` are torch allocator figures and exist only for the worker's
    own process. ``free_gb`` / ``total_gb`` describe the device and are what ComfyUI can report.
    """

    source: str = SOURCE_UNAVAILABLE
    allocated_gb: float | None = None
    reserved_gb: float | None = None
    free_gb: float | None = None
    total_gb: float | None = None
    # Peak since the last reset. This is the number every VRAM claim in this repo is actually about
    # -- the FP8 comparison was 29.49 against 30.94 GB PEAK, not current -- and it exists only for
    # the worker's own allocator. ComfyUI publishes no peak, so a native route leaves it None rather
    # than substituting a current reading that would read as a much smaller peak.
    max_allocated_gb: float | None = None
    max_reserved_gb: float | None = None

    @property
    def measured(self) -> bool:
        return self.source != SOURCE_UNAVAILABLE

    @property
    def measures(self) -> str:
        return _MEASURES.get(self.source, self.source)

    def payload(self) -> dict[str, Any]:
        """The fields a result envelope carries.

        ``cuda_allocated_gb`` and ``cuda_reserved_gb`` keep their names -- the UI, history rows and
        existing metadata all read them -- but they are now ``None`` when nothing was measured, and
        ``vram_source`` says which is which. A consumer that cannot handle null gets a field it can
        check first, which is strictly more than the zero told it.
        """
        return {
            "cuda_allocated_gb": self.allocated_gb,
            "cuda_reserved_gb": self.reserved_gb,
            "cuda_max_allocated_gb": self.max_allocated_gb,
            "cuda_max_reserved_gb": self.max_reserved_gb,
            "vram_free_gb": self.free_gb,
            "vram_total_gb": self.total_gb,
            "vram_source": self.source,
            "vram_measures": self.measures,
        }


def _gb(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number / _BYTES_PER_GB, 2) if number >= 0 else None


def worker_vram() -> VramReading:
    """What torch holds in THIS process. Correct for the diffusers routes and nothing else."""
    try:
        import torch
    except Exception:
        return VramReading()
    try:
        if not torch.cuda.is_available():
            return VramReading()
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        return VramReading(
            source=SOURCE_WORKER_TORCH,
            allocated_gb=_gb(torch.cuda.memory_allocated()),
            reserved_gb=_gb(torch.cuda.memory_reserved()),
            max_allocated_gb=_gb(torch.cuda.max_memory_allocated()),
            max_reserved_gb=_gb(torch.cuda.max_memory_reserved()),
            free_gb=_gb(free_bytes),
            total_gb=_gb(total_bytes),
        )
    except Exception as exc:
        # A reading that cannot be taken is reported as absent, never as zero -- which is the whole
        # defect this module exists to remove.
        log.warning("torch VRAM reading failed: %s", exc)
        return VramReading()


def comfy_vram(api_url: str, *, timeout: float = 5.0) -> VramReading:
    """What ComfyUI reports for the device it is running on.

    The native routes hand their work to another process, so this is the only honest answer
    available to them. ``allocated``/``reserved`` stay ``None``: ComfyUI publishes device totals and
    free memory, not a torch allocator figure for our benefit, and inventing one from
    ``total - free`` would attribute every other process's memory to this render.
    """
    try:
        from comfy_prompt_client import _http_get_json

        stats = _http_get_json(api_url, "/system_stats", timeout=timeout)
    except Exception as exc:
        log.warning("ComfyUI VRAM reading failed (%s): %s", api_url, exc)
        return VramReading()

    devices = (stats or {}).get("devices") if isinstance(stats, dict) else None
    if not isinstance(devices, list) or not devices:
        return VramReading()
    primary = devices[0] if isinstance(devices[0], dict) else {}
    free_gb = _gb(primary.get("vram_free"))
    total_gb = _gb(primary.get("vram_total"))
    if free_gb is None and total_gb is None:
        return VramReading()
    return VramReading(source=SOURCE_COMFY_STATS, free_gb=free_gb, total_gb=total_gb)


def remote_vram() -> VramReading:
    """For a route that renders on someone else's hardware -- FLUX.3 through the BFL API.

    The third case, and the one where the old literal ``0.0`` was very nearly TRUE: no local VRAM
    was used. It was still useless, because it is the same zero the ComfyUI routes wrote when they
    simply had not looked, and a reader cannot tell "this used no GPU here" from "nobody measured".
    Naming the source separates them.
    """
    return VramReading(source=SOURCE_REMOTE)


def reading_for(api_url: str | None = None) -> VramReading:
    """The right reader for the route: ComfyUI's when there is an endpoint, torch's otherwise."""
    if str(api_url or "").strip():
        reading = comfy_vram(str(api_url))
        if reading.measured:
            return reading
        # ComfyUI unreachable. Fall back to the worker's own view rather than to nothing, but the
        # source field still says which process was measured, so nobody compares the two by accident.
    return worker_vram()


def headroom_note(before: VramReading, after: VramReading | None = None) -> dict[str, Any]:
    """A submit-time reading, and the change across the render where both ends were measured.

    Not a budget check and not a refusal. No route has ever recorded what was free when it
    submitted, so an OOM arrives with no precondition on record and the first question after one --
    "how much was free when this started?" -- has never been answerable. Recording it is what makes
    a budget check possible later; guessing a threshold now would be a heuristic without a number.
    """
    note: dict[str, Any] = {
        "vram_free_at_submit_gb": before.free_gb,
        "vram_total_at_submit_gb": before.total_gb,
        "vram_source_at_submit": before.source,
    }
    if after is not None and before.free_gb is not None and after.free_gb is not None:
        if after.source == before.source:
            note["vram_free_delta_gb"] = round(before.free_gb - after.free_gb, 2)
        else:
            # Two sources measure two different things; subtracting them would manufacture a number.
            note["vram_free_delta_gb"] = None
    return note
