import json
import socket
import sys
from typing import Any

WORKER_HOST = "127.0.0.1"
WORKER_PORT = 8765
SOCKET_TIMEOUT_SEC = 120

CANONICAL_MESSAGE_TYPE = "job_update"
LEGACY_MESSAGE_TYPES = {"status", "progress", "result", "error"}
JOB_STATES = {"queued", "starting", "running", "completed", "failed", "cancelled"}


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


# Helper builders for the Sprint 7 contract. These are not yet auto-wired into
# the CLI path because the current worker service still expects command-based
# requests (for example: ping, t2i, i2i).
def build_start_job_request(command: str, **params: Any) -> dict[str, Any]:
    payload = {"command": command}
    payload.update(params)
    return payload


# Reserved for the upcoming service-side job registry work.
def build_cancel_job_request(job_id: str) -> dict[str, Any]:
    return {"action": "cancel_job", "job_id": job_id}


# Reserved for the upcoming service-side retry flow.
def build_retry_job_request(job_id: str) -> dict[str, Any]:
    return {"action": "retry_job", "job_id": job_id}



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



def normalize_worker_message(payload: dict[str, Any], last_job_id: str | None) -> tuple[dict[str, Any], str | None]:
    message_type = payload.get("type")

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



def stream_worker_messages(sock: socket.socket) -> int:
    file_obj = sock.makefile("r", encoding="utf-8", newline="\n")
    saw_line = False
    last_job_id: str | None = None

    for line in file_obj:
        text = line.rstrip("\r\n")
        if not text:
            continue

        saw_line = True

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            print(
                json.dumps(
                    {
                        "type": "client_error",
                        "ok": False,
                        "error": "Worker service returned a non-JSON line",
                        "raw_line": text,
                    }
                ),
                flush=True,
            )
            continue

        if not isinstance(payload, dict):
            print(
                json.dumps(
                    {
                        "type": "client_error",
                        "ok": False,
                        "error": "Worker service returned a non-object JSON payload",
                        "raw": payload,
                    }
                ),
                flush=True,
            )
            continue

        normalized, last_job_id = normalize_worker_message(payload, last_job_id)
        print(json.dumps(normalized), flush=True)

    if not saw_line:
        print(json.dumps({"ok": False, "error": "Worker service returned no response"}), flush=True)
        return 1

    return 0



def main() -> int:
    raw_payload = load_payload()
    if not raw_payload:
        print(json.dumps({"ok": False, "error": "No request payload provided"}), flush=True)
        return 1

    try:
        request_payload = parse_payload(raw_payload)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), flush=True)
        return 1

    try:
        with socket.create_connection((WORKER_HOST, WORKER_PORT), timeout=SOCKET_TIMEOUT_SEC) as sock:
            sock.sendall(json.dumps(request_payload).encode("utf-8") + b"\n")
            sock.shutdown(socket.SHUT_WR)
            return stream_worker_messages(sock)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
