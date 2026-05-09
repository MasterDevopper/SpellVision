from pathlib import Path
import re

path = Path("python/worker_service.py")
doc_path = Path("docs/sprints/SPRINT15C_PASS29H_PRESERVE_LTX_DISPATCH_THROUGH_QUEUE_README.md")
script_path = Path("scripts/refactors/apply_sprint15c_pass29h_preserve_ltx_dispatch_through_queue.py")

text = path.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# 1) Insert dispatch helpers before _video_request_command.
# ----------------------------------------------------------------------

helper_block = r'''
LTX_PROMPT_API_DISPATCH_COMMANDS = {
    "ltx_prompt_api_gated_submission",
    "ltx_prompt_api_submit",
    "ltx_submit_prompt_api",
    "ltx_prompt_api_submit_and_capture",
    "ltx_prompt_api_submit_wait",
    "video_family_prompt_api_gated_submission",
}

QUEUE_DISPLAY_COMMANDS = {"t2i", "i2i", "t2v", "i2v", "comfy_workflow"}


def _looks_like_ltx_prompt_api_request(req: dict[str, Any]) -> bool:
    command_values = [
        req.get("worker_command"),
        req.get("execution_command"),
        req.get("dispatch_command"),
        req.get("command"),
        req.get("task_command"),
        req.get("workflow_task_command"),
    ]

    for value in command_values:
        command = str(value or "").strip().lower()
        if command in LTX_PROMPT_API_DISPATCH_COMMANDS:
            return True

    haystack_parts = [
        req.get("video_family"),
        req.get("resolved_native_video_family"),
        req.get("model_family"),
        req.get("family"),
        req.get("video_backend_route"),
        req.get("video_backend_type"),
        req.get("video_backend_name"),
        req.get("prompt_api_export_path"),
        req.get("ltx_prompt_api_export_path"),
        req.get("api_workflow_path"),
        req.get("video_primary_model_name"),
        req.get("ltx_primary_model_name"),
        req.get("video_text_encoder_name"),
        req.get("ltx_text_encoder_name"),
        req.get("video_text_projection_name"),
        req.get("ltx_text_projection_name"),
        req.get("video_audio_vae_name"),
        req.get("ltx_audio_vae_name"),
        req.get("video_video_vae_name"),
        req.get("ltx_video_vae_name"),
        req.get("model"),
        req.get("model_display"),
    ]

    haystack = " ".join(str(part or "") for part in haystack_parts).lower()
    return "ltx" in haystack and ("prompt_api" in haystack or "ltx_api" in haystack)


def _queue_execution_command_for_request(req: dict[str, Any], display_command: str = "") -> str:
    if _looks_like_ltx_prompt_api_request(req):
        return "ltx_prompt_api_gated_submission"

    for key in ("worker_command", "execution_command", "dispatch_command", "command", "task_command", "workflow_task_command"):
        command = str(req.get(key) or "").strip().lower()
        if command:
            return command

    return str(display_command or "").strip().lower()


def _queue_display_command_for_request(req: dict[str, Any], execution_command: str, fallback: str = "") -> str:
    for key in ("queue_display_command", "source_generation_mode", "generation_mode", "source_command", "task_type", "mode", "video_request_kind"):
        command = str(req.get(key) or "").strip().lower()
        if command in QUEUE_DISPLAY_COMMANDS:
            return command

    fallback = str(fallback or "").strip().lower()
    if fallback in QUEUE_DISPLAY_COMMANDS:
        return fallback

    if execution_command in LTX_PROMPT_API_DISPATCH_COMMANDS:
        return "t2v"

    return execution_command


'''

if "LTX_PROMPT_API_DISPATCH_COMMANDS" not in text:
    marker = "def _video_request_command(req: dict[str, Any]) -> str:"
    idx = text.find(marker)
    if idx < 0:
        raise SystemExit("Could not find _video_request_command insertion point.")
    text = text[:idx] + helper_block + text[idx:]


# ----------------------------------------------------------------------
# 2) Upgrade _video_request_command to prefer dispatch command fields.
# ----------------------------------------------------------------------

