from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from runtime_adapters.base import AdapterExecutionError, RuntimeAdapter, RuntimeContext, RuntimeRequest, RuntimeResult


class NativeVideoAdapter(RuntimeAdapter):
    backend_kind = "native_python"

    def supports(self, request: RuntimeRequest) -> bool:
        return request.backend_kind == self.backend_kind and request.task_family == "video"

    def run(self, request: RuntimeRequest, context: RuntimeContext) -> RuntimeResult:
        entrypoint = _resolve_entrypoint(request)
        args_template = _resolve_args_template(request)
        if not entrypoint:
            raise AdapterExecutionError(
                f"Native adapter for {request.model_family} requires 'native_entrypoint' or a detectable repo script"
            )
        if not args_template:
            raise AdapterExecutionError(
                f"Native adapter for {request.model_family} requires 'native_args_template'. "
                "The official repos do not share a single stable CLI, so SpellVision keeps this explicit."
            )

        python_exe = str(request.get('python_exe') or sys.executable)
        working_dir = str(request.get('native_repo_dir') or request.get('working_dir') or context.working_dir or os.getcwd())
        mapping = _build_mapping(request)
        args = _expand_args(args_template, mapping)
        command = [python_exe, entrypoint, *args]

        context.status(f"launching native {request.model_family} runtime")
        context.progress(5, 100, f"starting {Path(entrypoint).name}")
        result = _run_external(command, working_dir, context)

        output_path = _resolve_output_path(request.output_path, result)
        if not output_path or not os.path.exists(output_path):
            raise AdapterExecutionError(f"Native runtime did not produce an output file: {output_path!r}")

        metadata_output = str(request.metadata_output or result.get('metadata_output') or '') or None
        backend_name = result.get('backend_name') or f"{request.model_family}_native"
        detected_pipeline = result.get('detected_pipeline') or f"{request.model_family}_official_repo"
        return RuntimeResult(
            ok=True,
            output=output_path,
            metadata_output=metadata_output,
            backend_name=backend_name,
            detected_pipeline=detected_pipeline,
            task_type=request.command,
            media_type=request.media_type,
            details=result,
        )


def _resolve_entrypoint(request: RuntimeRequest) -> str:
    explicit = str(request.get('native_entrypoint') or '').strip()
    if explicit:
        return explicit

    repo_dir = str(request.get('native_repo_dir') or '').strip()
    if not repo_dir:
        return ''

    family_candidates = {
        'wan': ('generate.py', 'examples/generate.py', 'app.py', 'scripts/inference.py'),
        'ltx': ('inference.py', 'scripts/inference.py', 'run.py', 'app.py'),
    }
    candidates = family_candidates.get(request.model_family, ('inference.py', 'generate.py', 'run.py'))
    for rel in candidates:
        candidate = Path(repo_dir) / rel
        if candidate.exists():
            return str(candidate)
    return ''


def _resolve_args_template(request: RuntimeRequest) -> str:
    family_key = f"{request.model_family}_args_template"
    command_key = f"{request.command}_args_template"
    return str(request.get('native_args_template') or request.get(family_key) or request.get(command_key) or '').strip()


def _build_mapping(request: RuntimeRequest) -> dict[str, object]:
    params = dict(request.params)
    return {
        'command': request.command,
        'model': request.model,
        'model_family': request.model_family,
        'output': request.output_path or '',
        'metadata_output': request.metadata_output or '',
        'prompt': params.get('prompt', ''),
        'negative_prompt': params.get('negative_prompt', ''),
        'seed': params.get('seed', ''),
        'steps': params.get('steps', ''),
        'cfg': params.get('cfg', ''),
        'width': params.get('width', ''),
        'height': params.get('height', ''),
        'fps': params.get('fps', ''),
        'num_frames': params.get('num_frames', ''),
        'duration_sec': params.get('duration_sec', ''),
        'input_image': params.get('input_image', ''),
        'input_video': params.get('input_video', ''),
        'native_repo_dir': params.get('native_repo_dir', ''),
    }


def _expand_args(template: str, mapping: dict[str, object]) -> list[str]:
    import shlex

    safe_mapping = {k: '' if v is None else str(v) for k, v in mapping.items()}
    try:
        formatted = template.format_map(_SafeFormatDict(safe_mapping))
    except Exception as exc:
        raise AdapterExecutionError(f"Failed to expand native args template: {exc}") from exc
    return shlex.split(formatted)


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return ''


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
        encoding='utf-8',
        errors='replace',
        bufsize=1,
    )

    last_json: dict[str, object] | None = None
    last_line = ''
    line_count = 0
    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            line_count += 1
            last_line = line
            if line.startswith('{') and line.endswith('}'):
                try:
                    payload = json.loads(line)
                    if isinstance(payload, dict):
                        last_json = payload
                except Exception:
                    pass
            if line_count % 25 == 0:
                context.progress(min(90, 10 + line_count // 5), 100, f'runtime log lines: {line_count}')
            context.check_cancelled()
        exit_code = proc.wait()
    except Exception:
        proc.kill()
        raise

    if exit_code != 0:
        raise AdapterExecutionError(f"Native runtime failed with exit code {exit_code}: {last_line}")

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
