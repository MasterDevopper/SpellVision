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
