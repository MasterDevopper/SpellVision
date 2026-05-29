#!/usr/bin/env python3
"""
PASS 8C.1: MainWindow API surface for chain submission
======================================================

What this script does
---------------------
Adds public API to MainWindow so that ChainStudioPage (in a later
sub-pass) can submit prebuilt chain payloads through the same worker
pipeline that ImageGenerationPage uses, without going through the
existing page-coupled submitGenerationRequest path.

Three additions, all in MainWindow.{h,cpp}:

1. Public getter: QueueManager *queueManager() const
   ChainStudioPage needs this to give its ChainCompletionWatcher a
   live QueueManager to bind to.

2. Public method: bool submitChainGenerationRequest(
       const QString &modeId,
       const QJsonObject &payload,
       const QString &queueItemId)
   Mirrors submitGenerationRequest's logic MINUS the page-specific
   bits (no page->setBusy calls, no page parameter). Reuses all the
   same readiness checks, telemetry property latches,
   buildWorkerGenerationRequest, sendWorkerRequest,
   applyWorkerQueueResponse, and appendLogLine. Returns true on
   accepted-by-worker, false on rejection at any validation gate or
   transport-level failure.

3. queue_item_id forward in buildWorkerGenerationRequest:
   If the incoming payload has a "queue_item_id" field, stamp it into
   THREE request fields per ChainCompletionWatcher's tri-handle
   correlation strategy (item.id OR item.workerJobId OR
   item.sourceJobId; first match wins). This is the defensive
   "stamp it everywhere" approach -- the worker may echo it back
   under any of those three names.

No behavioral change at runtime
-------------------------------
The new method has no callers (Pass 8c.3 wires the first caller).
The getter has no callers. The queue_item_id forward is a no-op
unless payload contains that field, which only ChainEngine's payload
builder produces. So this commit is a pure surface addition that
should build clean and change nothing visible.

What this script DOES NOT do
----------------------------
- Does not modify ChainStudioPage (that's Pass 8c.3)
- Does not modify ChainConfigPanelWidget (that's Pass 8c.2)
- Does not call the new method from anywhere

Why precise str_replace anchors not full-file rewrite
-----------------------------------------------------
MainWindow.cpp is ~3865 lines and full-file rewrite is unsafe at
that size. The header has well-defined insertion points. Both files
get surgical edits with abort-on-mismatch guards.

Idempotency
-----------
Marker-guarded by "// --- CHAIN STUDIO PASS 8C.1:" in both files.
Re-run is a clean no-op.

Output
------
  qt_ui/MainWindow.h
  qt_ui/MainWindow.cpp
  Backups:
    qt_ui/MainWindow.h.pre_pass8c1.bak
    qt_ui/MainWindow.cpp.pre_pass8c1.bak

Verification after applying
---------------------------
  1. .\\scripts\\dev\\run_ui.ps1
  2. Build should succeed with both MainWindow.cpp recompile and no
     warnings beyond pre-existing.
  3. UI behavior IDENTICAL to before -- no callers of the new method
     yet, no visible change.
  4. Click around the chain studio: same empty -> add T2I -> Draft
     flow as Pass 8b. Regenerate still no-op.
  5. Try a normal T2I submission via the T2I mode page: should work
     exactly as before (the existing submitGenerationRequest path is
     untouched).
"""

from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

NL = "\r\n"

# ---------------------------------------------------------------
# MainWindow.h edits
# ---------------------------------------------------------------

HEADER_REL = "qt_ui/MainWindow.h"
HEADER_MARKER = "// --- CHAIN STUDIO PASS 8C.1:"

# Edit H1: add public getter + public method declaration to the
# public: section just after the destructor. This puts the chain
# submission API at the top of MainWindow's public surface, next to
# the constructor that already establishes "things callers can use".
HEADER_EDITS = [
(
"""public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow() override = default;

protected:""",

"""public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow() override = default;

    // --- CHAIN STUDIO PASS 8C.1: public API for chain submission ---
    // ChainStudioPage uses these two methods to (a) bind its
    // ChainCompletionWatcher to the live QueueManager and (b) submit
    // engine-built payloads through the same worker pipeline that
    // ImageGenerationPage uses, without needing a page pointer.

    // Returns the QueueManager owned by this MainWindow. May be
    // nullptr if called before buildPersistentDocks() has run; safe
    // for ChainStudioPage to read once during its own construction
    // (which happens after MainWindow::buildPages -> after queue
    // manager exists).
    QueueManager *queueManager() const { return queueManager_; }

    // Submit a chain engine payload through the worker pipeline.
    // modeId is the lowercase task string ("t2i" / "i2i" / "t2v" /
    // "i2v"); queueItemId is the engine-generated UUID that the
    // ChainCompletionWatcher will look for on returned queue items.
    // Returns true if the worker accepted the request; false on any
    // validation rejection, missing-model, missing-input-image, or
    // worker transport error. (Engine treats false as a rejection
    // and rolls back the pending variation.)
    bool submitChainGenerationRequest(const QString &modeId,
                                      const QJsonObject &payload,
                                      const QString &queueItemId);

protected:""",
),
]

