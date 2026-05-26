r"""
SpellVision — Pass 7d.3 diagnostic v2.

v1 failed because its anchor matched the entire onAddStageClicked
function body — too brittle. If any whitespace, comment, or line
differed from what I wrote in PAGE_CPP / BAR_CPP, the anchor missed.

v2 fix: match the SMALL stable line "void ClassName::Method()" and
inject a qDebug immediately after the opening brace. Robust to any
body content. Same for the page handler.

Also adds the QDebug include if missing.

This patch is purely additive. Pass 7d.3 functional code stays
exactly as the user has it.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 7D3 DIAGNOSTIC V2"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def ensure_include(text: str, include_line: str, after_line: str) -> str:
    """Insert include_line after first occurrence of after_line if not present."""
    if include_line in text:
        return text
    # Try CRLF then LF
    for newline in ("\r\n", "\n"):
        anchor = after_line + newline
        if anchor in text:
            return text.replace(anchor, anchor + include_line + newline, 1)
    return text  # leave alone if anchor not found


def inject_after_open_brace(text: str, function_signature: str,
                            qdebug_lines: str, label: str) -> str:
    """
    Find a line like 'void Class::method()' followed by a '{' opener
    (either same-line or next-line) and inject qdebug_lines right after
    the open brace. Handles both brace-on-same-line and brace-on-next-
    line styles. Tolerant of whitespace variation around parens/args.
    """
    import re
    # Normalize the search pattern: split on common boundaries to allow
    # whitespace variation. E.g. "void Page::method(QPoint globalPos)"
    # becomes a regex that allows whitespace flexibility around ( ) ,
    # and around the param type/name.
    # Build by escaping then loosening whitespace.
    sig_loose = re.escape(function_signature)
    sig_loose = sig_loose.replace(r"\ ", r"\s+")     # space → \s+
    sig_loose = sig_loose.replace(r"\(", r"\s*\(\s*")
    sig_loose = sig_loose.replace(r"\)", r"\s*\)")
    pattern = re.compile(
        r"(" + sig_loose + r"\s*\{\s*\r?\n)",
        flags=re.MULTILINE,
    )
    matches = pattern.findall(text)
    if len(matches) == 0:
        raise RuntimeError(f"Function signature not found: {label}\n"
                           f"  searched: {function_signature}\n"
                           f"  regex:    {sig_loose}")
    if len(matches) > 1:
        raise RuntimeError(f"Function signature found {len(matches)}x: {label}")
    return pattern.sub(r"\1" + qdebug_lines, text, count=1)


# =============================================================================
# 1. ChainDialogBarWidget.cpp — log onAddStageClicked entry
# =============================================================================

def patch_bar_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainDialogBarWidget.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, ".pre_pass7d3_diag_v2_bar.bak")

    text = ensure_include(text, "#include <QDebug>", "#include <QCursor>")

    inject = (
        f"    // --- {MARKER} ---\n"
        "    qDebug() << \"[ChainStudio] DialogBar::onAddStageClicked fired,"
        " addButton_=\" << (void*)addButton_;\n"
    )
    text = inject_after_open_brace(
        text,
        "void ChainDialogBarWidget::onAddStageClicked()",
        inject,
        "dialog bar onAddStageClicked",
    )
    write_text(path, text)
    print(f"  Patched: {path.name}")


# =============================================================================
# 2. ChainStudioPage.cpp — log onRailAddStageRequested and showAddStageMenu
# =============================================================================

def patch_page_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStudioPage.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, ".pre_pass7d3_diag_v2_page.bak")

    text = ensure_include(text, "#include <QDebug>", "#include <QMenu>")

    inject_rail = (
        f"    // --- {MARKER} ---\n"
        "    qDebug() << \"[ChainStudio] Page::onRailAddStageRequested pos:\""
        " << globalPos;\n"
    )
    text = inject_after_open_brace(
        text,
        "void ChainStudioPage::onRailAddStageRequested(QPoint globalPos)",
        inject_rail,
        "page onRailAddStageRequested",
    )

    inject_menu = (
        f"    // --- {MARKER} ---\n"
        "    qDebug() << \"[ChainStudio] Page::showAddStageMenu pos:\""
        " << globalPos << \"stubChain stages:\" << stubChain_.stages.size()"
        " << \"entryKind:\" << static_cast<int>(stubChain_.entryKind);\n"
    )
    text = inject_after_open_brace(
        text,
        "void ChainStudioPage::showAddStageMenu(QPoint globalPos)",
        inject_menu,
        "page showAddStageMenu",
    )

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
    print("Click the + add stage button. Paste any [ChainStudio] lines")
    print("from the console output. The trail of which lines fire tells")
    print("us where the click flow breaks down:")
    print("  no logs at all          → click never reached the slot")
    print("  only 'DialogBar' line   → emit didn't reach the page")
    print("  + 'Page::onRail' line   → routing works, menu about to show")
    print("  + 'showAddStageMenu'    → menu was built and exec'd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
