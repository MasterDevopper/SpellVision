"""Cancelling a job must stop ComfyUI, not merely stop SpellVision watching it.

Before this module there was **no ``/interrupt`` call and no queue delete anywhere in the repo**.
Cancel set ``ActiveJobHandle.cancel_event``; ``raise_if_cancelled`` then raised out of the
``/history`` poll, the job went to CANCELLED, and the UI reported a clean cancel. ComfyUI never
heard about it. It rendered the prompt to completion holding 20+ GB of VRAM, and on the video
routes that is minutes of a card the user believes they just got back -- long enough for the next
submission to OOM against a job that was "cancelled".

That is the same shape as the rest of this pass: the failure REPORTS SUCCESS. The cancel button
worked on everything it owned and stopped at the process boundary.

## What ComfyUI offers

``POST /interrupt``
    Interrupts whatever is executing **right now**. It takes no prompt id, so it is a blunt
    instrument: firing it when our prompt is not the running one kills someone else's render.

``POST /queue`` with ``{"delete": [prompt_id, ...]}``
    Removes items that are still PENDING. Harmless for an id that is not queued.

``GET /queue``
    ``{"queue_running": [...], "queue_pending": [...]}``, each entry a list whose second element is
    the prompt id.

## The decision this module makes

Read the queue first, then act on where the prompt actually is:

============  =========================================================================
running       ``/interrupt`` -- it is ours, so interrupting is correct.
pending       ``/queue {"delete": [id]}`` -- never interrupt; that would kill a
              different, innocent prompt that happens to be executing.
absent        nothing. Already finished, or never queued. Reporting this honestly
              matters: a cancel that found nothing to cancel is not a failure, and
              saying so beats an unexplained no-op.
unknown       delete AND interrupt. Only when ``GET /queue`` itself failed, i.e. we
              cannot see what is running. Losing an unrelated render is the lesser
              harm against leaving 20+ GB pinned by a job the user cancelled, and a
              ComfyUI we cannot read is usually one SpellVision started and owns.
============  =========================================================================

The interrupt-only-when-ours rule is the load-bearing part. ComfyUI's own web UI can be open
against the same instance, and the plan's original "both when unknown" is safe exactly because
"unknown" here means the queue was unreadable, not "we did not bother to look".

Every function returns rather than raises. A cancel is already the unhappy path; a transport error
while cancelling must not replace the user's cancel with a stack trace.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 10.0


def _post_json(api_url: str, path: str, payload: dict[str, Any], *, timeout: float) -> tuple[bool, str]:
    """POST and report, never raise. Returns ``(ok, detail)``."""
    url = f"{api_url.rstrip('/')}{path}"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            resp.read()
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} {exc.reason}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # TimeoutError and the bare OSError family are NOT URLError subclasses. The /history poller
        # learned this the hard way -- a read timeout escaped a URLError-only handler and killed the
        # job. Same class of gap, caught here before it can exist.
        return False, f"{exc.__class__.__name__}: {exc}"


def _prompt_ids(entries: Any) -> set[str]:
    """Prompt ids out of one ``/queue`` list, tolerant of shape.

    A queue entry is ``[number, prompt_id, prompt, extra_data, outputs]``. Read positionally but
    accept a dict too: this is parsing another project's response, and a core bump that changed the
    shape must degrade to "I could not tell" rather than to a confident wrong answer.
    """
    found: set[str] = set()
    if not isinstance(entries, list):
        return found
    for entry in entries:
        if isinstance(entry, dict):
            value = entry.get("prompt_id") or entry.get("promptId")
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            value = entry[1]
        else:
            continue
        text = str(value or "").strip()
        if text:
            found.add(text)
    return found


def queue_snapshot(api_url: str, *, timeout: float = DEFAULT_TIMEOUT_SEC) -> tuple[set[str], set[str], str]:
    """``(running, pending, error)``. A non-empty error means the sets are meaningless."""
    url = f"{api_url.rstrip('/')}/queue"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return set(), set(), f"{exc.__class__.__name__}: {exc}"
    if not isinstance(payload, dict):
        return set(), set(), f"unexpected /queue body: {type(payload).__name__}"
    return _prompt_ids(payload.get("queue_running")), _prompt_ids(payload.get("queue_pending")), ""


def cancel_prompt(api_url: str, prompt_id: str, *, timeout: float = DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
    """Stop one prompt on the ComfyUI at ``api_url``.

    Reports what it found and what it did, so a cancel that could do nothing says why instead of
    looking identical to one that worked.
    """
    prompt_id = str(prompt_id or "").strip()
    if not prompt_id:
        return {"ok": False, "prompt_id": "", "state": "unknown", "actions": [], "errors": ["no prompt_id"]}

    running, pending, queue_error = queue_snapshot(api_url, timeout=timeout)
    if queue_error:
        state = "unknown"
    elif prompt_id in running:
        state = "running"
    elif prompt_id in pending:
        state = "pending"
    else:
        state = "absent"

    actions: list[str] = []
    errors: list[str] = []
    if queue_error:
        errors.append(f"/queue unreadable: {queue_error}")

    if state in {"pending", "unknown"}:
        ok, detail = _post_json(api_url, "/queue", {"delete": [prompt_id]}, timeout=timeout)
        actions.append("queue_delete")
        if not ok:
            errors.append(f"queue delete failed: {detail}")

    if state in {"running", "unknown"}:
        ok, detail = _post_json(api_url, "/interrupt", {}, timeout=timeout)
        actions.append("interrupt")
        if not ok:
            errors.append(f"interrupt failed: {detail}")

    outcome = {
        "ok": not errors,
        "prompt_id": prompt_id,
        "state": state,
        "actions": actions,
        "errors": errors,
    }
    # WARNING, not info: the root logger sits at WARNING, so info() is invisible in this repo
    # (CLAUDE.md 4). A cancel that did nothing is exactly the line worth having in the log.
    log.warning("comfy cancel prompt=%s state=%s actions=%s errors=%s", prompt_id, state, actions, errors)
    return outcome
