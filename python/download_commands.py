"""Worker commands for the background download lane.

Thin adapters over ``download_manager``: parse the request, call the lane, return a payload.
No transfer logic lives here, and none of these block -- ``start_download`` returns as soon as
the record exists, which is what keeps the rest of the app usable while a checkpoint comes down.

Credentials are read from the DPAPI-backed store the same way the import path does, so a token
saved in Settings actually reaches the download. Passing one explicitly still wins, which is how
the tests avoid touching the real store.
"""
from __future__ import annotations

from typing import Any

from request_payload import bounded_option
from download_manager import get_download_manager


def _manager():
    return get_download_manager()


def _credentials(req: dict[str, Any]) -> dict[str, Any]:
    """Explicit values win; otherwise fall back to the saved credentials."""
    civitai = str(req.get("civitai_api_key") or "").strip() or None
    hf = str(req.get("hf_token") or "").strip() or None
    if civitai is None or hf is None:
        try:
            from credential_store import get_credential

            civitai = civitai or (get_credential("civitai_api_key") or None)
            hf = hf or (get_credential("hf_token") or None)
        except Exception:
            # A missing or locked credential store is not a reason to refuse a public download.
            pass
    out: dict[str, Any] = {}
    if civitai:
        out["civitai_api_key"] = civitai
    if hf:
        out["hf_token"] = hf
    return out


def handle_start_download_command(req: dict[str, Any]) -> dict[str, Any]:
    reference = str(req.get("reference") or req.get("model") or req.get("url") or "").strip()
    if not reference:
        return {
            "type": "download_ack", "ok": False, "action": "start_download",
            "error": "start_download requires a reference (a URL, hf:// ref, or Civitai id)",
        }

    context = req.get("context")
    kwargs: dict[str, Any] = _credentials(req)
    if req.get("cache_root"):
        kwargs["cache_root"] = str(req["cache_root"])
    if req.get("force_download"):
        kwargs["force_download"] = True
    # Only used to disambiguate a Civitai model-page URL whose model holds variants for several
    # architectures. Never used to pick a different model.
    if req.get("preferred_architecture"):
        kwargs["preferred_architecture"] = str(req["preferred_architecture"])

    try:
        record = _manager().start(
            reference,
            label=str(req.get("label") or "").strip() or None,
            asset_type=str(req.get("asset_type") or "model"),
            context=context if isinstance(context, dict) else None,
            **kwargs,
        )
    except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
        return {
            "type": "download_ack", "ok": False, "action": "start_download",
            "reference": reference, "error": str(exc) or exc.__class__.__name__,
        }

    return {
        "type": "download_ack", "ok": True, "action": "start_download",
        "download_id": record.download_id, "item": record.payload(),
    }


