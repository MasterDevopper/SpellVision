"""Preview pictures for a weight.

Downloaded images live under `<models root>/.spellvision/previews/<sha256>/`, keyed by hash so a
renamed or moved file keeps its pictures. The COVER is the one the Models page shows, and it is
written to `<stem>.preview.jpg` only when the weight has no picture already: users and other
tools (Lora-Manager, Stability Matrix) drop `<stem>.png` beside a weight, and overwriting that
would destroy work the app did not create.

`set_user_picture` is the explicit path -- the user chose this image, so it becomes the cover and
the sidecar marks it `user_override` so no later refresh disturbs it.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = "SpellVision/1.0"
COVER_SUFFIX = ".preview.jpg"
_EXISTING_PICTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".preview.png", ".preview.jpeg")


def preview_dir(models_root: str | Path, sha256: str) -> Path:
    return Path(str(models_root)) / ".spellvision" / "previews" / str(sha256)


def cover_path(weight: str | Path) -> Path | None:
    path = Path(str(weight))
    for suffix in (COVER_SUFFIX,) + _EXISTING_PICTURE_SUFFIXES:
        candidate = path.with_name(path.stem + suffix)
        if candidate.exists():
            return candidate
    return None


def _has_hand_placed_picture(weight: Path) -> bool:
    for suffix in _EXISTING_PICTURE_SUFFIXES:
        if weight.with_name(weight.stem + suffix).exists():
            return True
    return False


def download_previews(
    version: dict[str, Any] | None,
    *,
    models_root: str | Path,
    sha256: str,
    weight: str | Path,
    opener: Any = None,
    preserve_cover: bool = False,
    limit: int = 6,
    max_nsfw_level: int = 2,
    timeout: float = 25.0,
) -> list[dict[str, Any]]:
    """Fetch up to `limit` previews. A failure skips that image; it never aborts the refresh."""
    # build_opener() returns an OpenerDirector, which has .open(). The `urllib.request` MODULE
    # does not -- defaulting to it means every real fetch raises AttributeError while every
    # fake-opener test passes, which is exactly how this shipped twice before being caught by a
    # live run rather than by the suite.
    client = opener or urllib.request.build_opener()
    weight_path = Path(str(weight))
    target_dir = preview_dir(models_root, sha256)
    out: list[dict[str, Any]] = []

    candidates = [
        image
        for image in (version or {}).get("images") or []
        if isinstance(image, dict)
        and image.get("url")
        and int(image.get("nsfwLevel") or 1) <= int(max_nsfw_level)
    ][:limit]

    for index, image in enumerate(candidates):
        destination = target_dir / f"{index}.jpg"
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(str(image["url"]), headers={"User-Agent": USER_AGENT})
            with client.open(request, timeout=timeout) as response:
                destination.write_bytes(response.read())
        # OSError alone was not the real exception surface. `urllib.request.Request` raises
        # ValueError ("unknown url type") for a malformed URL, and the URL comes straight out of
        # the CivitAI response; a truncated body raises http.client.HTTPException. Either one
        # escaped this loop, escaped the caller, and ended a 79-minute refresh -- against a
        # docstring one line up promising that a failure skips the image.
        except Exception:
            continue
        out.append({
            "origin_url": str(image["url"]),
            "local_path": str(destination),
            "width": image.get("width"),
            "height": image.get("height"),
            "nsfw_level": image.get("nsfwLevel"),
            "is_cover": not out,
            "user_override": False,
            "meta": image.get("meta") or {},
        })

    # `_has_hand_placed_picture` does NOT cover `<stem>.preview.jpg`, and it must not: that is the
    # file THIS function writes, so treating it as hand-placed would mean a cover is written once
    # and then never updated again. It is also the file `set_user_picture` writes, which is why the
    # caller has to tell us -- the user's picture was otherwise overwritten by the next refresh,
    # silently, with a picture off the site.
    if out and not preserve_cover and not _has_hand_placed_picture(weight_path):
        cover = weight_path.with_name(weight_path.stem + COVER_SUFFIX)
        try:
            cover.write_bytes(Path(out[0]["local_path"]).read_bytes())
        except Exception:
            pass

    return out


def set_user_picture(weight: str | Path, image: str | Path) -> Path:
    """The user chose this picture. It becomes the cover, whatever else is there.

    The sidecar entry that MARKS it as theirs is written by the caller
    (`model_intelligence_commands.handle_model_intel_set_user_command`); without that mark the
    next refresh overwrites this file, because nothing on disk distinguishes a cover the user
    chose from one the previews pass downloaded.
    """
    weight_path = Path(str(weight))
    cover = weight_path.with_name(weight_path.stem + COVER_SUFFIX)
    cover.write_bytes(Path(str(image)).read_bytes())
    return cover
