"""Run a real model-intelligence refresh over the live libraries and print a report.

This is the wave's live proof. It is a script rather than a test because the full pass is about
79 minutes on this box (759 files, 2.09 TB) -- far past any suite's budget -- and because the
result worth keeping is a table the walkthrough can quote, not a green tick.

    python scripts/dev/refresh_model_intelligence.py --roots D:/AI_ASSETS/models F:/AI_ASSETS/models
    python scripts/dev/refresh_model_intelligence.py --roots F:/AI_ASSETS/models --limit 40
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from credential_store import get_credential  # noqa: E402
from model_intelligence import readable_roots, refresh, sidecar  # noqa: E402
from model_intelligence.civitai_lookup import CivitaiClient  # noqa: E402
from model_intelligence.hf_lookup import HfClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", nargs="+", required=True)
    parser.add_argument("--limit", type=int, default=0, help="stop after N files (0 = all)")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    for status in (readable_roots.root_status(root) for root in args.roots):
        print(f"root {status['path']}: "
              f"{'readable' if status['readable'] else 'SKIPPED (' + status['reason'] + ')'}")

    started = time.time()
    seen = {"n": 0}

    def progress(done: int, total: int, name: str) -> None:
        seen["n"] = done
        if done % 10 == 0 or done == total:
            rate = done / max(time.time() - started, 0.001)
            print(f"  {done}/{total}  {rate:.1f} files/s  {name}")

    job = refresh.RefreshJob(
        args.roots,
        client=CivitaiClient(api_key=get_credential("civitai_api_key")),
        # The second arm. Public cards need no token; a stored one buys rate-limit headroom only.
        hf=HfClient(token=get_credential("hf_token")),
        models_root=args.roots[0],
        progress=progress,
        cancel=(lambda: args.limit and seen["n"] >= args.limit) if args.limit else None,
        force=args.force,
    )
    result = job.run()
    elapsed = time.time() - started

    print(json.dumps({k: v for k, v in result.items() if k != "roots"}, indent=1)[:2000])
    print(f"\nelapsed {elapsed / 60:.1f} min")

    identified = []
    for root in args.roots:
        for path in Path(root).rglob("*.spellvision.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            rec = payload.get("recommended") or {}
            steps = (rec.get("steps") or {})
            if steps.get("provenance") == "site:image-meta-mode":
                identified.append((path.stem.replace(".spellvision", ""),
                                   steps.get("value"), steps.get("n"),
                                   (rec.get("cfg") or {}).get("value"),
                                   (rec.get("sampler") or {}).get("value")))
    print(f"\n{len(identified)} models carry site-sourced settings:")
    for name, steps, n, cfg, sampler in sorted(identified)[:40]:
        print(f"  {name[:48]:48} steps={steps} (n={n}) cfg={cfg} sampler={sampler}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
