"""Walk the model roots, identify everything, write the sidecars.

Sizing decides the shape. Measured 2026-09-16: 759 files / 2.09 TB, hashing at ~440 MB/s, so a
full first pass is about 79 minutes. That is long enough that the job must be cancellable, must
persist its hash cache as it goes, and must order SMALLEST FILE FIRST -- the 475 LoRAs are 130 GB
and land within minutes, so the library fills in visibly while the 937 GB of checkpoints grind.
Ordering by directory instead would leave the user staring at nothing for half an hour.

A root that cannot be read is reported by name. It is never allowed to contribute zero files to a
total, because a zero is indistinguishable from a successful scan of an empty folder.

Two rules about failure, both learned the expensive way:

  * **A lookup that FAILED must not overwrite identity.** "The site says it does not know this
    hash" and "we could not ask the site" are different facts. The first is a `no_match` and is
    safe to record; the second carried `civitai_version=None` into `build_payload`, which
    reverted `display.name` to the file stem and emptied `trigger_words`, `sources` and `images`
    -- so ONE offline refresh erased all 34 identities the previous run had fetched, and reported
    `ok: true` while doing it.
  * **A per-file failure is a per-file failure.** The guards caught `OSError` only, so a
    CivitAI-supplied preview URL raising `ValueError: unknown url type` aborted the whole
    79-minute run: out of `run()`, out of the command handler, out of the TCP dispatcher, leaving
    the caller with a dropped connection and a timeout rather than an error.
"""
from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Any, Callable, Sequence

from model_intelligence import hashing, kinds, previews, readable_roots, recommended, sidecar
from model_intelligence.civitai_lookup import CivitaiClient, CivitaiThrottled

log = logging.getLogger(__name__)

try:  # the classifier is optional in unit tests
    from model_classification import classify_model
except Exception:  # pragma: no cover - exercised only when the worker package is absent
    classify_model = None  # type: ignore[assignment]


def plan(
    roots: Sequence[str | Path],
    *,
    extensions: frozenset[str] = hashing.MODEL_EXTENSIONS,
) -> list[Path]:
    """Every weight under the readable roots, smallest first."""
    found: list[tuple[int, Path]] = []
    for root in readable_roots.readable_models_roots(roots):
        for path in root.rglob("*"):
            if path.suffix.lower() not in extensions:
                continue
            try:
                if not path.is_file():
                    continue
                found.append((path.stat().st_size, path))
            except OSError:
                continue
    found.sort(key=lambda pair: (pair[0], str(pair[1]).lower()))
    return [path for _size, path in found]


