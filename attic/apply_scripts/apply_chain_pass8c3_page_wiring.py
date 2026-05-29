#!/usr/bin/env python3
"""
PASS 8C.3: ChainStudioPage real submission wiring
==================================================

What this script does
---------------------
Connects all the pieces built up in passes 8a, 8b, 8c.1, and 8c.2 so
that clicking Regenerate on a chain stage actually generates an
image through the worker pipeline. After this commit, the chain
studio is functionally complete (sans Pass 10 polish items).

Three integration changes, all in ChainStudioPage:

1. Owns a ChainCompletionWatcher.
   The watcher bridges the worker pipeline's poll-based snapshots
   to the engine's event-based variation completion. It binds to
   MainWindow's QueueManager once during page construction.

2. Real SubmitFn replaces the rejecting stub.
   The new submitFn captures a MainWindow* and, on each call,
   reads modeId from payload["mode"] (the lowercase task command
   set by ChainEngine::draftFromConfig), then calls
   mw->submitChainGenerationRequest(modeId, payload, engineId).
   Returns true on accepted, false on rejection -- the engine
   uses this to commit-or-rollback the pending variation.

3. onConfigRegenerateRequested body implemented.
   Harvests user edits from the config panel via
   configPanelWidget_->harvestCurrentConfig(), pushes them to the
   engine via setStageConfig, then calls regenerate. The engine
   builds the payload, calls the real submitFn, the watcher tracks
   the engineId, and on completion the watcher fires
   variationCompleted, which the engine handles by appending the
   real Variation and emitting chainMutated -> the canvas displays
   the new image.

Why this is safe to land in one pass
------------------------------------
By the time 8c.3 runs, every dependency exists:
- MainWindow::queueManager() (Pass 8c.1)
- MainWindow::submitChainGenerationRequest (Pass 8c.1)
- buildWorkerGenerationRequest queue_item_id forward (Pass 8c.1)
- ChainConfigPanelWidget::harvestCurrentConfig (Pass 8c.2)
- ChainEngine::regenerate path with completion watcher slots
  (Track A, committed at 968ade9)
- ChainCompletionWatcher implementation (Track A)

The only new code in 8c.3 is the wiring -- everything it calls is
already proven to build and exist.

Parent resolution detail
------------------------
ChainStudioPage's constructor takes a QWidget *parent. At
MainWindow::buildPages time, it's called as
new ChainStudioPage(this) where this is the MainWindow. We use
qobject_cast<MainWindow *>(parent) to resolve the typed pointer.
window() would not work here -- the page hasn't been added to a
top-level window yet during construction. If qobject_cast fails
(unexpected -- would mean the page was reparented or constructed
standalone for testing), the page falls back to a rejecting submitFn
identical to the Pass 8a behavior. This is defensive; the production
path always has a MainWindow parent.

Files
-----
  qt_ui/chain/ChainStudioPage.h
  qt_ui/chain/ChainStudioPage.cpp

  Backups:
    qt_ui/chain/ChainStudioPage.h.pre_pass8c3.bak
    qt_ui/chain/ChainStudioPage.cpp.pre_pass8c3.bak

Idempotency
-----------
Marker-guarded by "// --- CHAIN STUDIO PASS 8C.3:" in both files.
Re-run is a clean no-op.

Verification after applying
---------------------------
  1. .\\scripts\\dev\\run_ui.ps1
  2. Build should succeed -- ChainStudioPage.cpp recompiles, MOC
     likely re-emits (new include / member layout change).
  3. Open Chain mode. Click + add stage -> T2I -> stage appears.
  4. Click REGENERATE in the config panel bottom-right.
  5. EXPECTED OUTCOME:
       - Stage status flips Idle -> Queued -> Generating (rail status
         dot color changes; watcher correlates by engine UUID).
       - Bottom telemetry switches to Submitting / Running.
       - VRAM climbs; image generates (this can take 30s to 2min
         depending on the model).
       - When done, watcher fires variationCompleted -> engine
         appends the Variation -> canvas displays the result.
       - Stage status -> Completed.
       - Config panel + canvas pager update.

  6. Sanity: existing T2I / I2I / T2V / I2V pages should STILL
     submit normally -- the submitChainGenerationRequest path is
     entirely separate from submitGenerationRequest.
"""

