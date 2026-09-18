"""W5 Task 3 -- a picture the user chooses survives a later refresh.

The promise was written in three docstrings and held by nothing.

`sidecar.merge` protected a display field by asking whether it was a dict carrying
`user_override`. `display.images` is a LIST, so that branch could never fire; and `images` is
always present in the fresh payload, so the `field not in display` fallback could not fire either.
Every refresh therefore replaced the gallery wholesale, and the flag marking the user's own cover
went with it.

The file on disk was overwritten too, by a different mechanism. `previews.download_previews`
declines to write `<stem>.preview.jpg` when a picture is already sitting beside the weight -- but
its list of "already sitting there" suffixes deliberately excludes `.preview.jpg`, because that is
the file it writes itself. `set_user_picture` writes exactly that file. So the refresh saw no
hand-placed picture, and wrote a site image over the user's.

Two mechanisms, one promise, and a JSON-only fix would have looked like it worked: the sidecar
would have pointed at the right path while the bytes at that path were the site's.

These run the REAL `RefreshJob` against a fake CivitAI client. No network, no worker, no ComfyUI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

import model_intelligence_commands as mic  # noqa: E402
from model_intelligence import previews, sidecar  # noqa: E402
from model_intelligence.refresh import RefreshJob  # noqa: E402

USER_BYTES = b"\x89PNG-the-user-chose-this"
SITE_BYTES = b"\xff\xd8-the-site-published-this"


class FakeCivitai:
    """Answers every hash with one version that publishes one picture."""

    def __init__(self, image_url: str = "https://image.civitai.example/site.jpeg") -> None:
        self.image_url = image_url

    def model(self, model_id: int) -> dict:
        # The parent-model payload -- the only source of creator and licence flags.
        return {"id": int(model_id), "creator": {"username": "kreauser"},
                "allowCommercialUse": ["Image"], "allowDerivatives": True,
                "allowNoCredit": True, "allowDifferentLicense": False}

    def by_hash(self, digest: str) -> dict:
        return {
            "id": 3068874,
            "modelId": 2729908,
            "name": "V1.0",
            "baseModel": "Krea 2",
            "model": {"name": "[KREA 2] Detail Slider", "description": "<p>First version</p>"},
            "trainedWords": [],
            "images": [{"url": self.image_url, "width": 8, "height": 8, "nsfwLevel": 1,
                        "meta": {"steps": 12, "cfgScale": 1, "sampler": "Euler",
                                 "scheduler": "beta"}}],
            "files": [{"hashes": {"SHA256": digest.upper()}, "metadata": {"fp": "bf16"}}],
        }


class FakeOpener:
    """`build_opener()`-shaped: has `.open()` and returns a context manager."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def open(self, request, timeout=None):  # noqa: ANN001, ARG002
        payload = self.payload

        class _Response:
            def __enter__(self_inner):  # noqa: N805
                return self_inner

            def __exit__(self_inner, *exc):  # noqa: N805, ANN002
                return False

            def read(self_inner):  # noqa: N805
                return payload

        return _Response()


@pytest.fixture()
def library(tmp_path, monkeypatch):
    """A one-weight models root, with the previews pass wired to a fake opener."""
    root = tmp_path / "models"
    (root / "loras").mkdir(parents=True)
    weight = root / "loras" / "Detailer-KREA2.safetensors"
    weight.write_bytes(b"not a real weight, but a real file with a real digest")

    picture = root / "loras" / "my_own_shot.png"
    picture.write_bytes(USER_BYTES)

    real_download = previews.download_previews

    def download_with_fake_opener(*args, **kwargs):
        kwargs.setdefault("opener", FakeOpener(SITE_BYTES))
        return real_download(*args, **kwargs)

    monkeypatch.setattr(previews, "download_previews", download_with_fake_opener)
    monkeypatch.setattr("model_intelligence.refresh.previews.download_previews",
                        download_with_fake_opener)
    return root, weight, picture


def _refresh(root: Path) -> dict:
    return RefreshJob([root], client=FakeCivitai(), models_root=root).run()


def _cover_entry(weight: Path) -> dict | None:
    images = ((sidecar.read(weight) or {}).get("display") or {}).get("images") or []
    for image in images:
        if image.get("is_cover"):
            return image
    return None


def test_a_refresh_identifies_the_weight_and_publishes_the_site_cover(library):
    root, weight, _picture = library
    result = _refresh(root)
    assert result["ok"], result
    assert result["identified"] == 1

    cover = _cover_entry(weight)
    assert cover is not None
    assert cover["user_override"] is False
    assert Path(cover["local_path"]).read_bytes() == SITE_BYTES
    assert previews.cover_path(weight).read_bytes() == SITE_BYTES


