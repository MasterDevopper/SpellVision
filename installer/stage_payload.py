"""Stage the hybrid installer payload. Engines in the box. Models stay where they are.

Copies the layout that produced the known-good SpellVision.exe generate:
  SpellVision.exe + Qt runtime (windeployqt, applied later if the Release exe exists)
  python/                         worker sources (sentinel: python/worker_client.py)
  .venv/                          worker interpreter
  python-runtime/                 the CPython 3.12.10 those venvs were created against
  engines/ComfyUI/                live ComfyUI v0.34.0, without renders, inputs, or git history
  engines/.venv/                  isolated Comfy interpreter (kornia pin lives here)
  NOTICE

Does not copy checkpoints, VAEs, text encoders, clip-vision, or LoRAs. The managed
extra_model_paths block is stripped so a stranger machine is not pointed at this one's D:.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAYLOAD = REPO / "build" / "installer" / "payload"
COMFY_ROOT = Path(r"C:/sv_comfynext_v034/ComfyUI")
COMFY_VENV = Path(r"C:/sv_comfynext_v034/.venv")
WORKER_VENV = REPO / ".venv"
BASE_PYTHON = Path(r"C:/Program Files/Python312")
QT_BIN = Path(r"C:/Qt/6.10.2/msvc2022_64/bin")

SKIP_DIR_NAMES = {"__pycache__", ".git", "output", "input", "temp", "user", "LLM"}


def ignore(directory: str, names: list[str]) -> set[str]:
    skipped = set()
    for name in names:
        if name in SKIP_DIR_NAMES or name.endswith(".pyc"):
            skipped.add(name)
    return skipped


def copy_tree(src: Path, dst: Path) -> None:
    print(f"copy {src} -> {dst}", flush=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore, symlinks=False)


def strip_model_paths(comfy: Path) -> None:
    # The live yaml names this machine's D: and F: libraries. Those are not part of the
    # payload. First-run writes the managed block from the folder the user picks.
    yaml = comfy / "extra_model_paths.yaml"
    yaml.write_text(
        "# Models are not in the installer.\n"
        "# SpellVision writes the managed block here on launch, from the library folder\n"
        "# chosen in first-run. Checkpoints, VAEs, text encoders, and LoRAs stay out of the box.\n",
        encoding="utf-8",
    )


def deploy_app() -> None:
    exe = REPO / "build" / "Release" / "SpellVision.exe"
    if not exe.is_file():
        print("Release SpellVision.exe is not built yet; app files skipped", flush=True)
        return
    windeployqt = QT_BIN / "windeployqt.exe"
    print(f"windeployqt {exe}", flush=True)
    subprocess.check_call(
        [str(windeployqt), "--release", "--no-translations", "--dir", str(PAYLOAD), str(exe)],
    )
    shutil.copy2(exe, PAYLOAD / "SpellVision.exe")
    brand_src = REPO / "qt_ui" / "brand" / "spellvision_open.mp4"
    if brand_src.is_file():
        brand = PAYLOAD / "brand"
        brand.mkdir(parents=True, exist_ok=True)
        shutil.copy2(brand_src, brand / brand_src.name)
    notice = REPO / "NOTICE"
    if notice.is_file():
        shutil.copy2(notice, PAYLOAD / "NOTICE")


def main() -> int:
    PAYLOAD.mkdir(parents=True, exist_ok=True)
    copy_tree(REPO / "python", PAYLOAD / "python")
    copy_tree(WORKER_VENV, PAYLOAD / ".venv")
    copy_tree(BASE_PYTHON, PAYLOAD / "python-runtime")
    copy_tree(COMFY_ROOT, PAYLOAD / "engines" / "ComfyUI")
    copy_tree(COMFY_VENV, PAYLOAD / "engines" / ".venv")
    strip_model_paths(PAYLOAD / "engines" / "ComfyUI")
    deploy_app()
    sentinel = PAYLOAD / "python" / "worker_client.py"
    main_py = PAYLOAD / "engines" / "ComfyUI" / "main.py"
    print(f"sentinel {sentinel.is_file()} comfy {main_py.is_file()}", flush=True)
    return 0 if sentinel.is_file() and main_py.is_file() else 1


if __name__ == "__main__":
    sys.exit(main())