from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

NL = "\r\n"

# ---------------------------------------------------------------
# ChainStudioPage.h edits
# ---------------------------------------------------------------

HEADER_REL = "qt_ui/chain/ChainStudioPage.h"
HEADER_MARKER = "// --- CHAIN STUDIO PASS 8C.3:"

# Edit H1: add the MainWindow forward declaration to the GLOBAL
# namespace (since MainWindow is in the global namespace per
# MainWindow.h). Add the watcher forward declaration in the
# spellvision::chain namespace alongside the engine forward decl.
HEADER_EDITS = [
(
"""#include <QWidget>

class QLabel;

namespace spellvision::chain
{

// --- CHAIN STUDIO PASS 7C CANVAS: forward-declare ChainCanvasWidget ---
class ChainCanvasWidget;
// --- CHAIN STUDIO PASS 7D1 CONFIG PANEL: forward-declare ChainConfigPanelWidget ---
class ChainConfigPanelWidget;
// --- CHAIN STUDIO PASS 7D2 DIALOG BAR: forward-declare ChainDialogBarWidget ---
class ChainDialogBarWidget;
// --- CHAIN STUDIO PASS 8A: forward-declare ChainEngine ---
class ChainEngine;""",

"""#include <QWidget>

class QLabel;
// --- CHAIN STUDIO PASS 8C.3: forward-declare MainWindow ---
// MainWindow lives in the global namespace; the page uses it for
// queueManager() and submitChainGenerationRequest().
class MainWindow;

namespace spellvision::chain
{

// --- CHAIN STUDIO PASS 7C CANVAS: forward-declare ChainCanvasWidget ---
class ChainCanvasWidget;
// --- CHAIN STUDIO PASS 7D1 CONFIG PANEL: forward-declare ChainConfigPanelWidget ---
class ChainConfigPanelWidget;
// --- CHAIN STUDIO PASS 7D2 DIALOG BAR: forward-declare ChainDialogBarWidget ---
class ChainDialogBarWidget;
// --- CHAIN STUDIO PASS 8A: forward-declare ChainEngine ---
class ChainEngine;
// --- CHAIN STUDIO PASS 8C.3: forward-declare ChainCompletionWatcher ---
// The watcher bridges the poll-based QueueManager to engine event
// signals. The page owns one and binds it to MainWindow's queue.
class ChainCompletionWatcher;""",
),

# Edit H2: add the watcher_ member alongside engine_, with a brief
# comment explaining lifetime + binding semantics.
(
"""    ChainEngine *engine_ = nullptr;

    // UI-only selection state. The engine has a chain_.selectedStageId
    // field too, but page selection is driven independently by user
    // clicks on the rail; we don't push it into the engine.
    QString selectedStageId_;""",

"""    ChainEngine *engine_ = nullptr;

    // --- CHAIN STUDIO PASS 8C.3: completion watcher ---
    // Parented to `this` so Qt object ownership handles lifecycle.
    // Bound once during the page constructor to MainWindow's
    // QueueManager. The engine receives this pointer via bind()
    // and connects to its variationCompleted/Failed/Running signals
    // internally.
    ChainCompletionWatcher *watcher_ = nullptr;

    // UI-only selection state. The engine has a chain_.selectedStageId
    // field too, but page selection is driven independently by user
    // clicks on the rail; we don't push it into the engine.
    QString selectedStageId_;""",
),
]

# ---------------------------------------------------------------
# ChainStudioPage.cpp edits
# ---------------------------------------------------------------

CPP_REL = "qt_ui/chain/ChainStudioPage.cpp"
CPP_MARKER = "// --- CHAIN STUDIO PASS 8C.3:"