def test_the_users_picture_survives_a_later_refresh(library):
    root, weight, picture = library
    _refresh(root)

    reply = mic.handle_model_intel_set_user_command(
        {"path": str(weight), "picture": str(picture), "roots": [str(root)]}
    )
    assert reply["ok"], reply
    assert "picture" in reply["changed"]

    cover = _cover_entry(weight)
    assert cover is not None and cover["user_override"] is True
    assert Path(cover["local_path"]).read_bytes() == USER_BYTES

    # The site publishes something new, and the refresh runs again.
    result = _refresh(root)
    assert result["ok"] and result["identified"] == 1

    after = _cover_entry(weight)
    assert after is not None, "the refresh dropped the cover entirely"
    # The ENTRY survives...
    assert after["user_override"] is True, "the refresh replaced the gallery and lost the mark"
    # ...and so do the BYTES it points at. A JSON-only fix passes the line above and fails here.
    assert Path(after["local_path"]).read_bytes() == USER_BYTES, (
        "the sidecar still names the user's cover but the refresh overwrote the file"
    )
    assert previews.cover_path(weight).read_bytes() == USER_BYTES

    # The site's pictures are still there, behind the user's, and exactly one image is the cover.
    images = ((sidecar.read(weight) or {}).get("display") or {}).get("images") or []
    assert len(images) >= 2
    assert sum(1 for image in images if image.get("is_cover")) == 1
    assert images[0]["user_override"] is True
    assert any(image.get("origin_url") for image in images[1:])


def test_a_user_picture_on_an_unidentified_weight_is_recorded_and_survives(library):
    """The case the old code could not record at all.

    `images[0] = {**images[0], "user_override": True}` only did anything when the site had already
    supplied a gallery. For a weight nobody could identify -- the one a user is most likely to want
    their own picture on -- the list was empty, so nothing marked the choice and the next refresh
    wrote over the file.
    """
    root, weight, picture = library

    reply = mic.handle_model_intel_set_user_command(
        {"path": str(weight), "picture": str(picture), "roots": [str(root)]}
    )
    assert reply["ok"], reply

    cover = _cover_entry(weight)
    assert cover is not None, "nothing recorded the user's picture"
    assert cover["user_override"] is True
    assert Path(cover["local_path"]).read_bytes() == USER_BYTES

    _refresh(root)
    after = _cover_entry(weight)
    assert after is not None and after["user_override"] is True
    assert Path(after["local_path"]).read_bytes() == USER_BYTES


def test_a_picture_outside_the_model_roots_is_refused_with_a_reason(library):
    """Containment is by design, so the page has to be able to SAY so rather than fail silently."""
    root, weight, _picture = library
    outside = root.parent / "somewhere_else.png"
    outside.write_bytes(USER_BYTES)

    reply = mic.handle_model_intel_set_user_command(
        {"path": str(weight), "picture": str(outside), "roots": [str(root)]}
    )
    assert reply["ok"] is False
    assert "outside the model roots" in reply["error"]
    # And nothing was written on the way to refusing.
    assert previews.cover_path(weight) is None

    # A weight outside the roots is refused too, and the refusal names WHICH check failed.
    elsewhere = root.parent / "elsewhere.safetensors"
    elsewhere.write_bytes(b"x")
    refused = mic.handle_model_intel_set_user_command(
        {"path": str(elsewhere), "picture": str(_picture_of(root)), "roots": [str(root)]}
    )
    assert refused["ok"] is False
    assert "outside the model roots" in refused["error"]


def _picture_of(root: Path) -> Path:
    return root / "loras" / "my_own_shot.png"


def test_a_user_name_still_survives_a_refresh(library):
    """The dict-shaped display fields were always protected; this pins that the list fix did not
    break them on the way past."""
    root, weight, _picture = library
    _refresh(root)

    mic.handle_model_intel_set_user_command(
        {"path": str(weight), "name": "My Detail Slider", "roots": [str(root)]}
    )
    _refresh(root)

    display = (sidecar.read(weight) or {}).get("display") or {}
    assert display["name"]["value"] == "My Detail Slider"
    assert display["name"]["user_override"] is True
    # And the FILE was never renamed -- the whole point of a display name.
    assert weight.name == "Detailer-KREA2.safetensors"
    assert weight.exists()


def test_the_sidecar_stays_valid_json_through_all_of_it(library):
    root, weight, picture = library
    _refresh(root)
    mic.handle_model_intel_set_user_command(
        {"path": str(weight), "picture": str(picture), "roots": [str(root)]}
    )
    _refresh(root)
    text = sidecar.sidecar_path(weight).read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["schema"] == sidecar.SCHEMA
    assert payload["identity"]["kind"]
    assert payload["recommended"]


def test_refreshing_one_file_does_not_walk_the_whole_root(library, monkeypatch):
    """The inspector's "Refresh metadata" names ONE weight.

    `RefreshJob` has always supported a `files` list -- its own docstring explains why, in terms of
    the 475 LoRAs a download hook was re-identifying -- and `handle_model_intel_refresh_command`
    never passed one through. A request naming a single file therefore walked every root: 759 files
    and 2.09 TB of hashing on the owner's library, for a button about one weight.
    """
    root, weight, _picture = library
    neighbour = root / "loras" / "Someone-Else.safetensors"
    neighbour.write_bytes(b"a second weight nobody asked about")

    reply = mic.handle_model_intel_refresh_command(
        {"roots": [str(root)], "files": [str(weight)]}
    )
    assert reply["ok"], reply
    assert reply["examined"] == 1
    assert sidecar.read(weight) is not None
    assert sidecar.read(neighbour) is None, "the refresh identified a file nobody named"


def test_a_file_outside_the_named_roots_is_refused(library):
    root, _weight, _picture = library
    elsewhere = root.parent / "elsewhere.safetensors"
    elsewhere.write_bytes(b"x")

    reply = mic.handle_model_intel_refresh_command(
        {"roots": [str(root)], "files": [str(elsewhere)]}
    )
    assert reply["ok"] is False
    assert "outside the named roots" in reply["error"]
    assert sidecar.read(elsewhere) is None