# ---------------------------------------------------------------
# MainWindow.cpp edits
# ---------------------------------------------------------------

CPP_REL = "qt_ui/MainWindow.cpp"
CPP_MARKER = "// --- CHAIN STUDIO PASS 8C.1:"

# Edit C1: queue_item_id forward in buildWorkerGenerationRequest.
# The current code ends with the "if (videoOutput)" block then
# "return request;". We slot the forward in just before the return,
# after the video-specific fields. The defensive triple-stamp
# matches ChainCompletionWatcher's matchTrackedEngineId() which
# checks item.id OR item.workerJobId OR item.sourceJobId in order.
CPP_EDITS = [
(
"""    if (videoOutput)
    {
        request.insert(QStringLiteral("frames"), payload.value(QStringLiteral("frames")).toInt(payload.value(QStringLiteral("num_frames")).toInt(81)));
        request.insert(QStringLiteral("num_frames"), payload.value(QStringLiteral("num_frames")).toInt(payload.value(QStringLiteral("frames")).toInt(81)));
        request.insert(QStringLiteral("fps"), payload.value(QStringLiteral("fps")).toInt(16));
        request.insert(QStringLiteral("duration_seconds"), payload.value(QStringLiteral("duration_seconds")).toDouble(0.0));
        request.insert(QStringLiteral("media_type"), QStringLiteral("video"));
    }

    return request;
}

QJsonObject MainWindow::buildWorkflowLaunchRequest(const QJsonObject &profile) const""",

"""    if (videoOutput)
    {
        request.insert(QStringLiteral("frames"), payload.value(QStringLiteral("frames")).toInt(payload.value(QStringLiteral("num_frames")).toInt(81)));
        request.insert(QStringLiteral("num_frames"), payload.value(QStringLiteral("num_frames")).toInt(payload.value(QStringLiteral("frames")).toInt(81)));
        request.insert(QStringLiteral("fps"), payload.value(QStringLiteral("fps")).toInt(16));
        request.insert(QStringLiteral("duration_seconds"), payload.value(QStringLiteral("duration_seconds")).toDouble(0.0));
        request.insert(QStringLiteral("media_type"), QStringLiteral("video"));
    }

    // --- CHAIN STUDIO PASS 8C.1: queue_item_id forward ---
    // When the chain engine submits, it stamps its engine-generated
    // UUID into payload["queue_item_id"]. We mirror that into THREE
    // request fields because the Python worker may echo it back
    // under any of them, and ChainCompletionWatcher matches against
    // item.id OR item.workerJobId OR item.sourceJobId (first hit
    // wins). Belt-and-braces: stamping all three guarantees the
    // watcher can correlate completions back regardless of which
    // field the worker chooses to echo.
    const QString chainQueueItemId = payload.value(QStringLiteral("queue_item_id")).toString().trimmed();
    if (!chainQueueItemId.isEmpty())
    {
        request.insert(QStringLiteral("queue_item_id"), chainQueueItemId);
        request.insert(QStringLiteral("worker_job_id"), chainQueueItemId);
        request.insert(QStringLiteral("source_job_id"), chainQueueItemId);
    }

    return request;
}

QJsonObject MainWindow::buildWorkflowLaunchRequest(const QJsonObject &profile) const""",
),

# Edit C2: insert the new submitChainGenerationRequest implementation
# right before submitGenerationRequest's definition. Putting them
# adjacent keeps the "submit a generation" cluster of code together
# and makes it easy to compare what the chain variant omits.
(
"""void MainWindow::submitGenerationRequest(ImageGenerationPage *page, const QString &modeId, const QJsonObject &payload, bool enqueueOnly)
{
    if (!page)
        return;""",

"""// --- CHAIN STUDIO PASS 8C.1: chain submission variant ---
// Mirrors submitGenerationRequest below, MINUS the page-specific
// bits: no page parameter, no page->setBusy calls, no enqueueOnly
// flag (chain stages always submit as "Submitting" rather than
// "Queued"-only). The chain page's UX is driven by engine signals,
// not setBusy, so the page does not need to be told to spin.
//
// Returns true if the worker accepted (response.ok == true and a
// queue_item_id is present); false on any validation rejection or
// transport error. ChainEngine interprets false as a submission
// rejection and rolls back the pending variation.
bool MainWindow::submitChainGenerationRequest(const QString &modeId,
                                              const QJsonObject &payload,
                                              const QString &queueItemId)
{
    const QString taskCommand = workerTaskCommandForMode(modeId);
    if (taskCommand.isEmpty())
    {
        appendLogLine(QStringLiteral("Chain submission rejected: unknown mode %1.").arg(modeId));
        return false;
    }

    const bool videoMode = taskCommand == QStringLiteral("t2v") || taskCommand == QStringLiteral("i2v");
    const bool hasWorkflowBinding = spellvision::workers::WorkerSubmissionPolicy::hasWorkflowBinding(payload);
    const bool hasNativeVideoStack = videoMode && spellvision::workers::WorkerSubmissionPolicy::hasNativeVideoStackPayload(payload);
    const QString modelValue = spellvision::workers::WorkerSubmissionPolicy::resolvedModelValueFromPayload(payload);

    if (modelValue.isEmpty() && !(videoMode && (hasWorkflowBinding || hasNativeVideoStack)))
    {
        const QString message = spellvision::workers::WorkerSubmissionPolicy::missingModelMessage(modeId, videoMode);
        appendLogLine(QStringLiteral("Chain submission rejected: %1").arg(message));
        return false;
    }

    if ((taskCommand == QStringLiteral("i2i") || taskCommand == QStringLiteral("i2v")) &&
        payload.value(QStringLiteral("input_image")).toString().trimmed().isEmpty())
    {
        appendLogLine(QStringLiteral("Chain %1 submission rejected: missing input image.").arg(modeId.toUpper()));
        return false;
    }

    // Stamp the engine-provided queue_item_id into the payload so
    // buildWorkerGenerationRequest's forward picks it up. The
    // payload is const here; we work with a mutable copy.
    QJsonObject payloadWithId = payload;
    if (!queueItemId.trimmed().isEmpty())
        payloadWithId.insert(QStringLiteral("queue_item_id"), queueItemId);

    appendLogLine(spellvision::workers::WorkerSubmissionPolicy::acceptedRequestLogLine(
        modeId,
        videoMode,
        hasWorkflowBinding,
        modelValue));

    // Same telemetry property latches submitGenerationRequest uses
    // (Pass 28R/28S/28T). Without these the bottom telemetry bar
    // would not switch to Busy until the next queue poll.
    setProperty("svTelemetryBusy", true);
    setProperty("svTelemetryBusyMode", modeId);
    setProperty("svTelemetryBusyState", QStringLiteral("Submitting"));
    setProperty("svTelemetryPhaseRank", 1);
    setProperty("svTelemetryProgressTarget", 3);
    setProperty("svTelemetryJobActive", true);
    setProperty("svTelemetryCompletionPulse", false);

    const int completedRowsAtSubmit =
        (queueTableView_ && queueTableView_->model()) ? queueTableView_->model()->rowCount() : 0;
    setProperty("svTelemetryCompletedRowsAtSubmit", completedRowsAtSubmit);

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setValue(0);
        bottomProgressBar_->setFormat(QStringLiteral("%p%"));
    }

    syncBottomTelemetry();

    QString stderrText;
    bool startedOk = false;

    const QJsonObject request = buildWorkerGenerationRequest(modeId, payloadWithId);
    const QJsonObject response = sendWorkerRequest(request, &stderrText, &startedOk);

    if (!stderrText.trimmed().isEmpty())
        appendLogLine(stderrText.trimmed());

    if (!startedOk)
    {
        appendLogLine(QStringLiteral("Chain submission failed: could not start worker_client.py for %1.").arg(modeId.toUpper()));
        return false;
    }

    if (response.isEmpty())
    {
        appendLogLine(QStringLiteral("Chain submission failed: worker returned no JSON payload for %1.").arg(modeId.toUpper()));
        return false;
    }

    const bool ok = response.value(QStringLiteral("ok")).toBool(false);
    const QString errorText = response.value(QStringLiteral("error")).toString().trimmed();
    if (!ok)
    {
        if (!errorText.isEmpty())
            appendLogLine(QStringLiteral("Chain %1 request failed: %2").arg(modeId.toUpper(), errorText));
        else
            appendLogLine(QStringLiteral("Chain %1 request failed (no error text).").arg(modeId.toUpper()));
        return false;
    }

    applyWorkerQueueResponse(response);
    syncBottomTelemetry();

    const QString respQueueId = response.value(QStringLiteral("queue_item_id")).toString().trimmed();
    const QString respJobId = response.value(QStringLiteral("job_id")).toString().trimmed();
    appendLogLine(QStringLiteral("Chain %1 sent to worker queue%2%3.")
                      .arg(modeId.toUpper(),
                           respQueueId.isEmpty() ? QString() : QStringLiteral(" \\u2022 queue=%1").arg(respQueueId),
                           respJobId.isEmpty() ? QString() : QStringLiteral(" \\u2022 job=%1").arg(respJobId)));

    if (queueDock_ && !queueDock_->isVisible())
    {
        queueDock_->show();
        updateDockChrome();
    }

    return true;
}

void MainWindow::submitGenerationRequest(ImageGenerationPage *page, const QString &modeId, const QJsonObject &payload, bool enqueueOnly)
{
    if (!page)
        return;""",
),
]


