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
JOB_STATES = {"queued", "starting", "running", "completed", "failed", "cancelled"}
TERMINAL_JOB_STATES = {"completed", "failed", "cancelled"}

CONTROL_COMMANDS = {"queue_status", "enqueue", "enqueue_job", "remove_queue_item", "clear_pending_queue", "cancel_queue_item", "cancel_active_queue_item", "retry_queue_item"}
STREAMING_COMMANDS = {"t2i", "i2i", "ping"}


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
