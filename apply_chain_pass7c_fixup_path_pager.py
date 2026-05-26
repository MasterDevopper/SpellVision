r"""
SpellVision — Pass 7c fixup: image path + pager sizing.

Two real bugs from first render of Pass 7c:

(Bug A) The image isn't loading — canvas shows two faint "—" glyphs
    (the renderImage() fallback for missing files). Cause: my path
    resolution uses QDir::filePath() which concatenates without
    resolving "..", so the path comes out literally as
    ".../build/Debug/../../SpellVision.jpg". QFileInfo::exists()
    handles this, but QPixmap's load path appears not to. Fix: use
    QDir::cleanPath() to resolve the segments.

(Bug B) The pager only shows the "<" button — "variation N of M",
    the ">" button, and the LOCK pill are clipped/invisible. Cause:
    I set the buttons' size via stylesheet (min-width/max-width/etc)
    but Qt's layout engine uses sizeHint() and minimumSize() to lay
    out children, NOT stylesheet rules. The button's actual sizeHint
    is based on text + style, not on the stylesheet "min-width:30px"
    rule. Combined with pagerHost having QSizePolicy::Expanding+Fixed
    which means "fixed to sizeHint" (and the host has no content so
    its sizeHint is small), the row gets squished and clipped.

Fix Bug B by:
  1. Calling QWidget::setFixedSize() on prev/next buttons (the C++
     method, not the stylesheet) so the layout system tracks the
     real size.
  2. Setting pagerHost minimum height explicitly so the row reserves
     space regardless of how Qt computes sizeHint.

Both fixes are surgical edits to ChainCanvasWidget.cpp. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 7C FIXUP PATH AND PAGER SIZING"
BACKUP_SUFFIX = ".pre_pass7c_fixup.bak"


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


# =============================================================================
# Bug A — path resolution in ChainStudioPage.cpp's buildStubChain
# =============================================================================

PATH_OLD = (
    '    const QString projectRoot = QDir(QCoreApplication::applicationDirPath())\n'
    '        .filePath(QStringLiteral("../.."));\n'
)

PATH_NEW = (
    f'    // --- {MARKER} ---\n'
    '    // QDir::filePath() concatenates without resolving "..", so we\n'
    '    // need cleanPath() (or canonicalPath, but that requires the\n'
    '    // path to exist on disk) to get a real resolved root path that\n'
    '    // QPixmap will accept.\n'
    '    const QString projectRoot = QDir::cleanPath(\n'
    '        QDir(QCoreApplication::applicationDirPath())\n'
    '            .filePath(QStringLiteral("../..")));\n'
)


def patch_page(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStudioPage.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)
    text = replace_once(text, PATH_OLD, PATH_NEW, "projectRoot resolution")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# =============================================================================
# Bug B — pager sizing in ChainCanvasWidget.cpp
# =============================================================================

# Two surgical edits:
# 1. Replace the pagerHost setSizePolicy with setFixedHeight; this
#    reserves vertical space regardless of sizeHint computation.
# 2. After each pager button is created, call setFixedSize() with the
#    actual pixel dimensions so the layout engine sees them. The
#    stylesheet min-width/max-width was only a visual rule.
# 3. The lock button also needs a sensible width hint; the styled
#    "LOCK" / "LOCKED" pill currently relies on padding-derived
#    sizeHint, which gets squished. Use setMinimumWidth as a floor.

# Replace the pagerHost block. Make it tall enough for the buttons +
# 4px of breathing room, and let it expand horizontally.
PAGER_HOST_OLD = (
    '    auto *pagerHost = new QWidget(this);\n'
    '    pagerHost->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);\n'
    '    pagerRow_ = new QHBoxLayout(pagerHost);\n'
)

PAGER_HOST_NEW = (
    f'    // --- {MARKER}: explicit pager host height ---\n'
    '    auto *pagerHost = new QWidget(this);\n'
    '    pagerHost->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);\n'
    '    pagerHost->setFixedHeight(kPagerButtonSide + 8);  // buttons + breathing\n'
    '    pagerRow_ = new QHBoxLayout(pagerHost);\n'
)

# Patch each button creation to add setFixedSize / setMinimumWidth.
# prevButton_ and nextButton_ are square chips at kPagerButtonSide.
PREV_OLD = (
    '    prevButton_ = new QPushButton(QStringLiteral("\\u2039"), pagerHost);  // \xe2\x80\xb9\n'
    '    prevButton_->setCursor(Qt::PointingHandCursor);\n'
    '    prevButton_->setStyleSheet(pagerButtonStyle(true));\n'
)

PREV_NEW = (
    '    prevButton_ = new QPushButton(QStringLiteral("\\u2039"), pagerHost);  // \xe2\x80\xb9\n'
    '    prevButton_->setCursor(Qt::PointingHandCursor);\n'
    '    prevButton_->setFixedSize(kPagerButtonSide, kPagerButtonSide);\n'
    '    prevButton_->setStyleSheet(pagerButtonStyle(true));\n'
)

NEXT_OLD = (
    '    nextButton_ = new QPushButton(QStringLiteral("\\u203a"), pagerHost);  // \xe2\x80\xba\n'
    '    nextButton_->setCursor(Qt::PointingHandCursor);\n'
    '    nextButton_->setStyleSheet(pagerButtonStyle(true));\n'
)

NEXT_NEW = (
    '    nextButton_ = new QPushButton(QStringLiteral("\\u203a"), pagerHost);  // \xe2\x80\xba\n'
    '    nextButton_->setCursor(Qt::PointingHandCursor);\n'
    '    nextButton_->setFixedSize(kPagerButtonSide, kPagerButtonSide);\n'
    '    nextButton_->setStyleSheet(pagerButtonStyle(true));\n'
)

# Lock button — pill, needs sensible width floor.
LOCK_OLD = (
    '    lockButton_ = new QPushButton(QStringLiteral("LOCK"), pagerHost);\n'
    '    lockButton_->setCursor(Qt::PointingHandCursor);\n'
    '    lockButton_->setStyleSheet(lockButtonStyle(true));\n'
)

LOCK_NEW = (
    '    lockButton_ = new QPushButton(QStringLiteral("LOCK"), pagerHost);\n'
    '    lockButton_->setCursor(Qt::PointingHandCursor);\n'
    '    lockButton_->setMinimumWidth(80);  // pill width floor\n'
    '    lockButton_->setFixedHeight(kPagerButtonSide);\n'
    '    lockButton_->setStyleSheet(lockButtonStyle(true));\n'
)


def patch_canvas(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainCanvasWidget.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)
    text = replace_once(text, PAGER_HOST_OLD, PAGER_HOST_NEW, "pagerHost block")
    text = replace_once(text, PREV_OLD, PREV_NEW, "prev button creation")
    text = replace_once(text, NEXT_OLD, NEXT_NEW, "next button creation")
    text = replace_once(text, LOCK_OLD, LOCK_NEW, "lock button creation")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("qt_ui/chain/ChainStudioPage.cpp")
    patch_page(project)
    print()
    print("qt_ui/chain/ChainCanvasWidget.cpp")
    patch_canvas(project)
    print()
    print(f"Done — {MARKER} applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
