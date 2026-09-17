"""Fill creator and licence into sidecars that already know which model they are.

Doc 62 section 3k: `CivitaiClient.model()` existed and had no caller, so every identified sidecar
wrote `"creator": null` and a licence block of nulls -- 680 for 680 on this box. The by-hash
VERSION payload carries neither; only the parent model does.

This is a BACKFILL, not a refresh, and the distinction is the whole point of the module:

  * **No re-hash.** Every sidecar already stores `identity.sources[].model_id`. Re-running the
    full refresh to add two fields would cost the 58 minutes the hashing pass cost; reading the id
    the last run recorded costs one GET per DISTINCT model id -- 532 behind 680 weights here.
  * **It writes two fields and nothing else.** Not the name, not the pictures, not the
    `recommended` block. A backfill that re-derives everything is a refresh wearing a smaller
    name, and it would carry every risk a refresh carries for two fields' worth of benefit.
  * **A fetch that fails writes nothing.** "The site has no parent for this id" and "we could not
    ask" are different facts -- the same distinction `refresh.carry_forward` exists for. Only the
    first is recorded, as a `no_parent`; the second leaves the file untouched and is counted.

A value the USER set is never touched, in either the recorded shape: a display field that is a
dict carrying `user_override: true` is left exactly as it is, which is the same rule
`sidecar.merge` applies, expressed once more here because this writer does not go through merge.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Sequence

from model_intelligence import readable_roots, sidecar
from model_intelligence.civitai_lookup import CivitaiClient, CivitaiThrottled


def sidecar_files(roots: Sequence[str | Path]) -> list[Path]:
    """Every sidecar under the readable roots, in a stable order.

    A root that cannot be read is dropped by `readable_models_roots` rather than contributing
    zero files -- D:/AI_ASSETS can come up BitLocker-locked, and an empty inventory looks exactly
    like a successful scan of an empty library.
    """
    found: list[Path] = []
    for root in readable_roots.readable_models_roots(roots):
        found.extend(root.rglob("*" + sidecar.SUFFIX))
    return sorted(found, key=lambda p: str(p).lower())


def civitai_model_id(payload: dict[str, Any] | None) -> int | None:
    """The CivitAI model id a previous run recorded for this weight, or None."""
    for source in ((payload or {}).get("identity") or {}).get("sources") or []:
        if not isinstance(source, dict) or source.get("site") != "civitai":
            continue
        try:
            return int(source.get("model_id"))
        except (TypeError, ValueError):
            continue
    return None


def _is_user_set(value: Any) -> bool:
    return isinstance(value, dict) and bool(value.get("user_override"))


def apply_to_payload(payload: dict[str, Any], parent: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """Return (payload, fields actually changed). Never mutates the argument.

    Only a field whose new value is non-empty is written, so a parent that states no creator
    cannot blank one a card-based source filled in later.
    """
    out = dict(payload)
    display = dict(out.get("display") or {})
    changed: list[str] = []

    creator = sidecar.creator_of(parent)
    if creator and not _is_user_set(display.get("creator")) and display.get("creator") != creator:
        display["creator"] = creator
        changed.append("creator")

    if not _is_user_set(display.get("license")):
        existing = display.get("license") if isinstance(display.get("license"), dict) else {}
        # The card's licence NAME is not ours to overwrite -- CivitAI states permissions, never an
        # SPDX name, so `name` keeps whatever is already there.
        fresh = sidecar.license_of(parent, {"license": (existing or {}).get("name")})
        merged = {**(existing or {}), **{k: v for k, v in fresh.items() if v is not None}}
        if merged != existing:
            display["license"] = merged
            changed.append("license")

    if changed:
        out["display"] = display
    return out, changed


class BackfillJob:
    """One pass over the sidecars, filling creator and licence from the parent model."""

    def __init__(
        self,
        roots: Sequence[str | Path],
        *,
        client: Any = None,
        files: Sequence[str | Path] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        dry_run: bool = False,
    ) -> None:
        self.roots = list(roots)
        self.client = client if client is not None else CivitaiClient()
        self.files = [Path(str(f)) for f in files] if files is not None else None
        self.progress = progress
        self.cancel = cancel
        self.dry_run = dry_run

    def _parent(self, model_id: int, path: Path, errors: list[dict[str, str]]) -> tuple[Any, bool]:
        """(parent, asked). `asked=False` means we never got an answer and must write nothing."""
        try:
            return self.client.model(model_id), True
        except CivitaiThrottled as exc:
            errors.append({"path": str(path), "error": f"throttled: {exc}"})
        except Exception as exc:  # noqa: BLE001 -- one model id, not the run
            errors.append({"path": str(path), "error": f"parent model {model_id}: {exc}"})
        return None, False

    def run(self) -> dict[str, Any]:
        statuses = [readable_roots.root_status(root) for root in self.roots]
        files = list(self.files) if self.files is not None else sidecar_files(self.roots)
        total = len(files)
        examined = no_model_id = no_parent = lookup_failed = updated = unchanged = 0
        model_ids: set[int] = set()
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

            model_id = civitai_model_id(payload)
            if model_id is None:
                no_model_id += 1
                self._tick(examined, total, path)
                continue
            model_ids.add(model_id)

            parent, asked = self._parent(model_id, path, errors)
            if not asked:
                lookup_failed += 1
                self._tick(examined, total, path)
                continue
            if parent is None:
                no_parent += 1
                self._tick(examined, total, path)
                continue

            merged, changed = apply_to_payload(payload, parent)
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
            "no_model_id": no_model_id,
            "no_parent": no_parent,
            "lookup_failed": lookup_failed,
            "distinct_model_ids": len(model_ids),
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
    """The same atomic replace `sidecar.write` performs, addressed by SIDECAR path.

    `sidecar.write` takes the WEIGHT and derives the sidecar name from its stem; a backfill that
    walks sidecars would have to reconstruct the weight's extension to use it, and a weight whose
    extension it guessed wrong would be written to a file that is not the one it read.
    """
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)
