r"""
SpellVision — Chain Studio Pass 7b (engine piggyback): add canAddStage().

ChainStudioPage's chain rail needs to enable/disable the trailing
"+ add stage" button based on whether the current chain accepts a new
stage. Per design §3 + Pass 4b's addStage() validation:
  - Always allowed when stages is empty (first stage)
  - Otherwise: only when the last stage is Locked

The rule already lives implicitly inside addStage() (it returns "" on
rejection). Pass 7b needs to PREDICT the answer for UI gating without
actually attempting the add, so we extract the rule into a const
predicate. Additive — addStage() itself is unchanged.

Surgical: header gets one line in the public section near canGenerate,
.cpp gets the impl near canGenerate's. No state change, no signal
change, no behavior change in any existing method.

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 7B ENGINE ADDITIVE CANADDSTAGE"
HDR_BACKUP_SUFFIX = ".pre_pass7b_engine_hdr.bak"
CPP_BACKUP_SUFFIX = ".pre_pass7b_engine_cpp.bak"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Anchor not found: {label}")
    if text.count(old) > 1:
        raise RuntimeError(f"Anchor not unique ({text.count(old)}x): {label}")
    return text.replace(old, new, 1)


# Header: insert canAddStage declaration right after canGenerate's.
HDR_ANCHOR = (
    "    // True iff the stage is in a state from which Regenerate is\n"
    "    // valid: entry stage OR the prior stage isLocked(). Track B\n"
    "    // binds the Regenerate button to this.\n"
    "    bool canGenerate(const QString &stageId) const;\n"
)

HDR_REPLACEMENT = (
    "    // True iff the stage is in a state from which Regenerate is\n"
    "    // valid: entry stage OR the prior stage isLocked(). Track B\n"
    "    // binds the Regenerate button to this.\n"
    "    bool canGenerate(const QString &stageId) const;\n"
    "\n"
    "    // True iff a new stage can be appended right now. Used by the\n"
    "    // ChainStudioPage rail's trailing \"+ add stage\" button. Rule:\n"
    "    // always true when chain has no stages (first stage); else\n"
    "    // true only if the last stage is Locked. Mirrors the\n"
    "    // validation in addStage() so the UI can predict rejection\n"
    "    // without actually attempting the add.\n"
    "    bool canAddStage() const;\n"
)

# .cpp: insert canAddStage impl right before canGenerate's, in the
# // generation section. We anchor on the comment header so insertion
# doesn't depend on exact formatting of canGenerate itself.
CPP_ANCHOR = (
    "// ---------------------------------------------------------------------------\n"
    "// generation\n"
    "// ---------------------------------------------------------------------------\n"
    "\n"
    "bool ChainEngine::canGenerate(const QString &stageId) const\n"
)

CPP_REPLACEMENT = (
    "// ---------------------------------------------------------------------------\n"
    "// generation\n"
    "// ---------------------------------------------------------------------------\n"
    "\n"
    "bool ChainEngine::canAddStage() const\n"
    "{\n"
    "    if (chain_.stages.isEmpty())\n"
    "        return true;\n"
    "    return chain_.stages.back().status == StageStatus::Locked;\n"
    "}\n"
    "\n"
    "bool ChainEngine::canGenerate(const QString &stageId) const\n"
)


def patch_header(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainEngine.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text or "canAddStage" in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, HDR_BACKUP_SUFFIX)
    text = replace_once(text, HDR_ANCHOR, HDR_REPLACEMENT, "canGenerate header anchor")
    # Marker for idempotency in a stable spot. Put it as a comment
    # near the top of the namespace, not in the inserted block (since
    # the inserted block already mentions "canAddStage" — that's what
    # the existence check above keys on).
    write_text(path, text)
    print(f"  Patched: {path.name}")


def patch_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainEngine.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if "::canAddStage()" in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, CPP_BACKUP_SUFFIX)
    text = replace_once(text, CPP_ANCHOR, CPP_REPLACEMENT, "generation section anchor")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("qt_ui/chain/ChainEngine.h")
    patch_header(project)
    print()
    print("qt_ui/chain/ChainEngine.cpp")
    patch_cpp(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("This is one of two parts of Pass 7b — also save the new")
    print("ChainRailWidget files and run apply_chain_pass7b_rail.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
