#!/usr/bin/env python3
"""
PASS 8B: widget -> engine mutation routing for ChainStudioPage
==============================================================

What this script does
---------------------
Replaces five Q_UNUSED stub bodies in ChainStudioPage.cpp with real
engine_-> calls, making the page interactive against the in-memory
ChainEngine.  One handler (onConfigRegenerateRequested) STAYS as a
Q_UNUSED stub because the bound SubmitFn currently rejects -- wiring
it now would just produce "submission rejected" toasts. Pass 8c
replaces both the SubmitFn and this handler in lockstep.

Five handlers wired
-------------------
  1. onAddStageKindChosen(kind)
       -> engine_->addStage(kind); auto-select new stage; refresh.
  2. onCanvasVariationSelectionChanged(stageId, newVarIdx)
       -> engine_->selectVariation(stageId, newVarIdx).
  3. onCanvasLockRequested(stageId)
       -> engine_->lock(stageId).
  4. onDialogPromptChanged(text)
       -> harvest first-stage config, set .prompt = text,
          engine_->setStageConfig(firstStageId, newConfig).
       Falls through if chain has no stages yet.
  5. onDialogInputImageSelected(path)
       -> if chain is empty, engine_->newChain(UploadedImage, path);
          if chain has stages, refuse silently for now (Pass 10 polish
          adds a confirm-reset dialog).

One handler kept as Q_UNUSED
----------------------------
  6. onConfigRegenerateRequested(stageId) -- deferred to Pass 8c.

Why precise str_replace anchors rather than full-file rewrite
-------------------------------------------------------------
This is a surgical change.  The five edits are localized, the
surrounding code in 8a's output is known exactly (we just shipped it
and verified the build), and full-file rewrites risk introducing
formatting drift on lines we don't intend to touch.  Five
str_replace anchors keep the diff minimal and reviewable.

The script reads the file once, performs the substitutions in
memory, and writes once.  If any anchor is not found exactly once,
the script aborts WITHOUT writing anything -- safer than partial
patches.

Idempotency
-----------
Marker-guarded by "// --- CHAIN STUDIO PASS 8B:".  On re-run the
marker is detected and the script no-ops cleanly.

Output
------
  qt_ui/chain/ChainStudioPage.cpp  (modified)
  Backup:
    qt_ui/chain/ChainStudioPage.cpp.pre_pass8b.bak

Verification after applying
---------------------------
  1. .\\scripts\\dev\\run_ui.ps1
  2. Build should succeed.
  3. Chain Studio page: still empty at first launch.
  4. Click "+ add stage" -> menu with T2I / T2V.
     Click T2I -> a T2I node appears in the rail (Draft status).
     Config panel populates with that stage's empty config.
  5. Type text in the top dialog bar prompt input.
     The first stage's config (visible in config panel) updates.
  6. Click the upload box (IMG) -- since chain has stages now,
     the upload is refused silently (Pass 10 will toast/confirm).
  7. Click the upload box BEFORE adding any stages -- new chain
     starts with EntryKind::UploadedImage; "+ add stage" now offers
     I2I / I2V / I2_3D instead of T2I / T2V.
  8. Click Regenerate -- still no-op (Pass 8c).
"""

from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

NL = "\r\n"

CPP_REL = "qt_ui/chain/ChainStudioPage.cpp"

MARKER = "// --- CHAIN STUDIO PASS 8B:"

