import json
import socket
import sys


def load_payload() -> str:
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:]).strip()
    return sys.stdin.read().strip()


def main() -> int:
    payload = load_payload()
    if not payload:
        print(json.dumps({"ok": False, "error": "No request payload provided"}), flush=True)
        return 1

    try:
        json.loads(payload)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"Invalid request payload: {exc.msg}"}), flush=True)
        return 1

    try:
        with socket.create_connection(("127.0.0.1", 8765), timeout=120) as sock:
            sock.sendall(payload.encode("utf-8") + b"\n")
            sock.shutdown(socket.SHUT_WR)

            file_obj = sock.makefile("r", encoding="utf-8", newline="\n")
            saw_line = False

            for line in file_obj:
                text = line.rstrip("\r\n")
                if text:
                    print(text, flush=True)
                    saw_line = True

            if not saw_line:
                print(json.dumps({"ok": False, "error": "Worker service returned no response"}), flush=True)
                return 1

    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), flush=True)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())