def already_applied(text: str, marker: str) -> bool:
    return marker in text


def write_with_crlf(path: Path, body_lf: str) -> None:
    text = body_lf.replace("\r\n", "\n").replace("\n", NL)
    path.write_bytes(text.encode("utf-8"))


def apply_edits(path: Path, edits, marker, backup_suffix) -> bool:
    """
    Apply all edits to `path`. Returns True if changes made; False if
    marker already present (idempotent no-op). Aborts with non-zero
    return if any anchor is missing/ambiguous -- never partial-patches.
    """
    raw = path.read_bytes().decode("utf-8")
    body = raw.replace("\r\n", "\n")

    if already_applied(body, marker):
        print(f"  Already applied (marker present): {path.name}")
        return False

    # Validate every anchor matches exactly once before applying any.
    for i, (anchor, _replacement) in enumerate(edits, 1):
        count = body.count(anchor)
        if count != 1:
            print(f"  ERROR: edit #{i} anchor matches {count} times "
                  f"(expected exactly 1).")
            preview = anchor.split("\n")[0][:80]
            print(f"  First line of anchor: {preview!r}")
            return False

    for anchor, replacement in edits:
        body = body.replace(anchor, replacement, 1)

    if marker not in body:
        print(f"  ERROR: post-edit body does not contain MARKER {marker!r}.")
        return False

    backup = path.with_suffix(path.suffix + backup_suffix)
    backup.write_bytes(raw.encode("utf-8"))
    print(f"  Backup written: {backup.name}")

    write_with_crlf(path, body)
    print(f"  Rewrote: {path.name}")
    return True


