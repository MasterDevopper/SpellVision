from pathlib import Path
import re

# ----------------------------
# Patch 1: ltx_prompt_api_submission.py
# Add default Prompt API export fallback inside the submission route itself.
# ----------------------------
submission_path = Path("python/ltx_prompt_api_submission.py")
text = submission_path.read_text(encoding="utf-8")

if "import os" not in text:
    text = text.replace("import json\n", "import json\nimport os\n", 1)

helper = r'''
def _default_ltx_prompt_api_export_path() -> str:
    return str(os.environ.get(
        "SPELLVISION_LTX_PROMPT_API_EXPORT",
        r"D:\AI_ASSETS\comfy_runtime\ComfyUI\user\default\workflows\ltx_api.json",
    ) or "").strip()


def _ensure_ltx_prompt_api_export_path(req: dict[str, Any]) -> None:
    explicit = str(
        req.get("prompt_api_export_path")
        or req.get("ltx_prompt_api_export_path")
        or req.get("api_workflow_path")
        or req.get("workflow_prompt_api_path")
        or ""
    ).strip()

    export_path = explicit or _default_ltx_prompt_api_export_path()
    if not export_path:
        return

    req["prompt_api_export_path"] = export_path
    req["ltx_prompt_api_export_path"] = export_path
    req["api_workflow_path"] = export_path
    req["workflow_prompt_api_path"] = export_path


'''

if "_ensure_ltx_prompt_api_export_path" not in text:
    if "LTX_VIDEO_OUTPUT_EXTENSIONS" in text:
        marker = "def _ltx_output_media_type"
        idx = text.find(marker)
        if idx < 0:
            raise SystemExit("Could not find _ltx_output_media_type marker.")
        text = text[:idx] + helper + text[idx:]
    else:
        marker = "def _utc_now_iso"
        idx = text.find(marker)
        if idx < 0:
            raise SystemExit("Could not find _utc_now_iso marker.")
        text = text[:idx] + helper + text[idx:]

old = '''def ltx_prompt_api_gated_submission_snapshot(
    req: dict[str, Any] | None = None,
    runtime_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    req = req or {}
    runtime_status = runtime_status or {}
'''

new = '''def ltx_prompt_api_gated_submission_snapshot(
    req: dict[str, Any] | None = None,
    runtime_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    req = dict(req or {})
    _ensure_ltx_prompt_api_export_path(req)
    runtime_status = runtime_status or {}
'''

if old not in text:
    raise SystemExit("Could not find ltx_prompt_api_gated_submission_snapshot start block.")

text = text.replace(old, new, 1)
submission_path.write_text(text, encoding="utf-8")

# ----------------------------
# Patch 2: worker_service.py
# Preserve/fill Prompt API export path during queued LTX normalization.
# ----------------------------
worker_path = Path("python/worker_service.py")
text = worker_path.read_text(encoding="utf-8")

needle = '''    ltx_req["video_uses_prompt_api_backend"] = True
    ltx_req["video_validated_prompt_api_family"] = True
    ltx_req["video_validated_backend"] = True
    ltx_req["video_readiness_ok"] = True
'''

replacement = '''    ltx_req["video_uses_prompt_api_backend"] = True
    ltx_req["video_validated_prompt_api_family"] = True
    ltx_req["video_validated_backend"] = True
    ltx_req["video_readiness_ok"] = True

    # Sprint 15C Pass 29L:
    # Qt may queue an LTX request without carrying the Prompt API export path.
    # The LTX backend is Prompt-API-template based, so preserve any explicit
    # path and otherwise fall back to the standard exported LTX API graph.
    ltx_prompt_api_export_path = str(
        ltx_req.get("prompt_api_export_path")
        or ltx_req.get("ltx_prompt_api_export_path")
        or ltx_req.get("api_workflow_path")
        or ltx_req.get("workflow_prompt_api_path")
        or os.environ.get(
            "SPELLVISION_LTX_PROMPT_API_EXPORT",
            r"D:\\AI_ASSETS\\comfy_runtime\\ComfyUI\\user\\default\\workflows\\ltx_api.json",
        )
        or ""
    ).strip()
    if ltx_prompt_api_export_path:
        ltx_req["prompt_api_export_path"] = ltx_prompt_api_export_path
        ltx_req["ltx_prompt_api_export_path"] = ltx_prompt_api_export_path
        ltx_req["api_workflow_path"] = ltx_prompt_api_export_path
        ltx_req["workflow_prompt_api_path"] = ltx_prompt_api_export_path
'''

if needle not in text:
    raise SystemExit("Could not find LTX normalization insertion point in worker_service.py")

text = text.replace(needle, replacement, 1)
worker_path.write_text(text, encoding="utf-8")

print("Applied Sprint 15C Pass 29L: LTX UI queue Prompt API export fallback.")
