from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from model_registry import detect_model_reference
from model_sources import materialize_request_assets
from runtime_adapters.base import AdapterExecutionError, RuntimeAdapter, RuntimeContext, RuntimeRequest, RuntimeResult


class DiffusersAdapter(RuntimeAdapter):
    backend_kind = "diffusers"

    def supports(self, request: RuntimeRequest) -> bool:
        return request.backend_kind == self.backend_kind

    def run(self, request: RuntimeRequest, context: RuntimeContext) -> RuntimeResult:
        request = _with_materialized_assets(request)
        reference = detect_model_reference(request.model)
        context.status(f"preparing diffusers runtime for {request.model_family}")
        context.progress(0, 100, "validating diffusers request")
        context.check_cancelled()

        if reference.kind not in {"hf_repo", "directory", "directory_or_id"}:
            raise AdapterExecutionError(
                f"Diffusers backend expects a Hugging Face repo id or local model directory, got kind={reference.kind!r} for model={request.model!r}"
            )

        external_script = str(request.get("diffusers_entrypoint") or request.get("diffusers_script") or "").strip()
        args_template = str(request.get("diffusers_args_template") or request.get("external_args_template") or "").strip()
        if not external_script:
            raise AdapterExecutionError(
                "Direct in-process Diffusers video execution is not wired yet for this build. "
                "Provide 'diffusers_entrypoint' and 'diffusers_args_template', or use backend_kind='comfy_workflow' / 'native_python'."
            )
        if not args_template:
            raise AdapterExecutionError("Diffusers adapter requires 'diffusers_args_template' when using an external entrypoint")

        python_exe = str(request.get("python_exe") or sys.executable)
        working_dir = str(request.get("working_dir") or context.working_dir or os.getcwd())
        mapping = _build_mapping(request)
        args = _expand_args(args_template, mapping)
        command = [python_exe, external_script, *args]
        context.status(f"launching diffusers helper: {Path(external_script).name}")
        context.progress(10, 100, "starting diffusers helper")
        result = _run_external(command, working_dir, context)

        output_path = _resolve_output_path(request.output_path, result)
        if not output_path or not os.path.exists(output_path):
            raise AdapterExecutionError(f"Diffusers helper did not produce an output file: {output_path!r}")

        metadata_output = str(request.metadata_output or result.get("metadata_output") or "") or None
        return RuntimeResult(
            ok=True,
            output=output_path,
            metadata_output=metadata_output,
            backend_name=result.get("backend_name") or "diffusers_external",
            detected_pipeline=result.get("detected_pipeline") or f"{request.model_family}_diffusers",
            task_type=request.command,
            media_type=request.media_type,
            details=result,
        )


def _build_mapping(request: RuntimeRequest) -> dict[str, object]:
    params = dict(request.params)
    return {
        "command": request.command,
        "model": request.model,
        "model_family": request.model_family,
        "output": request.output_path or "",
        "lora": params.get("lora", ""),
        "loras_json": json.dumps(params.get("loras_resolved", params.get("loras", []))),
        "metadata_output": request.metadata_output or "",
        "prompt": params.get("prompt", ""),
        "negative_prompt": params.get("negative_prompt", ""),
        "seed": params.get("seed", ""),
        "steps": params.get("steps", ""),
        "cfg": params.get("cfg", ""),
        "width": params.get("width", ""),
        "height": params.get("height", ""),
        "fps": params.get("fps", ""),
        "num_frames": params.get("num_frames", ""),
        "duration_sec": params.get("duration_sec", ""),
        "input_image": params.get("input_image", ""),
        "input_video": params.get("input_video", ""),
    }


def _expand_args(template: str, mapping: dict[str, object]) -> list[str]:
    import shlex

    safe_mapping = {k: "" if v is None else str(v) for k, v in mapping.items()}
    try:
        formatted = template.format_map(_SafeFormatDict(safe_mapping))
    except Exception as exc:
        raise AdapterExecutionError(f"Failed to expand diffusers args template: {exc}") from exc
    return shlex.split(formatted)


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _run_external(command: list[str], working_dir: str, context: RuntimeContext) -> dict[str, object]:
    env = os.environ.copy()
    if context.env:
        env.update(context.env)

    proc = subprocess.Popen(
        command,
        cwd=working_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    last_json: dict[str, object] | None = None
    last_line = ""
    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            last_line = line
            if line.startswith('{') and line.endswith('}'):
                try:
                    payload = json.loads(line)
                    if isinstance(payload, dict):
                        last_json = payload
                except Exception:
                    pass
            context.check_cancelled()
        exit_code = proc.wait()
    except Exception:
        proc.kill()
        raise

    if exit_code != 0:
        raise AdapterExecutionError(f"Diffusers helper failed with exit code {exit_code}: {last_line}")

    result = dict(last_json or {})
    if last_line and 'last_line' not in result:
        result['last_line'] = last_line
    return result


def _resolve_output_path(requested_output: str | None, result: dict[str, object]) -> str | None:
    explicit = str(result.get('output') or result.get('video_path') or result.get('image_path') or '').strip()
    if explicit:
        if requested_output and os.path.abspath(explicit) != os.path.abspath(requested_output):
            os.makedirs(os.path.dirname(requested_output), exist_ok=True)
            shutil.copy2(explicit, requested_output)
            return requested_output
        return explicit
    return requested_output