# Edit C1: add the new includes after the existing chain includes
# and before the Qt includes. Keeps include order: local headers,
# then framework headers.
CPP_EDITS = [
(
"""#include "ThemeManager.h"
#include "chain/ChainCanvasWidget.h"
#include "chain/ChainConfigPanelWidget.h"
#include "chain/ChainDialogBarWidget.h"
// --- CHAIN STUDIO PASS 8A: engine ownership ---
#include "chain/ChainEngine.h"
#include "chain/ChainRailWidget.h"

#include <QAction>""",

"""#include "ThemeManager.h"
#include "chain/ChainCanvasWidget.h"
// --- CHAIN STUDIO PASS 8C.3: completion watcher + main window ---
#include "chain/ChainCompletionWatcher.h"
#include "chain/ChainConfigPanelWidget.h"
#include "chain/ChainDialogBarWidget.h"
// --- CHAIN STUDIO PASS 8A: engine ownership ---
#include "chain/ChainEngine.h"
#include "chain/ChainRailWidget.h"
#include "MainWindow.h"

#include <QAction>""",
),

# Edit C2: replace the engine bind block in the constructor.
# Construct the watcher first, look up MainWindow via parent,
# bind the watcher to MainWindow's queue if available, and bind
# the engine with the real (or fallback rejecting) submitFn.
(
"""    // --- CHAIN STUDIO PASS 8A: engine ownership ---
    // Construct the engine BEFORE the build* helpers run so they can
    // read engine_->chain() instead of the old stubChain_.
    //
    // bind() is called with null store + null watcher + a rejecting
    // submitFn. This is "display-only" wiring: the engine holds the
    // chain in memory, but cannot persist or actually submit. Pass 8b
    // wires real mutations through engine_-> methods; Pass 8c wires
    // the real submitFn, store, and watcher to connect into
    // QueueManager / worker_service.
    //
    // newChain(DescribedText) seeds an empty chain. The first stage
    // (T2I or T2V) will be added by the user via the "+ add stage"
    // kind-picker in Pass 8b. This pass shows an empty page.
    engine_ = new ChainEngine(this);
    auto rejectingSubmitFn = [](const QJsonObject &, const QString &) {
        return false;
    };
    engine_->bind(nullptr, nullptr, rejectingSubmitFn);
    engine_->newChain(EntryKind::DescribedText);""",

"""    // --- CHAIN STUDIO PASS 8C.3: engine + watcher + real submitFn ---
    // Pass 8a constructed the engine with a rejecting submitFn and
    // null watcher (display-only). Pass 8c.3 replaces both:
    //
    //   - watcher_ binds to MainWindow's QueueManager and observes
    //     queue snapshots, firing variation*-signals that the engine
    //     subscribes to via bind().
    //   - submitFn captures a MainWindow* and forwards each
    //     (payload, engineId) pair into
    //     MainWindow::submitChainGenerationRequest, which mirrors the
    //     existing submitGenerationRequest pipeline.
    //
    // Parent resolution: at construct time, qobject_cast<MainWindow*>
    // on the parent QWidget gives us the typed handle. window() would
    // not work because the page hasn't been added to a top-level
    // window yet. If the cast fails (unexpected -- would imply the
    // page was reparented or constructed standalone for testing), we
    // fall back to the Pass 8a rejecting submitFn so the page stays
    // functional for display.
    engine_ = new ChainEngine(this);
    watcher_ = new ChainCompletionWatcher(this);

    MainWindow *mw = qobject_cast<MainWindow *>(parent);
    if (mw != nullptr && mw->queueManager() != nullptr)
    {
        watcher_->bind(mw->queueManager(), nullptr);

        auto realSubmitFn = [mw](const QJsonObject &payload,
                                 const QString &engineId) -> bool
        {
            // ChainEngine::draftFromConfig stamps draft.mode =
            // toString(StageKind) which the GenerationRequestBuilder
            // emits as payload["mode"]. That is exactly the lowercase
            // task command MainWindow expects as modeId.
            const QString modeId = payload.value(QStringLiteral("mode")).toString();
            return mw->submitChainGenerationRequest(modeId, payload, engineId);
        };
        engine_->bind(nullptr, watcher_, realSubmitFn);
    }
    else
    {
        // Defensive fallback: no MainWindow available means no queue
        // and no submission path. Keep the engine bound to the same
        // rejecting stub as Pass 8a so the page renders but
        // submissions are inert.
        auto rejectingSubmitFn = [](const QJsonObject &, const QString &) {
            return false;
        };
        engine_->bind(nullptr, nullptr, rejectingSubmitFn);
    }

    engine_->newChain(EntryKind::DescribedText);""",
),

# Edit C3: replace onConfigRegenerateRequested body. Harvest panel
# config, push to engine, call regenerate. Engine internally fires
# stageStatusChanged(Queued) -> chainMutated -> refreshAllWidgets,
# then calls our real submitFn (which calls MainWindow).
(
"""void ChainStudioPage::onConfigRegenerateRequested(const QString &stageId)
{
    // Pass 8c: intentionally deferred. The currently-bound submitFn
    // returns false unconditionally, so calling engine_->regenerate
    // now would emit submissionRejected and mark the stage Failed
    // -- a worse experience than no-op. Pass 8c replaces this body
    // with the real call once the submitFn is wired into
    // MainWindow's worker submission pipeline.
    Q_UNUSED(stageId);
}""",

"""void ChainStudioPage::onConfigRegenerateRequested(const QString &stageId)
{
    // --- CHAIN STUDIO PASS 8C.3: harvest-then-regenerate ---
    // The config panel widget edits are NOT live-bound to the engine
    // (Option A from design): the user's spinbox/combobox changes
    // live in the widget until Regenerate fires. Here we harvest the
    // user's current widget state, push it into the engine's stage
    // config, and ONLY THEN call regenerate so the engine builds the
    // payload from the harvested values.
    if (configPanelWidget_ != nullptr)
    {
        const StageConfig harvested = configPanelWidget_->harvestCurrentConfig();
        engine_->setStageConfig(stageId, harvested);
    }

    // regenerate() emits stageStatusChanged(Queued) -> chainMutated
    // -> refreshAllWidgets, then synchronously calls the bound
    // submitFn. If submitFn returns false (rejected at any gate),
    // the engine fires submissionRejected and the stage transitions
    // to Failed. If true, the engine tracks engineId via the
    // watcher; later the watcher fires variationCompleted which the
    // engine handles by appending the real Variation and emitting
    // chainMutated again.
    engine_->regenerate(stageId);
}""",
),

]


