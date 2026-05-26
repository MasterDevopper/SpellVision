r"""
SpellVision — Chain Studio Pass 7c-prelude: add "chain" rail entry.

Adds a TEMPORARY rail entry pointing at ChainStudioPage so the
developing Track B work is visible while building. This is NOT the
final shell routing — that's Pass 9, which decides whether "chain"
gets promoted to "home" and what HomePage features migrate.

The entry is marked "(under construction)" in its tooltip to make
the scaffolding intent visible. Pass 9 will either promote this
entry to replace "home" or formalize it as its own first-class
mode, depending on the migration decision we make at that point.

Five surgical edits across three files:

1. ShellNavigationController.cpp — add {"chain", "Chain", "Chain Studio
   (under construction)"} to railButtonSpecs(); add pageContextForMode
   case.
2. MainWindow.h — forward-declare ChainStudioPage; add chainStudioPage_
   member.
3. MainWindow.cpp — include header; instantiate page in buildPages();
   add to pageStack_ for loop; register in modePages_.

Each edit is strictly additive. Existing modes and behavior are
unchanged. Pass 9's removal/promotion of this entry will use these
markers to find what to clean up.

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "CHAIN STUDIO PASS 7C-PRELUDE RAIL ENTRY"
NAV_BACKUP_SUFFIX = ".pre_pass7c_prelude_nav.bak"
MWH_BACKUP_SUFFIX = ".pre_pass7c_prelude_mwh.bak"
MWC_BACKUP_SUFFIX = ".pre_pass7c_prelude_mwc.bak"


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


# =============================================================================
# 1. ShellNavigationController.cpp
# =============================================================================

NAV_SPEC_ANCHOR = (
    '        {QStringLiteral("home"), QStringLiteral("Home"), QStringLiteral("Home")},\n'
)

NAV_SPEC_REPLACEMENT = (
    '        {QStringLiteral("home"), QStringLiteral("Home"), QStringLiteral("Home")},\n'
    f'        // --- {MARKER} ---\n'
    '        {QStringLiteral("chain"), QStringLiteral("Chain"), QStringLiteral("Chain Studio (under construction)")},\n'
)

NAV_CONTEXT_ANCHOR = (
    '    if (key == QStringLiteral("home"))\n'
    '        return QStringLiteral("Home");\n'
)

NAV_CONTEXT_REPLACEMENT = (
    '    if (key == QStringLiteral("home"))\n'
    '        return QStringLiteral("Home");\n'
    f'    // --- {MARKER} ---\n'
    '    if (key == QStringLiteral("chain"))\n'
    '        return QStringLiteral("Chain Studio");\n'
)


def patch_nav(project: Path) -> None:
    path = project / "qt_ui" / "shell" / "ShellNavigationController.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, NAV_BACKUP_SUFFIX)
    text = replace_once(text, NAV_SPEC_ANCHOR, NAV_SPEC_REPLACEMENT, "rail spec list")
    text = replace_once(text, NAV_CONTEXT_ANCHOR, NAV_CONTEXT_REPLACEMENT, "pageContextForMode")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# =============================================================================
# 2. MainWindow.h — forward-decl + member
# =============================================================================

# Forward-decl. ChainStudioPage lives in namespace spellvision::chain.
# Following the Pass 3 lesson: forward-declarations of namespaced
# types belong INSIDE that namespace, not in the global scope.
MWH_FWDDECL_ANCHOR = (
    'class HomePage;\n'
)

MWH_FWDDECL_REPLACEMENT = (
    'class HomePage;\n'
    f'// --- {MARKER} ---\n'
    'namespace spellvision::chain { class ChainStudioPage; }\n'
)

# Member declaration. Add immediately after homePage_ so all page
# members stay grouped (the existing convention).
MWH_MEMBER_ANCHOR = (
    '    HomePage *homePage_ = nullptr;\n'
)

MWH_MEMBER_REPLACEMENT = (
    '    HomePage *homePage_ = nullptr;\n'
    f'    // --- {MARKER} ---\n'
    '    spellvision::chain::ChainStudioPage *chainStudioPage_ = nullptr;\n'
)


def patch_mwh(project: Path) -> None:
    path = project / "qt_ui" / "MainWindow.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, MWH_BACKUP_SUFFIX)
    text = replace_once(text, MWH_FWDDECL_ANCHOR, MWH_FWDDECL_REPLACEMENT, "HomePage forward-decl")
    text = replace_once(text, MWH_MEMBER_ANCHOR, MWH_MEMBER_REPLACEMENT, "homePage_ member")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# =============================================================================
# 3. MainWindow.cpp — include + instantiate + stack + map
# =============================================================================

MWC_INCLUDE_ANCHOR = (
    '#include "HomePage.h"\n'
)

MWC_INCLUDE_REPLACEMENT = (
    '#include "HomePage.h"\n'
    f'// --- {MARKER} ---\n'
    '#include "chain/ChainStudioPage.h"\n'
)

MWC_INSTANTIATE_ANCHOR = (
    '    homePage_ = new HomePage(this);\n'
)

MWC_INSTANTIATE_REPLACEMENT = (
    '    homePage_ = new HomePage(this);\n'
    f'    // --- {MARKER} ---\n'
    '    chainStudioPage_ = new spellvision::chain::ChainStudioPage(this);\n'
)

MWC_STACK_ANCHOR = (
    '    for (QWidget *page : {static_cast<QWidget *>(homePage_),\n'
    '                          static_cast<QWidget *>(t2iPage_),\n'
)

MWC_STACK_REPLACEMENT = (
    '    for (QWidget *page : {static_cast<QWidget *>(homePage_),\n'
    f'                          static_cast<QWidget *>(chainStudioPage_),  // {MARKER}\n'
    '                          static_cast<QWidget *>(t2iPage_),\n'
)

MWC_MAP_ANCHOR = (
    '    modePages_.insert(QStringLiteral("home"), homePage_);\n'
)

MWC_MAP_REPLACEMENT = (
    '    modePages_.insert(QStringLiteral("home"), homePage_);\n'
    f'    // --- {MARKER} ---\n'
    '    modePages_.insert(QStringLiteral("chain"), chainStudioPage_);\n'
)


def patch_mwc(project: Path) -> None:
    path = project / "qt_ui" / "MainWindow.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, MWC_BACKUP_SUFFIX)
    text = replace_once(text, MWC_INCLUDE_ANCHOR, MWC_INCLUDE_REPLACEMENT, "HomePage include")
    text = replace_once(text, MWC_INSTANTIATE_ANCHOR, MWC_INSTANTIATE_REPLACEMENT, "homePage_ instantiation")
    text = replace_once(text, MWC_STACK_ANCHOR, MWC_STACK_REPLACEMENT, "pageStack for-loop")
    text = replace_once(text, MWC_MAP_ANCHOR, MWC_MAP_REPLACEMENT, "modePages_ map insertion")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("qt_ui/shell/ShellNavigationController.cpp")
    patch_nav(project)
    print()
    print("qt_ui/MainWindow.h")
    patch_mwh(project)
    print()
    print("qt_ui/MainWindow.cpp")
    patch_mwc(project)
    print()
    print(f"Done — {MARKER} applied.")
    print()
    print("After build, the rail has a new 'Chain' entry between 'Home'")
    print("and 'T2I'. Clicking it routes to ChainStudioPage. The entry")
    print("is marked 'under construction' in its tooltip. Pass 9 decides")
    print("whether to promote it to replace 'home' or formalize it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
