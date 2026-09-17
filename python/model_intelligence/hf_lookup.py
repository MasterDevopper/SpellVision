"""HuggingFace model metadata, and the local sha256 index that stands in for a by-hash API.

HF has NO by-hash endpoint (verified 2026-09-16), so a local weight can only be identified here if
we already know which repo it might belong to. `?blobs=true` is what makes even that possible: the
flag adds `siblings[].lfs.sha256`, and without it `siblings` carries filenames only.

For settings, the diffusers snippet in a card is the most reliable machine-readable source --
`num_inference_steps=50, guidance_scale=3.5` is what the authors actually run -- so it outranks
the prose regexes, which are a genuine guess.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

API = "https://huggingface.co/api/models"
RESOLVE = "https://huggingface.co"
USER_AGENT = "SpellVision/1.0"

_SNIPPET_KEYS = {
    "num_inference_steps": "steps",
    "guidance_scale": "guidance",
    "true_cfg_scale": "cfg",
    "shift": "shift",
    "num_frames": "frames",
    "fps": "fps",
    "height": "height",
    "width": "width",
}
_SNIPPET_RE = re.compile(
    r"\b(num_inference_steps|guidance_scale|true_cfg_scale|shift|num_frames|fps|height|width)"
    r"\s*=\s*([0-9]+(?:\.[0-9]+)?)"
)
_PROSE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # "trained for 15000 steps" is not a recommendation, and the old pattern had no leading \b, so
    # it matched the LAST THREE DIGITS of any longer run and produced steps: 0 -- a value nobody
    # wrote, outranking the family table. A digit run is one contiguous \w block, and \b only sits
    # at the edges of that block (digit-to-digit is never a boundary) -- so anchoring both ends of
    # the capture with \b means a 4+-digit run (a training step count, an epoch count, a parameter
    # count) can never match at all, not even partially: there is no boundary to land the \b on
    # except at the true start and end of the whole run.
    ("steps", re.compile(r"\b(\d{1,3})\b\s*(?:inference\s*)?steps\b", re.I)),
    ("cfg", re.compile(r"\bcfg(?:\s*scale)?\s*(?:of|=|:)?\s*([0-9]+(?:\.[0-9]+)?)", re.I)),
    ("guidance", re.compile(r"\bguidance(?:\s*scale)?\s*(?:of|=|:)?\s*([0-9]+(?:\.[0-9]+)?)", re.I)),
    ("shift", re.compile(r"\bshift\s*(?:of|=|:)?\s*([0-9]+(?:\.[0-9]+)?)", re.I)),
)


class HfClient:
    def __init__(self, token: str | None = None, *, opener: Any = None, timeout: float = 25.0):
        self.token = str(token or "").strip() or None
        self._opener = opener or urllib.request.build_opener()
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, url: str) -> str | None:
        request = urllib.request.Request(url, headers=self._headers())
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                return None
            raise

    def model_info(self, repo: str) -> dict[str, Any] | None:
        body = self._get(f"{API}/{str(repo).strip('/')}?blobs=true")
        if not body:
            return None
        try:
            payload = json.loads(body)
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    def readme(self, repo: str) -> str:
        return self._get(f"{RESOLVE}/{str(repo).strip('/')}/raw/main/README.md") or ""


def sha256_index(info: dict[str, Any] | None) -> dict[str, str]:
    """{sha256: rfilename} for every LFS sibling. Empty without `?blobs=true`."""
    out: dict[str, str] = {}
    for sibling in (info or {}).get("siblings") or []:
        lfs = sibling.get("lfs") if isinstance(sibling, dict) else None
        digest = str((lfs or {}).get("sha256") or "").lower()
        if len(digest) == 64:
            out[digest] = str(sibling.get("rfilename") or "")
    return out


def card_identity(info: dict[str, Any] | None) -> dict[str, Any]:
    card = (info or {}).get("cardData") or {}
    base = card.get("base_model")
    if isinstance(base, list):
        base = base[0] if base else None
    return {
        "license": card.get("license"),
        "license_name": card.get("license_name"),
        "base_model": base,
        "library_name": (info or {}).get("library_name") or card.get("library_name"),
        "pipeline_tag": (info or {}).get("pipeline_tag") or card.get("pipeline_tag"),
        "instance_prompt": card.get("instance_prompt"),
        "gated": (info or {}).get("gated"),
    }


def settings_from_readme(text: str) -> dict[str, dict[str, Any]]:
    """Settings a card states. Snippet kwargs outrank prose; nothing found means nothing returned."""
    body = str(text or "")
    out: dict[str, dict[str, Any]] = {}

    for match in _SNIPPET_RE.finditer(body):
        field = _SNIPPET_KEYS[match.group(1)]
        raw = match.group(2)
        value = float(raw) if "." in raw else int(raw)
        if field == "steps" and not (1 <= float(value) <= 300):
            # A snippet is code the author actually ran, but a stray 0 (or an out-of-range
            # figure a regex misread) is still not an inference-step count any sampler would
            # accept -- never invent/keep a value nobody could have meant.
            continue
        out[field] = {"value": value, "provenance": "card:snippet-regex"}

    for field, pattern in _PROSE_PATTERNS:
        if field in out:
            continue
        match = pattern.search(body)
        if not match:
            continue
        raw = match.group(1)
        value = float(raw) if "." in raw else int(raw)
        if field == "steps" and not (1 <= float(value) <= 300):
            # "0 steps" is the boundary case the leading \b fix above does not cover on its own --
            # a single-digit run of "0" is a genuine \b-bounded token, so it still matches the
            # pattern. It is never a real recommendation either way, so bound the result instead of
            # trusting whatever the regex happened to capture.
            continue
        out[field] = {"value": value, "provenance": "card:prose-regex"}

    return out