def already_applied(text: str, marker: str) -> bool:
    return marker in text


def write_with_crlf(path: Path, body_lf: str) -> None:
    text = body_lf.replace("\r\n", "\n").replace("\n", NL)
    path.write_bytes(text.encode("utf-8"))


def apply_edits(path: Path, edits, marker, backup_suffix) -> bool:
    raw = path.read_bytes().decode("utf-8")
    body = raw.replace("\r\n", "\n")

    if already_applied(body, marker):
        print(f"  Already applied (marker present): {path.name}")
        return False

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
    print("Applying PASS 8C.3: ChainStudioPage real submission wiring")
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

    print(HEADER_REL)
    h_changed = apply_edits(h_path, HEADER_EDITS, HEADER_MARKER, ".pre_pass8c3.bak")
    print()

    if not h_changed:
        print(CPP_REL)
        cpp_changed = apply_edits(cpp_path, CPP_EDITS, CPP_MARKER, ".pre_pass8c3.bak")
        print()
        if not cpp_changed:
            print("Done -- PASS 8C.3 was already applied (no-op).")
            return 0
        else:
            print("Warning: header already had marker but cpp did not.")
            print("Cpp has now been updated; investigate if unexpected.")
            return 0

    print(CPP_REL)
    cpp_changed = apply_edits(cpp_path, CPP_EDITS, CPP_MARKER, ".pre_pass8c3.bak")
    print()

    if not cpp_changed:
        print("ERROR: header edit succeeded but cpp edit failed.")
        print("       Restore ChainStudioPage.h.pre_pass8c3.bak and investigate.")
        return 2

    print("Done -- PASS 8C.3 applied.")
    print()
    print("Verify:")
    print("  1. .\\scripts\\dev\\run_ui.ps1")
    print("  2. Build should succeed -- ChainStudioPage.cpp recompiles.")
    print("  3. Open Chain mode. + add stage -> T2I -> stage appears.")
    print("  4. Click REGENERATE -- THIS TIME IT SHOULD ACTUALLY GENERATE:")
    print("     a. Stage status flips through Queued -> Generating.")
    print("     b. Bottom telemetry switches to Submitting / Running.")
    print("     c. VRAM climbs, image generates (30s-2min).")
    print("     d. When done, canvas displays the result. Status: Completed.")
    print("  5. Existing T2I / I2I / T2V / I2V flows still submit normally.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
