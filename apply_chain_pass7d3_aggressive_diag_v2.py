r"""
SpellVision — Pass 7d.3 aggressive diagnostic v2.

Fixes the v1 ordering bug: previous version installed the filter on
addButton_ BEFORE addButton_ was constructed (the if-guard meant nothing
happened). This version injects the filter install AFTER the connect
that follows addButton_'s construction.

What this adds:

  1. ctor log: confirms addButton_ pointer + properties at construction
  2. Test lambda connect: separate from the named-slot connect; if this
     lambda fires on click but the named slot doesn't, the issue is in
     the slot routing
  3. Event filter on addButton_: logs all mouse press/release events
     reaching the button
"""

from __future__ import annotations
import re
import sys
from pathlib import Path

MARKER = "PASS 7D3 AGGRESSIVE DIAGNOSTIC V2"


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    path = project / "qt_ui" / "chain" / "ChainDialogBarWidget.cpp"
    if not path.exists():
        print(f"  Not found: {path}")
        return 1

    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return 0

    backup_once(path, ".pre_pass7d3_aggressive_diag_v2.bak")

    # Remove v1 injections (the broken filter install + the diagnostic
    # at the connect) so we can place them properly. We're tolerant: if
    # v1 patterns aren't there, no-op.
    text = re.sub(
        r"\r?\n\s*// --- PASS 7D3 AGGRESSIVE DIAGNOSTIC: install filter on addButton_ to log clicks ---[\s\S]*?addButton_->installEventFilter\(this\);\r?\n",
        "",
        text,
    )
    text = re.sub(
        r"\r?\n\s*// --- PASS 7D3 AGGRESSIVE DIAGNOSTIC: confirm construction \+ connect succeeded ---[\s\S]*?qDebug\(\) << \"\[ChainStudio\] ctor: test lambda connect valid=\" << \(bool\)conn;\r?\n\s*\}\r?\n",
        "",
        text,
    )
    text = re.sub(
        r"\s*// --- PASS 7D3 AGGRESSIVE DIAGNOSTIC: log all events targeting addButton_ ---[\s\S]*?\}\r?\n\s*\}\r?\n",
        "",
        text,
    )

    # Ensure QDebug is available
    if "#include <QDebug>" not in text:
        m = re.search(r'(#include <QPushButton>\r?\n)', text)
        if m:
            text = text.replace(m.group(1),
                                m.group(1) + "#include <QDebug>\r\n", 1)

    # 1. Inject AFTER the connect(addButton_, ...) inside the constructor.
    #    Find the existing connect and add diagnostics + filter install
    #    + test lambda connect immediately after it.
    addbtn_connect_pattern = re.compile(
        r"(connect\(addButton_,\s*&QPushButton::clicked,\s*\r?\n"
        r"\s*this,\s*&ChainDialogBarWidget::onAddStageClicked\);\s*\r?\n)"
    )
    addbtn_match = addbtn_connect_pattern.search(text)
    if not addbtn_match:
        raise RuntimeError("Cannot find addButton_ connect in constructor")

    diag_injection = (
        f"\r\n    // --- {MARKER}: confirm construction + add filter + test lambda ---\r\n"
        "    qDebug() << \"[ChainStudio] ctor: addButton_ =\" << (void*)addButton_\r\n"
        "             << \"isVisible=\" << addButton_->isVisible()\r\n"
        "             << \"isEnabled=\" << addButton_->isEnabled();\r\n"
        "    addButton_->installEventFilter(this);\r\n"
        "    qDebug() << \"[ChainStudio] ctor: installed event filter on addButton_\";\r\n"
        "    {\r\n"
        "        QMetaObject::Connection conn = connect(\r\n"
        "            addButton_, &QPushButton::clicked, this,\r\n"
        "            []() { qDebug() << \"[ChainStudio] LAMBDA: addButton_ clicked signal received in lambda!\"; });\r\n"
        "        qDebug() << \"[ChainStudio] ctor: test lambda connect valid=\" << (bool)conn;\r\n"
        "    }\r\n"
    )
    text = text[:addbtn_match.end()] + diag_injection + text[addbtn_match.end():]

    # 2. Extend eventFilter to log addButton_ events at top of function
    ef_pattern = re.compile(
        r"(bool ChainDialogBarWidget::eventFilter\(QObject \*watched, QEvent \*event\)\r?\n\{\r?\n)"
    )
    ef_match = ef_pattern.search(text)
    if not ef_match:
        raise RuntimeError("Cannot find eventFilter function")
    ef_inject = (
        ef_match.group(1) +
        f"    // --- {MARKER}: log all events targeting addButton_ ---\r\n"
        "    if (watched == addButton_)\r\n"
        "    {\r\n"
        "        const QEvent::Type t = event->type();\r\n"
        "        if (t == QEvent::MouseButtonPress ||\r\n"
        "            t == QEvent::MouseButtonRelease ||\r\n"
        "            t == QEvent::Enter ||\r\n"
        "            t == QEvent::Leave)\r\n"
        "        {\r\n"
        "            qDebug() << \"[ChainStudio] eventFilter: addButton_ event type=\" << t;\r\n"
        "        }\r\n"
        "    }\r\n"
    )
    text = text.replace(ef_match.group(1), ef_inject, 1)

    path.write_text(text, encoding="utf-8")
    print(f"  Patched: {path.name}")
    print()
    print(f"Done — {MARKER} applied.")
    print()
    print("After rebuild and launch, look for these new log lines:")
    print()
    print("  AT STARTUP:")
    print("    '[ChainStudio] ctor: addButton_ = 0x... isVisible=true isEnabled=true'")
    print("    '[ChainStudio] ctor: installed event filter on addButton_'")
    print("    '[ChainStudio] ctor: test lambda connect valid= true'")
    print()
    print("  WHEN HOVERING + CLICKING THE BUTTON:")
    print("    '[ChainStudio] eventFilter: addButton_ event type= 10' (Enter)")
    print("    '[ChainStudio] eventFilter: addButton_ event type= 2'  (MouseButtonPress)")
    print("    '[ChainStudio] eventFilter: addButton_ event type= 3'  (MouseButtonRelease)")
    print("    '[ChainStudio] LAMBDA: addButton_ clicked signal received in lambda!'")
    print("    '[ChainStudio] DialogBar::onAddStageClicked fired'")
    print()
    print("Whichever lines DO NOT appear isolate where the problem is:")
    print("  No Enter event   → mouse position isn't reaching button (geometry issue)")
    print("  No Press event   → some parent eats clicks")
    print("  Press but no Release → button got disabled mid-click")
    print("  Both events but no LAMBDA → button doesn't fire clicked signal")
    print("  LAMBDA but no onAddStageClicked → named-slot connect broken (unlikely)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
