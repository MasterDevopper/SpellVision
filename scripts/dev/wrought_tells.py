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

CALIBRATED 2026-09-06 on the owner's keeper set -- the 17 locks under `_locks/` (002_orc_teacher,
bear_armor_w5 x6, bearfolk_r3, goblin_keep x8, human_002style; only 3 of the 17 are literally named
`plate.png`, which is why `_frames` falls back to an `rglob` when a directory has no top-level
PNGs). Jarvis's vision reading is not deterministic, so the calibration ran TWICE (n=17 both times)
to measure how much a rate can move on its own before any batch has changed:

| tell                  | run 1  | run 2  | abs diff |
|-----------------------|--------|--------|----------|
| plastic_skin          | 0.588  | 0.529  | 0.059    |
| waxy_skin             | 0.588  | 0.471  | 0.118    |
| perfect_symmetry      | 0.882  | 0.824  | 0.059    |
| centered_stock_pose   | 0.412  | 0.353  | 0.059    |
| light_from_everywhere | 0.471  | 0.235  | **0.235**|
| everything_in_focus   | 0.412  | 0.353  | 0.059    |
| no_grain              | 0.235  | 0.412  | 0.176    |
| oversaturated         | 0.000  | 0.000  | 0.000    |
| glossy_sheen          | 0.176  | 0.353  | 0.176    |
| generic_pretty_face   | 0.941  | 0.941  | 0.000    |
| cluttered_ornament    | 0.059  | 0.059  | 0.000    |

The largest run-to-run swing was `light_from_everywhere` at 0.235 (4/17 plates read differently),
rounded up to the nearest 0.05 -- FLOOR = max(0.15, 0.25) = **0.25**, wider than the 0.15 placeholder
this shipped with before a real keeper set existed.
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
FLOOR = 0.25
LAST_MODEL: str | None = None

# --- Task 15 probe questions (task-15-brief.md steps 1/2/4/5, task-15B-brief.md's controller
# amendments and its added same_person question). BEAST_QUESTION and DRAGON_QUESTION are the
# verbatim text blocks from task-15-brief.md steps 1 and 2; OUTFIT_QUESTION and FIGURE_QUESTION
# expand that brief's abbreviated field lists ("outfit": five words ...) into the same
# Answer-in-JSON-only template the other two already use, verbatim on every field description.
# All four (plus SAME_PERSON_QUESTION) are read through `ask_json` / `ask_json_pair`; none of them
# are called against Ollama in Phase 1 -- see the hermetic tests in tests/test_wrought_measures.py.
BEAST_QUESTION = (
    'Answer in JSON only. "species": the animal the ears and tail suggest, one of '
    '["leopard","bear","lion","deer","panda","wolf","fox","other","none"]. "horns": true/false '
    '(horns or antlers on the head). "human_ears": true/false (a second, human ear pair on the '
    'sides of the head). "fur_body": true/false (fur covering the body rather than skin). '
    '{"species": s, "horns": b, "human_ears": b, "fur_body": b}'
)
# DRAGON_QUESTION carries the "scale_coverage" field added by task-15B-brief's controller
# amendments (2026-09-06 10:10): report scale coverage below the jaw separately from the two
# clause versions on disk (named-places vs whole-body), which the dir name alone cannot tell --
# read `variation.lineage` and the skin prompt's own clause text from the record instead.
DRAGON_QUESTION = (
    'Answer in JSON only. "face_skin": two words for the skin tone of the face (e.g. "deep brown", '
    '"pale", "olive"). "scales_on_skin": true/false. "scales_on_garment": true/false (a scale '
    'pattern on the clothing). "scale_colour": one word. "scale_coverage": one of '
    '["whole","partial","none"] (how much of the body below the jaw shows scales). '
    '{"face_skin": s, "scales_on_skin": b, "scales_on_garment": b, "scale_colour": s, '
    '"scale_coverage": s}'
)
# task-15-brief.md step 4 gives only the field list ("outfit": five words naming the outfit,
# "hair": four words for the hairstyle, "candid": true/false ...); expanded here into the same
# template as BEAST_QUESTION/DRAGON_QUESTION, field wording unchanged.
OUTFIT_QUESTION = (
    'Answer in JSON only. "outfit": five words naming the outfit. "hair": four words for the '
    'hairstyle. "candid": true/false (off-centre, weight on one hip, gaze off-axis). '
    '{"outfit": s, "hair": s, "candid": b}'
)
# task-15-brief.md step 5, same expansion.
FIGURE_QUESTION = (
    'Answer in JSON only. "figure_present": true/false (a headless mannequin is not a figure). '
    '"object": three words. {"figure_present": b, "object": s}'
)
# task-15B-brief.md step 2, verbatim -- a pair question: both thumbs go to one `jarvis.see` call
# (see `ask_json_pair` / `_jarvis_ask_pair` below), never one call per image.
SAME_PERSON_QUESTION = (
    'Answer in JSON only. The two images are the same character in different clothes. '
    '"same_person": true/false, "reason": one short sentence. {"same_person": b, "reason": s}'
)


def _jarvis_ask(prompt: str, image: str) -> str:
    global LAST_MODEL
    if str(JARVIS_TOOLS) not in sys.path:
        sys.path.insert(0, str(JARVIS_TOOLS))
    import jarvis  # noqa: WPS433 -- lazy so the module imports without the engine
    reply = jarvis.see(prompt, images=[image])
    LAST_MODEL = reply.model
    return reply.text if reply.ok else ""


