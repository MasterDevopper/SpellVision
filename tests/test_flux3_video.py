from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


PYTHON_DIR = Path(__file__).resolve().parent.parent / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


import flux3_video
from flux3_video import Flux3ApiError, Flux3RequestError, build_flux3_payload, generate_flux3_video


def test_t2v_payload_maps_cockpit_shape_to_flux3_contract() -> None:
    payload = build_flux3_payload(
        {
            "command": "t2v",
            "prompt": "A fox runs through dawn mist.",
            "width": 1280,
            "height": 720,
            "frames": 192,
            "fps": 24,
        }
    )

    assert payload == {
        "mode": "t2v",
        "prompt": "A fox runs through dawn mist.",
        "aspect_ratio": "16:9",
        "duration": 8,
        "resolution": "hd",
        "version": "latest",
        "generate_audio": True,
        "safety_tolerance": 2,
        "draft": False,
    }


def test_i2v_payload_embeds_local_keyframe(tmp_path: Path) -> None:
    keyframe = tmp_path / "opening.png"
    keyframe.write_bytes(b"test-png")

    payload = build_flux3_payload(
        {
            "command": "i2v",
            "prompt": "The camera pushes forward.",
            "input_image": str(keyframe),
            "width": 720,
            "height": 1280,
            "frames": 120,
            "fps": 24,
        }
    )

    assert payload["mode"] == "i2v"
    assert payload["aspect_ratio"] == "9:16"
    assert payload["duration"] == 5
    assert payload["keyframes"] == "data:image/png;base64,dGVzdC1wbmc="


@pytest.mark.parametrize(
    ("payload_input", "message"),
    [
        ({"command": "t2v", "prompt": ""}, "prompt"),
        ({"command": "i2v", "prompt": "move"}, "keyframe"),
        ({"command": "v2v", "prompt": "continue"}, "mode"),
    ],
)
def test_payload_rejects_invalid_requests(payload_input: dict[str, object], message: str) -> None:
    with pytest.raises(Flux3RequestError, match=message):
        build_flux3_payload(payload_input)


def test_generate_requires_bfl_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BFL_API_KEY", raising=False)
    with pytest.raises(Flux3RequestError, match="BFL_API_KEY"):
        generate_flux3_video(
            {"command": "t2v", "prompt": "A fox runs through mist."},
            tmp_path / "unused.mp4",
            api_key=None,
        )


def test_production_api_rejects_insecure_polling_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        flux3_video,
        "_json_request",
        lambda _request, *, timeout: {
            "id": "job-insecure",
            "polling_url": "http://127.0.0.1/internal",
        },
    )

    with pytest.raises(Flux3ApiError, match="secure HTTPS polling URL"):
        generate_flux3_video(
            {"command": "t2v", "prompt": "A fox runs through mist."},
            tmp_path / "unused.mp4",
            api_key="test-key",
            poll_interval=0,
            timeout=2,
        )


def test_json_request_wraps_connection_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    def reset_connection(*_args: object, **_kwargs: object) -> None:
        raise ConnectionResetError("connection reset by peer")

    monkeypatch.setattr(flux3_video, "urlopen", reset_connection)

    with pytest.raises(Flux3ApiError, match="Could not reach"):
        flux3_video._json_request(
            flux3_video.Request("https://api.bfl.ai/test"),
            timeout=1,
        )


def test_generate_submits_polls_and_downloads_video(tmp_path: Path) -> None:
    state: dict[str, object] = {"polls": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            state["payload"] = json.loads(self.rfile.read(length))
            state["api_key"] = self.headers.get("x-key")
            self._json({"id": "job-1", "polling_url": f"{base_url}/result"})

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/clip.mp4":
                body = b"fake-mp4"
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            state["poll_api_key"] = self.headers.get("x-key")
            state["polls"] = int(state["polls"]) + 1
            if state["polls"] == 1:
                self._json({"id": "job-1", "status": "Pending"})
            else:
                self._json(
                    {
                        "id": "job-1",
                        "status": "Ready",
                        "result": {"sample": f"{base_url}/clip.mp4"},
                    }
                )

        def log_message(self, _format: str, *args: object) -> None:
            pass

        def _json(self, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    base_url = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output_path = tmp_path / "flux3.mp4"
    try:
        result = generate_flux3_video(
            {
                "command": "t2v",
                "prompt": "A fox runs through mist.",
                "width": 1280,
                "height": 720,
                "frames": 120,
                "fps": 24,
            },
            output_path,
            api_key="test-key",
            api_url=f"{base_url}/flux-3-video",
            poll_interval=0,
            timeout=2,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert output_path.read_bytes() == b"fake-mp4"
    assert result["request_id"] == "job-1"
    assert result["output_path"] == str(output_path)
    assert result["backend_route"] == "bfl_api"
    assert state["api_key"] == "test-key"
    assert state["poll_api_key"] == "test-key"
    assert state["payload"] == build_flux3_payload(
        {
            "command": "t2v",
            "prompt": "A fox runs through mist.",
            "width": 1280,
            "height": 720,
            "frames": 120,
            "fps": 24,
        }
    )
