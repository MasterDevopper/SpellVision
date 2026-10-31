"""Pack the heavy engines into <2GB zip parts. MSI cannot hold 65536+ components or a 2GB file."""
from __future__ import annotations

import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAYLOAD = REPO / "build" / "installer" / "payload"
OUT = REPO / "build" / "installer" / "msi-root" / "parts"
LIMIT = 1400 * 1024 * 1024
ROOTS = (".venv", "python-runtime", "engines")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("engines-*.zip"):
        old.unlink()
    index = 1
    current: zipfile.ZipFile | None = None
    written = 0

    def rotate() -> zipfile.ZipFile:
        nonlocal index, current, written
        if current is not None:
            current.close()
        path = OUT / f"engines-{index:02d}.zip"
        index += 1
        written = 0
        print(f"part {path.name}", flush=True)
        current = zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED, allowZip64=True)
        return current

    zf = rotate()
    for root_name in ROOTS:
        root = PAYLOAD / root_name
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(PAYLOAD).as_posix()
            size = path.stat().st_size
            if written and written + size > LIMIT:
                zf = rotate()
            zf.write(path, rel)
            written += size
    if current is not None:
        current.close()
    parts = sorted(OUT.glob("engines-*.zip"))
    print(f"parts {len(parts)}", flush=True)
    for part in parts:
        print(f"{part.name} {part.stat().st_size}", flush=True)
    return 0 if parts else 1


if __name__ == "__main__":
    raise SystemExit(main())
