#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CPP_PATH = ROOT / "qt_ui" / "ImageGenerationPage.cpp"
CMAKE_PATH = ROOT / "CMakeLists.txt"
SCANNER_CPP = ROOT / "qt_ui" / "assets" / "AssetCatalogScanner.cpp"
SCANNER_H = ROOT / "qt_ui" / "assets" / "AssetCatalogScanner.h"

FUNCTIONS_TO_MOVE = [
    "looksLikeWanHighNoisePath",
    "looksLikeWanLowNoisePath",
    "compactCatalogDisplay",
    "shortDisplayFromValue",
    "modelNameFilters",
    "scanCatalog",
    "normalizedPathText",
    "inferVideoFamilyFromText",
    "humanVideoFamily",
    "inferImageFamilyFromText",
    "humanImageFamily",
    "familyNeedles",
    "textMatchesAnyNeedle",
    "scanAssetPaths",
    "findBestCompanionPath",
    "scanImageModelCatalog",
    "scanDiffusersVideoFolders",
    "scanVideoModelStackCatalog",
    "resolveCatalogValueByCandidates",
]

USING_LINES = [
    "using spellvision::assets::compactCatalogDisplay;",
    "using spellvision::assets::findBestCompanionPath;",
    "using spellvision::assets::humanImageFamily;",
    "using spellvision::assets::humanVideoFamily;",
    "using spellvision::assets::inferImageFamilyFromText;",
    "using spellvision::assets::inferVideoFamilyFromText;",
    "using spellvision::assets::looksLikeWanHighNoisePath;",
    "using spellvision::assets::looksLikeWanLowNoisePath;",
    "using spellvision::assets::modelNameFilters;",
    "using spellvision::assets::normalizedPathText;",
    "using spellvision::assets::resolveCatalogValueByCandidates;",
    "using spellvision::assets::scanCatalog;",
    "using spellvision::assets::scanDiffusersVideoFolders;",
    "using spellvision::assets::scanImageModelCatalog;",
    "using spellvision::assets::scanVideoModelStackCatalog;",
    "using spellvision::assets::shortDisplayFromValue;",
]


def find_function_bounds(text: str, name: str) -> tuple[int, int] | None:
    needle = f"{name}("
    pos = text.find(needle)
    while pos != -1:
        # Skip declarations/calls by requiring a body before the next semicolon.
        open_brace = text.find("{", pos)
        semicolon = text.find(";", pos)
        if open_brace != -1 and (semicolon == -1 or open_brace < semicolon):
            # Walk backward to the beginning of the function signature.
            start = text.rfind("\n\n", 0, pos)
            if start == -1:
                start = text.rfind("\n", 0, pos)
            if start == -1:
                start = 0
            else:
                # Preserve one blank line boundary by starting after the separator.
                start += 2 if text[start:start+2] == "\n\n" else 1

            depth = 0
            i = open_brace
            in_string = False
            in_char = False
            in_line_comment = False
            in_block_comment = False
            escape = False
            while i < len(text):
                ch = text[i]
                nxt = text[i + 1] if i + 1 < len(text) else ""

                if in_line_comment:
                    if ch == "\n":
                        in_line_comment = False
                    i += 1
                    continue
                if in_block_comment:
                    if ch == "*" and nxt == "/":
                        in_block_comment = False
                        i += 2
                        continue
                    i += 1
                    continue
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                    i += 1
                    continue
                if in_char:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == "'":
                        in_char = False
                    i += 1
                    continue

                if ch == "/" and nxt == "/":
                    in_line_comment = True
                    i += 2
                    continue
                if ch == "/" and nxt == "*":
                    in_block_comment = True
                    i += 2
                    continue
                if ch == '"':
                    in_string = True
                    i += 1
                    continue
                if ch == "'":
                    in_char = True
                    i += 1
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        while end < len(text) and text[end] in " \t\r\n":
                            end += 1
                        return start, end
                i += 1
        pos = text.find(needle, pos + len(needle))
    return None


def remove_functions_and_collect(text: str) -> tuple[str, list[str]]:
    moved: list[tuple[int, int, str]] = []
    search_text = text
    for name in FUNCTIONS_TO_MOVE:
        bounds = find_function_bounds(search_text, name)
        if bounds is None:
            raise RuntimeError(f"Could not find function body for {name} in ImageGenerationPage.cpp")
        start, end = bounds
        moved.append((start, end, search_text[start:end].strip()))
        search_text = search_text[:start] + search_text[end:]

    return search_text, [body for _, _, body in moved]


def ensure_include(text: str) -> str:
    include = '#include "assets/AssetCatalogScanner.h"'
    if include in text:
        return text
    anchor = '#include "assets/CatalogPickerDialog.h"'
    if anchor not in text:
        raise RuntimeError("Could not find CatalogPickerDialog include anchor")
    return text.replace(anchor, anchor + "\n" + include, 1)


def ensure_using_lines(text: str) -> str:
    anchor = "using spellvision::assets::CatalogEntry;"
    if anchor not in text:
        raise RuntimeError("Could not find CatalogEntry using anchor")
    missing = [line for line in USING_LINES if line not in text]
    if not missing:
        return text
    insert = anchor + "\n" + "\n".join(missing)
    return text.replace(anchor, insert, 1)


def write_scanner_cpp(function_bodies: list[str]) -> None:
    SCANNER_CPP.parent.mkdir(parents=True, exist_ok=True)
    content = """#include \"AssetCatalogScanner.h\"\n\n#include <QDir>\n#include <QDirIterator>\n#include <QFileInfo>\n#include <QHash>\n#include <QJsonArray>\n#include <QJsonObject>\n#include <QSet>\n\n#include <algorithm>\n\nnamespace spellvision::assets\n{\n\n"""
    content += "\n\n".join(function_bodies)
    content += "\n\n} // namespace spellvision::assets\n"
    SCANNER_CPP.write_text(content, encoding="utf-8", newline="\n")


def patch_cmake() -> None:
    text = CMAKE_PATH.read_text(encoding="utf-8")
    if "qt_ui/assets/AssetCatalogScanner.cpp" in text:
        return
    insert = "    qt_ui/assets/AssetCatalogScanner.cpp\n    qt_ui/assets/AssetCatalogScanner.h"
    anchors = [
        "    qt_ui/assets/CatalogPickerDialog.h",
        "    qt_ui/assets/CatalogPickerDialog.cpp",
        "    qt_ui/assets/ModelStackState.h",
    ]
    for anchor in anchors:
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + insert, 1)
            CMAKE_PATH.write_text("\n".join(line.rstrip() for line in text.splitlines()) + "\n", encoding="utf-8", newline="\n")
            return
    raise RuntimeError("Could not find asset source anchor in CMakeLists.txt")


def main() -> None:
    if not CPP_PATH.exists():
        raise RuntimeError(f"Missing {CPP_PATH}")
    if not SCANNER_H.exists():
        raise RuntimeError(f"Missing {SCANNER_H}; copy the pass files before running this script")

    text = CPP_PATH.read_text(encoding="utf-8")
    if "assets/AssetCatalogScanner.h" in text and "scanVideoModelStackCatalog" not in text:
        print("Asset catalog scanner extraction already appears to be applied.")
        patch_cmake()
        return

    text = ensure_include(text)
    text = ensure_using_lines(text)
    text, function_bodies = remove_functions_and_collect(text)
    text = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
    CPP_PATH.write_text(text, encoding="utf-8", newline="\n")

    write_scanner_cpp(function_bodies)
    patch_cmake()
    print("Applied Sprint 14C Pass 13 AssetCatalogScanner extraction.")


if __name__ == "__main__":
    main()
