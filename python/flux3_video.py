from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class Flux3RequestError(ValueError):
    pass


class Flux3ApiError(RuntimeError):
    pass


class Flux3Cancelled(RuntimeError):
    pass


FLUX3_API_URL = "https://api.bfl.ai/v1/flux-3-video"
_TERMINAL_ERROR_STATUSES = {
    "error",
    "request moderated",
    "content moderated",
    "task not found",
}


_SUPPORTED_ASPECT_RATIOS: tuple[tuple[str, float], ...] = (
    ("21:9", 21 / 9),
    ("2:1", 2.0),
    ("16:9", 16 / 9),
    ("4:3", 4 / 3),
    ("1:1", 1.0),
    ("3:4", 3 / 4),
    ("9:16", 9 / 16),
)


def _nearest_aspect_ratio(width: Any, height: Any) -> str:
    try:
        ratio = float(width) / float(height)
    except (TypeError, ValueError, ZeroDivisionError):
        return "auto"
    if ratio <= 0:
        return "auto"
    return min(_SUPPORTED_ASPECT_RATIOS, key=lambda item: abs(item[1] - ratio))[0]


def _duration_seconds(frames: Any, fps: Any) -> int | str:
    try:
        seconds = round(float(frames) / float(fps))
    except (TypeError, ValueError, ZeroDivisionError):
        return "auto"
    return max(5, min(20, int(seconds)))


def _image_reference(value: Any) -> str:
    reference = str(value or "").strip()
    if not reference:
        raise Flux3RequestError("FLUX.3 image-to-video requires a keyframe image.")
    if reference.startswith(("https://", "http://", "data:")):
        return reference
    path = Path(reference)
    if not path.is_file():
        raise Flux3RequestError(f"FLUX.3 keyframe image was not found: {path}")
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_flux3_payload(req: dict[str, Any]) -> dict[str, Any]:
    mode = str(req.get("command") or req.get("task_type") or "t2v").strip().lower()
    if mode not in {"t2v", "i2v"}:
        raise Flux3RequestError(f"Unsupported FLUX.3 video mode: {mode or '<empty>'}")
    prompt = str(req.get("prompt") or "").strip()
    if not prompt:
        raise Flux3RequestError("FLUX.3 requires a non-empty prompt.")

    payload = {
        "mode": mode,
        "prompt": prompt,
        "aspect_ratio": _nearest_aspect_ratio(req.get("width"), req.get("height")),
        "duration": _duration_seconds(req.get("frames") or req.get("num_frames"), req.get("fps")),
        "resolution": "hd",
        "version": "latest",
        "generate_audio": True,
        "safety_tolerance": 2,
        "draft": False,
    }
    if payload["mode"] == "i2v":
        payload["keyframes"] = _image_reference(req.get("input_image") or req.get("input_path"))
    return payload


def _json_request(request: Request, *, timeout: float) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise Flux3ApiError(f"BFL API returned HTTP {exc.code}: {detail}") from exc
    except (URLError, OSError) as exc:
        detail = getattr(exc, "reason", exc)
        raise Flux3ApiError(f"Could not reach the BFL API: {detail}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Flux3ApiError("BFL API returned an invalid JSON response.") from exc
    if not isinstance(payload, dict):
        raise Flux3ApiError("BFL API returned an unexpected response shape.")
    return payload


def _require_secure_service_url(url: str, label: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise Flux3ApiError(f"BFL API did not return a secure HTTPS {label} URL.")


def _download_video(url: str, output_path: Path, *, timeout: float) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = output_path.with_suffix(output_path.suffix + ".part")
    try:
        request = Request(url, headers={"Accept": "video/mp4"}, method="GET")
        with urlopen(request, timeout=timeout) as response, partial_path.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
        partial_path.replace(output_path)
    except (HTTPError, URLError, OSError) as exc:
        partial_path.unlink(missing_ok=True)
        raise Flux3ApiError(f"Could not download the FLUX.3 result: {exc}") from exc


def generate_flux3_video(
    req: dict[str, Any],
    output_path: str | Path,
    *,
    api_key: str | None = None,
    api_url: str = FLUX3_API_URL,
    poll_interval: float = 2.0,
    timeout: float = 30 * 60,
    should_cancel: Callable[[], bool] | None = None,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    key = str(api_key or os.environ.get("BFL_API_KEY") or "").strip()
    if not key:
        raise Flux3RequestError(
            "FLUX.3 is a paid BFL API preview. Set BFL_API_KEY before generating."
        )

    payload = build_flux3_payload(req)
    production_api = api_url.rstrip("/") == FLUX3_API_URL
    request = Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-key": key,
        },
        method="POST",
    )
    submit = _json_request(request, timeout=min(float(timeout), 90.0))
    request_id = str(submit.get("id") or "").strip()
    polling_url = str(submit.get("polling_url") or "").strip()
    if not request_id or not polling_url:
        raise Flux3ApiError("BFL API submission did not return an id and polling_url.")
    if production_api:
        _require_secure_service_url(polling_url, "polling")

    deadline = time.monotonic() + float(timeout)
    last_status = "Submitted"
    while True:
        if should_cancel and should_cancel():
            raise Flux3Cancelled("FLUX.3 generation was cancelled locally.")
        if time.monotonic() >= deadline:
            raise Flux3ApiError(f"FLUX.3 generation timed out after {float(timeout):.0f} seconds.")
        if poll_interval > 0:
            time.sleep(poll_interval)
        poll_request = Request(
            polling_url,
            headers={"Accept": "application/json", "x-key": key},
            method="GET",
        )
        result = _json_request(poll_request, timeout=min(float(timeout), 90.0))
        last_status = str(result.get("status") or "Unknown").strip()
        if on_status:
            on_status(last_status)
        normalized_status = last_status.lower()
        if normalized_status == "ready":
            sample_url = str((result.get("result") or {}).get("sample") or "").strip()
            if not sample_url:
                raise Flux3ApiError("BFL API reported Ready without a result video URL.")
            if production_api:
                _require_secure_service_url(sample_url, "result")
            destination = Path(output_path)
            _download_video(sample_url, destination, timeout=min(float(timeout), 180.0))
            return {
                "request_id": request_id,
                "status": last_status,
                "output_path": str(destination),
                "backend_route": "bfl_api",
                "mode": payload["mode"],
                "duration": payload["duration"],
                "aspect_ratio": payload["aspect_ratio"],
            }
        if normalized_status in _TERMINAL_ERROR_STATUSES:
            detail = str(result.get("details") or result.get("error") or last_status)
            raise Flux3ApiError(f"FLUX.3 generation failed: {detail}")
