from pathlib import Path
import re

path = Path("python/ltx_prompt_api_adapter.py")
text = path.read_text(encoding="utf-8")

old_func = re.search(
    r"def _minimal_prompt_api_preview\(prompt_api_export: dict\[str, Any\], smoke_request: dict\[str, Any\]\) -> tuple\[dict\[str, Any\], list\[str\], list\[dict\[str, Any\]\]\]:.*?\n\n\ndef ltx_prompt_api_conversion_adapter_snapshot",
    text,
    flags=re.DOTALL,
)

if not old_func:
    raise SystemExit("Could not find _minimal_prompt_api_preview block.")

new_func = r'''def _minimal_prompt_api_preview(prompt_api_export: dict[str, Any], smoke_request: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    if not _is_prompt_api_graph(prompt_api_export):
        return {}, ["prompt_api_graph"], []

    preview = copy.deepcopy(prompt_api_export)
    mutation_preview: list[dict[str, Any]] = []
    unresolved: list[str] = []

    def node_title(node: dict[str, Any]) -> str:
        meta = node.get("_meta")
        if not isinstance(meta, dict):
            return ""
        return str(meta.get("title") or "")

    def set_input(node_id: str, role: str, input_key: str, value: Any, confidence: str = "high") -> bool:
        node = preview.get(str(node_id))
        if not isinstance(node, dict):
            return False

        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            return False

        old_value = inputs.get(input_key)
        inputs[input_key] = value
        mutation_preview.append(
            {
                "role": role,
                "node_id": str(node_id),
                "class_type": str(node.get("class_type") or ""),
                "source": "inputs",
                "input_key": input_key,
                "old_value_preview": str(old_value)[:120],
                "target_value": value,
                "confidence": confidence,
                "safe_to_mutate": True,
            }
        )
        return True

    def find_clip_text_node(title_token: str) -> str:
        token = title_token.lower()
        for node_id, node in preview.items():
            if not isinstance(node, dict):
                continue

            if str(node.get("class_type") or "") != "CLIPTextEncode":
                continue

            if token in node_title(node).lower():
                return str(node_id)

        return ""

    def find_first_node(class_tokens: tuple[str, ...], input_key: str) -> str:
        for node_id, node in preview.items():
            if not isinstance(node, dict):
                continue

            class_type = str(node.get("class_type") or "")
            if not any(token.lower() in class_type.lower() for token in class_tokens):
                continue

            inputs = node.get("inputs")
            if isinstance(inputs, dict) and input_key in inputs:
                return str(node_id)

        return ""

    positive_node_id = find_clip_text_node("positive")
    negative_node_id = find_clip_text_node("negative")

    if not positive_node_id or not set_input(positive_node_id, "prompt", "text", smoke_request.get("prompt", "")):
        unresolved.append("prompt")

    if not negative_node_id or not set_input(negative_node_id, "negative_prompt", "text", smoke_request.get("negative_prompt", "")):
        unresolved.append("negative_prompt")

    simple_roles = [
        ("seed", ("RandomNoise",), "noise_seed", smoke_request.get("seed")),
        ("steps", ("LTXVScheduler",), "steps", smoke_request.get("steps")),
        ("cfg", ("CFGGuider",), "cfg", smoke_request.get("cfg")),
        ("width", ("EmptyLTXVLatentVideo",), "width", smoke_request.get("width")),
        ("height", ("EmptyLTXVLatentVideo",), "height", smoke_request.get("height")),
        ("frames", ("EmptyLTXVLatentVideo",), "length", smoke_request.get("frames")),
    ]

    for role, class_tokens, input_key, value in simple_roles:
        node_id = find_first_node(class_tokens, input_key)
        if not node_id or not set_input(node_id, role, input_key, value, confidence="medium"):
            unresolved.append(role)

    return preview, unresolved, mutation_preview


def ltx_prompt_api_conversion_adapter_snapshot'''

text = text[:old_func.start()] + new_func + text[old_func.end():]

text = text.replace(
    '''    if req.get("submit") or req.get("execute") or req.get("submit_to_comfy"):
        blocked_submit_reasons.append("submission_intentionally_blocked_in_pass7")

    submission_status = "prompt_api_export_validated" if using_prompt_export else "adapter_preview_requires_prompt_api_export"
    adapter_status = "prompt_api_export_ready" if using_prompt_export else "ui_graph_adapter_plan_ready"
''',
    '''    requested_submit = bool(req.get("submit") or req.get("execute") or req.get("submit_to_comfy"))
    prompt_preview_has_positive_prompt = bool(
        isinstance(prompt_preview, dict)
        and isinstance(prompt_preview.get("2483"), dict)
        and isinstance(prompt_preview["2483"].get("inputs"), dict)
        and str(prompt_preview["2483"]["inputs"].get("text") or "").strip()
    )
    safe_to_submit = bool(
        using_prompt_export
        and bool(graph.get("gate_passed", False))
        and not export_unresolved
        and not blocked_submit_reasons
        and prompt_preview_has_positive_prompt
    )

    submission_status = "safe_prompt_api_payload_validated" if safe_to_submit else (
        "prompt_api_export_validated" if using_prompt_export else "adapter_preview_requires_prompt_api_export"
    )
    adapter_status = "safe_prompt_api_payload_ready" if safe_to_submit else (
        "prompt_api_export_ready" if using_prompt_export else "ui_graph_adapter_plan_ready"
    )
'''
)

text = text.replace(
    '''        "safe_to_submit": False,''',
    '''        "safe_to_submit": safe_to_submit,''',
    1
)

text = text.replace(
    '''        "requested_submit": bool(req.get("submit") or req.get("execute") or req.get("submit_to_comfy")),''',
    '''        "requested_submit": requested_submit,''',
)

text = text.replace(
    '''        safe_to_submit=False,''',
    '''        safe_to_submit=safe_to_submit,''',
)

text = text.replace(
    '''        "This pass creates the LTX Prompt API conversion adapter only; it does not submit to ComfyUI.",''',
    '''        "This pass validates a safe LTX Prompt API payload only; it does not submit to ComfyUI.",'''
)

path.write_text(text, encoding="utf-8")
print("Patched Sprint 15C Pass 8 safe normalization validator.")
