"""HuggingFace model metadata, and the local sha256 index that stands in for a by-hash API.

HF has NO by-hash endpoint (verified 2026-09-16), so a local weight can only be identified here if
we already know which repo it might belong to. `?blobs=true` is what makes even that possible: the
flag adds `siblings[].lfs.sha256`, and without it `siblings` carries filenames only.

For settings, the diffusers snippet in a card is the most reliable machine-readable source --
`num_inference_steps=50, guidance_scale=3.5` is what the authors actually run -- so it outranks
the prose regexes, which are a genuine guess. SAMPLING kwargs only: see `_SNIPPET_KEYS` for the
measurement that took the canvas fields back out of it.
"""
from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

API = "https://huggingface.co/api/models"
RESOLVE = "https://huggingface.co"
USER_AGENT = "SpellVision/1.0"
MAX_ATTEMPTS = 4


class HfThrottled(RuntimeError):
    """429 survived every retry.

    Raised rather than swallowed, and the distinction is not academic: the candidate step asks HF
    up to 25 times per unidentified weight, so a run over a whole library WILL meet a 429. Before
    this existed, `_get` raised a bare HTTPError, `hf_candidates._search` caught it as "no
    candidates", and the weight was recorded as not on HuggingFace -- a throttle wearing the
    costume of an answer. Measured 2026-09-17: a pass that had already been identifying weights
    correctly dropped from 38/79 to 25/79 for exactly this reason, and reported no errors.
    """

# SAMPLING kwargs only. `height`, `width`, `num_frames` and `fps` were here until 2026-09-18 and
# every value they produced over the live library was wrong:
#
#   LTX23_video_vae_bf16   width 50      (the regex found `width` in prose that is not a canvas)
#   wan2.2_vae             512x512, 24 frames   (a VAE repo's demo snippet)
#   wan2.2_*_pov_* LoRAs   854x480, 16 frames @ 8 fps   (a LoRA pack's demo snippet)
#
# The distinction is real rather than a reaction to four bad rows. `num_inference_steps=28` in a
# card's snippet is the author STATING how to sample this weight; `height=512` in the same snippet
# is boilerplate from the diffusers template, copied into thousands of cards, and it describes the
# demo the author happened to render rather than a canvas the model wants. The prose regexes below
# have never claimed a canvas for the same reason.
#
# `recommended.FIELDS` still carries width/height/frames/fps -- the SITE's example images state
# them honestly (that is `site:image-meta-mode`, read from real renders of this model) and so does
# `family_seed_table`. It is the CARD-snippet route that cannot tell a canvas from a template.
_SNIPPET_KEYS = {
    "num_inference_steps": "steps",
    "guidance_scale": "guidance",
    "true_cfg_scale": "cfg",
    "shift": "shift",
}
_SNIPPET_RE = re.compile(
    r"\b(num_inference_steps|guidance_scale|true_cfg_scale|shift)"
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
    def __init__(self, token: str | None = None, *, opener: Any = None, timeout: float = 25.0,
                 sleep: Callable[[float], None] = time.sleep):
        self.token = str(token or "").strip() or None
        self._opener = opener or urllib.request.build_opener()
        self._timeout = timeout
        self._sleep = sleep

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, url: str) -> str | None:
        last: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            request = urllib.request.Request(url, headers=self._headers())
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    return response.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403, 404):
                    return None
                if exc.code != 429:
                    raise
                last = exc
                if attempt < MAX_ATTEMPTS - 1:
                    self._sleep(min(8.0, 2**attempt) + random.random())
        raise HfThrottled(f"429 from huggingface.co after {MAX_ATTEMPTS} attempts") from last

    def search(self, query: str, *, author: str | None = None, limit: int = 20) -> list[str]:
        """Repo ids matching a free-text query, most relevant first.

        The candidate step HF's missing by-hash endpoint forces (`hf_candidates`). Nothing here
        identifies anything on its own -- a search result is a GUESS, and only `sha256_index`
        confirms it -- so a failure to search is an empty list, never an exception worth the run.
        """
        text = str(query or "").strip()
        if len(text) < 3:
            return []
        params = {"search": text, "limit": str(int(limit))}
        if author:
            params["author"] = str(author)
        body = self._get(f"{API}?{urllib.parse.urlencode(params)}")
        if not body:
            return []
        try:
            payload = json.loads(body)
        except ValueError:
            return []
        if not isinstance(payload, list):
            return []
        return [str(entry.get("modelId") or entry.get("id") or "")
                for entry in payload if isinstance(entry, dict)]

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
