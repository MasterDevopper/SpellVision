from __future__ import annotations

from pathlib import Path
import sys


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if old not in text:
        print(f"[skip] pattern not found: {label}")
        return text, False
    return text.replace(old, new, 1), True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_sprint13_pass3_pylance_fix.py .\\python\\worker_service.py")
        return 2

    target = Path(sys.argv[1])
    if not target.exists():
        print(f"worker_service.py not found: {target}")
        return 1

    text = target.read_text(encoding="utf-8")
    backup = target.with_suffix(target.suffix + ".pre_pass3_pylance_fix.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
        print(f"Backup written: {backup}")

    changed_any = False

    old_settings = '''def _spellvision_teacache_settings(req: dict[str, Any]) -> dict[str, Any]:
    accel = req.get("video_acceleration") if isinstance(req.get("video_acceleration"), dict) else {}
    profile = str(req.get("teacache_profile") or accel.get("profile") or "off").strip().lower() or "off"
    model_type = str(req.get("teacache_model_type") or accel.get("model_type") or "wan2.1_t2v_14b").strip() or "wan2.1_t2v_14b"
    cache_device = str(req.get("teacache_cache_device") or accel.get("cache_device") or "cpu").strip().lower() or "cpu"
    if cache_device not in {"cpu", "cuda"}:
        cache_device = "cpu"
    rel_l1 = _spellvision_clamped_float(req.get("teacache_rel_l1_thresh", accel.get("rel_l1_thresh", 0.20)), 0.20, 0.0, 2.0)
    start = _spellvision_clamped_float(req.get("teacache_start_percent", accel.get("start_percent", 0.0)), 0.0, 0.0, 1.0)
    end = _spellvision_clamped_float(req.get("teacache_end_percent", accel.get("end_percent", 1.0)), 1.0, 0.0, 1.0)
'''

    new_settings = '''def _spellvision_teacache_settings(req: dict[str, Any]) -> dict[str, Any]:
    raw_accel = req.get("video_acceleration")
    accel: dict[str, Any] = raw_accel if isinstance(raw_accel, dict) else {}

    profile = str(req.get("teacache_profile") or accel.get("profile") or "off").strip().lower() or "off"
    model_type = str(req.get("teacache_model_type") or accel.get("model_type") or "wan2.1_t2v_14b").strip() or "wan2.1_t2v_14b"
    cache_device = str(req.get("teacache_cache_device") or accel.get("cache_device") or "cpu").strip().lower() or "cpu"
    if cache_device not in {"cpu", "cuda"}:
        cache_device = "cpu"

    rel_l1 = _spellvision_clamped_float(
        req.get("teacache_rel_l1_thresh", accel.get("rel_l1_thresh", 0.20)),
        0.20,
        0.0,
        2.0,
    )
    start = _spellvision_clamped_float(
        req.get("teacache_start_percent", accel.get("start_percent", 0.0)),
        0.0,
        0.0,
        1.0,
    )
    end = _spellvision_clamped_float(
        req.get("teacache_end_percent", accel.get("end_percent", 1.0)),
        1.0,
        0.0,
        1.0,
    )
'''

    text, changed = replace_once(text, old_settings, new_settings, "TeaCache settings typed accel guard")
    changed_any = changed_any or changed

    old_route = '''    # Route downstream model consumers through TeaCache. Leave the TeaCache node's own input untouched.
    for node_id, node in prompt.items():
        if str(node_id).startswith("tc_") or not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for input_name, value in list(inputs.items()):
            if not (isinstance(value, list) and len(value) >= 2):
                continue
            source_id = str(value[0])
            tea_node_id = inserted.get(source_id)
            if not tea_node_id:
                continue
            if input_name not in {"model", "diffusion_model"}:
                continue
            inputs[input_name] = [tea_node_id, value[1]]
'''

    new_route = '''    # Route downstream model consumers through TeaCache. Leave the TeaCache node's own input untouched.
    for node_id, node in prompt.items():
        if str(node_id).startswith("tc_") or not isinstance(node, dict):
            continue

        node_inputs_any = node.get("inputs")
        if not isinstance(node_inputs_any, dict):
            continue

        node_inputs: dict[str, Any] = node_inputs_any
        for input_name, value in list(node_inputs.items()):
            if not (isinstance(value, list) and len(value) >= 2):
                continue

            source_id = str(value[0])
            tea_node_id = inserted.get(source_id)
            if not tea_node_id:
                continue

            if input_name not in {"model", "diffusion_model"}:
                continue

            node_inputs[input_name] = [tea_node_id, value[1]]
'''

    text, changed = replace_once(text, old_route, new_route, "TeaCache prompt routing typed node_inputs guard")
    changed_any = changed_any or changed

    if not changed_any:
        print("No changes made. The file may already be patched or the surrounding code differs.")
        return 1

    target.write_text(text, encoding="utf-8")
    print(f"Patched: {target}")
    print("Next:")
    print("  python -m py_compile .\\python\\worker_service.py")
    print("  Reload VS Code/Pylance if stale diagnostics remain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
