r"""
SpellVision — Chain Studio Pass 6: register ChainSelfTest + main.cpp hook.

Two coordinated edits in one apply pass:

1. CMakeLists.txt — register the two new files in the existing Chain
   Studio block.
2. main.cpp — add a 6-line early-exit hook that runs the chain self-
   test when --chain-selftest appears in argv, exiting with the
   number of failed scenarios (0 = all passed).

Idempotent. After applying, build normally:
    .\scripts\dev\run_ui.ps1
and then run the harness:
    .\build\Debug\SpellVision.exe --chain-selftest
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "CHAIN STUDIO PASS 6 SELF-TEST"
CMAKE_BACKUP_SUFFIX = ".pre_chain_pass6_cmake.bak"
MAIN_BACKUP_SUFFIX = ".pre_chain_pass6_main.bak"


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


# ----- CMakeLists.txt: append to the Pass 5 block ------------------------

CMAKE_ANCHOR = (
    "    # --- CHAIN STUDIO PASS 5 CMAKE REGISTRATION ---\n"
    "    qt_ui/chain/ChainThumbnailer.h\n"
    "    qt_ui/chain/ChainThumbnailer.cpp\n"
)

CMAKE_REPLACEMENT = (
    "    # --- CHAIN STUDIO PASS 5 CMAKE REGISTRATION ---\n"
    "    qt_ui/chain/ChainThumbnailer.h\n"
    "    qt_ui/chain/ChainThumbnailer.cpp\n"
    f"    # --- {MARKER} ---\n"
    "    qt_ui/chain/ChainSelfTest.h\n"
    "    qt_ui/chain/ChainSelfTest.cpp\n"
)

# ----- main.cpp: 6-line early-exit hook ----------------------------------

MAIN_ANCHOR = (
    '#include <QApplication>\n'
    '#include "MainWindow.h"\n'
    '\n'
    'int main(int argc, char *argv[])\n'
    '{\n'
    '    QApplication app(argc, argv);\n'
    '    QApplication::setApplicationName("SpellVision");\n'
    '    QApplication::setOrganizationName("Dark Duck Studio");\n'
    '\n'
    '    MainWindow window;\n'
    '    window.show();\n'
    '\n'
    '    return app.exec();\n'
    '}\n'
)

MAIN_REPLACEMENT = (
    '#include <QApplication>\n'
    '#include <QString>\n'
    '#include <QStringList>\n'
    '#include "MainWindow.h"\n'
    '#include "chain/ChainSelfTest.h"\n'
    '\n'
    'int main(int argc, char *argv[])\n'
    '{\n'
    '    QApplication app(argc, argv);\n'
    '    QApplication::setApplicationName("SpellVision");\n'
    '    QApplication::setOrganizationName("Dark Duck Studio");\n'
    '\n'
    f'    // --- {MARKER} ---\n'
    '    // Headless verification entry point. When --chain-selftest is\n'
    '    // present we run the chain studio engine harness and exit\n'
    '    // with the number of failed scenarios (0 == all passed).\n'
    '    // MainWindow is NEVER constructed in this path.\n'
    '    if (QCoreApplication::arguments().contains(QStringLiteral("--chain-selftest")))\n'
    '        return spellvision::chain::runChainSelfTest();\n'
    '\n'
    '    MainWindow window;\n'
    '    window.show();\n'
    '\n'
    '    return app.exec();\n'
    '}\n'
)


def patch_cmake(project: Path) -> None:
    path = project / "CMakeLists.txt"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, CMAKE_BACKUP_SUFFIX)
    text = replace_once(text, CMAKE_ANCHOR, CMAKE_REPLACEMENT,
                        "Chain Studio Pass 5 block tail")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def patch_main(project: Path) -> None:
    path = project / "qt_ui" / "main.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, MAIN_BACKUP_SUFFIX)
    text = replace_once(text, MAIN_ANCHOR, MAIN_REPLACEMENT, "main() body")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("CMakeLists.txt")
    patch_cmake(project)
    print()
    print("qt_ui/main.cpp")
    patch_main(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("Next:")
    print("    .\\scripts\\dev\\run_ui.ps1")
    print("    .\\build\\Debug\\SpellVision.exe --chain-selftest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