video_command_pattern = re.compile(
    r'def _video_request_command\(req: dict\[str, Any\]\) -> str:\n'
    r'    return str\(\n'
    r'.*?'
    r'    \)\.strip\(\)\.lower\(\)\n',
    re.DOTALL,
)

video_command_replacement = '''def _video_request_command(req: dict[str, Any]) -> str:
    return str(
        req.get("worker_command")
        or req.get("execution_command")
        or req.get("dispatch_command")
        or req.get("command")
        or req.get("task_command")
        or req.get("task_type")
        or req.get("workflow_task_command")
        or ""
    ).strip().lower()
'''

text, count = video_command_pattern.subn(video_command_replacement, text, count=1)
if count != 1:
    raise SystemExit("Could not replace _video_request_command body.")


# ----------------------------------------------------------------------
# 3) Patch QueueManager.enqueue task/display command normalization.
# ----------------------------------------------------------------------

enqueue_start = text.find("    def enqueue(self, req")
if enqueue_start < 0:
    raise SystemExit("Could not find QueueManager.enqueue function.")

queue_status_start = text.find("    def queue_status", enqueue_start)
if queue_status_start < 0:
    raise SystemExit("Could not find QueueManager.queue_status after enqueue.")

enqueue_text = text[enqueue_start:queue_status_start]

normalization_pattern = re.compile(
    r'        task_command = str\(req\.get\("task_command"\).*?\)\.strip\(\)\n'
    r'        if task_command not in \{.*?\}:\n'
    r'            raise ValueError\(.*?\)\n\n'
    r'        job_id = f"job_\{uuid\.uuid4\(\)\.hex\[:12\]\}"\n'
    r'        queue_id = f"queue_\{uuid\.uuid4\(\)\.hex\[:12\]\}"\n'
    r'        request_snapshot = copy\.deepcopy\(req\)\n'
    r'        request_snapshot\["command"\] = task_command\n'
    r'        request_snapshot\.pop\("task_command", None\)\n',
    re.DOTALL,
)

normalization_replacement = '''        raw_task_command = str(req.get("task_command") or req.get("generation_command") or req.get("task") or "").strip().lower()
        execution_command = _queue_execution_command_for_request(req, raw_task_command)
        task_command = _queue_display_command_for_request(req, execution_command, raw_task_command)

        if task_command not in QUEUE_DISPLAY_COMMANDS:
            raise ValueError("enqueue requires display task_command of 't2i', 'i2i', 't2v', 'i2v', or 'comfy_workflow'")

        if execution_command not in QUEUE_DISPLAY_COMMANDS and execution_command not in LTX_PROMPT_API_DISPATCH_COMMANDS:
            raise ValueError(f"enqueue received unsupported execution command: {execution_command}")

        job_id = f"job_{uuid.uuid4().hex[:12]}"
        queue_id = f"queue_{uuid.uuid4().hex[:12]}"
        request_snapshot = copy.deepcopy(req)

        # Sprint 15C Pass 29H:
        # Keep the visible queue mode as T2V/I2V, but preserve the execution
        # command that the worker dispatcher must run. Previously enqueue
        # rewrote command back to t2v, causing LTX Prompt API jobs to enter
        # the native video pipeline and fail at "loading native video pipeline".
        request_snapshot["command"] = execution_command
        request_snapshot["worker_command"] = execution_command
        request_snapshot["execution_command"] = execution_command
        request_snapshot["dispatch_command"] = execution_command
        request_snapshot["task_command"] = execution_command
        request_snapshot["workflow_task_command"] = execution_command

        request_snapshot["queue_display_command"] = task_command
        request_snapshot["source_generation_mode"] = request_snapshot.get("source_generation_mode") or task_command
        request_snapshot["generation_mode"] = request_snapshot.get("generation_mode") or task_command
        request_snapshot["task_type"] = request_snapshot.get("task_type") or task_command
        request_snapshot["mode"] = request_snapshot.get("mode") or task_command

        if execution_command in LTX_PROMPT_API_DISPATCH_COMMANDS:
            request_snapshot["family"] = "ltx"
            request_snapshot["model_family"] = "ltx"
            request_snapshot["video_family"] = "ltx"
            request_snapshot["resolved_native_video_family"] = "ltx"
            request_snapshot["backend"] = "comfy_prompt_api"
            request_snapshot["video_backend_route"] = "prompt_api"
            request_snapshot["video_backend_type"] = "comfy_prompt_api"
            request_snapshot["video_backend_name"] = "LTX Prompt API"
            request_snapshot["video_uses_prompt_api_backend"] = True
            request_snapshot["video_validated_prompt_api_family"] = True
            request_snapshot["video_validated_backend"] = True
            request_snapshot["video_readiness_ok"] = True
            request_snapshot["status"] = "submitting LTX Prompt API graph"
            request_snapshot["status_text"] = "submitting LTX Prompt API graph"
'''

