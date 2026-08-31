"""Is the installed ComfyUI behind the latest release?

Both halves of the answer were already one line away and were being thrown out:

  * **Installed** -- ``GET /system_stats`` returns ``system.comfyui_version``. It is fetched in four
    places and the body is discarded every time.
  * **Latest** -- ``GET api.github.com/repos/Comfy-Org/ComfyUI/releases/latest``. No auth, no git.

Two traps this exists to avoid.

**The repository moved.** ``comfyanonymous/ComfyUI`` 301-redirects; the releases API answers on
``Comfy-Org/ComfyUI``. An earlier note in the plan said to avoid the releases API entirely and use
``git ls-remote --tags`` -- wrong twice over, because it needs git (not present on an MSI machine)
and it invites the sort trap below.

**Versions are not strings.** Plain lexical ``sort`` over the 183 published tags returns ``v0.9.2``
as the newest; ``sort -V`` returns ``v0.34.1``. Comparison here is always a numeric tuple, so
0.9.2 < 0.34.1 the way a human means it. This is also why the check never says "up to date" from a
string equality test.

Never blocks the UI: results are cached with a TTL, and an unreachable GitHub is reported as
``unknown``, never as "up to date" -- a silent false negative would quietly strand someone on an old
core, which is exactly the outcome the update button is meant to prevent.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
import json
import time
import urllib.error
import urllib.request

RELEASES_URL = "https://api.github.com/repos/Comfy-Org/ComfyUI/releases/latest"
CACHE_TTL_SEC = 6 * 3600
CACHE_VERSION = 1

STATUS_UP_TO_DATE = "up_to_date"
STATUS_UPDATE_AVAILABLE = "update_available"
STATUS_AHEAD = "ahead"
STATUS_UNKNOWN = "unknown"


@dataclass
class VersionCheck:
    status: str
    installed: str | None = None
    latest: str | None = None
    release_url: str | None = None
    published_at: str | None = None
    checked_at: float = 0.0
    from_cache: bool = False
    reason: str = ""

    @property
    def update_available(self) -> bool:
        return self.status == STATUS_UPDATE_AVAILABLE

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["update_available"] = self.update_available
        return payload


def parse_version(value: str | None) -> tuple[int, ...] | None:
    """``"v0.34.1"`` -> ``(0, 34, 1)``. None when there is no numeric version to read.

    Trailing non-numeric parts (``0.34.1-rc2``) stop the parse at the numeric prefix, so a release
    candidate compares as its base version rather than failing outright.
    """
    if not value:
        return None
    text = str(value).strip().lstrip("vV")
    parts: list[int] = []
    for chunk in text.split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or None


def compare_versions(installed: str | None, latest: str | None) -> str:
    """Numeric-tuple comparison. Lexical comparison calls 0.9.2 newer than 0.34.1."""
    a, b = parse_version(installed), parse_version(latest)
    if a is None or b is None:
        return STATUS_UNKNOWN
    width = max(len(a), len(b))
    a = a + (0,) * (width - len(a))
    b = b + (0,) * (width - len(b))
    if a < b:
        return STATUS_UPDATE_AVAILABLE
    if a > b:
        # A local build newer than the newest release. Not an error, and definitely not an update.
        return STATUS_AHEAD
    return STATUS_UP_TO_DATE


def default_cache_path() -> Path:
    try:
        from runtime_paths import RuntimePaths

        return Path(RuntimePaths.CACHE) / "comfy_registry" / "latest_release.json"
    except Exception:
        return Path(__file__).resolve().parent.parent / "runtime" / "cache" / "comfy_registry" / "latest_release.json"


def _read_cache(path: Path, ttl: float) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
        return None
    if time.time() - float(payload.get("checked_at") or 0.0) > ttl:
        return None
    return payload


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": CACHE_VERSION, **payload}, indent=1), encoding="utf-8")
    except Exception:
        pass


def _default_fetch(url: str, *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "SpellVision/1.0 (comfy version check)",
    })
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_release(
    *,
    fetch: Callable[..., dict[str, Any]] = _default_fetch,
    cache_path: str | Path | None = None,
    ttl: float = CACHE_TTL_SEC,
    timeout: float = 10.0,
    force: bool = False,
) -> tuple[dict[str, Any] | None, bool]:
    """``(release_or_None, from_cache)``. Never raises; a failure is a None, not an exception."""
    path = Path(cache_path) if cache_path else default_cache_path()
    if not force:
        cached = _read_cache(path, ttl)
        if cached is not None:
            return cached.get("release"), True
    try:
        release = fetch(RELEASES_URL, timeout=timeout)
    except Exception:
        # A stale cached answer beats no answer, and beats guessing "up to date".
        stale = _read_cache(path, float("inf"))
        if stale is not None:
            return stale.get("release"), True
        return None, False
    if not isinstance(release, dict):
        return None, False
    _write_cache(path, {"checked_at": time.time(), "release": release})
    return release, False


def check_comfy_version(
    installed_version: str | None,
    *,
    fetch: Callable[..., dict[str, Any]] = _default_fetch,
    cache_path: str | Path | None = None,
    ttl: float = CACHE_TTL_SEC,
    timeout: float = 10.0,
    force: bool = False,
) -> VersionCheck:
    """Compare the installed ComfyUI against the newest published release."""
    if not installed_version:
        return VersionCheck(status=STATUS_UNKNOWN, checked_at=time.time(),
                            reason="ComfyUI is not running, so its version could not be read.")

    release, from_cache = latest_release(fetch=fetch, cache_path=cache_path, ttl=ttl,
                                         timeout=timeout, force=force)
    if release is None:
        return VersionCheck(status=STATUS_UNKNOWN, installed=installed_version, checked_at=time.time(),
                            reason="Could not reach GitHub to read the latest ComfyUI release.")
    if release.get("prerelease") or release.get("draft"):
        return VersionCheck(status=STATUS_UNKNOWN, installed=installed_version, checked_at=time.time(),
                            from_cache=from_cache,
                            reason="The newest published release is a prerelease; not offering it as an update.")

    latest = str(release.get("tag_name") or release.get("name") or "").strip() or None
    status = compare_versions(installed_version, latest)
    reason = ""
    if status == STATUS_UNKNOWN:
        reason = f"Could not compare {installed_version!r} with {latest!r} as version numbers."
    elif status == STATUS_AHEAD:
        reason = "The installed build is newer than the latest published release."
    return VersionCheck(
        status=status,
        installed=installed_version,
        latest=latest,
        release_url=str(release.get("html_url") or "") or None,
        published_at=str(release.get("published_at") or "") or None,
        checked_at=time.time(),
        from_cache=from_cache,
        reason=reason,
    )


def installed_version_from_system_stats(system_stats: Any) -> str | None:
    """Read ``system.comfyui_version`` out of a /system_stats body."""
    if not isinstance(system_stats, dict):
        return None
    system = system_stats.get("system")
    if not isinstance(system, dict):
        return None
    value = system.get("comfyui_version")
    return str(value).strip() or None if value else None
