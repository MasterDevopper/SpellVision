"""Worker commands for model intelligence.

Six commands, each a thin adapter over `model_intelligence`: read what we know about one weight,
refresh a library, cancel that refresh, record a user override, resolve the settings a model
wants (which is what W2's generation pages ask for on every checkpoint change), and report which
roots are readable.

Two properties this module owns, both of which were claimed before they existed:

**Containment.** `_weight_path` validated only the file EXTENSION, so any `*.safetensors`-suffixed
path anywhere was accepted -- a `.spellvision.json` could be written outside every model root, and
`model_intel_set_user`'s `picture` argument would read any readable file and copy it beside any
path as `<stem>.preview.jpg`. `worker_auth` bounds this surface to LOCAL_TRUSTED, so it never
crossed a boundary the worker defends -- but the protocol document and a test named
`test_a_path_outside_the_model_roots_is_refused` both asserted a location check that the code did
not perform, and a false guarantee in a governing document is worse than a documented gap. A
request that names `roots` (or `models_roots`) now has `path` and `picture` resolved against them
and refused when they fall outside. A request that names NO roots gets no location check, which
is the honest state of affairs and is documented as such in the protocol doc.

**Cancellability and not pinning a connection.** `model_intel_refresh` used to call `job.run()`
inline, so a full library pass held one TCP handler for the better part of an hour and could not
be stopped. The work now runs on a background thread with a flag in `model_intelligence.jobs`.
`background: true` returns the job id immediately and publishes progress and the final result to
`subscribe`rs; without it the handler still streams on the open connection (what the shipped
protocol does), but `model_intel_cancel` on a second connection now ends it.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from model_intelligence import (
    hashing,
    jobs,
    previews,
    readable_roots,
    recommended,
    resolve,
    sidecar,
)
from model_intelligence.civitai_lookup import DEFAULT_HOST, CivitaiClient
from model_intelligence.hf_lookup import HfClient
from model_intelligence.refresh import RefreshJob


def _request_roots(req: dict[str, Any]) -> list[Path]:
    """The roots this request is bounded by. `models_roots` and `roots` are the same list."""
    raw = req.get("models_roots")
    if raw is None:
        raw = req.get("roots")
    return [Path(str(r)) for r in (raw or []) if str(r).strip()]


def _within(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve(strict=False)
    except (OSError, ValueError):
        return False
    for root in roots:
        try:
            if resolved.is_relative_to(root.resolve(strict=False)):
                return True
        except (OSError, ValueError):
            continue
    return False


def _weight_path(req: dict[str, Any]) -> tuple[Path | None, str]:
    """(path, refusal). A refusal names WHICH check failed, because "not a model file" for a
    path that is plainly a model file and merely in the wrong place is how the old test passed
    under a name about location while only the extension was ever examined."""
    text = str(req.get("path") or "").strip()
    if not text:
        return None, "path is not a model file"
    path = Path(text)
    if path.suffix.lower() not in hashing.MODEL_EXTENSIONS:
        return None, "path is not a model file"
    roots = _request_roots(req)
    if roots and not _within(path, roots):
        return None, "path is outside the model roots named by this request"
    return path, ""


def handle_model_intel_get_command(req: dict[str, Any]) -> dict[str, Any]:
    path, refusal = _weight_path(req)
    if path is None:
        return {"ok": False, "type": "model_intel", "error": refusal}
    payload = sidecar.read(path)
    return {
        "ok": True,
        "type": "model_intel",
        "path": str(path),
        "sidecar": payload,
        "recommended": (payload or {}).get("recommended") or {},
    }


def handle_model_recommended_settings_command(req: dict[str, Any]) -> dict[str, Any]:
    path, refusal = _weight_path(req)
    if path is None and str(req.get("path") or "").strip():
        return {"ok": False, "type": "model_recommended_settings", "error": refusal}
    family = str(req.get("family") or "").strip() or None
    mode = str(req.get("mode") or "").strip()
    warnings: list[str] = []

    payload = sidecar.read(path) if path is not None else None
    if payload:
        family = family or ((payload.get("identity") or {}).get("family"))
    elif path is not None:
        warnings.append("no sidecar yet; run model_intel_refresh to identify this model")

    live_samplers = req.get("live_samplers")
    live_schedulers = req.get("live_schedulers")
    resolved = resolve.resolve_model_defaults(
        path=str(path) if path else "",
        family=family,
        mode=mode,
        sidecar_payload=payload,
        live_samplers=list(live_samplers) if live_samplers else None,
        live_schedulers=list(live_schedulers) if live_schedulers else None,
        vram_gb=req.get("vram_gb"),
        host_ram_gb=req.get("host_ram_gb"),
    )
    warnings.extend(resolved["warnings"])

    # Owner ruling (Doc 62): Simple offers the samplers known good with THIS model; Advanced offers
    # those, a labelled separation, then everything else the build has -- one dropdown. The split is
    # resolved here, in Python, with the model's own published sampler folded in as an INPUT, so the
    # cockpit receives a finished pair of lists and never merges anything itself. The family-keyed
    # snapshot that `video_family_contracts` ships carries the same two groups; this reply is the
    # only place the per-model half can be known, and 483 of 759 weights now publish one.
    def _published(field: str) -> Any:
        entry = resolved["settings"].get(field)
        return entry.get("value") if isinstance(entry, dict) else None

    from family_operating_points import family_sampling_choices

    sampling = family_sampling_choices(
        resolved["family"] or family,
        model_sampler=_published("sampler"),
        model_scheduler=_published("scheduler"),
        live_samplers=list(live_samplers) if live_samplers else None,
        live_schedulers=list(live_schedulers) if live_schedulers else None,
    )

    return {
        "ok": True,
        "type": "model_recommended_settings",
        "path": str(path) if path else "",
        "family": resolved["family"] or family,
        "settings": resolved["settings"],
        "sampling": sampling,
        "warnings": warnings,
        "operating_point": resolved["operating_point"],
    }


def handle_model_intel_set_user_command(req: dict[str, Any]) -> dict[str, Any]:
    path, refusal = _weight_path(req)
    if path is None:
        return {"ok": False, "type": "model_intel_set_user", "error": refusal}

    payload = sidecar.read(path) or {
        "schema": sidecar.SCHEMA, "identity": {}, "display": {}, "recommended": {},
        "user": {"notes": "", "favorite": False},
    }
    display = dict(payload.get("display") or {})
    changed: list[str] = []

    name = str(req.get("name") or "").strip()
    if name:
        display["name"] = {"value": name, "user_override": True}
        changed.append("name")

    picture = str(req.get("picture") or "").strip()
    if picture:
        # The SOURCE of the picture is contained too. Unchecked, this was an arbitrary-file-read
        # primitive with an attacker-chosen destination: any readable file copied anywhere as
        # <stem>.preview.jpg.
        roots = _request_roots(req)
        if roots and not _within(Path(picture), roots):
            return {"ok": False, "type": "model_intel_set_user",
                    "error": "picture is outside the model roots named by this request"}
        try:
            cover = previews.set_user_picture(path, picture)
        except OSError as exc:
            return {"ok": False, "type": "model_intel_set_user", "error": str(exc)}
        # Record the picture the user chose, pointing at the file that was actually written.
        # Marking `images[0]` only worked when the site had already supplied a gallery -- so for
        # an UNIDENTIFIED weight, the one case where a user is most likely to want their own
        # picture, nothing recorded the choice at all and the next refresh overwrote the file.
        previous = [
            image for image in (display.get("images") or [])
            if isinstance(image, dict) and not image.get("user_override")
        ]
        display["images"] = [{
            "origin_url": "",
            "local_path": str(cover),
            "width": None,
            "height": None,
            "nsfw_level": 0,
            "is_cover": True,
            "user_override": True,
            "meta": {},
        }] + [{**image, "is_cover": False} for image in previous]
        changed.append("picture")

    notes = req.get("notes")
    if isinstance(notes, str):
        payload["user"] = {**(payload.get("user") or {}), "notes": notes}
        changed.append("notes")

    settings = req.get("settings")
    if isinstance(settings, dict):
        wanted = dict(payload.get("recommended") or {})
        for field, value in settings.items():
            if field in recommended.FIELDS:
                wanted[field] = {"value": value, "provenance": "user", "confidence": 1.0,
                                 "n": None, "total": None}
                changed.append(f"settings.{field}")
        payload["recommended"] = wanted

    payload["display"] = display
    try:
        sidecar.write(path, payload)
    except OSError as exc:
        return {"ok": False, "type": "model_intel_set_user", "error": str(exc)}

    return {"ok": True, "type": "model_intel_set_user", "path": str(path), "changed": changed}


def _fanout(payload: dict[str, Any]) -> None:
    """Publish to `subscribe`rs. A detached job has no connection of its own to answer on."""
    try:
        import worker_subscribe

        worker_subscribe.fanout(payload)
    except Exception:  # noqa: BLE001 -- a missing fan-out never costs the job
        pass


def _publisher(emitter: Any, background: bool) -> Callable[[dict[str, Any]], None]:
    if background or emitter is None:
        return _fanout
    return emitter.emit


def handle_model_intel_refresh_command(req: dict[str, Any], emitter: Any = None) -> dict[str, Any]:
    roots = [str(r) for r in (req.get("roots") or []) if str(r).strip()]
    if not roots:
        return {"ok": False, "type": "model_intel_refresh", "error": "roots is required"}

    host = str(req.get("civitai_host") or DEFAULT_HOST)
    api_key = req.get("civitai_api_key")
    if not api_key:
        try:
            from credential_store import get_credential

            api_key = get_credential("civitai_api_key")
        except Exception:
            api_key = None

    # The SECOND arm. HF public model cards need no token, so an absent one is normal; a stored
    # token is passed only for rate-limit headroom and is never logged or echoed. Doc 62 3j: this
    # module constructed a CivitAI client and nothing else, so `no_match` meant "CivitAI does not
    # know it" while the summary read as though both sites had been asked.
    hf_token = req.get("hf_token")
    if not hf_token:
        try:
            from credential_store import get_credential

            hf_token = get_credential("hf_token")
        except Exception:
            hf_token = None

    try:
        client = CivitaiClient(host=host, api_key=api_key)
    except ValueError as exc:
        # A bad host is a refusal, not a crash -- it can arrive here from a settings field the
        # user typed into, not just from code that already validated it.
        return {"ok": False, "type": "model_intel_refresh", "error": str(exc)}

    background = bool(req.get("background"))
    publish = _publisher(emitter, background)
    job_id = jobs.start()

    def progress(done: int, total: int, name: str) -> None:
        publish({
            "ok": True, "type": "model_intel_progress", "job_id": job_id,
            "current": done, "total": total, "message": name,
            "percent": int(100 * done / total) if total else 0,
        })

    # `files` is the narrow entry point RefreshJob already supports and nothing reached. The Models
    # inspector's "Refresh metadata" is about ONE weight; without this it walked every root, which
    # on the owner's library is 759 files and 2.09 TB of hashing for a button that names one file.
    # Contained by the same roots the rest of this module is.
    wanted = [str(f) for f in (req.get("files") or []) if str(f).strip()]
    files: list[str] | None = None
    if wanted:
        bounded = [Path(f) for f in wanted]
        outside = [str(f) for f in bounded if not _within(f, [Path(r) for r in roots])]
        if outside:
            return {"ok": False, "type": "model_intel_refresh",
                    "error": f"files outside the named roots: {', '.join(outside)}"}
        files = [str(f) for f in bounded]

    job = RefreshJob(
        roots,
        files=files,
        client=client,
        hf=HfClient(token=hf_token),
        models_root=req.get("models_root") or roots[0],
        progress=progress,
        cancel=jobs.cancel_check(job_id),
        force=bool(req.get("force")),
    )
    started = {"ok": True, "type": "model_intel_refresh_started", "job_id": job_id,
               "roots": roots, "background": background}
    outcome: dict[str, Any] = {}

    def _run() -> None:
        try:
            outcome["result"] = {**job.run(), "type": "model_intel_refresh", "job_id": job_id}
        except Exception as exc:  # noqa: BLE001
            # Nothing may escape to the dispatcher. The one-shot branches in worker_tcp.handle()
            # are not wrapped, so an exception reached socketserver.handle_error, which logs and
            # closes the connection WITHOUT a reply -- the caller waited out its timeout and got
            # "worker did not produce a complete response", indistinguishable from a hung worker
            # after up to 79 minutes of work.
            outcome["result"] = {"ok": False, "type": "model_intel_refresh", "job_id": job_id,
                                 "error": f"{exc.__class__.__name__}: {exc}"}
        finally:
            jobs.finish(job_id)
        if background:
            _fanout(outcome["result"])

    thread = threading.Thread(target=_run, name=f"model-intel-{job_id}", daemon=True)
    thread.start()

    if background:
        return started

    # Foreground: the caller gets the job id up front (so it can cancel) and the result on the
    # same connection, which is what the shipped protocol and its callers expect.
    if emitter is not None:
        emitter.emit(started)
    thread.join()
    return outcome.get("result") or {
        "ok": False, "type": "model_intel_refresh", "job_id": job_id,
        "error": "the refresh produced no result",
    }


def handle_model_intel_cancel_command(req: dict[str, Any]) -> dict[str, Any]:
    job_id = str(req.get("job_id") or "").strip()
    cancelled = jobs.cancel(job_id)
    reply: dict[str, Any] = {
        "ok": bool(cancelled),
        "type": "model_intel_cancel",
        "job_id": job_id,
        "cancelled": cancelled,
        "running": jobs.running(),
    }
    if not cancelled:
        reply["error"] = (
            f"no refresh is running with job id {job_id!r}" if job_id
            else "no refresh is running"
        )
    return reply


def handle_model_roots_status_command(req: dict[str, Any]) -> dict[str, Any]:
    roots = [str(r) for r in (req.get("roots") or []) if str(r).strip()]
    return {
        "ok": True,
        "type": "model_roots_status",
        "roots": [readable_roots.root_status(root) for root in roots],
    }
