from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

import model_sources
from model_sources import AssetReference


class FakeResponse:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self._offset = 0
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._body):
            return b""
        if size < 0:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def _ref(filename: str) -> AssetReference:
    return AssetReference(
        raw={"url": "https://example.invalid/model", "filename": filename},
        kind="direct_url",
        source_name="direct",
        asset_type="model",
        url="https://example.invalid/model",
        filename=filename,
    )


def test_remote_filename_cannot_escape_cache_root(tmp_path: Path, monkeypatch) -> None:
    called = False

    def unexpected_open(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("unsafe path must fail before network access")

    monkeypatch.setattr(model_sources.urllib.request, "urlopen", unexpected_open)
    with pytest.raises(ValueError, match="filename"):
        model_sources._download_remote_asset(
            _ref("../../escaped.bin"),
            cache_root=str(tmp_path),
            civitai_api_key=None,
            force_download=False,
            timeout_sec=1,
        )
    assert called is False
    assert not (tmp_path.parent / "escaped.bin").exists()


def test_streaming_download_enforces_byte_ceiling_and_cleans_part(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SPELLVISION_MAX_MODEL_DOWNLOAD_BYTES", "8")
    monkeypatch.setattr(
        model_sources.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"123456789"),
    )

    with pytest.raises(RuntimeError, match="byte limit"):
        model_sources._download_remote_asset(
            _ref("model.bin"),
            cache_root=str(tmp_path),
            civitai_api_key=None,
            force_download=False,
            timeout_sec=1,
        )
    target_dir = tmp_path / "direct" / "model"
    assert list(target_dir.glob("*.part")) == []
    assert not (target_dir / "model.bin").exists()


def test_content_length_is_validated_before_atomic_publish(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SPELLVISION_MAX_MODEL_DOWNLOAD_BYTES", "1024")
    monkeypatch.setattr(
        model_sources.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"payload", {"Content-Length": "8"}),
    )

    with pytest.raises(RuntimeError, match="Content-Length"):
        model_sources._download_remote_asset(
            _ref("model.bin"),
            cache_root=str(tmp_path),
            civitai_api_key=None,
            force_download=False,
            timeout_sec=1,
        )
    assert not (tmp_path / "direct" / "model" / "model.bin").exists()
