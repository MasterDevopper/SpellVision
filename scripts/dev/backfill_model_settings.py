"""Backfill publisher-stated SETTINGS into the sidecars already on disk, from HuggingFace cards.

The T5 gap, measured over the owner's 759 sidecars on 2026-09-18: sdxl 269 of 287 weights carried a
value a publisher actually stated, while **ltx 0 of 21, hunyuan_video 0 of 7 and mochi 0 of 2** did.
Every video family fell back entirely to `family_seed_table` -- the floor the whole model-defaults
arc exists to replace -- and not for want of supply: `Lightricks/LTX-2.3`'s card yields
`steps 8 / cfg 1`. CivitAI simply HAS those files, so the HuggingFace arm was never reached, and a
CivitAI video post's `images[].meta` carries no sampler settings.

This is a script rather than a test for the same reason `backfill_model_metadata.py` is: the result
worth keeping is a per-family before/after over the live library, not a green tick. It does not
re-hash, does not download previews, and writes the `recommended` block plus (where it gained one) a
`huggingface` entry in `identity.sources` naming where the numbers came from.

    python scripts/dev/backfill_model_settings.py --roots D:/AI_ASSETS/models F:/AI_ASSETS/models
    python scripts/dev/backfill_model_settings.py --roots F:/AI_ASSETS/models --dry-run

Reads are anonymous. No key is sent, read or written by this script.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from model_intelligence import backfill, card_settings, readable_roots, settings_backfill  # noqa: E402


def census(roots: list[str]) -> dict[str, dict[str, int]]:
    """Per family: how many weights carry a publisher-stated (non-table) value RIGHT NOW.

    THE deliverable. Run before and after and printed as a pair, because "the mechanism works" and
    "the library has the answers" are different claims and only the second one is the arc's goal.
    """
    per: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"models": 0, "real": 0, "site": 0, "card": 0})
    for path in backfill.sidecar_files(roots):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        family = ((payload.get("identity") or {}).get("family")) or "(unclassified)"
        row = per[family]
        row["models"] += 1
        provenances = [str((entry or {}).get("provenance") or "")
                       for entry in (payload.get("recommended") or {}).values()
                       if isinstance(entry, dict)]
        if any(p.startswith(("site:", "card:")) or p == "user" for p in provenances):
            row["real"] += 1
        if any(p.startswith("site:") for p in provenances):
            row["site"] += 1
        if any(p.startswith("card:") for p in provenances):
            row["card"] += 1
    return dict(per)


def print_table(before: dict[str, dict[str, int]], after: dict[str, dict[str, int]]) -> None:
    print(f"\n{'family':18} {'models':>6} {'real before':>12} {'real after':>11} {'card:*':>7}")
    families = sorted(set(before) | set(after), key=lambda f: -(after.get(f, {}).get("models", 0)))
    for family in families:
        b = before.get(family, {"models": 0, "real": 0, "card": 0})
        a = after.get(family, {"models": 0, "real": 0, "card": 0})
        print(f"{family:18} {a['models']:>6} {b['real']:>12} {a['real']:>11} {a['card']:>7}")


def _needs_card(path: Path) -> bool:
    """A sidecar this pass still has work to do on -- the same gate the job applies, so `--only-
    missing` after a 429 costs a re-run of what it missed rather than of everything."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return card_settings.needs_card_settings((payload or {}).get("recommended"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", nargs="+", required=True)
    parser.add_argument("--limit", type=int, default=0, help="stop after N sidecars (0 = all)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pace", type=float, default=0.0,
                        help="seconds to wait before each HuggingFace read; the first "
                             "live pass was throttled on 56 of 172 weights without it")
    parser.add_argument("--only-missing", action="store_true",
                        help="visit only sidecars with no site-stated setting -- what to run after "
                             "a 429 ended a pass part-way through")
    args = parser.parse_args()

    for status in (readable_roots.root_status(root) for root in args.roots):
        print(f"root {status['path']}: "
              f"{'readable' if status['readable'] else 'SKIPPED (' + status['reason'] + ')'}")

    before = census(args.roots)

    files = None
    if args.only_missing:
        files = [path for path in backfill.sidecar_files(args.roots) if _needs_card(path)]
        print(f"only-missing: {len(files)} sidecars with nothing the site stated")

    started = time.time()
    seen = {"n": 0}

    def progress(done: int, total: int, name: str) -> None:
        seen["n"] = done
        if done % 25 == 0 or done == total:
            rate = done / max(time.time() - started, 0.001)
            print(f"  {done}/{total}  {rate:.1f} sidecars/s")

    result = settings_backfill.SettingsBackfillJob(
        args.roots,
        files=files,
        progress=progress,
        cancel=(lambda: bool(args.limit) and seen["n"] >= args.limit) if args.limit else None,
        dry_run=args.dry_run,
        pace=args.pace,
    ).run()
    elapsed = time.time() - started

    print(json.dumps({k: v for k, v in result.items() if k != "roots"}, indent=1)[:6000])
    print(f"\nelapsed {elapsed / 60:.1f} min")

    print_table(before, census(args.roots))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
