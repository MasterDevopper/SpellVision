"""Jarvis reads the night's frames as the owner would, and writes his own assessment.

Owner instruction (2026-09-05 01:50): "tap Jarvis to look through the images as if it were me and
write his own assessment and I'll read through both yours and Jarvis". So this is an INDEPENDENT
read -- Jarvis is not shown the gate verdicts, the face-texture numbers or Claude's notes. He is
given the owner's own acceptance criteria (PICK.md, the same-game test in 002_REPEATABLE_FACTORS)
and the teacher plate, and asked to keep or reject each frame the way the owner does.

Jarvis is the engine's united interface over the local model stack
(SpellBound-Engine/tools/jarvis, stack.toml). Two passes:

  1. SEE  -- the vision role (gemma4:12b) reads every frame of every finished race against the
             rubric and returns one JSON verdict per frame.
  2. WRITE -- the same model, without images, is given the verdict table and writes the assessment
             in the owner's terms. The reason role is NOT used tonight: stack.toml binds it to the
             node's card, which is rendering the night run; a 16.5 GB reasoner beside a 20 GB
             render is a contest the render loses. Say so in the header rather than pretend.

Runs incrementally: a race whose assessment JSON already exists is skipped, so it can be pointed at
the roots again as more races finish.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, "C:/Users/xXste/Code_Projects/SpellBound-Engine/tools")
import jarvis  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
TEACHER = Path("C:/Users/xXste/OneDrive/Pictures/Game characters/_locks/002_orc_teacher/plate.png")
PICK = Path("C:/Users/xXste/OneDrive/Pictures/Game characters/PICK.md")
FACTORS = REPO / "runtime/style/datasets/wrought_house_v1/002_REPEATABLE_FACTORS.md"

RUBRIC = """You are grading a candidate still for a game-character style dataset. The FIRST image is
the style teacher (an orc swordswoman plate the owner locked as the in-game look). The SECOND image
is the candidate. Grade the candidate against the teacher and the owner's own criteria below. Be the
owner: blunt, specific, no praise padding.

OWNER'S KEEP CRITERIA (PICK.md):
- WROUGHT: dark studio, one hard key light, materials read as real (leather grain, metal edge wear,
  cloth weave) -- NOT a photograph, NOT oil-sketch/painterly, NOT CGI catalog, NOT anime/cel.
- Age about 20-25 (up to ~30 ok). Old, lined, haggard faces fail.
- Race reads at a glance. Beast folk and dragonborn are KEMONOMIMI: human face + ears/horns/scales,
  NO animal head, NO muzzle.
- Cloth texture readable.
- Fit hourglass / the race's body band: not plus-size, not skinny-stick. Female must read female
  (waist, hips, bust), never "a man with breasts".
- Do NOT throw away a good face because the outfit is wrong.

SAME-GAME TEST (002_REPEATABLE_FACTORS section 7): keep only if ALL true --
1 one hard key, almost no fill; 2 worked leather/metal at the teacher's density; 3 skin is not a
pore-photo and not a cel; 4 full earth/iron colour, not muted, not neon; 5 face is a PERSON, not a
mask and not a hag; 6 you could swap the clothes and believe she exists in the teacher's world.

Reply with ONLY a JSON object, no prose before or after:
{"keep": true|false, "score": 1-10, "style": "wrought"|"photo"|"painterly"|"cgi"|"anime",
 "age_read": "20s"|"30s"|"40+", "race_reads": true|false, "female_reads": true|false,
 "body": "fit"|"heavy"|"thin", "fails": ["short reason", ...], "note": "one sentence as the owner"}
"""

WRITEUP = """You are Jarvis, writing for the owner who asked you to look through a night's worth of
generated character frames "as if it were me" and give your own assessment. Below are your per-frame
verdicts for one race (you produced them by looking at each frame against the owner's PICK.md and
the 002 same-game test). Write the race's assessment in the owner's voice and terms: what the race
is doing right, what is systematically wrong (name the pattern and cite frame numbers), which frames
you would keep for the LoRA set, and what you would change in the prompt or the criteria. Blunt,
specific, no padding, under 350 words. Markdown, starting with a '### {race}' heading.

