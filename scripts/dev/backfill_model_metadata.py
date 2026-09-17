"""Backfill `display.creator` and `display.license` into the sidecars already on disk.

Doc 62 section 3k. The by-hash lookup the 2026-09-17 refresh ran identifies a weight but carries
no creator and no licence flag; only the PARENT model payload does, and nothing ever fetched it.
This reads the model id each sidecar already recorded and fills the two fields in place.

It is a script rather than a test for the same reason `refresh_model_intelligence.py` is: the
result worth keeping is a before/after count over the live library, not a green tick. It does not
re-hash, does not download previews and rewrites nothing but those two fields.

    python scripts/dev/backfill_model_metadata.py --roots D:/AI_ASSETS/models F:/AI_ASSETS/models
    python scripts/dev/backfill_model_metadata.py --roots F:/AI_ASSETS/models --dry-run

Reads are anonymous by default: the CivitAI reply was measured identical with and without a key
(`civitai_lookup`'s docstring), so a key is never required. `--use-key` reads the owner's stored
key through the credential store for rate-limit headroom; it is never printed or written.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from model_intelligence import backfill, readable_roots  # noqa: E402
from model_intelligence.civitai_lookup import CivitaiClient  # noqa: E402


def census(roots: list[str]) -> dict[str, int]:
    """How many sidecars carry each field RIGHT NOW. Run before and after, printed as a pair."""
    counts = {"sidecars": 0, "identified": 0, "creator": 0, "license_flags": 0, "license_name": 0}
    for path in backfill.sidecar_files(roots):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        counts["sidecars"] += 1
        if backfill.civitai_model_id(payload) is not None:
            counts["identified"] += 1
        display = payload.get("display") or {}
        if display.get("creator"):
            counts["creator"] += 1
        licence = display.get("license") or {}
        if any(licence.get(flag) is not None for flag in ("allowCommercialUse", "allowDerivatives",
                                                          "allowNoCredit", "allowDifferentLicense")):
            counts["license_flags"] += 1
        if licence.get("name"):
            counts["license_name"] += 1
    return counts


def _needs_licence(path: Path) -> bool:
    """A sidecar this pass still has work to do on.

    CivitAI answered 429 for 76 of the 759 on the first live pass (2026-09-17), which is the whole
    reason this exists: a throttle must cost a re-run of what it missed, not of everything.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    licence = (payload.get("display") or {}).get("license") or {}
    return not any(licence.get(flag) is not None for flag in
                   ("allowCommercialUse", "allowDerivatives", "allowNoCredit", "allowDifferentLicense"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", nargs="+", required=True)
    parser.add_argument("--limit", type=int, default=0, help="stop after N sidecars (0 = all)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--use-key", action="store_true",
                        help="send the stored CivitAI key; reads work anonymously without it")
    parser.add_argument("--only-missing", action="store_true",
                        help="visit only sidecars that still have no licence flags -- what to run "
                             "after a 429 ended a pass part-way through")
    args = parser.parse_args()

    for status in (readable_roots.root_status(root) for root in args.roots):
        print(f"root {status['path']}: "
              f"{'readable' if status['readable'] else 'SKIPPED (' + status['reason'] + ')'}")

    before = census(args.roots)
    print(f"before: {json.dumps(before)}")

    api_key = None
    if args.use_key:
        from credential_store import get_credential

        api_key = get_credential("civitai_api_key")
        print(f"key: {'present' if api_key else 'absent -- continuing anonymously'}")

    started = time.time()
    seen = {"n": 0}

    def progress(done: int, total: int, name: str) -> None:
        seen["n"] = done
        if done % 25 == 0 or done == total:
            rate = done / max(time.time() - started, 0.001)
            print(f"  {done}/{total}  {rate:.1f} sidecars/s")

    files = None
    if args.only_missing:
        files = [path for path in backfill.sidecar_files(args.roots) if _needs_licence(path)]
        print(f"only-missing: {len(files)} sidecars still unfilled")

    result = backfill.BackfillJob(
        args.roots,
        client=CivitaiClient(api_key=api_key),
        files=files,
        progress=progress,
        cancel=(lambda: bool(args.limit) and seen["n"] >= args.limit) if args.limit else None,
        dry_run=args.dry_run,
    ).run()
    elapsed = time.time() - started

    print(json.dumps({k: v for k, v in result.items() if k != "roots"}, indent=1)[:4000])
    print(f"\nelapsed {elapsed / 60:.1f} min")

    after = census(args.roots)
    print(f"after:  {json.dumps(after)}")
    for field in ("creator", "license_flags", "license_name"):
        print(f"  {field}: {before[field]} -> {after[field]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
