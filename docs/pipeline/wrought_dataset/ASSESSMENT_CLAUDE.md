# Claude's assessment of the night run

*Written 09:45, 2026-09-05, six races in; completed 13:25 with all nine — 900 frames, 836 through
the gate (92%). Jarvis's independent read is in `_JARVIS_ASSESSMENT.md`
beside the audit sheets — he was shown none of these numbers.*

Read against one plate: `_locks/002_orc_teacher/plate.png`. Keep criteria: PICK.md and the
same-game test in `002_REPEATABLE_FACTORS.md` §7.

## The one-line verdict

**The register holds.** Across 900 frames the dark studio, the single hard key, the tooled leather
and beaten metal, the full earth-and-iron colour and the paint-pocket skin are there on nearly
every frame — 92% through the calibrated gate, and the failures are overwhelmingly specular on
plate or pale scale, not drift. The photoreal slide that wasted earlier batches is gone; the
face-texture measure that catches it sits at p50 0.41–0.48 on every human-faced race, against
0.82–0.94 for the batch that prompted it. The prompt overhaul from your own notes did that, and it
did it before the first frame rendered.

**The defect that matters for training is identity, not style** — and it splits the night in two.
Orc, goblin and dark elf rendered before the identity axis: each is one woman a hundred times. Every
race that started after 03:58 varies face, hair, skin and (for dragonborn) lineage. For a style LoRA
the first group teaches the trigger a face; the second teaches it a look.

## Per race

**Orc (100, gate 91).** Sits next to 002 — 001, 005, 041, 046, 056 could be her sisters. Tusks
present and three-dimensional on nearly every frame; the "white lip cut" collapse LESSONS_ORC
recorded is gone. Two faults: **one face** (pre-axis), and **the green is weak** — a third of the
set reads as a tanned human with tusks (003, 010, 043). Both were the model's single prior filling
what the prompt left open; both are fixed for any re-run (`SKIN_BY_RACE`). Keep candidates: the
figure-framed light-armour and working-tier frames; skip the nine gloss failures (three are the
v20Quants white blowout — 023, 093, 097). Ages 61/29/10.

**Dark elf (100, gate 98).** The strongest race of the night. Obsidian skin with the violet cast,
pupil-less luminous eyes on every frame, worked leather at the teacher's density, no coverage leak.
Rendered before the age trim, so 13 "weathered and old" and 13 middle-aged — thin those in the
picks. One face (pre-axis), white hair on all (correct for the race regardless). Face-texture
false positive on this race: 097 (1.025) and 069 (0.67) are ordinary; dark skin under white hair
puts hard edges in the crop.

**Goblin (100, gate 97).** Race reads on every frame — ears, sallow green, compact band — and the
faces vary more than the orc's even without the axis. Two bald frames (023, 038; fixed
downstream). **Three speckle artifacts passed the gate** (020, 025, 029) — the new advisory flag
lists nine, of which those three plus 016, 045, 054, 099, 095 are real. Reject those.

**Dragonborn (100, gate 79).** The identity axis landed here first and it shows: faces, hair,
skin and lineage all vary; kemonomimi holds on every frame; claws and tails present. Your reference
was a red; the set has all ten. The 21 gloss failures follow lineage — white 4/10 and silver 7/14
pass, everything else ≈100% — pale scale under a hard key throws a specular the organic rule
counts against skin. **Do not use the face-texture number on this race** (p50 0.67): the temple and
cheek scales sit inside the face crop and are high-frequency by design. Keep candidates: any
non-pale lineage that passed; the pale ones by eye.

**Dwarf (100, gate 94).** **Reads as a dwarf.** Stocky, short-limbed, about five and a half heads,
broad through the shoulders — 010 is the proof frame. This closes your "short fat human woman"
note. Hair red / black / blonde / auburn / grey-streaked; skins ruddy / freckled / brown / tan.
Freckled skin inflates face texture (nine flags, none photographs) and fine weave trips the speckle
flag (of ten, only 020 and 022 are real). A few older reads (016) from the middle-aged tail.

**Beastfolk (100, gate 94).** The cleanest kemonomimi set — human face, ears, small horns, fur
markings on skin, tails, faces varying, body band curvy-athletic. One speckle artifact (019).