enqueue_text, count = normalization_pattern.subn(normalization_replacement, enqueue_text, count=1)
if count != 1:
    raise SystemExit("Could not patch QueueManager.enqueue normalization block with regex.")


# ----------------------------------------------------------------------
# 4) Ensure JobRecord executes execution_command.
# ----------------------------------------------------------------------

if "command=execution_command" not in enqueue_text:
    enqueue_text, count = re.subn(
        r'            command=task_command,',
        '            command=execution_command,',
        enqueue_text,
        count=1,
    )
    if count != 1:
        raise SystemExit("Could not patch JobRecord command assignment inside enqueue.")


text = text[:enqueue_start] + enqueue_text + text[queue_status_start:]


# ----------------------------------------------------------------------
# 5) Patch retry preservation if the old retry line still exists.
# ----------------------------------------------------------------------

if "retry_execution_command = _queue_execution_command_for_request" not in text:
    old_retry = '        retry_req["task_command"] = retry_req.get("command")'
    new_retry = '''        # Sprint 15C Pass 29H:
        # Preserve LTX Prompt API dispatch on retry instead of collapsing back
        # to native t2v/i2v.
        retry_execution_command = _queue_execution_command_for_request(retry_req, str(retry_req.get("queue_display_command") or retry_req.get("command") or ""))
        retry_display_command = _queue_display_command_for_request(retry_req, retry_execution_command, str(retry_req.get("queue_display_command") or retry_req.get("command") or ""))
        retry_req["command"] = retry_execution_command
        retry_req["worker_command"] = retry_execution_command
        retry_req["execution_command"] = retry_execution_command
        retry_req["dispatch_command"] = retry_execution_command
        retry_req["task_command"] = retry_execution_command
        retry_req["workflow_task_command"] = retry_execution_command
        retry_req["queue_display_command"] = retry_display_command'''
    if old_retry in text:
        text = text.replace(old_retry, new_retry, 1)


path.write_text(text, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text("""# Sprint 15C Pass 29H — Preserve LTX Dispatch Through Queue

## Problem

Qt generated and accepted the request as Prompt API video, but the Python queue still failed at:

`loading native video pipeline`

The enqueue path was collapsing the request back into native `t2v` by validating only display task commands and rewriting `request_snapshot["command"] = task_command`.

## Fix

Queue enqueue now separates:

- display command: `t2v` / `i2v`
- execution command: `ltx_prompt_api_gated_submission`

For LTX Prompt API requests, the queued job stores:

- `command`
- `worker_command`
- `execution_command`
- `dispatch_command`
- `task_command`
- `workflow_task_command`

as `ltx_prompt_api_gated_submission`, while preserving `queue_display_command=t2v`.

## Expected behavior

LTX queued Generate should no longer enter the native video pipeline. It should either complete through the LTX Prompt API path or fail with a specific adapter/Comfy reason.
""", encoding="utf-8")

script_path.write_text("# generated by Sprint 15C Pass 29H-R robust patch\\n", encoding="utf-8")

print("Applied Sprint 15C Pass 29H-R: LTX dispatch command preserved through queue enqueue.")