Verdicts (frame: json):
{table}
"""


def thumb(path: Path, side: int = 640) -> Path:
    """A downscaled copy for the vision model -- it reads at 640 as well as at 1344 and 4x faster."""
    # Keyed by root as well as race dir: human_woman exists under BOTH night roots with overlapping
    # indices, and a race-dir-only key had one root's thumbnails overwriting the other's.
    out = (Path(sys.argv[0]).resolve().parent.parent.parent / "runtime" / "_jarvis_thumbs"
           / f"{path.parent.parent.name}__{path.parent.name}")
    out.mkdir(parents=True, exist_ok=True)
    dst = out / path.name
    if not dst.exists():
        im = Image.open(path).convert("RGB")
        im.thumbnail((side, side))
        im.save(dst, quality=88)
    return dst


def parse_json(text: str) -> dict | None:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def assess_race(race: str, frames: list[Path], out_dir: Path, teacher: Path,
                max_frames: int | None, rng: random.Random) -> dict:
    result_path = out_dir / f"_jarvis_{race}.json"
    if result_path.exists():
        return json.loads(result_path.read_text(encoding="utf-8"))
    if max_frames and len(frames) > max_frames:
        frames = sorted(rng.sample(frames, max_frames))
    verdicts: dict[str, dict] = {}
    t0 = time.time()
    for i, f in enumerate(frames):
        reply = jarvis.see(RUBRIC, images=[str(teacher), str(thumb(f))])
        v = parse_json(reply.text) if reply.ok else None
        # Keyed by root AND stem: human is split across two roots with overlapping indices, and a
        # stem-only key collided a hundred verdicts into sixty.
        verdicts[f"{f.parent.parent.name}/{f.stem}"] = v or {"keep": None, "error": (reply.text or "")[:200]}
        if (i + 1) % 10 == 0:
            print(f"  {race}: {i + 1}/{len(frames)} ({time.time() - t0:.0f}s)", flush=True)
    result = {"race": race, "model": reply.model, "frames": len(frames), "verdicts": verdicts,
              "seconds": round(time.time() - t0)}
    result_path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def write_up(race: str, result: dict) -> str:
    table = "\n".join(f"{k}: {json.dumps(v)}" for k, v in result["verdicts"].items())
    reply = jarvis.call("vision", WRITEUP.format(race=race, table=table))
    return reply.text.strip() if reply.ok else f"### {race}\n\n(write-up failed: {reply.text[:200]})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+")
    parser.add_argument("--out", default=str(REPO / "runtime/wrought_night/_audit"))
    parser.add_argument("--max-per-race", type=int, default=None,
                        help="sample this many frames per race instead of all (time bound)")
    parser.add_argument("--only-finished", action="store_true",
                        help="skip a race unless its _summary.json exists (the generator writes "
                             "it at the end of the batch)")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    teacher = thumb(TEACHER)
    rng = random.Random(args.seed)

    health = jarvis.health()
    print("jarvis stack:", {k: v for k, v in health.items() if k in ("vision",)} or health, flush=True)

    races: dict[str, list[Path]] = {}
    for root in map(Path, args.roots):
        for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name.endswith("_woman")):
            if args.only_finished and not (d / "_summary.json").exists():
                continue
            races.setdefault(d.name[:-len("_woman")], []).extend(sorted(d.glob("[0-9][0-9][0-9].png")))

    sections = []
    totals = {"frames": 0, "keep": 0}
    for race, frames in sorted(races.items()):
        print(f"== {race}: {len(frames)} frames", flush=True)
        result = assess_race(race, frames, out, teacher, args.max_per_race, rng)
        keep = sum(1 for v in result["verdicts"].values() if v.get("keep") is True)
        totals["frames"] += result["frames"]; totals["keep"] += keep
        sections.append(write_up(race, result))
        # write after every race so a partial run still leaves a readable file
        header = (f"# Jarvis's assessment of the night run\n\n"
                  f"Read by `{result['model']}` (the stack's vision role) against the teacher plate, "
                  f"PICK.md and the 002 same-game test, frame by frame; write-ups by the same model "
                  f"from its own verdicts. The reason role was not used: stack.toml binds it to the "
                  f"node's card, which was rendering the night run. Independent of Claude's read -- "
                  f"no gate verdicts or metrics were shown.\n\n"
                  f"**{totals['keep']} of {totals['frames']} frames kept so far.**\n\n")
        (out / "_JARVIS_ASSESSMENT.md").write_text(header + "\n\n".join(sections) + "\n", encoding="utf-8")
        print(f"   {race}: keep {keep}/{result['frames']} in {result['seconds']}s", flush=True)
    print(f"wrote {out / '_JARVIS_ASSESSMENT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