class RefreshJob:
    def __init__(
        self,
        roots: Sequence[str | Path],
        *,
        files: Sequence[str | Path] | None = None,
        client: Any = None,
        hf: Any = None,
        models_root: str | Path | None = None,
        cache_path: str | Path | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        force: bool = False,
    ) -> None:
        self.roots = list(roots)
        # `files` is the narrow entry point. The post-download hook knows exactly which file
        # landed; walking its whole destination directory instead re-identified every neighbour
        # on every download -- 475 files on the owner's loras/, 130 GB-sized ones on checkpoints/.
        self.files = [Path(str(f)) for f in files] if files is not None else None
        self.client = client if client is not None else CivitaiClient()
        self.hf = hf
        self.models_root = Path(str(models_root)) if models_root else (
            Path(str(self.roots[0])) if self.roots else Path(".")
        )
        self.cache_path = Path(str(cache_path)) if cache_path else (
            self.models_root / ".spellvision" / "hash_index.json"
        )
        self.progress = progress
        self.cancel = cancel
        self.force = force

    def _kind_and_family(self, path: Path) -> tuple[str, str | None]:
        if classify_model is None:
            return "other", None
        try:
            result = classify_model(str(path))
        except Exception:
            return "other", None
        # ONE vocabulary, shared with classify_models. And an undetermined family is None, not
        # the truthy string "unknown" -- see model_intelligence/kinds.py for what that cost.
        return (
            kinds.normalise_kind(getattr(result, "model_type", None)),
            kinds.normalise_family(getattr(result, "family", None)),
        )

    def _lookup(self, digest: str, path: Path, errors: list[dict[str, str]]) -> tuple[Any, bool]:
        """Returns (version, failed). `version=None, failed=False` is a real miss -- the site
        answered and does not know this hash. `failed=True` means we never got an answer, and the
        caller must not record that as "this model is unknown"."""
        try:
            return self.client.by_hash(digest), False
        except CivitaiThrottled as exc:
            errors.append({"path": str(path), "error": f"throttled: {exc}"})
        except Exception as exc:  # noqa: BLE001 -- a per-file failure never aborts the run
            errors.append({"path": str(path), "error": str(exc)})
        return None, True

    def run(self) -> dict[str, Any]:
        statuses = [readable_roots.root_status(root) for root in self.roots]
        skipped = [status["path"] for status in statuses if not status["readable"]]

        files = list(self.files) if self.files is not None else plan(self.roots)
        cache = hashing.HashCache(self.cache_path)
        total = len(files)
        examined = identified = no_match = lookup_failed = 0
        cancelled = False
        errors: list[dict[str, str]] = []
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()

        for path in files:
            if self.cancel is not None and self.cancel():
                cancelled = True
                break

            digest = None if self.force else cache.get(path)
            if digest is None:
                try:
                    # hash_and_cache owns the stamp-before/hash/stamp-after sequence: a file that
                    # changes while it is being hashed must not be cached under its new identity.
                    digest = hashing.hash_and_cache(cache, path, cancel=self.cancel)
                except Exception as exc:  # noqa: BLE001 -- one unreadable file, not the run
                    errors.append({"path": str(path), "error": str(exc)})
                    examined += 1
                    continue
                if digest is None:  # cancelled mid-file
                    cancelled = True
                    break

            version, failed = self._lookup(digest, path, errors)
            kind, family = self._kind_and_family(path)
            existing = sidecar.read(path)

            if failed:
                # We could not ask. Carry forward everything a previous successful run learned
                # and update only what THIS run established: hash, size, kind, family.
                payload = sidecar.carry_forward(
                    existing, weight=path, sha256=digest, kind=kind, family=family
                )
            else:
                images: list[dict[str, Any]] = []
                if version:
                    try:
                        images = previews.download_previews(
                            version, models_root=self.models_root, sha256=digest, weight=path
                        )
                    except Exception as exc:  # noqa: BLE001 -- pictures never cost an identity
                        errors.append({"path": str(path), "error": f"previews: {exc}"})
                block = recommended.build(
                    civitai_version=version,
                    card_settings=None,
                    family=family,
                    existing_user=sidecar.user_values(existing),
                )
                payload = sidecar.merge(existing, sidecar.build_payload(
                    weight=path, sha256=digest, kind=kind, family=family,
                    civitai_version=version, hf=None, recommended=block,
                    images=images, fetched_at=now,
                ))

            try:
                sidecar.write(path, payload)
            except Exception as exc:  # noqa: BLE001
                errors.append({"path": str(path), "error": f"sidecar: {exc}"})

            examined += 1
            if failed:
                lookup_failed += 1
            elif version:
                identified += 1
            else:
                no_match += 1
            if self.progress is not None:
                self.progress(examined, total, path.name)
            if examined % 25 == 0:
                _save_cache(cache, errors)

        _save_cache(cache, errors)
        return {
            "ok": True,
            "examined": examined,
            "identified": identified,
            "no_match": no_match,
            "lookup_failed": lookup_failed,
            "cancelled": cancelled,
            "skipped_unreadable": skipped,
            "errors": errors,
            "roots": statuses,
            "total": total,
        }


def _save_cache(cache: hashing.HashCache, errors: list[dict[str, str]]) -> None:
    """A cache write that fails costs time on the NEXT run. It must never cost THIS run's report:
    unguarded, an `os.replace` losing its temp file to a concurrent writer raised out of `run()`
    and the caller got a dropped connection instead of an hour's worth of results."""
    try:
        cache.save()
    except Exception as exc:  # noqa: BLE001
        log.warning("hash cache could not be saved to %s: %s", cache.path, exc)
        errors.append({"path": str(cache.path), "error": f"hash cache: {exc}"})


def refresh_one(
    path: str | Path,
    *,
    models_root: str | Path,
    client: Any = None,
    cache_path: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Identify ONE weight. This is the post-download hook's entry point: a file landed, so
    refresh that file rather than the directory it landed in."""
    return RefreshJob(
        [], files=[path], client=client, models_root=models_root,
        cache_path=cache_path, force=force,
    ).run()
