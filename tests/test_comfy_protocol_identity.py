"""Comfy adoption requires Comfy-specific HTTP identity, not open TCP port."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_H = (ROOT / "qt_ui" / "shell" / "RuntimeProfile.h").read_text(encoding="utf-8")
RUNTIME_CPP = (ROOT / "qt_ui" / "shell" / "RuntimeProfile.cpp").read_text(encoding="utf-8")
MAIN = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
FIRST_RUN = (ROOT / "qt_ui" / "shell" / "FirstRunDialog.cpp").read_text(encoding="utf-8")


def test_comfy_probe_validates_http_identity_payload() -> None:
    assert "bool probeComfyProtocol" in RUNTIME_H
    body = RUNTIME_CPP.split("bool probeComfyProtocol", 1)[1].split(
        "QString resolvePreferredComfyRoot", 1
    )[0]
    assert 'GET /system_stats HTTP/1.1' in body
    assert 'statusLine.contains(QStringLiteral(" 200 "))' in body
    assert 'value(QStringLiteral("system")).isObject()' in body
    assert 'value(QStringLiteral("devices")).isArray()' in body


def test_runtime_adoption_and_first_run_use_identity_probe() -> None:
    probe = MAIN.split("bool MainWindow::probeComfyRuntime", 1)[1].split(
        "bool MainWindow::writeComfySessionFile", 1
    )[0]
    assert "probeComfyProtocol" in probe
    assert "probeTcpPort" not in probe
    assert FIRST_RUN.count("probeComfyProtocol") >= 2
    assert "probeTcpPort(profile.comfyHost" not in FIRST_RUN
    assert "probeTcpPort(profile_.comfyHost" not in FIRST_RUN
