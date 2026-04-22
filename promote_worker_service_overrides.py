from __future__ import annotations

from pathlib import Path
import re
import sys


RENAMED_MARKER = "# --- SPELLVISION PATCH OVERRIDES PROMOTED BY LEGACY RENAMES V1 ---"


def rename_first_function(text: str, old_name: str, new_name: str) -> tuple[str, bool]:
    pattern = re.compile(rf"(?m)^def\s+{re.escape(old_name)}\s*\(")
    match = pattern.search(text)
    if not match:
        return text, False

    start, end = match.span()
    replacement = f"def {new_name}("
    return text[:start] + replacement + text[end:], True


def replace_assignment(text: str, old_assignment: str, new_assignment: str) -> tuple[str, bool]:
    if old_assignment not in text:
        return text, False
    return text.replace(old_assignment, new_assignment, 1), True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python promote_worker_service_overrides.py .\\python\\worker_service.py")
        return 2

    target = Path(sys.argv[1])
    if not target.exists():
        print(f"worker_service.py not found: {target}")
        return 1

    text = target.read_text(encoding="utf-8")

    if RENAMED_MARKER in text:
        print("worker_service.py has already had the patch override redeclarations cleaned up.")
        return 0

    if "# --- SPELLVISION WAN DUAL CORE OVERRIDE V1 ---" not in text:
        print("Wan dual core override block was not found. No changes made.")
        return 1

    if "# --- SPELLVISION VIDEO METADATA FINALIZATION FIX V1 ---" not in text:
        print("Video metadata override block was not found. No changes made.")
        return 1

    backup = target.with_suffix(target.suffix + ".pre_pylance_redeclare_cleanup.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
        print(f"Backup written: {backup}")

    changes: list[str] = []

    text, changed = rename_first_function(
        text,
        "build_metadata_payload",
        "_legacy_build_metadata_payload",
    )
    if changed:
        changes.append("Renamed original build_metadata_payload -> _legacy_build_metadata_payload")

    text, changed = replace_assignment(
        text,
        "_spellvision_original_build_metadata_payload = build_metadata_payload",
        "_spellvision_original_build_metadata_payload = _legacy_build_metadata_payload",
    )
    if changed:
        changes.append("Updated metadata override to call _legacy_build_metadata_payload")

    text, changed = rename_first_function(
        text,
        "_build_native_wan_core_video_prompt",
        "_legacy_build_native_wan_core_video_prompt",
    )
    if changed:
        changes.append("Renamed original _build_native_wan_core_video_prompt -> _legacy_build_native_wan_core_video_prompt")

    text, changed = rename_first_function(
        text,
        "_build_native_split_video_prompt",
        "_legacy_build_native_split_video_prompt",
    )
    if changed:
        changes.append("Renamed original _build_native_split_video_prompt -> _legacy_build_native_split_video_prompt")

    text, changed = replace_assignment(
        text,
        "_spellvision_original_build_native_split_video_prompt = _build_native_split_video_prompt",
        "_spellvision_original_build_native_split_video_prompt = _legacy_build_native_split_video_prompt",
    )
    if changed:
        changes.append("Updated native split override to call _legacy_build_native_split_video_prompt")

    # Leave a small marker near the import section so repeated runs are idempotent.
    insert_after = "warnings.filterwarnings(\"ignore\", category=FutureWarning, module=\"diffusers\")"
    if insert_after in text:
        text = text.replace(insert_after, insert_after + "\n" + RENAMED_MARKER, 1)
    else:
        text = RENAMED_MARKER + "\n" + text

    target.write_text(text, encoding="utf-8")

    print(f"Patched: {target}")
    if changes:
        print("Changes:")
        for item in changes:
            print(f"  - {item}")
    else:
        print("No rename changes were needed, but marker was added.")

    print("Next:")
    print("  python -m py_compile .\\python\\worker_service.py")
    print("  Then reload VS Code / restart Pylance if the old diagnostics linger.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
