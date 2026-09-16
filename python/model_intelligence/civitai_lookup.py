"""CivitAI reads. Identification by hash, no key required.

Measured 2026-09-16 against the live API with the owner's read-only key:

  * `GET /api/v1/model-versions/by-hash/{sha256}` hit 4 of 4 local weights, and the ANONYMOUS
    response was identical to the keyed one. A key buys downloads and mature previews, nothing
    here. So an absent key is a normal state, never an error.
  * `civitai.red` -- Civitai's official NSFW front door since 2026-04-15 -- served byte-identical
    JSON for the same hash. The host is therefore a setting, defaulting to civitai.com, and
    restricted to the two official spellings so a typo cannot send the owner's key elsewhere.
  * an all-zero hash answers 404. That is a MISS. Most local weights will miss, and a miss must
    cost nothing.

No published rate limit exists, so 429 is retried with jittered backoff and then surfaced rather
than swallowed: a silent give-up would look exactly like "this model is not on CivitAI".
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Sequence

DEFAULT_HOST = "civitai.com"
ALLOWED_HOSTS = frozenset({"civitai.com", "civitai.red"})
USER_AGENT = "SpellVision/1.0 (+https://github.com/MasterDevopper)"
MAX_BULK = 100
MAX_ATTEMPTS = 4


class CivitaiThrottled(RuntimeError):
    """429 survived every retry."""


class CivitaiClient:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        api_key: str | None = None,
        *,
        opener: Any = None,
        timeout: float = 25.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        cleaned = str(host or DEFAULT_HOST).strip().lower().removeprefix("https://").strip("/")
        if cleaned not in ALLOWED_HOSTS:
            raise ValueError(f"host must be one of {sorted(ALLOWED_HOSTS)}, got {host!r}")
        self.host = cleaned
        self.api_key = str(api_key or "").strip() or None
        self._opener = opener or urllib.request
        self._timeout = timeout
        self._sleep = sleep

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, path: str, *, data: bytes | None = None) -> Any:
        url = f"https://{self.host}/api/v1/{path.lstrip('/')}"
        headers = self._headers()
        if data is not None:
            headers["Content-Type"] = "application/json"
        last: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            request = urllib.request.Request(url, data=data, headers=headers)
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return None
                if exc.code != 429:
                    raise
                last = exc
                if attempt < MAX_ATTEMPTS - 1:
                    self._sleep(min(8.0, 2**attempt) + random.random())
        raise CivitaiThrottled(f"429 from {self.host} after {MAX_ATTEMPTS} attempts") from last

    def by_hash(self, sha256_hex: str) -> dict[str, Any] | None:
        digest = str(sha256_hex or "").strip().lower()
        if not digest:
            return None
        payload = self._request(f"model-versions/by-hash/{digest}")
        return payload if isinstance(payload, dict) else None

    def by_hashes(self, hashes: Sequence[str]) -> dict[str, dict[str, Any]]:
        """Bulk by-hash. Returns only the hashes that matched, keyed by the hash we asked for."""
        wanted = [str(h or "").strip().lower() for h in hashes if str(h or "").strip()]
        found: dict[str, dict[str, Any]] = {}
        for start in range(0, len(wanted), MAX_BULK):
            batch = wanted[start : start + MAX_BULK]
            payload = self._request(
                "model-versions/by-hash", data=json.dumps(batch).encode("utf-8")
            )
            for version in payload or []:
                if not isinstance(version, dict):
                    continue
                for file_entry in version.get("files") or []:
                    for value in (file_entry.get("hashes") or {}).values():
                        key = str(value or "").lower()
                        if key in batch:
                            found[key] = version
        return found

    def model(self, model_id: int) -> dict[str, Any] | None:
        payload = self._request(f"models/{int(model_id)}")
        return payload if isinstance(payload, dict) else None