def _jarvis_ask_pair(prompt: str, image_a: str, image_b: str) -> str:
    """Like `_jarvis_ask`, but both images go to ONE `jarvis.see` call -- `same_person` needs to
    compare them, not read them separately."""
    global LAST_MODEL
    if str(JARVIS_TOOLS) not in sys.path:
        sys.path.insert(0, str(JARVIS_TOOLS))
    import jarvis  # noqa: WPS433
    reply = jarvis.see(prompt, images=[image_a, image_b])
    LAST_MODEL = reply.model
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
    """The last valid JSON object in the text, not the first -- a model that echoes the schema
    before answering (`schema: {...} ... my answer: {...}`) would otherwise have its answer
    swallowed by the echo."""
    decoder = json.JSONDecoder()
    best: dict | None = None
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            best = obj
    return best


def ask_json(path: Path, question: str, ask=None) -> dict:
    ask = ask or _jarvis_ask
    text = ask(question, str(thumb(Path(path))))
    parsed = _parse(text or "")
    return parsed if parsed is not None else {"error": (text or "")[:200]}


def ask_json_pair(path_a: Path, path_b: Path, question: str, ask=None) -> dict:
    """Like `ask_json`, for a question that compares two plates of the same character
    (`SAME_PERSON_QUESTION`) -- both thumbs go to one model call."""
    ask = ask or _jarvis_ask_pair
    text = ask(question, str(thumb(Path(path_a))), str(thumb(Path(path_b))))
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
              "model": LAST_MODEL or "injected",
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
    readable = sum("error" not in r for r in batch)
    if readable < max(3, len(batch) // 2):
        # Every rate below is computed over READABLE frames only, so a batch Jarvis mostly
        # failed to read would otherwise show every rate at zero and pass as clean -- success
        # reported by a component that saw nothing, the shape this repo keeps meeting.
        return GateVerdict(ok=False, n=readable, offending=[{
            "tell": "_unreadable", "batch_rate": readable / max(len(batch), 1),
            "keeper_rate": None, "limit": None,
            "reason": "fewer than half the frames were readable",
        }])
    batch_rates = rates(batch)
    n = max(readable, 1)
    offending = []
    for tell in TELLS:
        p = keeper.get("rates", {}).get(tell, 0.0)
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
    """A directory's own PNGs, or -- when it holds none at its top level -- every PNG under it.

    The owner's keeper set (`_locks/`) is one subfolder per lock, and only 3 of the 17 plates are
    literally named `plate.png`; a flat `*.png` glob on `_locks/` itself finds nothing. The same
    shape shows up on a Lane-A canvas-check root (`orc_woman/`, `human_woman/` subfolders, no PNG at
    the root): rglob over it gates the pair as one batch instead of needing a per-race invocation."""
    out: list[Path] = []
    for raw in args:
        p = Path(raw)
        if p.is_dir():
            top = sorted(p.glob("*.png"))
            out.extend(top if top else sorted(p.rglob("*.png")))
        else:
            out.append(p)
    return out


def _record_for(frame: Path) -> dict | None:
    """The `NNN.json` beside a frame -- `000_skin.png` / `000_suit.png` / `000_outfit.png` /
    `000_fit.png` all sit beside `000.json`; a legacy flat record (no lane suffix) is already
    `NNN.png` next to `NNN.json`, so stripping one leading `_<suffix>` segment covers both shapes.
    Returns None (never raises) when the JSON is missing -- a gate run against a plain frame list
    with no records beside it must still gate, just without covary annotation for that frame."""
    stem = frame.stem.split("_", 1)[0]
    j = frame.with_name(f"{stem}.json")
    if not j.exists():
        return None
    return json.loads(j.read_text(encoding="utf-8"))


def annotate_covary(offending: list[dict], frames: list[Path], readings: list[dict]) -> list[dict]:
    """For each offending tell, attach `covary`'s top three axis values -- which clause carries it.

    Builds the `records` covary needs (each with its own `_tells`) from the NNN.json beside every
    frame; a frame with no record alongside it (or that Jarvis could not read) is simply left out
    of that build rather than failing the whole gate.
    """
    records = []
    for frame, reading in zip(frames, readings):
        rec = _record_for(frame)
        if rec is not None:
            records.append(dict(rec, _tells=reading.get("ai_tells", [])))
    for off in offending:
        off["covary_top3"] = covary(records, off["tell"])[:3]
    return offending


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("probe", "calibrate", "gate"):
        s = sub.add_parser(name)
        s.add_argument("paths", nargs="+")
        s.add_argument("--out", default=None)
        s.add_argument("--keeper", default=str(REPO / "runtime/wrought_gate/keeper_rates.json"))
        if name == "gate":
            s.add_argument("--records", action="store_true",
                            help="load the NNN.json beside each frame and print covary's top "
                                 "three axis values per offending tell")
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
        if args.records and not verdict.ok:
            annotate_covary(verdict.offending, frames, readings)
        print("GATE", "PASS" if verdict.ok else "REJECT", json.dumps(verdict.offending))
        return 0 if verdict.ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
