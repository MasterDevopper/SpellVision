"""Preview pictures.

The rule that matters: a hand-placed picture is never clobbered. Users (and other tools) already
drop `<stem>.png` beside a weight, and a metadata refresh that overwrote it would destroy work
the app did not create. So the downloaded cover only lands when nothing is there, and a picture
the user explicitly chooses is marked so no later refresh touches it.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import previews

PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64


class FakeResponse(io.BytesIO):
    status = 200


class FakeOpener:
    def __init__(self, body=PNG):
        self.body = body
        self.urls = []

    def open(self, request, timeout=None):
        self.urls.append(getattr(request, "full_url", str(request)))
        return FakeResponse(self.body)


def _weight(tmp_path: Path) -> Path:
    path = tmp_path / "model.safetensors"
    path.write_bytes(b"w")
    return path


def _version(count=3, level=1):
    return {"images": [{"url": f"https://image.civitai.com/x/{i}.jpeg", "width": 8, "height": 8,
                        "nsfwLevel": level, "meta": {"steps": 8}} for i in range(count)]}


def test_downloads_into_a_hash_scoped_folder(tmp_path: Path):
    weight = _weight(tmp_path)
    opener = FakeOpener()
    images = previews.download_previews(_version(2), models_root=tmp_path, sha256="a" * 64,
                                        weight=weight, opener=opener)
    assert len(images) == 2
    for entry in images:
        assert Path(entry["local_path"]).exists()
        assert "a" * 64 in entry["local_path"].replace("\\", "/")


def test_the_cover_is_written_when_nothing_is_there(tmp_path: Path):
    weight = _weight(tmp_path)
    previews.download_previews(_version(1), models_root=tmp_path, sha256="a" * 64,
                               weight=weight, opener=FakeOpener())
    assert (tmp_path / "model.preview.jpg").exists()


def test_a_hand_placed_picture_is_never_clobbered(tmp_path: Path):
    weight = _weight(tmp_path)
    hand = tmp_path / "model.png"
    hand.write_bytes(b"the user's own picture")
    previews.download_previews(_version(1), models_root=tmp_path, sha256="a" * 64,
                               weight=weight, opener=FakeOpener())
    assert hand.read_bytes() == b"the user's own picture"
    assert not (tmp_path / "model.preview.jpg").exists()


def test_mature_previews_are_skipped_below_the_threshold(tmp_path: Path):
    weight = _weight(tmp_path)
    images = previews.download_previews(_version(3, level=8), models_root=tmp_path,
                                        sha256="a" * 64, weight=weight, opener=FakeOpener(),
                                        max_nsfw_level=2)
    assert images == []


def test_the_limit_is_respected(tmp_path: Path):
    weight = _weight(tmp_path)
    images = previews.download_previews(_version(20), models_root=tmp_path, sha256="a" * 64,
                                        weight=weight, opener=FakeOpener(), limit=6)
    assert len(images) == 6


def test_set_user_picture_marks_the_override(tmp_path: Path):
    weight = _weight(tmp_path)
    mine = tmp_path / "mine.png"
    mine.write_bytes(PNG)
    written = previews.set_user_picture(weight, mine)
    assert written.exists()
    assert previews.cover_path(weight) == written


def test_a_download_failure_is_skipped_not_fatal(tmp_path: Path):
    class Broken:
        def open(self, request, timeout=None):
            raise OSError("no route to host")

    weight = _weight(tmp_path)
    assert previews.download_previews(_version(2), models_root=tmp_path, sha256="a" * 64,
                                      weight=weight, opener=Broken()) == []
