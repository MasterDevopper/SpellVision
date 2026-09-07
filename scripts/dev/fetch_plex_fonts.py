"""Fetch the five IBM Plex faces SpellVision bundles, plus the OFL text.

Google Fonts serves TTF instances to a legacy user agent; this box's curl cannot reach the
network but urllib can (repo memory: HF single-file pulls work the same way). Files land in
qt_ui/fonts with the names ThemeManager and SvFonts expect. Re-runnable; overwrites.
"""
from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "qt_ui" / "fonts"
UA = ("Mozilla/5.0 (Linux; U; Android 4.1.1; en-us; Nexus S Build/JRO03E) AppleWebKit/534.30 "
      "(KHTML, like Gecko) Version/4.0 Mobile Safari/534.30")
# The brief's original UA (an IE6 string) got a real response, but Google Fonts collapsed it to
# ONE weight per family (400 only) -- old IE can't do CSS font-weight synthesis reliably, so the
# service just doesn't offer the others to it. This Android 4.1 UA is the one that is old enough
# to be handed raw .ttf (no woff/woff2 wrapper) but still gets the full 400/500/600 weight set.
CSS = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600"
       "&family=IBM+Plex+Mono:wght@400;500")
OFL_URLS = (
    "https://raw.githubusercontent.com/IBM/plex/master/LICENSE.txt",
    "https://openfontlicense.org/documents/OFL.txt",
)
NAMES = {
    ("IBM Plex Sans", 400): "IBMPlexSans-Regular.ttf",
    ("IBM Plex Sans", 500): "IBMPlexSans-Medium.ttf",
    ("IBM Plex Sans", 600): "IBMPlexSans-SemiBold.ttf",
    ("IBM Plex Mono", 400): "IBMPlexMono-Regular.ttf",
    ("IBM Plex Mono", 500): "IBMPlexMono-Medium.ttf",
}
BLOCK = re.compile(
    r"font-family:\s*'([^']+)';\s*font-style:\s*normal;\s*font-weight:\s*(\d+);.*?src:\s*url\(([^)]+)\)",
    re.S,
)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    css = fetch(CSS).decode("utf-8")
    found: dict[tuple[str, int], str] = {}
    for family, weight, url in BLOCK.findall(css):
        found[(family, int(weight))] = url
    missing = [k for k in NAMES if k not in found]
    if missing:
        print("CSS did not list:", missing)
        return 2
    for key, name in NAMES.items():
        data = fetch(found[key])
        if data[:4] not in (b"\x00\x01\x00\x00", b"true") or len(data) < 50_000:
            print("not a TTF or too small:", name, data[:4], len(data))
            return 3
        (OUT / name).write_bytes(data)
        print(f"{name}  {len(data) // 1024} KB")
    licence = b""
    for url in OFL_URLS:
        try:
            licence = fetch(url)
            break
        except Exception as exc:  # noqa: BLE001 - try the next mirror
            print("licence fetch failed:", url, exc)
    if b"SIL OPEN FONT LICENSE" not in licence.upper():
        print("OFL text not obtained; supply qt_ui/fonts/OFL.txt by hand before committing")
        return 4
    (OUT / "OFL.txt").write_bytes(licence)
    (OUT / "README.md").write_text(
        "# Bundled fonts\n\n"
        "IBM Plex Sans (Regular, Medium, SemiBold) and IBM Plex Mono (Regular, Medium), "
        "licensed under the SIL Open Font License 1.1 (see OFL.txt). Fetched by "
        "`scripts/dev/fetch_plex_fonts.py`; registered at startup by `qt_ui/style/SvFonts.cpp`.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
