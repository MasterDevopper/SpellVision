r"""
SpellVision — Pass 7d.3 diagnostic: trace add-stage click.

User reports: clicking the + add stage button does nothing. Build is
clean and connects compile, so the signals SHOULD fire. Need real
runtime data instead of guessing.

This patch adds qDebug() lines at four points along the click flow:

1. Dialog bar's onAddStageClicked  — fires on click
2. Page's onRailAddStageRequested  — receives the signal
3. Page's showAddStageMenu         — about to exec the menu
4. After menu.exec returns         — was a selection made

Run the build, click the + button, and paste the [ChainStudio] log
lines. Whichever line is LAST tells us where the flow breaks:

- Nothing logs → connect is broken (signal not reaching slot)
- Line 1 logs, nothing more → dialog bar→page connect broken
- Lines 1-2 log, no 3 → onRailAddStageRequested isn't routing right
- Lines 1-3 log, no menu visible → menu is showing but offscreen,
  or has no items, or is suppressed by stylesheet, etc.

Surgical edits to two files. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 7D3 DIAGNOSTIC ADD STAGE CLICK"


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


# -- 1. Dialog bar onAddStageClicked: log entry + computed pos --

BAR_OLD = (
    "void ChainDialogBarWidget::onAddStageClicked()\r\n"
    "{\r\n"
    "    // --- CHAIN STUDIO PASS 7D3 KIND PICKER ---\r\n"
    "    // Compute the button's bottom-left in global screen coords so\r\n"
    "    // the page can pop the kind-picker QMenu just below it.\r\n"
    "    const QPoint pos = addButton_\r\n"
    "        ? addButton_->mapToGlobal(QPoint(0, addButton_->height()))\r\n"
    "        : QCursor::pos();\r\n"
    "    emit addStageRequested(pos);\r\n"
    "}\r\n"
)

BAR_NEW = (
    "void ChainDialogBarWidget::onAddStageClicked()\r\n"
    "{\r\n"
    f"    // --- {MARKER} ---\r\n"
    "    qDebug() << \"[ChainStudio] DialogBar::onAddStageClicked fired\";\r\n"
    "    const QPoint pos = addButton_\r\n"
    "        ? addButton_->mapToGlobal(QPoint(0, addButton_->height()))\r\n"
    "        : QCursor::pos();\r\n"
    "    qDebug() << \"[ChainStudio] DialogBar emit addStageRequested pos:\" << pos;\r\n"
    "    emit addStageRequested(pos);\r\n"
    "}\r\n"
)


def patch_bar_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainDialogBarWidget.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, ".pre_pass7d3_diag_bar.bak")
    # Ensure QDebug include
    if "#include <QDebug>" not in text:
        if "#include <QCursor>\r\n" in text:
            text = text.replace(
                "#include <QCursor>\r\n",
                "#include <QCursor>\r\n#include <QDebug>\r\n",
                1,
            )
    # Try CRLF first, then LF fallback
    if BAR_OLD in text:
        text = replace_once(text, BAR_OLD, BAR_NEW, "dialog bar onAddStageClicked (CRLF)")
    else:
        bar_old_lf = BAR_OLD.replace("\r\n", "\n")
        bar_new_lf = BAR_NEW.replace("\r\n", "\n")
        text = replace_once(text, bar_old_lf, bar_new_lf,
                            "dialog bar onAddStageClicked (LF)")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# -- 2. Page onRailAddStageRequested + showAddStageMenu: log along the path --

PAGE_OLD = (
    "void ChainStudioPage::onRailAddStageRequested(QPoint globalPos)\r\n"
    "{\r\n"
    "    // Single entry point for both + buttons (rail and dialog bar).\r\n"
    "    showAddStageMenu(globalPos);\r\n"
    "}\r\n"
    "\r\n"
    "void ChainStudioPage::showAddStageMenu(QPoint globalPos)\r\n"
    "{\r\n"
    "    // Build a fresh QMenu each call — cheap, and keeps state simple.\r\n"
    "    // Mirrors MainWindow.cpp's showTitleBarMenu / showLayoutMenu /\r\n"
    "    // showSystemMenu pattern (stack-allocated QMenu, exec at pos).\r\n"
    "    QMenu menu(this);\r\n"
    "\r\n"
    "    const QVector<StageKind> kinds = validKindsForAdd(stubChain_);\r\n"
)

PAGE_NEW = (
    "void ChainStudioPage::onRailAddStageRequested(QPoint globalPos)\r\n"
    "{\r\n"
    f"    // --- {MARKER} ---\r\n"
    "    qDebug() << \"[ChainStudio] Page::onRailAddStageRequested pos:\" << globalPos;\r\n"
    "    showAddStageMenu(globalPos);\r\n"
    "}\r\n"
    "\r\n"
    "void ChainStudioPage::showAddStageMenu(QPoint globalPos)\r\n"
    "{\r\n"
    f"    // --- {MARKER} ---\r\n"
    "    qDebug() << \"[ChainStudio] Page::showAddStageMenu entered, pos:\" << globalPos;\r\n"
    "    QMenu menu(this);\r\n"
    "\r\n"
    "    const QVector<StageKind> kinds = validKindsForAdd(stubChain_);\r\n"
    "    qDebug() << \"[ChainStudio] kinds.size:\" << kinds.size();\r\n"
)


# Also wrap the menu.exec call to log result.

PAGE_EXEC_OLD = (
    "    if (kinds.isEmpty())\r\n"
    "    {\r\n"
    "        QAction *noKinds = menu.addAction(QStringLiteral(\"No valid kinds\"));\r\n"
    "        noKinds->setEnabled(false);\r\n"
    "    }\r\n"
    "\r\n"
    "    menu.exec(globalPos);\r\n"
    "}\r\n"
)

PAGE_EXEC_NEW = (
    "    if (kinds.isEmpty())\r\n"
    "    {\r\n"
    "        QAction *noKinds = menu.addAction(QStringLiteral(\"No valid kinds\"));\r\n"
    "        noKinds->setEnabled(false);\r\n"
    "    }\r\n"
    "\r\n"
    f"    // --- {MARKER} ---\r\n"
    "    qDebug() << \"[ChainStudio] about to menu.exec, actions:\" << menu.actions().size();\r\n"
    "    QAction *picked = menu.exec(globalPos);\r\n"
    "    qDebug() << \"[ChainStudio] menu.exec returned, picked:\""
    " << (picked ? picked->text() : QStringLiteral(\"<nullptr>\"));\r\n"
    "}\r\n"
)


def patch_page_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStudioPage.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, ".pre_pass7d3_diag_page.bak")
    # Ensure QDebug include
    if "#include <QDebug>" not in text:
        if "#include <QMenu>\r\n" in text:
            text = text.replace(
                "#include <QMenu>\r\n",
                "#include <QDebug>\r\n#include <QMenu>\r\n",
                1,
            )
    # First the rail/menu entry block
    if PAGE_OLD in text:
        text = replace_once(text, PAGE_OLD, PAGE_NEW,
                            "page onRailAddStageRequested + showAddStageMenu head (CRLF)")
    else:
        page_old_lf = PAGE_OLD.replace("\r\n", "\n")
        page_new_lf = PAGE_NEW.replace("\r\n", "\n")
        text = replace_once(text, page_old_lf, page_new_lf,
                            "page onRailAddStageRequested head (LF)")
    # Then the menu.exec wrapper
    if PAGE_EXEC_OLD in text:
        text = replace_once(text, PAGE_EXEC_OLD, PAGE_EXEC_NEW,
                            "page menu.exec wrap (CRLF)")
    else:
        exec_old_lf = PAGE_EXEC_OLD.replace("\r\n", "\n")
        exec_new_lf = PAGE_EXEC_NEW.replace("\r\n", "\n")
        text = replace_once(text, exec_old_lf, exec_new_lf,
                            "page menu.exec wrap (LF)")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("qt_ui/chain/ChainDialogBarWidget.cpp")
    patch_bar_cpp(project)
    print()
    print("qt_ui/chain/ChainStudioPage.cpp")
    patch_page_cpp(project)
    print()
    print(f"Done — {MARKER} applied.")
    print()
    print("Next: .\\scripts\\dev\\run_ui.ps1")
    print()
    print("After it builds, click the + add stage button. Then paste")
    print("any [ChainStudio] lines from the console output. The trail")
    print("of which lines fired tells us exactly where the click flow")
    print("breaks down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
