"""Did the faster arm produce the same picture.

A lever that is faster and wrong is not a win, and the three ways a lever on this list goes wrong
are known and specific:

* **black frames** -- SageAttention's documented overflow failure (``pv_accum_dtype``). Cheapest
  catastrophic failure to detect and the most expensive to publish a speedup over, so it is checked
  on every row whatever the lever.
* **a keyframe that drifted** -- i2v only. Frame-0 MAE against the conditioning image is a measure
  this project already uses: LTX ~3.5, Wan 2.2 5.19, Hunyuan 5.55 on render-proven runs.
* **visible artefacts** -- the caching and quantization levers degrade rather than break. Measured
  as mean absolute difference against the baseline arm's output at the SAME seed, which is the only
  comparison that means anything.

The measurements need pixels, so this module imports numpy and Pillow LAZILY and reports
``not_measured`` when they are absent -- a guard that says "pass" because nothing measured it is
worse than no guard, because it makes the row look checked. Video frames come out through ffmpeg
for the same reason: if it is not on PATH the answer is "not measured", never "fine".
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

VIDEO_SUFFIXES = {".mp4", ".webm", ".mkv", ".mov"}


def _pixels(path: Path):
    """An HxWx3 float array for an image, or None when the tooling is not here."""
    try:
        import numpy  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("quality guard: numpy/Pillow unavailable (%s); nothing will be measured", exc)
        return None
    try:
        with Image.open(path) as handle:
            return numpy.asarray(handle.convert("RGB"), dtype="float32")
    except Exception as exc:  # noqa: BLE001
        log.warning("quality guard: could not read %s (%s)", path, exc)
        return None


def _first_frame(path: Path):
    """Frame 0 of a video, via ffmpeg. None when ffmpeg is absent or the decode fails."""
    with tempfile.TemporaryDirectory() as tmp:
        frame = Path(tmp) / "frame0.png"
        try:
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-frames:v", "1", str(frame)],
                check=True, capture_output=True, timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("quality guard: ffmpeg could not read %s (%s)", path, exc)
            return None
        return _pixels(frame) if frame.is_file() else None


def frame(path: str | Path):
    """The comparable frame of an output, whether it is an image or a video."""
    path = Path(path)
    if not path.is_file():
        return None
    return _first_frame(path) if path.suffix.lower() in VIDEO_SUFFIXES else _pixels(path)


def measure(dest: str | Path, *, guards: tuple[str, ...], keyframe: str | Path | None = None,
            baseline_dest: str | Path | None = None) -> dict[str, Any]:
    """The measured values for the guards this row requires. Absent keys mean "not measured"."""
    values: dict[str, Any] = {}
    pixels = frame(dest)
    if pixels is None:
        return values

    if "black_frame" in guards:
        # Near-black rather than exactly zero: an overflow produces a frame that is black to the
        # eye, not necessarily one whose every channel is literally 0.
        values["black_fraction"] = float((pixels.max(axis=2) < 8.0).mean())

    if "frame0_mae" in guards and keyframe:
        reference = frame(keyframe)
        if reference is not None and reference.shape == pixels.shape:
            values["frame0_mae"] = float(abs(reference - pixels).mean())

    if "artefact" in guards and baseline_dest:
        reference = frame(baseline_dest)
        if reference is not None and reference.shape == pixels.shape:
            values["artefact_delta"] = float(abs(reference - pixels).mean())

    return values
