import json
import socket
import sys
from typing import Any

WORKER_HOST = "127.0.0.1"
WORKER_PORT = 8765
SOCKET_TIMEOUT_SEC = 120

CANONICAL_MESSAGE_TYPE = "job_update"
LEGACY_MESSAGE_TYPES = {"status", "progress", "result", "error"}
QUEUE_MESSAGE_TYPES = {"queue_snapshot", "queue_ack"}
WORKFLOW_MESSAGE_TYPES = {"workflow_import_result", "workflow_profiles"}
RUNTIME_MESSAGE_TYPES = {"comfy_runtime_status", "comfy_runtime_ack", "runtime_memory_status", "runtime_memory_ack"}
MANAGER_MESSAGE_TYPES = {"comfy_manager_status", "comfy_manager_ack"}
HISTORY_MESSAGE_TYPES = {"video_history_snapshot"}
VIDEO_FAMILY_MESSAGE_TYPES = {"video_family_contracts"}
VIDEO_READINESS_MESSAGE_TYPES = {"ltx_readiness_status", "video_family_readiness_status"}
VIDEO_WORKFLOW_CONTRACT_MESSAGE_TYPES = {"ltx_test_workflow_contract", "video_family_workflow_contract"}
LTX_SMOKE_TEST_MESSAGE_TYPES = {"ltx_t2v_smoke_test", "video_family_smoke_test_route"}
LTX_MATERIALIZATION_MESSAGE_TYPES = {"ltx_workflow_materialization_dry_run", "video_family_materialization_dry_run"}
JOB_STATES = {"queued", "starting", "running", "completed", "failed", "cancelled"}
TERMINAL_JOB_STATES = {"completed", "failed", "cancelled"}

CONTROL_COMMANDS = {"queue_status", "enqueue", "enqueue_job", "remove_queue_item", "clear_pending_queue", "cancel_queue_item", "cancel_active_queue_item", "retry_queue_item", "move_queue_item_up", "move_queue_item_down", "duplicate_queue_item", "pause_queue", "resume_queue", "cancel_all_queue_items", "generate_dataset", "import_workflow", "list_workflow_profiles", "comfy_runtime_status", "ensure_comfy_runtime", "start_comfy_runtime", "stop_comfy_runtime", "restart_comfy_runtime", "comfy_manager_status", "install_comfy_manager", "install_custom_node", "install_recommended_video_nodes", "runtime_memory_status", "runtime_diagnostics", "unload_image_runtime", "unload_video_runtime", "unload_all_runtimes", "clear_cuda_cache", "video_family_contracts", "video_family_status", "ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status", "ltx_test_workflow_contract", "ltx_workflow_contract", "video_family_test_workflow_contract", "video_family_workflow_contract"}
STREAMING_COMMANDS = {"t2i", "i2i", "ping", "comfy_workflow"}


def load_payload() -> str:
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:]).strip()
    return sys.stdin.read().strip()