def handle_civitai_variants_command(req: dict[str, Any]) -> dict[str, Any]:
    """List the selectable versions behind a Civitai reference, WITHOUT downloading anything.

    Exists so the UI can ask the question before starting a transfer rather than discovering the
    ambiguity from a failed one. ``needs_choice`` is the field to branch on: a single-version model
    answers False and the caller can go straight to the download.
    """
    reference = str(req.get("reference") or req.get("model") or req.get("url") or "").strip()
    if not reference:
        return {
            "type": "civitai_variants", "ok": False,
            "error": "civitai_variants requires a reference",
        }

    from model_sources import (
        _civitai_api_get_json,
        model_variants,
        parse_asset_reference,
        precision_candidates,
        precision_disputes,
        recommend_across_variants,
        select_variant,
    )

    ref = parse_asset_reference(reference, asset_type=str(req.get("asset_type") or "model"))
    if ref.kind not in {"civitai_model_page", "civitai_model_version"} or not ref.model_id:
        # Not a Civitai model reference, or one that already names its version: nothing to choose.
        return {
            "type": "civitai_variants", "ok": True, "reference": reference,
            "needs_choice": False, "variants": [], "kind": ref.kind,
        }
    if ref.model_version_id:
        return {
            "type": "civitai_variants", "ok": True, "reference": reference,
            "needs_choice": False, "variants": [], "kind": ref.kind,
            "model_version_id": ref.model_version_id,
        }

    creds = _credentials(req)
    try:
        payload = _civitai_api_get_json(
            f"https://civitai.com/api/v1/models/{ref.model_id}",
            civitai_api_key=creds.get("civitai_api_key"),
            timeout_sec=bounded_option(req, "timeout_sec", 30),
        )
    except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
        return {
            "type": "civitai_variants", "ok": False, "reference": reference,
            "error": f"Could not read Civitai model {ref.model_id}: {exc}",
        }

    variants = model_variants(payload)
    preferred = str(req.get("preferred_architecture") or "").strip() or None
    auto = select_variant(variants, preferred)
    # Explicit None check: a caller passing 0 means "assume no VRAM", which `or` would turn into
    # auto-detection. Same falsy-zero trap as the object_info budget.
    requested_vram = req.get("vram_gb")
    vram_gb = _detected_vram_gb() if requested_vram is None else float(requested_vram) or None

    # ONE mark for the whole model, not one per version. Civitai puts the precision axis on the
    # version axis as often as on the file axis -- model 2726029 ships six versions of one
    # checkpoint, one precision each -- and a per-version recommendation marked all six. Measured
    # 6 of 6: a star on every row is a star that says nothing.
    recommendation = recommend_across_variants(variants, vram_gb)
    disputes = precision_disputes(variants)

    return {
        "type": "civitai_variants", "ok": True,
        "reference": reference,
        "model_id": ref.model_id,
        "model_name": str(payload.get("name") or ""),
        "model_type": str(payload.get("type") or ""),
        "preferred_architecture": preferred,
        # False when there is nothing to ask: one version, or the preference picked exactly one.
        "needs_choice": len(variants) > 1 and auto is None,
        "auto_selected": None if auto is None else auto.version_id,
        "variants": [
            {
                "version_id": v.version_id,
                "version_name": v.version_name,
                "base_model": v.base_model,
                "architecture": v.architecture,
                "filename": v.filename,
                "size_kb": v.size_kb,
                "download_url": v.download_url,
                # True when this variant suits the architecture the caller asked about, so the UI
                # can mark the compatible ones without hiding the rest.
                "architecture_match": bool(preferred and v.architecture == preferred),
                # Every precision of THIS checkpoint. One Civitai version routinely carries the
                # same filename at bf16, fp8, int8 and nvfp4, so the UI needs file_id to tell them
                # apart -- a name cannot.
                "files": [
                    {
                        "file_id": f.file_id,
                        "name": f.name,
                        "precision": f.precision,
                        "size_kb": f.size_kb,
                        "size_gb": round(f.size_gb, 2),
                        "download_url": f.download_url,
                        "recommended": recommendation == (v.version_id, f.file_id),
                        # Non-empty when the file's declared precision contradicts its size. The
                        # row stays selectable -- it is marked, never hidden -- but it is never the
                        # recommendation.
                        "precision_dispute": disputes.get(f.file_id, ""),
                    }
                    for f in v.precision_variants()
                ],
                # The text encoder / VAE bundled in the same version -- Civitai's own "Required
                # Components", which we would otherwise make the user hunt for separately.
                "companions": [
                    {"file_id": f.file_id, "name": f.name, "size_gb": round(f.size_gb, 2),
                     "download_url": f.download_url}
                    for f in v.companion_files()
                ],
            }
            for v in variants
        ],
    }


def _detected_vram_gb() -> float | None:
    """Total VRAM, for sizing the recommendation. None when it cannot be read.

    None is a real answer: recommend_file falls back to "highest precision" and lets the user read
    the size, which is better than sizing against a card we guessed at.
    """
    try:
        import subprocess

        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8,
        )
        if out.returncode == 0 and out.stdout.strip():
            return float(out.stdout.strip().splitlines()[0]) / 1024.0
    except Exception:
        pass
    return None


def handle_download_status_command(req: dict[str, Any]) -> dict[str, Any]:
    download_id = str(req.get("download_id") or "").strip()
    if download_id:
        record = _manager().get(download_id)
        if record is None:
            return {
                "type": "download_status", "ok": False,
                "download_id": download_id, "error": "unknown download_id",
            }
        return {"type": "download_status", "ok": True, "items": [record.payload()]}
    return _manager().snapshot()


def handle_cancel_download_command(req: dict[str, Any]) -> dict[str, Any]:
    download_id = str(req.get("download_id") or "").strip()
    if not download_id:
        return {
            "type": "download_ack", "ok": False, "action": "cancel_download",
            "error": "cancel_download requires download_id",
        }
    accepted = _manager().cancel(download_id)
    record = _manager().get(download_id)
    return {
        "type": "download_ack", "ok": bool(accepted), "action": "cancel_download",
        "download_id": download_id, "cancel_requested": bool(accepted),
        "item": record.payload() if record else None,
        **({} if accepted else {"error": "download is unknown or already finished"}),
    }
