from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

import runtime_identity as ri


def _isolate_worker_python_env(monkeypatch) -> None:
    """resolve_worker_python consults SPELLVISION_WORKER_PYTHON and VIRTUAL_ENV ahead of
    project_root/.venv. pytest itself runs from the activated project venv, so without this
    the runner's own interpreter wins and these tests assert against the dev box instead of
    tmp_path. Mirrors the delenv discipline the comfy tests below already use."""
    monkeypatch.delenv("SPELLVISION_WORKER_PYTHON", raising=False)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)


def test_directory_at_python_path_is_not_an_executable(tmp_path: Path, monkeypatch) -> None:
    _isolate_worker_python_env(monkeypatch)
    fake = tmp_path / "Scripts"
    fake.mkdir()
    decoy = fake / "python.exe"
    decoy.mkdir()
    assert decoy.exists()
    assert not ri.is_regular_executable(decoy)
    assert ri.resolve_worker_python(tmp_path, explicit=decoy) is None


def test_regular_file_python_is_accepted(tmp_path: Path, monkeypatch) -> None:
    _isolate_worker_python_env(monkeypatch)
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fake")
    resolved = ri.resolve_worker_python(tmp_path)
    assert resolved == python.resolve()


def test_comfy_python_does_not_fall_back_to_worker_python(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SPELLVISION_COMFY_PYTHON", raising=False)
    monkeypatch.delenv("SPELLVISION_COMFY", raising=False)
    worker = tmp_path / "worker-python.exe"
    worker.write_bytes(b"fake")
    comfy_root = tmp_path / "ComfyUI"
    comfy_root.mkdir()
    assert ri.resolve_comfy_python(comfy_root, explicit=None) is None
    isolated = tmp_path / ".venv" / "Scripts" / "python.exe"
    isolated.parent.mkdir(parents=True)
    isolated.write_bytes(b"comfy")
    resolved = ri.resolve_comfy_python(comfy_root)
    assert resolved == isolated.resolve()
    assert resolved != worker.resolve()


def test_comfy_root_env_wins(tmp_path: Path, monkeypatch) -> None:
    chosen = tmp_path / "live-comfy"
    chosen.mkdir()
    monkeypatch.setenv("SPELLVISION_COMFY", str(chosen))
    assert ri.resolve_comfy_root(tmp_path) == chosen.resolve()


def test_rollback_comfy_env_remaps_to_live_when_present(monkeypatch) -> None:
    if not ri.LIVE_COMFY.exists():
        return
    monkeypatch.setenv("SPELLVISION_COMFY", str(ri.ROLLBACK_COMFY))
    assert ri.resolve_comfy_root() == ri.LIVE_COMFY.resolve()
    assert ri.resolve_comfy_root(explicit=ri.ROLLBACK_COMFY) == ri.LIVE_COMFY.resolve()


def test_request_comfy_python_ignores_worker_python_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SPELLVISION_COMFY_PYTHON", raising=False)
    monkeypatch.delenv("SPELLVISION_COMFY", raising=False)
    worker = tmp_path / "worker.exe"
    worker.write_bytes(b"w")
    comfy_root = tmp_path / "ComfyUI"
    comfy_root.mkdir()
    value = ri.resolve_comfy_python_from_request(
        {
            "comfy_root": str(comfy_root),
            "python_executable": str(worker),
        }
    )
    assert value == ""
    isolated = tmp_path / ".venv" / "Scripts" / "python.exe"
    isolated.parent.mkdir(parents=True)
    isolated.write_bytes(b"comfy")
    value = ri.resolve_comfy_python_from_request(
        {
            "comfy_root": str(comfy_root),
            "python_executable": str(worker),
        }
    )
    assert Path(value) == isolated.resolve()