def parse_payload(raw_payload: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid request payload: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Request payload must be a JSON object")

    return payload


def normalize_outbound_request(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "")).strip()
    if action == "cancel_job":
        return {"command": "cancel", "job_id": payload.get("job_id", "")}
    if action == "retry_job":
        return {"command": "retry", "job_id": payload.get("job_id", "")}
    if action == "enqueue_job":
        normalized = dict(payload)
        normalized["command"] = "enqueue"
        normalized["task_command"] = payload.get("task_command") or payload.get("generation_command") or payload.get("job_command")
        normalized.pop("action", None)
        return normalized
    if action == "queue_status":
        return {"command": "queue_status"}
    if action == "remove_queue_item":
        return {"command": "remove_queue_item", "queue_item_id": payload.get("queue_item_id", "")}
    if action == "clear_pending_queue":
        return {"command": "clear_pending_queue"}
    if action == "cancel_queue_item":
        return {"command": "cancel_queue_item", "queue_item_id": payload.get("queue_item_id", "")}
    if action == "retry_queue_item":
        return {"command": "retry_queue_item", "job_id": payload.get("job_id", ""), "source_job_id": payload.get("source_job_id", "")}
    if action == "move_queue_item_up":
        return {"command": "move_queue_item_up", "queue_item_id": payload.get("queue_item_id", "")}
    if action == "move_queue_item_down":
        return {"command": "move_queue_item_down", "queue_item_id": payload.get("queue_item_id", "")}
    if action == "duplicate_queue_item":
        return {"command": "duplicate_queue_item", "queue_item_id": payload.get("queue_item_id", "")}
    if action == "pause_queue":
        return {"command": "pause_queue"}
    if action == "resume_queue":
        return {"command": "resume_queue"}
    if action == "cancel_all_queue_items":
        return {"command": "cancel_all_queue_items"}
    if action == "generate_dataset":
        normalized = dict(payload)
        normalized["command"] = "generate_dataset"
        normalized.pop("action", None)
        return normalized

    if action == "import_workflow":
        normalized = dict(payload)
        normalized["command"] = "import_workflow"
        normalized.pop("action", None)
        return normalized
    if action == "list_workflow_profiles":
        return {"command": "list_workflow_profiles"}
    if action == "comfy_runtime_status":
        return {"command": "comfy_runtime_status"}
    if action == "ensure_comfy_runtime":
        return {"command": "ensure_comfy_runtime"}
    if action == "start_comfy_runtime":
        return {"command": "start_comfy_runtime"}
    if action == "stop_comfy_runtime":
        return {"command": "stop_comfy_runtime"}
    if action == "restart_comfy_runtime":
        return {"command": "restart_comfy_runtime"}
    if action == "comfy_manager_status":
        return {"command": "comfy_manager_status"}
    if action == "install_comfy_manager":
        normalized = dict(payload)
        normalized["command"] = "install_comfy_manager"
        normalized.pop("action", None)
        return normalized
    if action == "install_custom_node":
        normalized = dict(payload)
        normalized["command"] = "install_custom_node"
        normalized.pop("action", None)
        return normalized
    if action in {"video_history_status", "history_video_status"}:
        normalized = dict(payload)
        normalized["command"] = action
        normalized.pop("action", None)
        return normalized
    if action in {"runtime_memory_status", "runtime_diagnostics", "unload_image_runtime", "unload_video_runtime", "unload_all_runtimes", "clear_cuda_cache"}:
        normalized = dict(payload)
        normalized["command"] = action
        normalized.pop("action", None)
        return normalized
    if action in {"video_family_contracts", "video_family_status"}:
        normalized = dict(payload)
        normalized["command"] = action
        normalized.pop("action", None)
        return normalized
    if action in {"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status", "ltx_test_workflow_contract", "ltx_workflow_contract", "video_family_test_workflow_contract", "video_family_workflow_contract", "ltx_t2v_smoke_test", "ltx_smoke_test_route", "video_family_smoke_test_route", "ltx_workflow_materialization_dry_run", "ltx_materialize_workflow", "ltx_t2v_materialize_dry_run", "video_family_materialization_dry_run"}:
        normalized = dict(payload)
        normalized["command"] = action
        normalized.pop("action", None)
        return normalized
    if action == "install_recommended_video_nodes":
        normalized = dict(payload)
        normalized["command"] = "install_recommended_video_nodes"
        normalized.pop("action", None)
        return normalized
    return payload


# Helper builders for the Sprint 7 contract. These are not yet auto-wired into
# the CLI path because the current worker service still expects command-based
# requests (for example: ping, t2i, i2i).
def build_start_job_request(command: str, **params: Any) -> dict[str, Any]:
    payload = {"command": command}
    payload.update(params)
    return payload


# Reserved for the upcoming service-side job registry work.
def build_cancel_job_request(job_id: str) -> dict[str, Any]:
    return {"command": "cancel", "job_id": job_id}


# Reserved for the upcoming service-side retry flow.
def build_retry_job_request(job_id: str) -> dict[str, Any]:
    return {"action": "retry_job", "job_id": job_id}


def build_enqueue_request(task_command: str, **params: Any) -> dict[str, Any]:
    payload = {"command": "enqueue", "task_command": task_command}
    payload.update(params)
    return payload


def build_queue_status_request() -> dict[str, Any]:
    return {"command": "queue_status"}


def build_remove_queue_item_request(queue_item_id: str) -> dict[str, Any]:
    return {"command": "remove_queue_item", "queue_item_id": queue_item_id}


def build_clear_pending_queue_request() -> dict[str, Any]:
    return {"command": "clear_pending_queue"}


def build_cancel_queue_item_request(queue_item_id: str) -> dict[str, Any]:
    return {"command": "cancel_queue_item", "queue_item_id": queue_item_id}


def build_retry_queue_item_request(job_id: str) -> dict[str, Any]:
    return {"command": "retry_queue_item", "job_id": job_id}


def build_move_queue_item_up_request(queue_item_id: str) -> dict[str, Any]:
    return {"command": "move_queue_item_up", "queue_item_id": queue_item_id}


def build_move_queue_item_down_request(queue_item_id: str) -> dict[str, Any]:
    return {"command": "move_queue_item_down", "queue_item_id": queue_item_id}


def build_duplicate_queue_item_request(queue_item_id: str) -> dict[str, Any]:
    return {"command": "duplicate_queue_item", "queue_item_id": queue_item_id}


def build_pause_queue_request() -> dict[str, Any]:
    return {"command": "pause_queue"}


def build_resume_queue_request() -> dict[str, Any]:
    return {"command": "resume_queue"}


def build_cancel_all_queue_items_request() -> dict[str, Any]:
    return {"command": "cancel_all_queue_items"}


