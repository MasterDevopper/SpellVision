"""Render the model registry's licence table into the C++ header the Qt badge path reads.

Why a generated file rather than a worker round trip
----------------------------------------------------

The badge is painted by ``ModelCardDelegate`` over a card grid ``ModelManagerPage`` built from a
disk scan, on a page that opens before -- and, in a standalone launch, without -- any worker. A
licence answer that arrives asynchronously is an answer that is absent exactly when the grid first
paints, and an absent non-commercial badge is the failure mode Doc 50 rule 4 is about: it looks
correct while being wrong, and it under-reports, which is the dangerous direction.

So the table ships in the binary. That makes it a second copy of the registry, which Doc 50 rule 5
permits only in the layering case and only ``pinned together with a test``:
``tests/test_family_license_surfaced.py`` re-renders this file on every pytest run and fails on any
difference, so the copy cannot drift from ``python/model_registry.py``.

What it replaces
----------------

``qt_ui/assets/FamilyLicense.h`` used to answer the licence question with

    return !(hay.contains("anima") || hay.contains("hunyuan"));

-- two family names hardcoded in C++, matched as substrings. That is wrong in both directions. It
false-POSITIVES on animagine / animatediff / animation, the exact decoy collision the anima spec's
own comment in model_registry says its narrow aliases exist to avoid; and it silently answers
"commercial use is fine" for any future non-commercial family the registry gains, with no test
anywhere that would notice.

Usage
-----

    python scripts/dev/generate_family_license_table.py            # write
    python scripts/dev/generate_family_license_table.py --check    # exit 1 if stale
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "qt_ui" / "assets" / "FamilyLicenseTable.h"

sys.path.insert(0, str(ROOT / "python"))


def _cxx_string(value: str) -> str:
    """A C++ string literal for ``value``.

    Escaped by hand rather than through ``json.dumps``: JSON escapes non-ASCII as ``\\uXXXX``, which
    is a valid C++ escape with a *different* meaning inside a narrow string literal, and the licence
    notes are prose that may grow a dash or a quote at any time.
    """
    out = []
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) > 0x7E:
            # UTF-8 bytes, spelled explicitly. A raw non-ASCII byte in a header is at the mercy of
            # MSVC's source charset detection.
            out.extend("\\x%02X" % b for b in ch.encode("utf-8"))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def render() -> str:
    from model_registry import family_license_catalog

    rows = family_license_catalog()
    lines = [
        "#pragma once",
        "",
        "// GENERATED FILE -- DO NOT EDIT BY HAND.",
        "//",
        "// Rendered from MODEL_FAMILIES in python/model_registry.py by",
        "//     scripts/dev/generate_family_license_table.py",
        "// and re-rendered + compared on every pytest run by tests/test_family_license_surfaced.py,",
        "// so this copy cannot drift from the registry. Edit the registry, then regenerate.",
        "//",
        "// It exists because the model card grid is built from a disk scan and paints before any",
        "// worker round trip could answer; a licence badge that arrives late is a licence badge that",
        "// is absent when it matters. The predecessor of this table was two family names hardcoded in",
        "// C++ and matched as SUBSTRINGS -- true of animagine, animatediff and animation, and silently",
        "// false for any non-commercial family the registry gains after it was written.",
        "//",
        "// `aliases` is pipe-separated, and lookup is by EXACT key or EXACT alias (see FamilyLicense.cpp),",
        "// mirroring resolve_model_capabilities. Never by substring: that is the defect this replaces.",
        "",
        "namespace spellvision::assets::generated",
        "{",
        "",
        "struct FamilyLicenseRow",
        "{",
        "    const char *key;",
        "    const char *aliases;      // pipe-separated, may be empty",
        "    bool commercialUse;",
        "    const char *licenseNote;  // may be empty",
        "};",
        "",
        "inline constexpr FamilyLicenseRow kFamilyLicenseTable[] = {",
    ]
    for row in rows:
        lines.append("    {%s, %s, %s, %s}," % (
            _cxx_string(str(row["key"])),
            _cxx_string("|".join(str(a) for a in row["aliases"])),
            "true" if row["commercial_use"] else "false",
            _cxx_string(str(row["license_note"])),
        ))
    lines += [
        "};",
        "",
        "// The row a family key that is in no row falls back to. The registry answers an unrecognised",
        "// family with MODEL_FAMILIES[\"unknown\"] (resolve_model_capabilities), so C++ carries no",
        "// default of its own -- it uses the registry's.",
        "inline constexpr const char *kFamilyLicenseFallbackKey = \"unknown\";",
        "",
        "} // namespace spellvision::assets::generated",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if the generated header is stale, and write nothing")
    args = parser.parse_args(argv)

    rendered = render()
    current = HEADER.read_text(encoding="utf-8") if HEADER.exists() else None
    if args.check:
        if current == rendered:
            print("up to date: %s" % HEADER)
            return 0
        print("STALE: %s -- rerun scripts/dev/generate_family_license_table.py" % HEADER,
              file=sys.stderr)
        return 1
    if current == rendered:
        print("unchanged: %s" % HEADER)
        return 0
    HEADER.parent.mkdir(parents=True, exist_ok=True)
    HEADER.write_text(rendered, encoding="utf-8")
    print("wrote %s" % HEADER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
