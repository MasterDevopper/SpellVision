r"""
SpellVision — Pass 7d.3 fixup: rail addStageRequested emission.

Two problems from the previous run:

1. Apply script anchor 'emit addStageRequested();' didn't match the
   actual rail cpp — the rail uses signal-to-signal passthrough
   connect (no explicit emit). The script half-applied: rail HEADER
   now has the new `void addStageRequested(QPoint globalPos)` signal,
   but the rail CPP still has the old passthrough connect:

       connect(addButton_, &QPushButton::clicked,
               this, &ChainRailWidget::addStageRequested);

2. That mismatch produced the build error:
   QAbstractButton::clicked(bool) cannot be passthrough-connected to
   addStageRequested(QPoint) — incompatible signal signatures.

ROOT CAUSE: I assumed every signal is emitted via `emit Foo();`. The
rail uses Qt's signal-to-signal connect shortcut: when you `connect`
signal A directly to signal B with no slot logic, Qt forwards. That
shortcut requires matching signatures. Now that the signal carries
QPoint, we need a lambda in between to compute the position.

FIX: replace the passthrough connect with a lambda that maps the
button's bottom-left to global coords and emits with that QPoint:

    connect(addButton_, &QPushButton::clicked, this, [this]() {
        const QPoint pos = addButton_
            ? addButton_->mapToGlobal(QPoint(0, addButton_->height()))
            : QCursor::pos();
        emit addStageRequested(pos);
    });

Anchor-matched against the actual two-line passthrough. Adds <QCursor>
include if missing. Idempotent.

LESSON ADDED TO TRAP CHECKLIST (#9):
  Qt's `connect(sender, &Sender::sigA, this, &Self::sigB)` directly
  forwards signal sigA into sigB. When you change sigB's signature,
  this passthrough breaks. Before changing a signal signature, grep
  ALL `connect.*&...::<signal_name>` lines in the project that touch
  that signal — not just `emit <signal_name>` lines.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 7D3 FIXUP RAIL CONNECT"
BACKUP_SUFFIX = ".pre_pass7d3_fixup_rail_connect.bak"


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


# The actual passthrough connect, verified against the project's
# ChainRailWidget.cpp. Two lines, with CRLF preserved.
OLD_CONNECT = (
    "    connect(addButton_, &QPushButton::clicked,\r\n"
    "            this, &ChainRailWidget::addStageRequested);\r\n"
)

NEW_CONNECT = (
    f"    // --- {MARKER} ---\r\n"
    "    // Was a signal-to-signal passthrough; now needs a lambda to\r\n"
    "    // compute the button's bottom-left in global screen coords\r\n"
    "    // so the page can pop the kind-picker QMenu just below it.\r\n"
    "    connect(addButton_, &QPushButton::clicked, this, [this]() {\r\n"
    "        const QPoint pos = addButton_\r\n"
    "            ? addButton_->mapToGlobal(QPoint(0, addButton_->height()))\r\n"
    "            : QCursor::pos();\r\n"
    "        emit addStageRequested(pos);\r\n"
    "    });\r\n"
)


def patch_rail_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainRailWidget.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return

    # Defensive: also try the LF variant in case the project gets
    # normalized somehow. Project convention is CRLF, but be tolerant.
    old_crlf = OLD_CONNECT
    old_lf   = OLD_CONNECT.replace("\r\n", "\n")
    new_crlf = NEW_CONNECT
    new_lf   = NEW_CONNECT.replace("\r\n", "\n")

    backup_once(path)
    if old_crlf in text:
        text = replace_once(text, old_crlf, new_crlf, "passthrough connect (CRLF)")
    elif old_lf in text:
        text = replace_once(text, old_lf, new_lf, "passthrough connect (LF)")
    else:
        raise RuntimeError(
            "Couldn't find the passthrough connect line. Has the rail "
            "cpp been edited since 7d.3 attempt? Expected two-line:\n"
            "    connect(addButton_, &QPushButton::clicked,\n"
            "            this, &ChainRailWidget::addStageRequested);")

    # Ensure QCursor is included (used by the new lambda fallback).
    if "#include <QCursor>" not in text:
        if "#include <QPushButton>\r\n" in text:
            text = text.replace(
                "#include <QPushButton>\r\n",
                "#include <QCursor>\r\n#include <QPushButton>\r\n",
                1,
            )
        elif "#include <QPushButton>\n" in text:
            text = text.replace(
                "#include <QPushButton>\n",
                "#include <QCursor>\n#include <QPushButton>\n",
                1,
            )
        # else: leave as-is; user can add the include manually if needed.

    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("qt_ui/chain/ChainRailWidget.cpp")
    patch_rail_cpp(project)
    print()
    print(f"Done — {MARKER} applied.")
    print()
    print("Next: .\\scripts\\dev\\run_ui.ps1")
    print()
    print("Build should now clear. The kind-picker menu should pop")
    print("below either + button when clicked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