def build_generate_dataset_request(**params: Any) -> dict[str, Any]:
    payload = {"command": "generate_dataset"}
    payload.update(params)
    return payload


def is_valid_job_update(payload: dict[str, Any]) -> bool:
    required = {"type", "job_id", "state", "progress", "result", "error", "timestamps"}
    if not required.issubset(payload.keys()):
        return False

    if payload.get("type") != CANONICAL_MESSAGE_TYPE:
        return False

    if payload.get("state") not in JOB_STATES:
        return False

    if not isinstance(payload.get("progress"), dict):
        return False

    timestamps = payload.get("timestamps")
    if not isinstance(timestamps, dict):
        return False

    return True





def is_terminal_message(payload: dict[str, Any]) -> bool:
    message_type = payload.get("type")
    if message_type == CANONICAL_MESSAGE_TYPE:
        return payload.get("state") in TERMINAL_JOB_STATES
    if message_type in {"result", "error"}:
        return True
    return False
def normalize_worker_message(payload: dict[str, Any], last_job_id: str | None) -> tuple[dict[str, Any], str | None]:
    message_type = payload.get("type")

    if message_type is None and "ok" in payload:
        if last_job_id and "job_id" not in payload:
            payload = dict(payload)
            payload["job_id"] = last_job_id
        return payload, payload.get("job_id", last_job_id)

    if message_type == CANONICAL_MESSAGE_TYPE:
        if is_valid_job_update(payload):
            return payload, str(payload.get("job_id") or last_job_id or "") or last_job_id

        return (
            {
                "type": "client_error",
                "ok": False,
                "error": "Worker returned malformed job_update payload",
                "raw": payload,
            },
            last_job_id,
        )

    if message_type in LEGACY_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

    if message_type in QUEUE_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

    if message_type in WORKFLOW_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

    if message_type in RUNTIME_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

    if message_type in MANAGER_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

    if message_type in HISTORY_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

    if message_type in VIDEO_FAMILY_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

    if message_type in VIDEO_READINESS_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

    if message_type in VIDEO_WORKFLOW_CONTRACT_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

    if message_type in LTX_SMOKE_TEST_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

    if message_type in LTX_MATERIALIZATION_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)

    return (
        {
            "type": "client_warning",
            "ok": True,
            "warning": "Unknown worker message type",
            "raw": payload,
            **({"job_id": last_job_id} if last_job_id else {}),
        },
        last_job_id,
    )



def stream_worker_messages(sock: socket.socket, request_command: str) -> int:
    file_obj = sock.makefile("r", encoding="utf-8", newline="\n")
    saw_line = False
    last_job_id: str | None = None
    terminal_seen = False
    expects_terminal_job_event = request_command in STREAMING_COMMANDS

    for line in file_obj:
        text = line.rstrip("\r\n")
        if not text:
            continue

        saw_line = True

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            normalized = {
                "type": "client_error",
                "ok": False,
                "error": "Worker service returned a non-JSON line",
                "raw_line": text,
                **({"job_id": last_job_id} if last_job_id else {}),
            }
            print(json.dumps(normalized), flush=True)
            continue

        if not isinstance(payload, dict):
            normalized = {
                "type": "client_error",
                "ok": False,
                "error": "Worker service returned a non-object JSON payload",
                "raw": payload,
                **({"job_id": last_job_id} if last_job_id else {}),
            }
            print(json.dumps(normalized), flush=True)
            continue

        normalized, last_job_id = normalize_worker_message(payload, last_job_id)
        terminal_seen = terminal_seen or is_terminal_message(normalized)
        print(json.dumps(normalized), flush=True)

    if not saw_line:
        print(json.dumps({"type": "client_error", "ok": False, "error": "Worker service returned no response"}), flush=True)
        return 1

    if expects_terminal_job_event and last_job_id and not terminal_seen:
        print(json.dumps({
            "type": "client_error",
            "ok": False,
            "job_id": last_job_id,
            "error": "Worker stream ended before a terminal job event was received",
        }), flush=True)
        return 1

    return 0



def main() -> int:
    raw_payload = load_payload()
    if not raw_payload:
        print(json.dumps({"ok": False, "error": "No request payload provided"}), flush=True)
        return 1

    try:
        request_payload = normalize_outbound_request(parse_payload(raw_payload))
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), flush=True)
        return 1

    try:
        with socket.create_connection((WORKER_HOST, WORKER_PORT), timeout=SOCKET_TIMEOUT_SEC) as sock:
            request_command = str(request_payload.get("command") or request_payload.get("action") or "").strip()
            sock.sendall(json.dumps(request_payload).encode("utf-8") + b"\n")
            sock.shutdown(socket.SHUT_WR)
            return stream_worker_messages(sock, request_command)
    except Exception as exc:
        print(json.dumps({"type": "client_error", "ok": False, "error": str(exc)}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