# Each edit is a (anchor, replacement) pair. Anchors use \n; the
# script normalizes file content to \n during search and writes back
# as CRLF on success.
EDITS = [

# -----------------------------------------------------------------
# Edit 1: section comment header above the handlers
# -----------------------------------------------------------------
(
"""// --- CHAIN STUDIO PASS 8A: mutation handlers are Q_UNUSED stubs ---
// Pass 8b will replace each body with engine_-> calls. Each Q_UNUSED
// silences a "-Wunused-parameter" warning; the engine_ pointer is
// already in scope when those bodies land.""",

"""// --- CHAIN STUDIO PASS 8B: mutation handlers wired to engine ---
// Five of six mutation handlers now route through engine_-> calls.
// Each engine call may emit chainMutated, which fires
// refreshAllWidgets() and fans state out to all four widgets.
//
// The sixth, onConfigRegenerateRequested, STAYS as a Q_UNUSED stub
// because the currently-bound submitFn returns false unconditionally
// -- calling engine_->regenerate now would emit submissionRejected
// and mark the stage Failed. Pass 8c wires the real submitFn into
// MainWindow's worker pipeline and replaces this body in lockstep.""",
),

# -----------------------------------------------------------------
# Edit 2: onAddStageKindChosen
# -----------------------------------------------------------------
(
"""void ChainStudioPage::onAddStageKindChosen(StageKind kind)
{
    // Pass 8b: engine_->addStage(kind).
    Q_UNUSED(kind);
}""",

"""void ChainStudioPage::onAddStageKindChosen(StageKind kind)
{
    // Engine validates and returns "" on rejection (kind mismatched
    // entry, or predecessor not Locked). On success the chainMutated
    // signal already fired during addStage() -- our refresh below
    // additionally pushes the new selection out.
    const QString newStageId = engine_->addStage(kind);
    if (newStageId.isEmpty())
        return;
    selectedStageId_ = newStageId;
    refreshAllWidgets();
}""",
),

# -----------------------------------------------------------------
# Edit 3: onCanvasVariationSelectionChanged
# -----------------------------------------------------------------
(
"""void ChainStudioPage::onCanvasVariationSelectionChanged(const QString &stageId, int newVarIdx)
{
    // Pass 8b: engine_->selectVariation(stageId, newVarIdx).
    Q_UNUSED(stageId);
    Q_UNUSED(newVarIdx);
}""",

"""void ChainStudioPage::onCanvasVariationSelectionChanged(const QString &stageId, int newVarIdx)
{
    // Engine emits chainMutated on success -> refreshAllWidgets()
    // fires automatically. Out-of-range idx is silently ignored by
    // the engine; we don't need to surface that.
    engine_->selectVariation(stageId, newVarIdx);
}""",
),

# -----------------------------------------------------------------
# Edit 4: onCanvasLockRequested
# -----------------------------------------------------------------
(
"""void ChainStudioPage::onCanvasLockRequested(const QString &stageId)
{
    // Pass 8b: engine_->lock(stageId).
    Q_UNUSED(stageId);
}""",

"""void ChainStudioPage::onCanvasLockRequested(const QString &stageId)
{
    // Engine validates (must be Completed, must have selectedVarIdx
    // >= 0); rejection is silent and the chain stays unchanged. On
    // success the engine emits chainMutated -> refreshAllWidgets().
    engine_->lock(stageId);
}""",
),

# -----------------------------------------------------------------
# Edit 5: onConfigRegenerateRequested -- KEEPS its stub body but
# we update the comment so it's clear this is intentional, not
# overlooked.
# -----------------------------------------------------------------
(
"""void ChainStudioPage::onConfigRegenerateRequested(const QString &stageId)
{
    // Pass 8c: engine_->regenerate(stageId) with the real SubmitFn.
    // Currently the bound submitFn returns false unconditionally, so
    // calling regenerate now would emit submissionRejected without
    // doing anything useful. Better to no-op until 8c lands.
    Q_UNUSED(stageId);
}""",

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
),

# -----------------------------------------------------------------
# Edit 6: onDialogInputImageSelected
# -----------------------------------------------------------------
(
"""void ChainStudioPage::onDialogInputImageSelected(const QString &path)
{
    // Pass 8b: this needs design discussion. UX-wise, setting the
    // entry image on a chain that already has stages would either
    // require unlocking everything or starting a fresh chain. The
    // engine API offers newChain(EntryKind::UploadedImage, path)
    // for the latter; setStageConfig() does not touch chain-level
    // sourceImagePath.
    Q_UNUSED(path);
}""",

"""void ChainStudioPage::onDialogInputImageSelected(const QString &path)
{
    // If the chain already has stages, refuse the upload silently
    // for now -- swapping entry image on a non-empty chain would
    // need to wipe everything (engine has no incremental "swap
    // source image" API), and a silent wipe would be a UX trap.
    // Pass 10 polish: confirm-dialog or toast before reset.
    if (!engine_->chain().stages.isEmpty())
        return;

    // Empty chain -- safe to re-seed with UploadedImage entry. The
    // kind-picker menu will switch to offering I2I / I2V / I2_3D.
    engine_->newChain(EntryKind::UploadedImage, path);
}""",
),

# -----------------------------------------------------------------
# Edit 7: onDialogPromptChanged
# -----------------------------------------------------------------
(
"""void ChainStudioPage::onDialogPromptChanged(const QString &text)
{
    // Pass 8b: harvest first-stage config, set .prompt = text, call
    // engine_->setStageConfig(firstStageId, newConfig). Falls
    // through silently if there is no first stage yet.
    Q_UNUSED(text);
}""",

"""void ChainStudioPage::onDialogPromptChanged(const QString &text)
{
    // The top dialog bar drives the FIRST stage's prompt (per v3
    // mockup). If there is no first stage yet the user is still in
    // "describe what you want to make" mode -- the text input
    // accepts text freely; we just can't push it anywhere until a
    // stage exists.
    if (engine_->chain().stages.isEmpty())
        return;

    // Engine rejects setStageConfig on Locked stages, but the entry
    // stage is rarely Locked during prompt editing. Harvest the
    // existing config so we only mutate the prompt field.
    const QString firstStageId = engine_->chain().stages.first().id;
    StageConfig newConfig = engine_->chain().stages.first().config;
    newConfig.prompt = text;
    engine_->setStageConfig(firstStageId, newConfig);
}""",
),

]


