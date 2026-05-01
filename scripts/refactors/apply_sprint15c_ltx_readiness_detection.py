from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKER_SERVICE = ROOT / "python" / "worker_service.py"
WORKER_CLIENT = ROOT / "python" / "worker_client.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def patch_worker_service() -> None:
    text = read(WORKER_SERVICE)

    if "from video_family_readiness import ltx_readiness_snapshot" not in text:
        needle = "    video_family_pipeline_candidates,\n)\nimport urllib.error"
        replacement = (
            "    video_family_pipeline_candidates,\n"
            ")\n"
            "from video_family_readiness import ltx_readiness_snapshot\n"
            "import urllib.error"
        )
        require(needle in text, "Could not find video_family_contracts import block in worker_service.py")
        text = text.replace(needle, replacement, 1)

    command_block = '''        if command in {"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
                emitter.emit({
                    "type": "video_family_readiness_status",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_readiness_family",
                    "ready_to_test": False,
                    "message": "Readiness probing is implemented for LTX in Sprint 15C Pass 2.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_readiness_snapshot(runtime_status=runtime_status))
            return
'''

    if "ltx_runtime_readiness" not in text:
        needle = '''        if command in {"video_family_contracts", "video_family_status"}:
            emitter.emit(video_family_contracts_snapshot())
            return
'''
        require(needle in text, "Could not find video_family_contracts command block in worker_service.py")
        text = text.replace(needle, needle + command_block, 1)

    write(WORKER_SERVICE, text)


def add_to_control_commands(text: str, command: str) -> str:
    if f'"{command}"' in text:
        return text
    marker = "CONTROL_COMMANDS = {"
    start = text.find(marker)
    require(start >= 0, "Could not find CONTROL_COMMANDS in worker_client.py")
    end = text.find("}\n", start)
    require(end >= 0, "Could not find end of CONTROL_COMMANDS in worker_client.py")
    return text[:end] + f', "{command}"' + text[end:]


def patch_worker_client() -> None:
    text = read(WORKER_CLIENT)

    if "VIDEO_READINESS_MESSAGE_TYPES" not in text:
        needle = 'VIDEO_FAMILY_MESSAGE_TYPES = {"video_family_contracts"}\n'
        replacement = (
            'VIDEO_FAMILY_MESSAGE_TYPES = {"video_family_contracts"}\n'
            'VIDEO_READINESS_MESSAGE_TYPES = {"ltx_readiness_status", "video_family_readiness_status"}\n'
        )
        require(needle in text, "Could not find VIDEO_FAMILY_MESSAGE_TYPES in worker_client.py")
        text = text.replace(needle, replacement, 1)

    for command in (
        "ltx_readiness_status",
        "ltx_runtime_readiness",
        "video_family_readiness",
        "video_family_readiness_status",
    ):
        text = add_to_control_commands(text, command)

    if 'if action in {"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status"}:' not in text:
        needle = '''    if action in {"video_family_contracts", "video_family_status"}:
        normalized = dict(payload)
        normalized["command"] = action
        normalized.pop("action", None)
        return normalized
'''
        addition = needle + '''    if action in {"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status"}:
        normalized = dict(payload)
        normalized["command"] = action
        normalized.pop("action", None)
        return normalized
'''
        require(needle in text, "Could not find video_family outbound normalizer in worker_client.py")
        text = text.replace(needle, addition, 1)

    if "if message_type in VIDEO_READINESS_MESSAGE_TYPES:" not in text:
        needle = '''    if message_type in VIDEO_FAMILY_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)
'''
        addition = needle + '''
    if message_type in VIDEO_READINESS_MESSAGE_TYPES:
        normalized = dict(payload)
        if last_job_id and "job_id" not in normalized:
            normalized["job_id"] = last_job_id
        return normalized, normalized.get("job_id", last_job_id)
'''
        require(needle in text, "Could not find video_family message normalizer in worker_client.py")
        text = text.replace(needle, addition, 1)

    write(WORKER_CLIENT, text)


def main() -> None:
    patch_worker_service()
    patch_worker_client()
    print("Sprint 15C Pass 2 LTX readiness detection applied.")


if __name__ == "__main__":
    main()
