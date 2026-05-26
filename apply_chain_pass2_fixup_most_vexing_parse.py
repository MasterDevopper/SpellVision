r"""
SpellVision — Chain Studio Pass 2 fixup: MSVC most-vexing-parse.

Build error:
  error C2228: left of '.beginGroup' must have class/struct/union
  at qt_ui/chain/ChainStore.cpp(500,11)

Cause: the form
    QSettings s(QLatin1String(kOrg), QLatin1String(kApp));
is ambiguous in standard C++ and the language REQUIRES the compiler
to pick the function-declaration interpretation (most vexing parse).
MSVC sees this as a function `s` taking two QLatin1String parameters,
not a QSettings variable. Subsequent `s.beginGroup(...)` then fails
because `s` is a function, not an object.

Fix: brace-initialize. Braces can't start a function declaration, so
the ambiguity disappears:
    QSettings s{QLatin1String(kOrg), QLatin1String(kApp)};

This pattern bites Windows/MSVC builds specifically often enough that
it's worth fixing for the project to remember: prefer brace-init for
constructor calls where any argument is itself a parenthesized
type-cast or single-arg construction.

Two call sites (setLastActiveChainId, lastActiveChainId). Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 2 FIXUP MOST VEXING PARSE"
BACKUP_SUFFIX = ".pre_pass2_fixup.bak"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def replace_all(text: str, old: str, new: str, label: str, expected: int) -> str:
    n = text.count(old)
    if n == 0:
        raise RuntimeError(f"Anchor not found: {label}")
    if n != expected:
        raise RuntimeError(
            f"Anchor count mismatch ({n}, expected {expected}): {label}"
        )
    return text.replace(old, new)


# Both call sites share the exact same construction line, so one
# replacement covers both. Two occurrences expected.
OLD_LINE = "    QSettings s(QLatin1String(kOrg), QLatin1String(kApp));\n"
NEW_LINE = "    QSettings s{QLatin1String(kOrg), QLatin1String(kApp)};  // brace-init avoids most-vexing-parse on MSVC\n"


def patch_chainstore(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStore.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)
    text = replace_all(text, OLD_LINE, NEW_LINE, "QSettings construction", expected=2)
    # Marker comment for idempotency, placed in a stable spot near the
    # top of the file's anonymous namespace.
    text = text.replace(
        "namespace\n{\n",
        f"namespace\n{{\n// --- {MARKER} ---\n",
        1,
    )
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("ChainStore.cpp")
    patch_chainstore(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("Next: .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
