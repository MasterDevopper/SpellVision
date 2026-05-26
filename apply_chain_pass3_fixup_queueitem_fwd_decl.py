r"""
SpellVision — Chain Studio Pass 3 fixup: QueueItem forward-declaration namespace.

Build error:
  error C2027: use of undefined type 'spellvision::chain::QueueItem'
  (~21 cascading errors all pointing at the same false phantom)

Cause: ChainCompletionWatcher.h declared
    QString matchTrackedEngineId(const class QueueItem &item) const;
inside `namespace spellvision::chain { ... }`. An inline `class X`
forward-declaration applies to the CURRENT namespace — so this
forward-declared a phantom `spellvision::chain::QueueItem` instead of
the real global `::QueueItem` from QueueManager.h. The .cpp then sees
two different types: the real one (via #include "QueueManager.h") and
the phantom (in the member signature), so every `item.<field>` access
through the phantom is unresolved.

Cascading effects:
  - QVector<QueueItem> picks up the phantom => container mismatch
    (C2440 const QList<QueueItem> -> const QList<spellvision::chain::QueueItem>)
  - `const auto isRunning = item.state == ...` fails type deduction
    (phantom has no .state) => "const object must be initialized" (C2737)

Fix: put a proper forward-declaration of the real ::QueueItem in the
global namespace at the top of the header, BEFORE the namespace
opens. Also fix the bad inline `class QueueItem` to plain `QueueItem`
in the member signature. The real type is a struct, not a class —
inline elaborated-type-specifier with the wrong tag is a separate
hazard worth removing.

Two surgical edits to ChainCompletionWatcher.h:
  1. Insert `struct QueueItem;` in the global namespace alongside the
     existing forward-decls of QueueManager / WorkerQueueController.
  2. Drop the `class` tag from the member signature so it refers to
     the just-forward-declared global struct.

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 3 FIXUP QUEUEITEM FORWARD DECL"
BACKUP_SUFFIX = ".pre_pass3_fixup.bak"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Anchor not found: {label}")
    if text.count(old) > 1:
        raise RuntimeError(f"Anchor not unique ({text.count(old)}x): {label}")
    return text.replace(old, new, 1)


# Edit 1: add the global QueueItem forward-decl alongside the existing
# forward-decls of QueueManager / WorkerQueueController. Anchor on the
# pair that's already there so the new line lands in the right spot.
FWD_OLD = (
    "class QueueManager;\n"
    "class WorkerQueueController;\n"
)
FWD_NEW = (
    "class QueueManager;\n"
    "class WorkerQueueController;\n"
    f"struct QueueItem;  // {MARKER}: real ::QueueItem from QueueManager.h\n"
)

# Edit 2: drop the bogus inline `class` tag from the member signature.
SIG_OLD = "    QString matchTrackedEngineId(const class QueueItem &item) const;\n"
SIG_NEW = "    QString matchTrackedEngineId(const QueueItem &item) const;\n"


def patch_header(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainCompletionWatcher.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)
    text = replace_once(text, FWD_OLD, FWD_NEW, "global forward-decl block")
    text = replace_once(text, SIG_OLD, SIG_NEW, "matchTrackedEngineId signature")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("ChainCompletionWatcher.h")
    patch_header(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("Next: .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