**High elf (100, gate 95).** Elegant, varied (platinum, black, chestnut, silver-white), pale
skins as drawn. Two or three frames lean anime-smooth (011, 016) — the Class C floor let them
through; worth an eye. 004 carries the white-blowout artifact and neither flag caught it (the
speckle measure sees chroma noise; the white variety is what gloss usually catches, and here it
didn't). Hair drawn silver-white 29 / platinum 22 / gold 21 / chestnut 16 / black 12.

**Wood elf (100, gate 92).** Athletic and well-fed on every frame seen — your "malnourished" note
from the peak sheet is closed. Coppery / warm brown / tan olive / deep copper skins, auburn / black /
red / chestnut hair, green and leaf-trimmed kit. Face texture p50 0.44, the tightest band of the
night. Two speckle artifacts (000, 015); three dark "fine" frames failed the material floor.

**Human (100, gate 96).** Both halves in. Skins across all six tones on both boxes, builds across
the Bible's five bands, faces and hair varying; nothing systematic to flag. The most ordinary race
by design and the cleanest gate after dark elf and goblin.

## What I would do before training

1. **Pick from the post-axis races first** (dragonborn, dwarf, beastfolk, high elf, wood elf,
   human) and take orc / dark elf / goblin sparingly — a dozen each, chosen for *different* frames
   (framing, tier, light), so the single face is diluted rather than reinforced.
2. **Reject on sight, not on number:** the speckle/blowout frames (goblin 020/025/029/016/045/054/
   099/095; dwarf 020/022; orc 023/093/097; high elf 004; beastfolk 019) and the pale-lineage gloss
   frames you don't like. The advisory numbers rank; four of them have a documented false positive
   each (scales, freckles, weave, white hair) and none of them should be a threshold yet.
3. **Re-run orc and dark elf with the current vocabulary** if you want them at full weight — ~2 h
   each on spellnode. The green fix and the identity axis are both waiting for them.
4. **Pull `qwen3vl_4b_bf16.safetensors`** (Comfy-Org/Qwen3-VL, ~8 GB) — the only blocker the
   training rig has; the fp8-scaled encoder on disk cannot be loaded strictly.
5. Then `collect_wrought_picks.py picks.txt` → `train_wrought_lora.ps1 -Name wrought_v1`.

## On Jarvis's read (final, 13:25)

He kept **186 of 900** (20%) against the gate's 92%, and his keeps are wildly race-dependent: orc
55, goblin 55, dragonborn 23, wood elf 23, high elf 15, beastfolk 7, dwarf 4, dark elf 4, human 0. His
style label explains the shape — dwarf 93/100 "photo", high elf 67 "photo", human ~90/100 "photo",
while orc and goblin are 55 "wrought" each. The races he passes are the ones that look like the
teacher plate he was shown beside every candidate (an orc, green, warm earth); the races he calls
photographs are the pale human-skinned ones. Read that as an anchoring effect of the two-image
rubric rather than as 93 photographic dwarves — the face-texture measure, which has no teacher in
front of it, puts dwarf at p50 0.46 and high elf at 0.46, the same band as the orc he keeps.

Where the two reads *agree* is the useful part: 168 of his 186 keeps also passed the gate. Those
168 are the strictest possible pick list — both a rule-based gate and an independent eye said yes.
`_jarvis_<race>.json` carries his per-frame verdict and one-sentence note if you want them beside
the sheets. His full write-up: `ASSESSMENT_JARVIS.md` (a copy of `_audit/_JARVIS_ASSESSMENT.md`).

## What the night proved about the process

- The owner's graded notes were the missing input; every prompt law that fixed the drift was
  already written down in August.
- A negative prunes, only the positive builds — coverage, hairline, and (in the identity axis)
  colour all needed stating.
- A whole-subject number for a per-material law was wrong a fifth and sixth time tonight (speckle
  on scales, face texture on freckles). Each time the fix was the same: scope the number to the
  race's own baseline, and let it rank rather than decide.
- Every fix landed from the *next* race onward without touching a running one — a fresh subprocess
  per race was the right shape for an unattended night.