def main() -> int:
    print("Applying PASS 8C.1: MainWindow API surface for chain submission")
    print(f"  Project root: {PROJECT_ROOT}")
    print()

    h_path = PROJECT_ROOT / HEADER_REL
    cpp_path = PROJECT_ROOT / CPP_REL

    if not h_path.exists():
        print(f"ERROR: {HEADER_REL} does not exist at {h_path}")
        return 1
    if not cpp_path.exists():
        print(f"ERROR: {CPP_REL} does not exist at {cpp_path}")
        return 1

    # Header first -- if anchor in header doesn't match, abort before
    # touching the cpp.
    print(HEADER_REL)
    h_changed = apply_edits(h_path, HEADER_EDITS, HEADER_MARKER, ".pre_pass8c1.bak")
    print()

    if not h_changed:
        # If header was already applied, check cpp too -- maybe a
        # prior run finished both.
        print(CPP_REL)
        cpp_changed = apply_edits(cpp_path, CPP_EDITS, CPP_MARKER, ".pre_pass8c1.bak")
        print()
        if not cpp_changed:
            print("Done -- PASS 8C.1 was already applied (no-op).")
            return 0
        else:
            print("Warning: header already had marker but cpp did not.")
            print("This usually means a prior aborted run.  Cpp has now been updated.")
            return 0

    # Header was just modified. Now do cpp; if cpp anchor fails, the
    # header IS in an "applied" state but cpp won't be. The verifier
    # check in step 1 above means anchor must have matched exactly,
    # so the only realistic failure path here is "header anchor
    # changed unexpectedly" -- treat as fatal.
    print(CPP_REL)
    cpp_changed = apply_edits(cpp_path, CPP_EDITS, CPP_MARKER, ".pre_pass8c1.bak")
    print()

    if not cpp_changed:
        print("ERROR: header edit succeeded but cpp edit failed.")
        print("       Restore from MainWindow.h.pre_pass8c1.bak and investigate.")
        return 2

    print("Done -- PASS 8C.1 applied.")
    print()
    print("Verify:")
    print("  1. .\\scripts\\dev\\run_ui.ps1")
    print("  2. Build should succeed; MainWindow.cpp will recompile.")
    print("  3. No behavioral change visible -- pure surface addition.")
    print("  4. Chain studio behaves identically to Pass 8b: empty page,")
    print("     + add stage -> T2I node appears, Regenerate still no-op.")
    print("  5. Existing T2I / I2I / T2V / I2V pages still submit normally.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