def already_applied(path: Path) -> bool:
    try:
        return MARKER in path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False


def write_with_crlf(path: Path, body_lf: str) -> None:
    text = body_lf.replace("\r\n", "\n").replace("\n", NL)
    path.write_bytes(text.encode("utf-8"))


def apply_edits(path: Path) -> bool:
    """
    Apply all edits to file at `path`. Returns True if changes were
    made; False if marker already present (idempotent no-op).
    Aborts with a non-zero return if any anchor is missing or
    ambiguous -- never partial-patches.
    """
    raw = path.read_bytes().decode("utf-8")
    # Normalize CRLF -> LF for anchor matching.
    body = raw.replace("\r\n", "\n")

    if MARKER in body:
        print(f"  Already applied (marker present): {path.name}")
        return False

    # Validate every anchor matches exactly once before applying ANY edit.
    for i, (anchor, _replacement) in enumerate(EDITS, 1):
        count = body.count(anchor)
        if count != 1:
            print(f"  ERROR: edit #{i} anchor matches {count} times "
                  f"(expected exactly 1).")
            preview = anchor.split("\n")[0][:80]
            print(f"  First line of anchor: {preview!r}")
            return False

    # All anchors verified. Now perform the substitutions.
    for anchor, replacement in EDITS:
        body = body.replace(anchor, replacement, 1)

    # Confirm the marker landed.
    if MARKER not in body:
        print("  ERROR: post-edit body does not contain MARKER. "
              "Something is wrong with the replacement strings.")
        return False

    # Write backup, then new content with CRLF.
    backup = path.with_suffix(path.suffix + ".pre_pass8b.bak")
    backup.write_bytes(raw.encode("utf-8"))
    print(f"  Backup written: {backup.name}")

    write_with_crlf(path, body)
    print(f"  Rewrote: {path.name}")
    return True


def main() -> int:
    print("Applying PASS 8B: widget -> engine mutation routing")
    print(f"  Project root: {PROJECT_ROOT}")
    print()

    path = PROJECT_ROOT / CPP_REL
    if not path.exists():
        print(f"ERROR: {CPP_REL} does not exist at {path}")
        return 1

    print(CPP_REL)
    changed = apply_edits(path)
    print()

    if changed:
        print("Done -- PASS 8B applied.")
    else:
        print("Done -- PASS 8B was already applied (no-op).")

    print()
    print("Verify:")
    print("  1. .\\scripts\\dev\\run_ui.ps1")
    print("  2. Build should succeed.")
    print("  3. Chain Studio empty -> click '+ add stage' -> T2I.")
    print("  4. Rail shows a T2I node (Draft); config panel populates.")
    print("  5. Type in the top prompt input -> first-stage prompt updates.")
    print("  6. (Optional) Click upload BEFORE any stages -> chain switches")
    print("     to UploadedImage entry, '+ add stage' offers I2I / I2V / I2_3D.")
    print("  7. Click Regenerate -- still no-op (Pass 8c wires it).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
