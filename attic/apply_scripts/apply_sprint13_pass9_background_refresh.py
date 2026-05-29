from __future__ import annotations

from pathlib import Path
import sys


def backup_once(path: Path, suffix: str, original: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
        print(f"Backup written: {backup}")


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if old not in text:
        print(f"[skip] pattern not found: {label}")
        return text, False
    return text.replace(old, new, 1), True


def patch_cmake(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    if "find_package(Qt6 REQUIRED COMPONENTS" in text and "Concurrent" not in text.split("find_package(Qt6 REQUIRED COMPONENTS",1)[1].split(")",1)[0]:
        text, did = replace_once(
            text,
            "find_package(Qt6 REQUIRED COMPONENTS Widgets Svg)",
            "find_package(Qt6 REQUIRED COMPONENTS Widgets Svg Concurrent)",
            "add Qt6 Concurrent component",
        )
        changed = changed or did

    if "Qt6::Concurrent" not in text:
        # try common target_link_libraries block
        old = """target_link_libraries(SpellVision
    PRIVATE
    Qt6::Widgets
    Qt6::Svg
"""
        new = """target_link_libraries(SpellVision
    PRIVATE
    Qt6::Widgets
    Qt6::Svg
    Qt6::Concurrent
"""
        text, did = replace_once(text, old, new, "link Qt6::Concurrent")
        changed = changed or did

    if not changed:
        return False

    backup_once(path, ".pre_pass9_background_refresh.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_sprint13_pass9_background_refresh.py <SpellVision project root>")
        return 2

    root = Path(sys.argv[1]).resolve()
    cmake = root / "CMakeLists.txt"
    if not cmake.exists():
        print(f"Missing file: {cmake}")
        return 1

    changed = patch_cmake(cmake)
    if not changed:
        print("No CMake changes were needed.")
        return 0

    print("Pass 9 CMake patch applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
