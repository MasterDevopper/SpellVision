"""Fill publisher-stated SETTINGS into the sidecars already on disk, from the HuggingFace card.

`refresh` now asks the card for a weight CivitAI identified and published no settings for
(`card_settings`), but that only helps a library someone re-refreshes. This does the same thing to
the 759 sidecars already written, and is a BACKFILL for the same three reasons `backfill.py` is:

  * **No re-hash.** Every sidecar already stores `identity.hashes.sha256`, which is exactly what
    confirms a HuggingFace repo. Re-running the refresh to add two numbers would cost the 58
    minutes the hashing pass cost.
  * **It writes the `recommended` block and nothing else.** Not the name, not the pictures, not the
    licence. The one identity fact it may add is a `huggingface` entry in `identity.sources`, so the
    file records WHERE the settings came from -- a value shown under a provenance caption whose
    source is not in the file is the defect this arc is about.
  * **A fetch that fails writes nothing.** `HfThrottled` is counted as `lookup_failed` and the file
    is left alone: "HuggingFace does not host this weight" and "we could not ask" are different
    facts, and reading the second as the first once cost 13 identifications while reporting zero
    errors.

The gate is `card_settings.needs_card_settings` -- a block with any `site:*` entry is skipped -- and
it is a COST control, not a safety one. `recommended.overlay` uses the same `_offer` the resolver
does, so a card value can only fill a field the site left empty, and can never displace `user`.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Sequence

from model_intelligence import backfill, card_settings, hf_lookup, readable_roots, recommended


def weight_for(sidecar_path: Path, payload: dict[str, Any] | None) -> Path:
    """The weight a sidecar describes.

    From `identity.file_name` when it is there, because that is the name with the real extension;
    the sidecar's own stem is the fallback and cannot know whether the weight is `.safetensors`,
    `.gguf` or `.pth`. Only the NAME is used here -- `hf_candidates.search_queries` reads the stem
    and the parent folder, and both are right either way.
    """
    name = str(((payload or {}).get("identity") or {}).get("file_name") or "").strip()
    if not name:
        name = sidecar_path.name[: -len(".spellvision.json")]
    return sidecar_path.parent / name


def sha256_of(payload: dict[str, Any] | None) -> str:
    digest = str((((payload or {}).get("identity") or {}).get("hashes") or {}).get("sha256") or "")
    return digest.strip().lower()


def _source_already_named(payload: dict[str, Any], repo: str) -> bool:
    for source in ((payload.get("identity") or {}).get("sources") or []):
        if isinstance(source, dict) and source.get("site") == "huggingface" \
                and str(source.get("repo") or "") == repo:
            return True
    return False


def apply_to_payload(payload: dict[str, Any], card: dict[str, Any] | None,
                     settings: dict[str, dict[str, Any]] | None) -> tuple[dict[str, Any], list[str]]:
    """Return (payload, the fields actually changed). Never mutates the argument."""
    block = payload.get("recommended") or {}
    merged = recommended.overlay(block, settings)
    changed = [field for field, entry in merged.items()
               if (block.get(field) or {}).get("provenance") != entry.get("provenance")
               or (block.get(field) or {}).get("value") != entry.get("value")]
    if not changed:
        return payload, []

    out = dict(payload)
    out["recommended"] = merged
    repo = str((card or {}).get("repo") or "")
    if repo and not _source_already_named(out, repo):
        identity = dict(out.get("identity") or {})
        identity["sources"] = list(identity.get("sources") or []) + [
            {"site": "huggingface", "repo": repo, "path": (card or {}).get("path")}
        ]
        out["identity"] = identity
    return out, changed


class SettingsBackfillJob:
    """One pass over the sidecars, filling `recommended` from the cards."""

    def __init__(
        self,
        roots: Sequence[str | Path],
        *,
        hf: Any = None,
        files: Sequence[str | Path] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        dry_run: bool = False,
        pace: float = 0.0,
    ) -> None:
        self.roots = list(roots)
        self.hf = hf if hf is not None else hf_lookup.HfClient()
        self.files = [Path(str(f)) for f in files] if files is not None else None
        self.progress = progress
        self.cancel = cancel
        self.dry_run = dry_run
        # Seconds to wait before each HuggingFace read. MEASURED, not guessed: the first live pass
        # over 172 sidecars was throttled on 56 of them, because `candidate_repos` issues up to 22
        # searches per weight and the anonymous rate limit is per-minute. `HfThrottled` means the
        # run reports those as `lookup_failed` rather than as "not on HuggingFace" -- which is the
        # bug it exists to prevent -- but a pass that throttles half its work is still a pass that
        # has to be re-run. Pacing costs wall time and buys a complete answer.
        self.pace = max(0.0, float(pace))
        # One index and one README cache for the whole pass: 21 LTX weights in one repo cost one
        # confirmation and one document.
        self.reader = card_settings.CardReader(self.hf)

    def run(self) -> dict[str, Any]:
        statuses = [readable_roots.root_status(root) for root in self.roots]
        files = list(self.files) if self.files is not None else backfill.sidecar_files(self.roots)
        total = len(files)
        examined = skipped_has_site = no_digest = no_repo = no_card_settings = 0
        lookup_failed = updated = unchanged = 0
        cancelled = False
        errors: list[dict[str, str]] = []

        for path in files:
            if self.cancel is not None and self.cancel():
                cancelled = True
                break
            examined += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                errors.append({"path": str(path), "error": f"unreadable sidecar: {exc}"})
                continue
            if not isinstance(payload, dict):
                errors.append({"path": str(path), "error": "sidecar is not an object"})
                continue

            if not card_settings.needs_card_settings(payload.get("recommended")):
                skipped_has_site += 1
                self._tick(examined, total, path)
                continue
            digest = sha256_of(payload)
            if len(digest) != 64:
                no_digest += 1
                self._tick(examined, total, path)
                continue

            if self.pace:
                time.sleep(self.pace)
            try:
                card, settings = self.reader.read(weight=weight_for(path, payload), sha256=digest)
            except hf_lookup.HfThrottled as exc:
                lookup_failed += 1
                errors.append({"path": str(path), "error": f"throttled: {exc}"})
                self._tick(examined, total, path)
                continue
            except Exception as exc:  # noqa: BLE001 -- one sidecar, never the pass
                lookup_failed += 1
                errors.append({"path": str(path), "error": f"huggingface: {exc}"})
                self._tick(examined, total, path)
                continue

            if not card:
                no_repo += 1
                self._tick(examined, total, path)
                continue
            if not settings:
                no_card_settings += 1
                self._tick(examined, total, path)
                continue

            merged, changed = apply_to_payload(payload, card, settings)
            if not changed:
                unchanged += 1
            else:
                updated += 1
                if not self.dry_run:
                    try:
                        _write(path, merged)
                    except OSError as exc:
                        updated -= 1
                        errors.append({"path": str(path), "error": f"write: {exc}"})
            self._tick(examined, total, path)

        return {
            "ok": True,
            "examined": examined,
            "updated": updated,
            "unchanged": unchanged,
            "skipped_has_site": skipped_has_site,
            "no_digest": no_digest,
            "no_repo": no_repo,
            "no_card_settings": no_card_settings,
            "lookup_failed": lookup_failed,
            "repos_confirmed": self.reader.repos_confirmed,
            "readmes_read": self.reader.readmes_read,
            "mirrors_used": self.reader.mirrors_used,
            "cancelled": cancelled,
            "dry_run": self.dry_run,
            "errors": errors,
            "roots": statuses,
            "total": total,
        }

    def _tick(self, examined: int, total: int, path: Path) -> None:
        if self.progress is not None:
            self.progress(examined, total, path.name)


def _write(path: Path, payload: dict[str, Any]) -> None:
    """The atomic replace `sidecar.write` performs, addressed by SIDECAR path -- see
    `backfill._write` for why a sidecar walker must not go through the weight-named door."""
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)
