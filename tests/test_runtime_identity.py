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


def test_runtime_page_lists_its_endpoints_from_data() -> None:
    """T6: Runtime lists the machines this install may render on, and it lists them from DATA.

    This replaces three greps that held the old shape in place: that ManagerPage.cpp contains the
    literal "192.168.1.127", that it contains "ComfyUI-Distributed", and that enableDistributedPack
    installs a zipball. All three described a design the W6 research overturned, and the first of
    them actively required the defect -- a ratchet asserting that the second machine is spelled in
    the C++ is a ratchet against ever having more than one.
    """
    root = ROOT / "qt_ui" / "shell"
    registry = (root / "EndpointRegistry.h").read_text(encoding="utf-8")
    panel = (root / "EndpointPanel.h").read_text(encoding="utf-8")
    manager = (ROOT / "qt_ui" / "ManagerPage.cpp").read_text(encoding="utf-8")

    assert "runtime/endpoints" in (root / "EndpointRegistry.cpp").read_text(encoding="utf-8")
    assert "familiesAllowed" in registry
    assert "endpointPanel_" in manager

    # The honesty line stays. Two machines are two machines.
    panel_body = (root / "EndpointPanel.cpp").read_text(encoding="utf-8")
    assert "does not pool VRAM" in panel_body

    # And the health of the master is no longer a substring of a caption.
    assert 'text().contains(QStringLiteral("healthy=yes"))' not in manager


def test_the_distributed_pack_is_gone_and_stays_gone() -> None:
    """T6: ComfyUI-Distributed was chosen in Doc 54 and overturned by the research.

    With no reachable worker it logs "Falling back to master execution" and runs the job on the
    master -- the opposite of the fail-closed requirement -- and its master-free mode is an open
    feature request. It also needs its own Collector and Seed nodes in every graph. The Enable
    button could never have installed it on the second machine in any case: install_custom_node is
    in LOCAL_INSTALL_COMMANDS and is refused for a remote endpoint by design, so it wrote the pack
    into THIS machine's custom_nodes and reported success.
    """
    manager = (ROOT / "qt_ui" / "ManagerPage.cpp").read_text(encoding="utf-8")
    assert "ComfyUI-Distributed" not in manager
    assert "robertvoy" not in manager
    assert "dualPcShareFolder" not in manager
    assert "dualPcConsent" not in manager

    # The guard that made the button pointless is still there, and still the reason.
    tcp = (ROOT / "python" / "worker_tcp.py").read_text(encoding="utf-8")
    assert "LOCAL_INSTALL_COMMANDS" in tcp
    assert "install_custom_node" in tcp


def test_remote_queuing_is_one_consent() -> None:
    """T6: one consent, and it governs the thing that needs consenting to -- sending a prompt and
    its input image to another machine, unauthenticated, because ComfyUI has no auth.

    The share-folder consent it replaces guarded `runtime/dualPcShareFolder`, a QSettings value with
    no consumer anywhere in the tree: the user was asked to approve something nothing read.
    """
    panel = (ROOT / "qt_ui" / "shell" / "EndpointPanel.cpp").read_text(encoding="utf-8")
    window = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
    assert "runtime/allowRemoteQueuing" in panel
    # Read where it matters: immediately before the enqueue, not only where it is set.
    assert "runtime/allowRemoteQueuing" in window
