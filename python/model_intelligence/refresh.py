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

TWO arms, in order. CivitAI answers by hash. A weight it does not know goes to HuggingFace, which
has no by-hash endpoint at all -- `hf_candidates` guesses a repo from the filename and the folder
and CONFIRMS it by sha256, so a wrong guess costs a request and can never mislabel a file. That
arm is skipped entirely when no `hf` client is given, and it only ever sees a real MISS: a lookup
that FAILED is not evidence that CivitAI lacks the weight. Until 2026-09-17 there was no second
arm, and the summary's `no_match: 79, lookup_failed: 0` read as "both sites were asked".

**Identity and settings are two questions, and the arms answer them on different schedules**
(2026-09-18). A CivitAI hit ends the search for IDENTITY -- that is what a hash match establishes,
and asking the other site again would spend up to 25 requests per weight for a name we already
have. It does NOT end the search for SETTINGS: CivitAI's `images[].meta` yields no sampler values
for a video post, so ltx 0/21, hunyuan_video 0/7 and mochi 0/2 carried a publisher-stated value
while CivitAI held the files. So a weight whose `recommended` block comes back with no `site:*`
entry at all is asked about a second time, for its card alone (`_card_settings_for`,
`model_intelligence/card_settings.py`), and `settings_from_card` is reported beside
`identified_hf` because the two are different facts.
"""
from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Any, Callable, Sequence

from model_intelligence import (
    card_settings,
    hashing,
    hf_candidates,
    kinds,
    previews,
    readable_roots,
    recommended,
    sidecar,
)
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
        # Shared across the whole run on purpose: a repackaged bundle holds a transformer, a VAE
        # and a text encoder that share no searchable name, so confirming one hands us the rest
        # for free (`hf_candidates.RepoIndex`). The reader adds a per-repo README cache on top,
        # because LTX is 21 files in one repo and that is otherwise 21 fetches of one document.
        self._hf_index = hf_candidates.RepoIndex(self.hf)
        self._cards = card_settings.CardReader(self.hf, index=self._hf_index)

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

    def _parent(self, version: Any, path: Path, errors: list[dict[str, str]]) -> Any:
        """The parent model behind a matched version -- the ONLY source of creator and licence.

        Kept separate from `_lookup` because its failure is cheaper: a weight with no parent is
        still identified, still named, still has its pictures and its settings. So a 404, a
        throttle or a dropped connection here records an error and writes nulls, and
        `sidecar.merge` declines to let those nulls erase what an earlier run established.

        `CivitaiClient.model` memoises by id, so this is one request per DISTINCT model id across
        a whole run, not one per weight -- 532 ids behind 680 identified weights on this box.
        """
        model_id = (version or {}).get("modelId")
        if not model_id:
            return None
        try:
            return self.client.model(model_id)
        except Exception as exc:  # noqa: BLE001 -- a missing licence never costs an identity
            errors.append({"path": str(path), "error": f"parent model {model_id}: {exc}"})
            return None

    def _hf(self, digest: str, path: Path, errors: list[dict[str, str]]) -> tuple[Any, Any]:
        """The second arm: ask HuggingFace about a weight CivitAI does not know.

        Only reached on a real MISS -- a CivitAI hit is already an identity, and a lookup that
        FAILED must not be treated as "CivitAI does not have it". Before this existed the summary
        said `no_match: 79, lookup_failed: 0`, which reads as "both sites were asked". One was.

        Returns (card, settings). `card` is the block `build_payload(hf=...)` wants; `settings` is
        what the repo's README states. Both None when nothing confirmed, which is the common answer
        and costs only searches.

        It is also reached on a CivitAI HIT whose settings are empty -- see `_card_settings_for`.
        That is not a contradiction of the paragraph above: a hit ends the search for IDENTITY, and
        identity is all a hit establishes.
        """
        if self.hf is None or not digest:
            return None, None
        try:
            return self._cards.read(weight=path, sha256=digest)
        except Exception as exc:  # noqa: BLE001 -- a per-file failure never aborts the run
            errors.append({"path": str(path), "error": f"huggingface: {exc}"})
            return None, None

    def _card_settings_for(self, block: dict[str, dict[str, Any]], digest: str, path: Path,
                           errors: list[dict[str, str]]) -> tuple[Any, dict[str, dict[str, Any]] | None]:
        """The card's settings for a weight CivitAI identified and said nothing useful about.

        `card_settings.needs_card_settings` is the gate, and it is a COST control rather than a
        safety one: `recommended.PROVENANCE_ORDER` ranks every `card:*` tier below every `site:*`
        settings tier, so a card can only fill a field the site left empty even if this ran on
        every weight. What the gate buys is that 587 of 759 weights never ask HuggingFace at all.

        Measured 2026-09-18 over the live library: ltx 0/21, hunyuan_video 0/7 and mochi 0/2
        carried a publisher-stated value, while CivitAI held the files for 14, 2 and 2 of them --
        so those are identified weights whose settings nobody had asked the right site about.

        The CARD comes back too, and is handed to `build_payload` alongside the CivitAI version.
        Every identity field there already prefers the version (`name` from `model.name`,
        `base_model` from `version.baseModel or card.base_model`), so nothing is overwritten -- what
        it adds is `identity.sources[]` naming the repo the settings were read from. A number shown
        under a provenance caption whose source is not in the file is the defect this arc is about.
        """
        if self.hf is None or not digest or not card_settings.needs_card_settings(block):
            return None, None
        card, settings = self._hf(digest, path, errors)
        return card, (settings or None)

    def run(self) -> dict[str, Any]:
        statuses = [readable_roots.root_status(root) for root in self.roots]
        skipped = [status["path"] for status in statuses if not status["readable"]]

        files = list(self.files) if self.files is not None else plan(self.roots)
        cache = hashing.HashCache(self.cache_path)
        total = len(files)
        examined = identified = no_match = lookup_failed = identified_hf = 0
        # Counted apart from `identified_hf` on purpose: "HuggingFace holds these bytes" and
        # "HuggingFace's card is where this weight's steps came from" are different facts, and
        # the second is the one this arm was extended for.
        settings_from_card = 0
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
            card: Any = None  # the HuggingFace card, when the second arm confirmed a repo

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
                            version, models_root=self.models_root, sha256=digest, weight=path,
                            # Do not touch `<stem>.preview.jpg` when the user chose it. The
                            # sidecar merge keeps their ENTRY; without this the FILE it points at
                            # was overwritten anyway, so the promise held in the JSON and broke on
                            # disk.
                            preserve_cover=bool(sidecar.user_images(existing)),
                        )
                    except Exception as exc:  # noqa: BLE001 -- pictures never cost an identity
                        errors.append({"path": str(path), "error": f"previews: {exc}"})
                parent = self._parent(version, path, errors) if version else None
                # The local is `card_values`, not `card_settings`: that name is now the MODULE
                # holding the one rule for when a card is worth reading, and shadowing it here
                # would make the gate below resolve to a dict.
                card, card_values = (None, None) if version else self._hf(digest, path, errors)
                block = recommended.build(
                    civitai_version=version,
                    card_settings=card_values,
                    family=family,
                    existing_user=sidecar.user_values(existing),
                )
                # A CivitAI hit is an identity, not a set of settings. When the site published
                # nothing about how to render this weight, ask the card and rebuild through the
                # SAME precedence function -- never by patching the block, which would be a second
                # ordering. `civitai_version` is passed again unchanged, so identity and every
                # site value the first build found win exactly as they did.
                late_card, late = self._card_settings_for(block, digest, path, errors)
                if late:
                    block = recommended.build(
                        civitai_version=version,
                        card_settings=late,
                        family=family,
                        existing_user=sidecar.user_values(existing),
                    )
                    card = card or late_card
                    settings_from_card += 1
                payload = sidecar.merge(existing, sidecar.build_payload(
                    weight=path, sha256=digest, kind=kind, family=family,
                    civitai_version=version, hf=card, recommended=block,
                    images=images, fetched_at=now, civitai_model=parent,
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
            elif card:
                # Identified, by the OTHER site. Counted separately as well as in `identified`,
                # because "CivitAI knows this" and "a HuggingFace repo holds these exact bytes"
                # are different facts and a single total hides which arm is working.
                identified += 1
                identified_hf += 1
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
            "identified_hf": identified_hf,
            "settings_from_card": settings_from_card,
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
