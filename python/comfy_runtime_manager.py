from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from comfy_bootstrap import bootstrap_comfy_runtime, default_comfy_python, logs_dir_path, state_file_path, resolve_managed_comfy_python

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore


class ComfyRuntimeManager:
    def __init__(
        self,
        comfy_root: str,
        *,
        python_executable: str | None = None,
        host: str = "127.0.0.1",
        port: int = 8188,
        startup_timeout_sec: float = 60.0,
        poll_interval_sec: float = 0.5,
    ) -> None:
        self.comfy_root = str(Path(comfy_root).resolve())
        self.python_executable = resolve_managed_comfy_python(comfy_root, python_executable)
        self.host = host
        self.port = int(port)
        self.startup_timeout_sec = float(startup_timeout_sec)
        self.poll_interval_sec = float(poll_interval_sec)
        self.lock = threading.RLock()
        self.endpoint = f"http://{self.host}:{self.port}"
        self._state_path = state_file_path(self.comfy_root)
        self._logs_dir = logs_dir_path(self.comfy_root)
        self._last_status: dict[str, Any] = {}

    def _normalize_path(self, value: str | None) -> str:
        if not value:
            return ""
        try:
            return str(Path(value).resolve()).replace("\\", "/").lower()
        except Exception:
            return str(value).replace("\\", "/").lower()

    def _read_state(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return {}
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _write_state(self, payload: dict[str, Any]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _clear_state(self) -> None:
        try:
            self._state_path.unlink(missing_ok=True)
        except Exception:
            pass

    def _http_json(self, path: str, timeout_sec: float = 3.0) -> dict[str, Any]:
        url = f"{self.endpoint}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        if not raw.strip():
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {"raw": payload}

    def is_healthy(self) -> bool:
        try:
            self._http_json("/system_stats", timeout_sec=2.0)
            return True
        except Exception:
            try:
                self._http_json("/queue", timeout_sec=2.0)
                return True
            except Exception:
                return False

    def _get_process_info(self, pid: int | None) -> dict[str, Any]:
        info: dict[str, Any] = {
            "pid": pid,
            "exists": False,
            "cmdline": [],
            "exe": None,
            "cwd": None,
            "create_time": None,
        }
        if not pid or pid <= 0:
            return info

        if psutil is not None:
            try:
                proc = psutil.Process(pid)
                if not proc.is_running():
                    return info
                info["exists"] = True
                try:
                    info["cmdline"] = proc.cmdline()
                except Exception:
                    info["cmdline"] = []
                try:
                    info["exe"] = proc.exe()
                except Exception:
                    info["exe"] = None
                try:
                    info["cwd"] = proc.cwd()
                except Exception:
                    info["cwd"] = None
                try:
                    info["create_time"] = float(proc.create_time())
                except Exception:
                    info["create_time"] = None
                return info
            except Exception:
                return info

        try:
            os.kill(pid, 0)
            info["exists"] = True
        except OSError:
            pass
        return info

    def _process_looks_like_managed_comfy(self, info: dict[str, Any]) -> bool:
        if not info.get("exists"):
            return False
        comfy_root = self._normalize_path(self.comfy_root)
        cmdline = [self._normalize_path(part) for part in info.get("cmdline") or []]
        cwd = self._normalize_path(info.get("cwd"))
        exe = self._normalize_path(info.get("exe"))

        has_root_reference = any(comfy_root in part for part in cmdline if part) or (cwd.startswith(comfy_root) if cwd else False)
        has_entrypoint = any(part.endswith("/main.py") or part.endswith("/server.py") for part in cmdline)
        pythonish = exe.endswith("python.exe") or exe.endswith("python") or not exe
        return bool(has_root_reference and has_entrypoint and pythonish)

    def _process_is_owned(self, state: dict[str, Any], info: dict[str, Any]) -> bool:
        if not state.get("started_by_spellvision"):
            return False
        if not self._process_looks_like_managed_comfy(info):
            return False
        recorded = state.get("process_create_time")
        actual = info.get("create_time")
        if recorded is None or actual is None:
            return True
        try:
            return abs(float(recorded) - float(actual)) < 2.0
        except Exception:
            return True

    def status(self) -> dict[str, Any]:
        with self.lock:
            bootstrap = bootstrap_comfy_runtime(
                self.comfy_root,
                python_executable=self.python_executable,
                host=self.host,
                port=self.port,
                create_dirs=True,
            )
            state = self._read_state()
            pid = int(state.get("pid") or 0) if state.get("pid") else None
            process_info = self._get_process_info(pid)
            pid_alive = bool(process_info.get("exists"))
            owned = self._process_is_owned(state, process_info)
            healthy = self.is_healthy()
            installed = bool(bootstrap.get("installed"))

            state_key = "stopped"
            ownership = "none"
            message = "Managed Comfy runtime is stopped."

            if not installed:
                state_key = "not_installed"
                ownership = "none"
                message = "Managed Comfy runtime is not installed."
            elif healthy and owned:
                state_key = "ready_managed"
                ownership = "managed"
                message = "Managed Comfy runtime is ready."
            elif healthy:
                state_key = "ready_external"
                ownership = "external"
                message = "External Comfy runtime detected at the configured endpoint."
            elif owned and pid_alive:
                state_key = "starting_managed"
                ownership = "managed"
                message = "Managed Comfy runtime is starting."
            elif state.get("started_by_spellvision") and not pid_alive:
                message = "Managed Comfy runtime is stopped."

            status = dict(bootstrap)
            status.update(
                {
                    "ok": True,
                    "state": state_key,
                    "ownership": ownership,
                    "running": bool(owned and pid_alive),
                    "healthy": bool(healthy),
                    "endpoint_alive": bool(healthy),
                    "pid": pid if owned and pid_alive else None,
                    "detected_pid": pid if pid_alive else None,
                    "can_stop": bool(owned and pid_alive),
                    "started_by_spellvision": bool(state.get("started_by_spellvision")),
                    "state_file_present": bool(state),
                    "started_at": state.get("started_at"),
                    "stdout_log": state.get("stdout_log") or str(self._logs_dir / "comfy_stdout.log"),
                    "stderr_log": state.get("stderr_log") or str(self._logs_dir / "comfy_stderr.log"),
                    "python_executable": str(state.get("python_executable") or self.python_executable),
                    "launch_python_executable": self.python_executable,
                    "message": message,
                }
            )

            if healthy:
                try:
                    status["system_stats"] = self._http_json("/system_stats", timeout_sec=2.0)
                except Exception:
                    pass

            self._last_status = status
            return status

    def start(self, timeout_sec: float | None = None) -> dict[str, Any]:
        with self.lock:
            existing = self.status()
            state_key = str(existing.get("state") or "")
            if state_key == "ready_managed":
                existing["message"] = "Managed Comfy runtime is already running."
                existing["ok"] = True
                return existing
            if state_key == "starting_managed":
                deadline = time.time() + (timeout_sec or self.startup_timeout_sec)
                while time.time() < deadline:
                    payload = self.status()
                    if payload.get("state") == "ready_managed":
                        payload["ok"] = True
                        return payload
                    time.sleep(self.poll_interval_sec)
                payload = self.status()
                payload["ok"] = False
                payload["message"] = f"Timed out waiting for managed Comfy runtime at {self.endpoint}"
                return payload
            if state_key == "ready_external":
                existing["ok"] = False
                existing["message"] = "External Comfy runtime detected at the configured endpoint. SpellVision will not start a second managed runtime on the same port."
                return existing
            if not existing.get("ready_to_launch"):
                existing["ok"] = False
                existing["message"] = existing.get("message") or "Managed Comfy runtime is not installed."
                return existing

            self.python_executable = resolve_managed_comfy_python(self.comfy_root, self.python_executable)
            bootstrap = bootstrap_comfy_runtime(
                self.comfy_root,
                python_executable=self.python_executable,
                host=self.host,
                port=self.port,
                create_dirs=True,
            )
            command = list(bootstrap.get("recommended_command") or [])
            if not command:
                existing["ok"] = False
                existing["message"] = "ComfyUI entrypoint was not found."
                return existing

            self._logs_dir.mkdir(parents=True, exist_ok=True)
            stdout_log = self._logs_dir / "comfy_stdout.log"
            stderr_log = self._logs_dir / "comfy_stderr.log"
            creationflags = 0
            if os.name == "nt":
                creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
                creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

            with stdout_log.open("a", encoding="utf-8", errors="ignore") as stdout_fp, stderr_log.open("a", encoding="utf-8", errors="ignore") as stderr_fp:
                proc = subprocess.Popen(
                    command,
                    cwd=self.comfy_root,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_fp,
                    stderr=stderr_fp,
                    creationflags=creationflags,
                )

            create_time = None
            proc_info = self._get_process_info(proc.pid)
            if proc_info.get("create_time") is not None:
                create_time = proc_info.get("create_time")

            self._write_state(
                {
                    "pid": proc.pid,
                    "endpoint": self.endpoint,
                    "host": self.host,
                    "port": self.port,
                    "comfy_root": self.comfy_root,
                    "python_executable": self.python_executable,
                    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "stdout_log": str(stdout_log),
                    "stderr_log": str(stderr_log),
                    "command": command,
                    "started_by_spellvision": True,
                    "process_create_time": create_time,
                }
            )

            deadline = time.time() + (timeout_sec or self.startup_timeout_sec)
            while time.time() < deadline:
                payload = self.status()
                if payload.get("state") == "ready_managed":
                    payload["ok"] = True
                    return payload
                if payload.get("state") == "ready_external":
                    payload["ok"] = False
                    payload["message"] = "A different Comfy runtime became active on the configured endpoint during startup."
                    return payload
                time.sleep(self.poll_interval_sec)

            payload = self.status()
            payload["ok"] = False
            payload["message"] = f"Timed out waiting for managed Comfy runtime at {self.endpoint}"
            return payload

    def ensure_running(self, timeout_sec: float | None = None) -> dict[str, Any]:
        status = self.status()
        if status.get("state") in {"ready_managed", "ready_external"}:
            status["ok"] = True
            return status
        if status.get("state") == "not_installed":
            status["ok"] = False
            return status
        return self.start(timeout_sec=timeout_sec)

    def stop(self, graceful_timeout_sec: float = 8.0) -> dict[str, Any]:
        with self.lock:
            status = self.status()
            state_key = str(status.get("state") or "")
            if state_key == "ready_external":
                status["ok"] = False
                status["message"] = "External Comfy runtime detected; not owned by SpellVision, so it will not be stopped."
                return status
            if not status.get("can_stop"):
                self._clear_state()
                payload = self.status()
                payload["ok"] = True
                payload["message"] = "Managed Comfy runtime is already stopped."
                return payload

            state = self._read_state()
            pid = int(state.get("pid") or 0) if state.get("pid") else None
            if not pid:
                payload = self.status()
                payload["ok"] = True
                payload["message"] = "Managed Comfy runtime is already stopped."
                return payload

            try:
                if psutil is not None:
                    try:
                        proc = psutil.Process(pid)
                        children = proc.children(recursive=True)
                        for child in children:
                            try:
                                child.terminate()
                            except Exception:
                                pass
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        _, alive = psutil.wait_procs([proc, *children], timeout=graceful_timeout_sec)
                        for p in alive:
                            try:
                                p.kill()
                            except Exception:
                                pass
                    except Exception:
                        if os.name == "nt":
                            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True, text=True)
                        else:
                            os.kill(pid, signal.SIGTERM)
                elif os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True, text=True)
                else:
                    os.kill(pid, signal.SIGTERM)
                    deadline = time.time() + graceful_timeout_sec
                    while time.time() < deadline and self._get_process_info(pid).get("exists"):
                        time.sleep(0.2)
                    if self._get_process_info(pid).get("exists"):
                        os.kill(pid, signal.SIGKILL)
            finally:
                self._clear_state()

            payload = self.status()
            payload["ok"] = True
            if payload.get("state") == "ready_external":
                payload["message"] = "Managed Comfy runtime stopped, but an external Comfy runtime is still responding on the configured endpoint."
            else:
                payload["message"] = "Managed Comfy runtime stopped."
            return payload

    def restart(self, timeout_sec: float | None = None) -> dict[str, Any]:
        with self.lock:
            status = self.status()
            if status.get("state") == "ready_external":
                status["ok"] = False
                status["message"] = "External Comfy runtime detected; SpellVision will not restart a runtime it does not own."
                return status
            self.stop()
            return self.start(timeout_sec=timeout_sec)
