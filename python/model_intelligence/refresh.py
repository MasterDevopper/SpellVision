"""Walk the model roots, identify everything, write the sidecars.

Sizing decides the shape. Measured 2026-09-16: 759 files / 2.09 TB, hashing at ~440 MB/s, so a
full first pass is about 79 minutes. That is long enough that the job must be cancellable, must
persist its hash cache as it goes, and must order SMALLEST FILE FIRST -- the 475 LoRAs are 130 GB
and land within minutes, so the library fills in visibly while the 937 GB of checkpoints grind.
Ordering by directory instead would leave the user staring at nothing for half an hour.

A root that cannot be read is reported by name. It is never allowed to contribute zero files to a
total, because a zero is indistinguishable from a successful scan of an empty folder.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Callable, Sequence

from model_intelligence import hashing, previews, readable_roots, recommended, sidecar
from model_intelligence.civitai_lookup import CivitaiClient, CivitaiThrottled

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
        client: Any = None,
        hf: Any = None,
        models_root: str | Path | None = None,
        cache_path: str | Path | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        force: bool = False,
    ) -> None:
        self.roots = list(roots)
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
        return getattr(result, "model_type", "other") or "other", getattr(result, "family", None)

    def run(self) -> dict[str, Any]:
        statuses = [readable_roots.root_status(root) for root in self.roots]
        skipped = [status["path"] for status in statuses if not status["readable"]]

        files = plan(self.roots)
        cache = hashing.HashCache(self.cache_path)
        total = len(files)
        examined = identified = no_match = 0
        errors: list[dict[str, str]] = []
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()

        for path in files:
            if self.cancel is not None and self.cancel():
                break

            digest = None if self.force else cache.get(path)
            if digest is None:
                try:
                    # hash_and_cache owns the stamp-before/hash/stamp-after sequence: a file that
                    # changes while it is being hashed must not be cached under its new identity.
                    digest = hashing.hash_and_cache(cache, path, cancel=self.cancel)
                except OSError as exc:
                    errors.append({"path": str(path), "error": str(exc)})
                    examined += 1
                    continue
                if digest is None:  # cancelled mid-file
                    break

            version = None
            try:
                version = self.client.by_hash(digest)
            except CivitaiThrottled as exc:
                errors.append({"path": str(path), "error": f"throttled: {exc}"})
            except OSError as exc:
                errors.append({"path": str(path), "error": str(exc)})

            kind, family = self._kind_and_family(path)
            existing = sidecar.read(path)
            images = []
            if version:
                try:
                    images = previews.download_previews(
                        version, models_root=self.models_root, sha256=digest, weight=path
                    )
                except OSError as exc:
                    errors.append({"path": str(path), "error": f"previews: {exc}"})

            block = recommended.build(
                civitai_version=version,
                card_settings=None,
                family=family,
                existing_user=sidecar.user_values(existing),
            )
            payload = sidecar.build_payload(
                weight=path, sha256=digest, kind=kind, family=family,
                civitai_version=version, hf=None, recommended=block,
                images=images, fetched_at=now,
            )
            try:
                sidecar.write(path, sidecar.merge(existing, payload))
            except OSError as exc:
                errors.append({"path": str(path), "error": f"sidecar: {exc}"})

            examined += 1
            if version:
                identified += 1
            else:
                no_match += 1
            if self.progress is not None:
                self.progress(examined, total, path.name)
            if examined % 25 == 0:
                cache.save()

        cache.save()
        return {
            "ok": True,
            "examined": examined,
            "identified": identified,
            "no_match": no_match,
            "skipped_unreadable": skipped,
            "errors": errors,
            "roots": statuses,
            "total": total,
        }
