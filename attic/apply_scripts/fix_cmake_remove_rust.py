#!/usr/bin/env python3
"""
Remove the vestigial Rust core (spellvision_rust / spellvision_core) from
CMakeLists.txt. Nothing in the C++ tree references these symbols, but the
build still tries to `cargo build` the archived rust/ directory and fails.

Atomic: validates ALL three anchors before writing ANY change. Preserves the
file's original line endings.

Run from the project root:
    python fix_cmake_remove_rust.py
"""
import sys
from pathlib import Path

PATH = Path("CMakeLists.txt")

# --- (anchor, replacement) edits ---------------------------------------------
EDITS = [
    # 1. The custom target + imported-library block (lines ~30-45).
    (
        'add_custom_target(spellvision_rust ALL\n'
        '    COMMAND cargo build --manifest-path ${CMAKE_SOURCE_DIR}/rust/Cargo.toml\n'
        '    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/rust\n'
        '    COMMENT "Building Rust core"\n'
        ')\n'
        '\n'
        'if(WIN32)\n'
        '    set(RUST_LIB_PATH ${CMAKE_SOURCE_DIR}/rust/target/debug/spellvision_core.lib)\n'
        'else()\n'
        '    set(RUST_LIB_PATH ${CMAKE_SOURCE_DIR}/rust/target/debug/libspellvision_core.a)\n'
        'endif()\n'
        '\n'
        'add_library(spellvision_core STATIC IMPORTED GLOBAL)\n'
        'set_target_properties(spellvision_core PROPERTIES\n'
        '    IMPORTED_LOCATION ${RUST_LIB_PATH}\n'
        ')\n'
        '\n',
        '',
    ),
    # 2. The dependency edge.
    (
        'add_dependencies(SpellVision spellvision_rust)\n'
        '\n',
        '',
    ),
    # 3. The link entry (keep Concurrent + the closing paren).
    (
        '    Qt6::Concurrent\n'
        '    spellvision_core\n'
        ')',
        '    Qt6::Concurrent\n'
        ')',
    ),
]


def main() -> None:
    if not PATH.exists():
        raise SystemExit(f"ERROR: {PATH} not found. Run from the project root.")

    raw = PATH.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")

    # Validate ALL anchors first (atomic).
    missing = [i for i, (old, _) in enumerate(EDITS, 1) if old not in text]
    if missing:
        raise SystemExit(
            "ERROR: anchor(s) "
            + ", ".join(map(str, missing))
            + " not found. File may already be patched or has drifted; aborting "
            "without writing."
        )

    for old, new in EDITS:
        text = text.replace(old, new, 1)

    # Post-conditions: no Rust references should survive.
    for token in ("spellvision_rust", "spellvision_core", "RUST_LIB_PATH"):
        if token in text:
            raise SystemExit(f"ERROR: '{token}' still present after edit; aborting.")

    out = text.replace("\n", "\r\n") if crlf else text
    PATH.write_bytes(out.encode("utf-8"))
    print("OK: removed Rust core dependency from CMakeLists.txt "
          f"({'CRLF' if crlf else 'LF'} preserved).")


if __name__ == "__main__":
    main()
