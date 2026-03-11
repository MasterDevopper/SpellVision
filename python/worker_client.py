import ast
import json
import socket
import sys


def normalize_payload(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        raise ValueError("Empty payload")

    try:
        obj = json.loads(raw)
        return json.dumps(obj, ensure_ascii=False)
    except json.JSONDecodeError:
        pass

    try:
        obj = ast.literal_eval(raw)
        return json.dumps(obj, ensure_ascii=False)
    except Exception as e:
        raise ValueError(f"Invalid request payload: {raw}") from e


def main():
    raw_payload = sys.stdin.read().strip()
    if not raw_payload and len(sys.argv) > 1:
        raw_payload = sys.argv[1]

    if not raw_payload:
        print(json.dumps({"ok": False, "error": "Expected one JSON argument or stdin payload"}))
        sys.exit(2)

    try:
        payload = normalize_payload(raw_payload)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(2)

    with socket.create_connection(("127.0.0.1", 8765), timeout=120) as sock:
        sock.sendall((payload + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk

    if not data:
        print(json.dumps({"ok": False, "error": "No response from worker service"}))
        sys.exit(3)

    print(data.decode("utf-8").strip())


if __name__ == "__main__":
    main()