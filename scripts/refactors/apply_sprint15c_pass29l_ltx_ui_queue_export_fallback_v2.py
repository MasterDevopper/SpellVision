from pathlib import Path
import re

# ----------------------------
# Patch 1: ltx_prompt_api_submission.py
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

if "def _ensure_ltx_prompt_api_export_path" not in text:
    marker = "def _utc_now_iso"
    idx = text.find(marker)
    if idx < 0:
        raise SystemExit("Could not find insertion marker def _utc_now_iso.")
    text = text[:idx] + helper + text[idx:]

pattern = re.compile(
    r'(def ltx_prompt_api_gated_submission_snapshot\(\s*\n'
    r'\s*req: dict\[str, Any\] \| None = None,\s*\n'
    r'\s*runtime_status: dict\[str, Any\] \| None = None,\s*\n'
    r'\s*\) -> dict\[str, Any\]:\s*\n)'
    r'(\s*req\s*=\s*(?:req or \{\}|dict\(req or \{\}\))\s*\n)'
    r'(\s*runtime_status\s*=\s*runtime_status or \{\}\s*\n)',
    re.MULTILINE,
)

replacement = (
    r'\1'
    r'    req = dict(req or {})' + "\n"
    r'    _ensure_ltx_prompt_api_export_path(req)' + "\n"
    r'\3'
)

text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit("Could not patch ltx_prompt_api_gated_submission_snapshot request initialization.")

submission_path.write_text(text, encoding="utf-8")

# ----------------------------
# Patch 2: worker_service.py
# ----------------------------
worker_path = Path("python/worker_service.py")
text = worker_path.read_text(encoding="utf-8")

insert_after = '''    ltx_req["video_readiness_ok"] = True
'''

fallback_block = '''    # Sprint 15C Pass 29L:
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

if "Sprint 15C Pass 29L" not in text:
    if insert_after not in text:
        raise SystemExit("Could not find worker_service.py insertion point.")
    text = text.replace(insert_after, insert_after + "\n" + fallback_block, 1)

worker_path.write_text(text, encoding="utf-8")

print("Applied Sprint 15C Pass 29L v2: LTX UI queue Prompt API export fallback.")
