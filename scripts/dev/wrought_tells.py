# scripts/dev/wrought_tells.py
"""The AI-look tells, read by Jarvis's vision role and gated as CHANGE DETECTION against the locks.

Measured 2026-09-05 on the night run: every race scored 7.5-8/10 for "reads as AI", and so did the
002 teacher plate (8: symmetry, light everywhere, gloss, generic face). A score threshold would fail
the truth. So this never scores; it counts NAMED TELLS at a fixed vocabulary, calibrates their rates
on the owner's keeper set (the locks + 002), and rejects a batch only when a tell's rate exceeds the
keeper rate by more than a stated margin. Jarvis's sign-off condition (DIRECTION_V2 section 8): the
calibration run is completed and the keeper rates logged before any batch is released.

Margin = max(FLOOR, 2 * sqrt(p(1-p)/n_batch)) -- a two-sigma binomial band around the keeper rate p
with a floor so a rate of 0 is not a hair trigger. Both numbers are stated here and re-derived in
the calibration task from the keeper spread; they are not taste.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
JARVIS_TOOLS = Path("C:/Users/xXste/Code_Projects/SpellBound-Engine/tools")

TELLS = ("plastic_skin", "waxy_skin", "perfect_symmetry", "centered_stock_pose", "light_from_everywhere",
         "everything_in_focus", "no_grain", "oversaturated", "glossy_sheen", "generic_pretty_face",
         "cluttered_ornament")
TELLS_QUESTION = (
    "Look at this generated fantasy character still and answer in JSON only.\n"
    '"ai_tells": list the visual tells that make it read as AI-generated, from this vocabulary only, '
    "strongest first: " + json.dumps(list(TELLS) + ["none"]) + ".\n"
    '"ai_score": 1-10 how strongly it reads as AI art (10 = obvious).\n'
    '{"ai_tells": [...], "ai_score": n}'
)
FLOOR = 0.15


def _jarvis_ask(prompt: str, image: str) -> str:
    sys.path.insert(0, str(JARVIS_TOOLS))
    import jarvis  # noqa: WPS433 -- lazy so the module imports without the engine
    reply = jarvis.see(prompt, images=[image])
    return reply.text if reply.ok else ""


def thumb(path: Path, side: int = 640) -> Path:
    """A 640 px copy for the vision model, keyed by root AND directory (human lived under two roots)."""
    out = REPO / "runtime" / "_jarvis_thumbs" / f"{path.parent.parent.name}__{path.parent.name}"
    out.mkdir(parents=True, exist_ok=True)
    dst = out / path.name
    if not dst.exists():
        im = Image.open(path).convert("RGB")
        im.thumbnail((side, side))
        im.save(dst)
    return dst


def _parse(text: str) -> dict | None:
    a, b = text.find("{"), text.rfind("}")
    if a == -1 or b == -1:
        return None
    try:
        return json.loads(text[a:b + 1])
    except json.JSONDecodeError:
        return None


def ask_json(path: Path, question: str, ask=None) -> dict:
    ask = ask or _jarvis_ask
    text = ask(question, str(thumb(Path(path))))
    parsed = _parse(text or "")
    return parsed if parsed is not None else {"error": (text or "")[:200]}


def read_frame(path: Path, ask=None) -> dict:
    r = ask_json(path, TELLS_QUESTION, ask)
    if "error" in r:
        return r
    r["ai_tells"] = [x for x in r.get("ai_tells", []) if x in TELLS]
    return r


def rates(readings: list[dict]) -> dict[str, float]:
    readable = [r for r in readings if "error" not in r]
    n = max(len(readable), 1)
    return {tell: sum(tell in r.get("ai_tells", []) for r in readable) / n for tell in TELLS}


def calibrate(paths: list[Path], out_json: Path, ask=None) -> dict:
    readings = [read_frame(p, ask) for p in paths]
    result = {"n": sum("error" not in r for r in readings), "rates": rates(readings),
              "frames": [str(p) for p in paths], "readings": readings}
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


@dataclass
class GateVerdict:
    ok: bool
    n: int
    offending: list[dict] = field(default_factory=list)


def gate(batch: list[dict], keeper: dict, floor: float = FLOOR) -> GateVerdict:
    batch_rates = rates(batch)
    n = max(sum("error" not in r for r in batch), 1)
    offending = []
    for tell in TELLS:
        p = keeper["rates"].get(tell, 0.0)
        limit = max(floor, 2 * math.sqrt(p * (1 - p) / n))
        if batch_rates[tell] > p + limit:
            offending.append({"tell": tell, "batch_rate": batch_rates[tell], "keeper_rate": p, "limit": limit})
    return GateVerdict(ok=not offending, n=n, offending=offending)


AXES = ("tier", "dialect", "nation", "framing", "light", "subspecies", "appearance")


def covary(records: list[dict], tell: str) -> list[tuple[str, float]]:
    """Which axis VALUE carries the tell: rate of the tell among frames with that value, best first."""
    hits: dict[str, list[int]] = collections.defaultdict(list)
    for rec in records:
        v = rec.get("variation", {})
        carry = int(tell in rec.get("_tells", []))
        for axis in AXES:
            val = v.get(axis)
            if val:
                hits[f"{axis}={val}"].append(carry)
    scored = [(k, sum(xs) / len(xs)) for k, xs in hits.items() if len(xs) >= 2]
    return sorted(scored, key=lambda kv: -kv[1])


def _frames(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in args:
        p = Path(raw)
        out.extend(sorted(p.glob("*.png")) if p.is_dir() else [p])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("probe", "calibrate", "gate"):
        s = sub.add_parser(name)
        s.add_argument("paths", nargs="+")
        s.add_argument("--out", default=None)
        s.add_argument("--keeper", default=str(REPO / "runtime/wrought_gate/keeper_rates.json"))
    args = parser.parse_args()
    frames = _frames(args.paths)
    if args.cmd == "calibrate":
        result = calibrate(frames, Path(args.out or REPO / "runtime/wrought_gate/keeper_rates.json"))
        print(json.dumps({"n": result["n"], "rates": result["rates"]}, indent=1))
        return 0
    readings = [read_frame(p) for p in frames]
    if args.out:
        Path(args.out).write_text(json.dumps(readings, indent=1), encoding="utf-8")
    print(json.dumps(rates(readings), indent=1))
    if args.cmd == "gate":
        keeper = json.loads(Path(args.keeper).read_text(encoding="utf-8"))
        verdict = gate(readings, keeper)
        print("GATE", "PASS" if verdict.ok else "REJECT", json.dumps(verdict.offending))
        return 0 if verdict.ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
