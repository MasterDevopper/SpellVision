"""The worker adoption handshake proves service identity and protocol compatibility."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_PROFILE = (ROOT / "qt_ui" / "shell" / "RuntimeProfile.cpp").read_text(encoding="utf-8")


def test_ping_reports_worker_identity_and_protocol_version(worker_client) -> None:
    messages = worker_client({"command": "ping"})
    pong = next(message for message in messages if message.get("pong") is True)
    assert pong["service"] == "spellvision_worker"
    assert pong["protocol_version"] == 1


def test_qt_adoption_requires_identity_and_exact_protocol_version() -> None:
    assert 'QStringLiteral("spellvision_worker")' in RUNTIME_PROFILE
    assert 'QStringLiteral("service")' in RUNTIME_PROFILE
    assert 'QStringLiteral("protocol_version")' in RUNTIME_PROFILE
    assert "kWorkerProtocolVersion" in RUNTIME_PROFILE
