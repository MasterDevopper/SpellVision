# Wrought dataset — what was learned dialling it in (2026-09-04 → 05)

The record of the two-day pass that took the Wrought race vocabulary from "renders something" to
"renders next to 002", the evidence for each step, the prompts that produced it, and the night run
that came out of it. Every claim below points at a frame in [`evidence/`](evidence/) or a JSON
record under `runtime/`. Where a number is quoted, the script that measured it is named.

**Source of truth for the look is one image:** `_locks/002_orc_teacher/plate.png`
(= `runtime/style/datasets/wrought_house_v1/images/002.png`). Utopic v10BF16, seed 1002, 52 steps,
CFG 3.5, euler/simple, AuraFlow shift 1.15, 768×1024. Not a prompt — a plate. Everything is graded
against it, and the owner's own note on it is the governing document:
[`002_REPEATABLE_FACTORS.md`](../../../runtime/style/datasets/wrought_house_v1/002_REPEATABLE_FACTORS.md).

![002](evidence/00_teacher_002.jpg)

---

## 0. The finding that reorders everything else

**The owner had already graded most of this, and the vocabulary was authored without reading it.**

`runtime/style/datasets/wrought_house_v1/` holds his measured notes from August —
`KREA2_PROMPT_ENGINEERING.md`, `002_REPEATABLE_FACTORS.md`, `LESSONS_ORC.md`, `GOBLIN_10.md`,
`RACE_FEMALE_LOOK_LOCK.md` — plus the prompt pack and body cheatsheet one level up, and
`PICK.md` beside the locked plates. Four things the style block asked for were things he had
already graded as misses:

| the block asked for | the owner had graded | where |
|---|---|---|
| subject first, style last | *"house paint wants studio + PBR materials in the FIRST sentence, then the woman"*; subject-first plates *"went photoreal or anime"* | KREA2_PROMPT_ENGINEERING |
| `WROUGHT style` as the opening token | *"Never lead the prompt with the word WROUGHT — it burned in as gold title text"* (and it burned in here, on an axe blade) | LESSONS_ORC, GOBLIN_10, KREA2 notes |
| `painterly rendered surfaces` | W5 lock = *"002-lead + not painterly / not oil / not brushstrokes"*; every W4 nit is *"too painterly"* | KREA2_PROMPT_ENGINEERING |
| `controlled saturation, restrained palette` | *"Saturation is the game-character tell… NOT muted, not cinematic grade"*; bans `muted, desaturated, washed, grey-olive` | 002_REPEATABLE_FACTORS §4 |

That is where the photoreal drift the owner kept seeing came from. Not a mystery of the model —
a prompt asking for the graded failure. **Rule, now in memory: before authoring any prompt
vocabulary in this repo, read those files first.**

---

## 1. The instruments

Three scripts, all under `scripts/dev/`:

- **`generate_wrought_dataset.py`** — one race per invocation, reads materials/ornament/palette
  from the engine's `assets/content/cultures/<race>.ron`, draws a variation per frame from
  `wrought_variants.py`, renders through ComfyUI `/prompt`, fetches over HTTP `/view` (never a
  disk path — a remote endpoint's output dir is not this machine's), gates each frame, writes
  `NNN.png` + `NNN.json` (prompt, variation, seed, canvas, model, metrics, verdict).
- **`wrought_variants.py`** — the vocabulary. Race physiology (5e-grounded, then the owner's
  tweaks), the feminine invariant, dimorphism markers, heads, lineages, appearance tiers with the
  owner's floor, hair, clothing tiers, framing, light. Everything the owner edits lives here.
- **`check_wrought.py`** — the gate. Calibrated on the 17 locked plates, not chosen. Enforced:
  `detail_mid ≥ 0.030` (Class C floor — below it is anime-smooth / flat-lit), `material_floor ≥
  0.10` (no grimdark grade), `gloss_fraction ≤ 0.045` under `--organic`. Advisory: saturation
  (per-material law, whole-subject number), and — new tonight — face texture (§7).
- **`audit_wrought_night.py`** — the morning read: contact sheets per race, a drift sheet ranked by
  face texture, content-only captions beside every frame, one summary table.

Production config, measured against the model matrix on 09-04: **`loxsUtopicWorldKrea2_v20Quants`,
52 steps, CFG 3.5, euler/simple, shift 1.15**, canvas **768×1024 for portraits / 768×1344 for
figures** (the owner's locked sizes; the 832×1216 used before tonight matched no locked plate).

---

## 2. Peak beauty — "the objective, no matter who is looking, most beautiful women of each race"

![peak](evidence/01_peak_beauty_9_races.jpg)

`--peak` collapses the distribution to its best case: mid-twenties, the STRIKING tier, a portrait
framing, a flattering key. The first STRIKING text said *"beautiful by her own people's
standards"* — the opposite of the instruction; it tells the sampler to grade on a curve. Now:
*"a strikingly beautiful face by any standard… beautiful regardless of who is looking."*

Per-race reads from the owner, and what changed: dwarf "looks like a short fat human" → proportion
stated in heads (§6); dark elf "old" → young, unlined, flawless; wood elf "malnourished" → athletic
with a soft layer; goblin refined toward small/delicate; dragonborn "human face on a bipedal
dragon" → §4. Tusks: the owner's rule *"female orcs should have smaller tusks"* was generalised into
a `DIMORPHISM` table — every race's signature feature has a sexed expression, because a tusk reads
in a portrait crop where hips do not.

Records: `runtime/wrought_dataset/<race>_peak_woman/`.

---

## 3. The suit pass — the wardrobe was carrying the silhouette

![suit](evidence/02_suit_pass_8_races.jpg)

The standard clean-body garment: anthropometric scanning dresses a subject in a compression suit
because it adds a millimetre at the hip instead of a handspan, so the silhouette that comes out *is*
the body. The 002 regeneration met the same fact as a bug (a corset cinched the waist, pauldrons
squared the shoulders); a race judged in armour is judged in its armourer's taste. `--suit` swaps
only the garment and opens the framing to full body — the Wrought light law stays, because
`WROUGHT_NEG` forbids "flat lighting" by name and a flat-lit measurement frame would fail the gate
it is judged against.

![orc suit](evidence/13_orc_suit_wardrobe_carried_silhouette.jpg)

What the suit exposed, per frame record `orc_peak_suit_woman/000.json`:
- **Build was random across an 8-way list including "heavy and thick-set" and "slight and
  narrow"** — both ends PICK.md names as failures (*"not plus-size dump, not skinny stick"*), and
  `RACE_FEMALE_LOOK_LOCK` lists "one body for all races" as drift cause #1. Now `BUILD_BY_RACE`,
  the Vision Bible's own bands (Drow slim/lithe · elegant curvy · athletic-rogue; Goblin compact;
  Orc tall solid · warrior athletic · amazon curvy · lean raider; Human slim → amazon).
- **Orc tusks vanished** under "smaller, finer". LESSONS_ORC had recorded exactly this: *"Small
  tusks collapse to a white lip cut. Prompt 3D ivory tusks past the lip."* Now that phrasing.
- **Dwarf still read as a short human.** Breadth-versus-height language did nothing; both frames
  rendered a normal human head-count. Now stated the way figure drawing states it: *"about five and
  a half heads tall, short limbs against a long deep torso."*
- **Hands and feet human on every race**, dragonborn included. Open.

Prompt (suit, orc, seed 7700): `runtime/wrought_dataset/orc_peak_suit_woman/000.json`.

---

## 4. Dragonborn — four dragon heads, then the owner's reference

![four heads](evidence/03_dragonborn_four_dragon_heads.jpg)

The owner's read of the peak sheet — *"a human face on what otherwise would have been a bipedal
dragon… we will need to refine the look to find a good hybrid"* — was read as *go fully draconic*,
and the head could not even be varied until it was pulled out of the three places it was written
(race `core`, the `female` line, `FEMININE_FACE_OVERRIDE`) into one `HEAD_VARIANTS` table.
A: draconic · B: short muzzle · C: flat faced (collapsed to A — "no muzzle at all" lost to the
model's one prior for a dragon head) · D: crested.

Then the reference:

![owner reference](evidence/04_owner_reference_kemonomimi_dragonborn.jpg)

**Kemonomimi.** A human face carrying draconic features — scales as a skin treatment at the temples,
jaw and neck; ridged horns above the ears; long pointed ears; amber slit pupils; ordinary hair; the
scale and the claw pushed out to the limbs. The exemption had been mine: PICK.md and README state
the rule for the *world* (*"human face + ears/horns, NO ANIMAL HEADS"*), not for beastfolk. The
complaint was about a badly executed hybrid, not about hybridising. (The Vision Bible's row 7 says
"dragon head" — the owner's reference on 09-05 overrides it.)

Three dependents fell out rather than needing fixes: the feminine face override (a human face takes
`FEMININE_READ` like every other race), the horn-crest hair special case (hair follows the *head*),
and the full-hide scale description in the core (now says where the scale *lives* — heaviest at
forearms, shoulders, lower legs; lightest at the face).

![kemonomimi](evidence/07_kemonomimi_coverage_stated.jpg)

**The coverage lesson, learned twice in one hour.** First pass: 2 of 6 topless. The negative
`nude, topless, bare chest` already existed — in `SUIT_NEGATIVE`, so the one mode that *cannot*
produce the defect was the only mode defended. Moved to the shared negative: still 2 of 6. The
positive was already satisfied — an open riding coat over a bare torso *is* "wearing an oiled riding
coat". Stated: *"fully clothed, the garment closed and covering the chest, torso and legs
completely"* → 10 of 10 clothed. **A negative prunes; only the positive builds.** Third arrival of
that lesson here (the orthographic profile had to be described by its consequences; the appearance
tiers by their features).

Prompt: `runtime/wrought_dataset/dragonborn_peak_kemonomimi_woman/003.json`.

### Lineage

![lineages](evidence/08_dragonborn_ten_lineages.jpg)

*"There are red blue and black dragonborn."* The core had hardcoded *"bronze slate green or dull
red"* — one smeared average — so no lineage could be asked for. `LINEAGE` now holds all ten 5e
ancestries, keyed by race (beastfolk pelts want the same shape), drawn uniformly so a batch covers
them, `--lineage` pins one. Two clauses had to stop owning a colour: the core (scale colour) and the
head (*"amber eyes"* contradicts blue's pale gold). **Each feature has one owner clause** — the same
conflict as crest-versus-hair, upper-left-versus-the-light-axis, and three tusk clauses on one orc.

White and silver failed the gate on gloss (0.099 / 0.088 vs 0.045): a pale scale under a hard key
blows the specular. Stated matte in their own text rather than loosening the rule for everyone.

---

## 5. The photoreal measurement

The owner's instruction for the night: *"diverting to photoreal need to be critically handled or
the night run will be a waste."* The gate had **no photoreal criterion** — its docstring says
"micro-pore photoreal pushes energy high", and `detail_high` was measured, reported and never gated.
Measured: **42 of 125 session frames sat above the locks' `detail_high` maximum (0.0511), and 38
of them passed.**

A ceiling on that number would not have fixed it. Three deliberate photograph probes (style block
replaced by an explicit DSLR request — the negative class the gate had never seen):

![probes](evidence/09_photoreal_probes.jpg)

They measured `detail_high` 0.014–0.042 whole-subject — *inside* the locks' 0.0003–0.051.
Chainmail and scale are high-frequency and correct; a whole-subject band cannot tell a pore from a
rivet. That would have been the fifth whole-subject-number-for-a-per-material-law error in this
checker (gloss, crush, saturation floor, saturation ceiling before it).

The Look Matrix files micro-pore detail under §3 *Skin*, so the measurement lives on the face:
largest detected face, central 60% (cheeks, nose, brow), **native resolution** — `fine` = residual
under a 1.2 px blur (pore scale), `meso` = the 1.2–6 px band (form scale, Class C), ratio =
pore field against paint.

| set | `face_fine_over_meso` |
|---|---|
| photograph probes | 0.545 – 0.660 |
| locked plates (4 with a face ≥ 180 px) | 0.386 – 0.501 |
| early male orc batch (`runtime/wrought_dataset/orc/`) | 0.82 – 0.94 |

![extremes](evidence/10_face_texture_extremes.jpg)

Lowest ratios are the beastfolk frames — clean paint-pocket skin. Highest are the early orc batch —
pore-mapped, wrinkled, the *"documentary skin"* 002_REPEATABLE_FACTORS names. **Recorded in every
frame's JSON as advisory with a band label, not a gate criterion:** four locks is too thin a sample
to fail a frame on, and the threshold is set from a labelled hundred in the morning, not from four
tonight. `check_wrought.py --calibrate` over the keepers gives it a real sample.

---

## 6. The prompt after the owner's findings (what the night run uses)

Before (peak, dragonborn, seed 8900 — `dragonborn_peak_woman/000.json`):

> a single dragonborn woman, … , palette of bronze, slate, deep red-ochre, jade, **WROUGHT style**,
> grounded stylized realism, PBR-native, … , **controlled saturation, restrained palette, painterly
> rendered surfaces**

After (verification, orc, seed 31001 — `runtime/wrought_verify/orc_woman/001.json`):

> **A single strong directional key light in a dark studio, deep readable form shadows, almost no
> fill, no rim light, no set. Worked materials: tooled leather with flex creases and stitching,
> rivets seated in straps, beaten engraved metal that highlights only on its edges, matte chalky
> cloth with readable weave. Selective realism, not a photograph, not pore-level skin, not oil
> paint, not painterly, not cartoon. Full punchy earth and iron colour, not muted, not cinematic
> grade.** a single orc woman, a young adult in their mid-twenties, about twenty-five, a lean
> raider's build, greyish-green skin, lower tusks, … small but clearly three-dimensional ivory lower
> tusks rising past the lip, finer than an orc man's, unmistakably female, … wearing layered
> lamellar over a long padded coat, well kept but used, fully clothed, the garment closed and
> covering the chest, torso and legs completely, … head and shoulders portrait, key light from the
> upper left, materials of this culture: wrought iron, leather, fur, bone, unfinished timber, worn
> surfaces, trophy ornament, palette of ash, iron gray, oxblood, feast ember, grounded stylized
> realism, physically based materials, material truth, … skin with living colour variation and no
> pore field, busy on the kit and simple on the void, same paint as the orc swordswoman plate

![verify orc](evidence/11_verify_orc_002_lead.jpg)
![verify rest](evidence/12_verify_dragonborn_darkelf_dwarf.jpg)

Also folded in from the same documents: no rim light and nothing lit from below (both graded
misses — `LIGHT_WEIGHTED`, upper-left ×4); always a full hairline (*"bald / shaved scalp =
unattractive"*); the mid-twenties, where PICK.md's 20–25 and LESSONS_ORC's 25–30 overlap; the old
age tier removed for women and WEATHERED made a men's appearance tier (the beauty bell has no tier
below ordinary-attractive); race-keyed `tail` negative; the house negative merged; dark-elf eyes
pupil-less and luminous per the Bible; goblin *"adult head-to-body proportion, not a doll"* per
GOBLIN_10 r3.

The two verification frames that drew old faces are what prompted the age trim. The dwarf's cyan
coat is the culture palette's `forge ember`/`gold` rendered hot — a saturation breach the advisory
number will flag; not fixed tonight.

---

## 7. The night run (launched 01:32, 2026-09-05)

900 women, 9 races, one sex per batch as the owner directed. `v20Quants` @ 52, canvases by framing,
organic gate, face texture recorded. Two boxes, **one runner per endpoint, distinct output roots**
(two runners into one root collided on frame index earlier today — the later finisher won):

| box | out root | jobs | frames |
|---|---|---|---|
| spellnode 192.168.1.127 (3090 Ti, ~1.5× faster than the 5090 on this model — measured, not assumed) | `runtime/wrought_night/` | orc, goblin, dwarf, high_elf, wood_elf, human×60 | 560 |
| 5090 local | `runtime/wrought_night_b/` | dark_elf, dragonborn, beastfolk, human×40 | 340 |

Logs: `_log_spellnode.txt`, `_log_5090.txt` in each root. Launched as **detached OS processes**
(`Start-Process`), not harness background tasks — those cap at a 10-minute timeout and an 11-hour
run cannot sit on the hope that the cap is ignored. Runner: `runtime/night_run.py` (health-polls the
endpoint before each race, waits up to 20 minutes if it is down, retries a failed race once).
Known wart: the runner's per-frame echo filters on a left-stripped line and prints nothing; the
JSON records are the log.

**Morning:**

```
.venv\Scripts\python.exe scripts\dev\audit_wrought_night.py runtime\wrought_night runtime\wrought_night_b --captions
```

→ `runtime/wrought_night/_audit/`: `_AUDIT.md`, `<race>_pNN.png` (20 a page, judge here),
`<race>_drift_top20.png` (highest face texture first — look here for photoreal), and an `NNN.txt`
caption beside every frame (trigger first, content only, per Doc 43 — the style is learned from the
pixels, not the words).

**Two independent reads in the morning.** Owner instruction at 01:50: if he has not surfaced by
10:00, Jarvis reads the frames as if he were the owner and writes his own assessment, and the
owner reads both. `scripts/dev/jarvis_assess_wrought.py` drives the engine's united model
interface (`SpellBound-Engine/tools/jarvis`, `stack.toml`): the vision role (gemma4:12b, local)
grades every frame of every finished race against the teacher plate, PICK.md and the 002
same-game test — one JSON verdict per frame, then a per-race write-up from its own verdicts. It is
shown no gate verdicts and no metrics. The reason role stays untouched tonight because
`stack.toml` binds it to the node's card, which is rendering. Outputs:
`runtime/wrought_night/_audit/_JARVIS_ASSESSMENT.md` and `_CLAUDE_ASSESSMENT.md`.

### Night log

- **01:32 / 01:33** — both runners up. First frames carry `face_fine_over_meso`; the verification
  frames rendered before the patch do not.
- **01:40** — first read of orc 000–008 (`runtime/wrought_night/_audit/orc_p01.png`, attempt 1).
  Three of nine read older and harder than the dark elves. Attributed from the records, not the
  eye: 002 and 004 drew the "weathered and old" age tier, 004 and 006 drew the WEATHERED
  appearance tier (both already removed for the races still to come), 003 drew "close-cropped
  practical hair" and rendered shaved. Dark elf 000–004: nothing to fix.
- **01:44** — women's hair now always a full hairline (`56f8078`, LESSONS_ORC: "bald / shaved
  scalp = unattractive"). **Orc restarted on spellnode** — 9 frames lost, 91 gained under the
  corrected distribution; orc is the flagship race. Attempt-1 log kept as
  `_log_spellnode_attempt1.txt`. Runner's per-frame echo fixed at the same time (it stripped the
  wrong side of the line and printed nothing); the 5090 runner keeps the old copy loaded, so its
  log stays terse until it restarts.
- **03:46** — orc complete (attempt 2), 100 frames at 73 s/frame on spellnode. Gate 91/100; the
  nine failures are gloss — three of them the v20Quants white-blowout artifact (093, 097, 023 —
  the gate catching what it exists to catch), the rest plate cuirasses and a brigandine throwing a
  legitimate specular under a hard key, which is the "skin rule applied to a helmet" category error
  `check_wrought.py` already records. Face texture: 41 measured, p50 0.476, p90 0.609, five above
  0.60 (089, 004, 026, 007, 066) — borderline to the eye, and far from the 0.82–0.94 of the batch
  that prompted the measure. Ages 61/29/10 young/thirty/middle. No coverage leak in 100.
  **The systematic defect the sheets show is one woman a hundred times** — same face, dark hair,
  olive skin (`orc_p01.png`, `orc_p03.png`). The green is weak too: many frames read as a tanned
  human with tusks. Both are the model's single prior filling every slot the prompt left open.
- **03:58** — identity axis (`skin / hair colour / eyes / face shape / nose`, per race, drawn),
  with the race cores' colour ranges moved into the tables so there is one owner clause
  (`f098832`). Orc's green is now explicit and varied (olive / forest / grey-green
  slate / deep green). Applies from dwarf onward on spellnode and dragonborn onward on the 5090;
  orc, goblin and dark elf carry the old single face. Captions carry skin/face/eyes.
- **04:12** — dark elf complete, 100 frames at 96 s/frame on the 5090. Gate 98/100 (two gloss:
  046 a "fine" dress under a side key, 062 plate). The strongest race of the night so far: obsidian
  skin with the violet cast, pupil-less luminous eyes on every frame, worked leather at the
  teacher's density, no coverage leak (`dark_elf_p03.png`). Started at 01:33, before the age trim,
  so it carries the old tail: 13 "weathered and old", 13 middle-aged — the picks will thin it.
  Same single face across the set as the orc (the identity axis landed after it started).
  **Face texture has a false positive on this race:** 097 measured 1.025 and 069 0.670 and both
  look ordinary on the sheet — dark skin under stark white hair puts hard edges inside the face
  crop. The number ranks; it does not decide. Worth remembering when the threshold is set.
- **04:13** — dragonborn started on the 5090 with the identity axis live.
- **05:51** — goblin complete, 100 frames. Gate 97/100. Race reads on every frame — ears, sallow
  green, compact body band; faces vary more than the orc's did even without the identity axis
  (`goblin_p02.png`). Two frames rendered **bald** (023, 038 — both drew "wild and uncombed"): the
  shaved styles were already excluded, so the gap was the absence of a positive claim → the hair
  clause is now "a full head of *colour* hair" (`2c06cd1`). Three frames carry the **v20Quants
  speckle artifact and passed** (020, 025, 029 — iridescent cyan/white noise on a garment): gloss
  cannot see it and `detail_mid` is inflated by it. New advisory measure in the audit —
  chroma high-pass over the subject; artifacts 0.039–0.068 against clean 0.002–0.014 — flagged
  above 3× the race's own median (a flat threshold flagged 43 dragonborn, every one of them
  lineage scale). `goblin_speckle.png` lists nine.
- **05:55** — dragonborn at 63 with the identity axis live: faces, hair, skin and lineage all vary,
  kemonomimi on every frame (`dragonborn_p01.png`). Gate 48/63 — 15 gloss failures are pale
  lineages (white ×4, silver ×5) and polished plate throwing a specular the organic rule counts
  against skin. **Face texture is structurally inflated on this race** (p50 0.715): the scales at
  temple and cheek sit inside the face crop and are high-frequency by design, not photoreal. Rank
  only; do not threshold dragonborn on it.
- **06:53** — dragonborn complete, 100 frames. Gate 79/100; failures are gloss and they follow the
  lineage: white 4/10, silver 7/14 pass, every other lineage 100% or near. Pale scale under a hard
  key blows the specular and the organic rule counts it as skin. Face texture p50 0.666 — the
  structural scale-in-crop inflation; rank only. Post-axis frames (`dragonborn_p04.png`): faces,
  hair, skin and lineage all vary, kemonomimi holds, hands clawed, tails present. Skins drawn
  30/27/23/20 across the four tones; ages 55/32/13.
- **06:58** — dwarf at 51 (`dwarf_p01.png`): **reads as a dwarf.** Stocky, short-limbed, about
  five and a half heads, broad through the shoulders — 010 full-figure is the proof frame. The
  head-count phrasing moved the proportion prior where "extremely broad for her height" had not.
  Hair red / black / blonde / auburn / grey-streaked, skins ruddy / freckled / brown / tan — the
  identity axis in its first race. Gate 48/51 (three gloss, plate). This closes the owner's
  "short fat human woman" note from the peak sheet.
- **07:55** — dwarf complete, 100 frames. Gate 94/100 (five gloss on plate, one material floor).
  Proportion holds across the set — every full-figure frame is a dwarf, not a short human. Hair
  and skin vary as drawn (black 14 / grey-streaked 11 / auburn 9 / red 7 / blonde 6 / brown 6;
  freckled 17 / brown 13 / ruddy 12 / tan 11). **Two more structural caveats on the advisory
  measures, both found by looking:** (a) "pale freckled skin" inflates face texture the way scales
  did — nine "photoreal-textured" flags, none of them photographs on the drift sheet; (b) fine
  woven cloth trips the speckle flag — of dwarf's ten, only 020 and 022 are the real artifact
  (`dwarf_speckle.png`). Both numbers rank; the eye decides; a dense-cluster term would separate
  weave from blowout and is the next refinement if the owner wants the flag trusted.
- **07:58** — beastfolk at 40 (`beastfolk_p01.png`): the cleanest kemonomimi set of the night —
  human face, ears, small horns, fur markings on skin, tails, faces varying with the axis, body
  band curvy-athletic. Gate 38/39. One speckle artifact (019). High elf started on spellnode.
- **09:33** — beastfolk complete, 100 frames. Gate 94/100 (five gloss, one floor). Skins drawn
  29/24/24/23 across the four tones; kemonomimi held on every frame seen. The 5090 moved to its
  last job, human ×40. High elf at 82 on spellnode, 78 through the gate.
- **09:38** — Jarvis's read launched early (gemma4:12b, 7 GB VRAM) beside the 5090's last job.
  **09:42 — host RAM crossed the cliff** (`[warn] host RAM free 7.8 GB`); human frames went
  86 → 84 → 103 → 185 s. The tenancy rule in `stack.toml` was right and the VRAM headroom was a
  false comfort: Ollama maps the model into host memory, which is the resource DynamicVRAM pages
  into. Jarvis was allowed to finish beastfolk (verdicts are written per race), then stopped and
  the model evicted (`keep_alive: 0`). He resumes when the 5090's human batch ends; finished races
  are skipped. Claude's assessment: `ASSESSMENT_CLAUDE.md` (also in `_audit/`).
- **09:57** — high elf complete, 100 frames. Gate 95/100 (three gloss, two floor). Hair drawn
  silver-white 29 / platinum 22 / gold 21 / chestnut 16 / black 12 with "a full head of" live from
  frame 0; pale skins as drawn. Two or three frames lean anime-smooth (011, 016) — the Class C floor
  let them through, worth an eye. 004 carries the white-blowout artifact and no flag caught it: the
  speckle measure sees chroma noise, the white variety is gloss's, and here it wasn't enough. Wood
  elf started on spellnode; the 5090's human batch at 16.
- **10:38** — the 5090 finished: 340 frames (dark elf, dragonborn, beastfolk, human ×40). Human
  38/40 through the gate; skins drawn across all six tones, builds amazon 13 / curvy 13 /
  athletic 7 / slim 4 / average 3. Captions written beside every frame (`--captions`). Jarvis
  resumed on the freed card at 10:39 (beastfolk skipped, verdicts already saved). Spellnode still
  on wood elf, then human ×60 — ETA ~13:15.
- **11:05** — Jarvis's read complete for eight races: 164 of 740 kept, race-dependent in a way
  his own style label explains (orc 55, goblin 55 "wrought"; dwarf 93/100 "photo", high elf 67,
  human 36/40). Recorded in `ASSESSMENT_CLAUDE.md` as an anchoring effect of the two-image rubric
  — the races that resemble the teacher plate pass. 149 frames both reads accept. Both files sent.
- **12:01** — wood elf complete, 100 frames. Gate 92/100 (five gloss, three floor). Face texture
  p50 0.442 / p90 0.480 — the tightest of the night. Skins coppery / warm brown / tan olive / deep
  copper 25/26/29/20; hair auburn / dark brown / black / dark red / chestnut. Captions written for
  every finished frame. Last job — human ×60 — running on spellnode; ETA ~13:15.
- **13:15 — the run is complete.** 900 frames, **836 through the gate (92%)**, a caption beside
  every frame. Spellnode 560 in 11 h 31 m (73 s/frame incl. the orc restart); the 5090 340 in
  9 h 05 m (96 s/frame). Per race: dark elf 98, goblin 97, human 96, high elf 95, dwarf 94,
  beastfolk 94, wood elf 92, orc 91, dragonborn 79. Human's 60 spellnode frames 58/60. No runner
  died; one race restarted by choice; one host-RAM cliff, caused by me, caught in four minutes.
  Sheets, drift and speckle rankings, both assessments: `runtime/wrought_night/_audit/`.
- **15:15** — picker built (`_audit/picker/index.html`: 900 frames, C 553 / J 187 / both 78, the
  owner's ★ exports root-qualified pick lines). bf16 text encoder pulled and the cache-only smoke
  passed on eight frames — the training rig has no open blocker. Next move is the owner's picks.

---

## 8. Training — the researched path (not run)

Krea 2 is a single-stream MMDiT with Qwen3-VL-4B as text encoder and the Qwen-Image VAE
([technical report](https://www.krea.ai/blog/krea-2-technical-report)); the Utopic checkpoints are
Krea 2 finetunes in the same layout. The owner's Doc 43 rule stands — **train on RAW (or the Utopic
BF16 merge), never on Turbo; run daily on Turbo + LoRA** — and it matches the official guidance
([krea-ai/krea-2](https://github.com/krea-ai/krea-2)).

**Trainer: [musubi-tuner](https://github.com/kohya-ss/musubi-tuner/blob/main/docs/krea2.md)**
(kohya) has first-class Krea 2 support and is the community's recommendation over ai-toolkit for
VRAM behaviour on this architecture. Recipe from its docs:

- Models: DiT `.safetensors` (Utopic v20BF16 or `krea2_raw` — both on `D:/AI_ASSETS/models/
  diffusion_models/`), text encoder `qwen3vl_4b` single-file, VAE `qwen_image_vae`. All three are
  already on disk.
- Dataset TOML (`[general]`: `resolution=[1024,1024]`, `caption_extension=".txt"`,
  `enable_bucket=true`, `bucket_no_upscale=true`, `batch_size=1..2`; `[[datasets]]`:
  `image_directory`, `cache_directory`, `num_repeats`). Captions pair by stem — which is exactly
  what `--captions` writes.
- Pre-cache: `krea2_cache_latents.py --dataset_config … --vae …` then
  `krea2_cache_text_encoder_outputs.py --dataset_config … --text_encoder … --batch_size 1`.
- Train: `accelerate launch --mixed_precision bf16 krea2_train_network.py --dit … --vae …
  --dataset_config … --sdpa --timestep_sampling shift --weighting_scheme none
  --discrete_flow_shift 2.5 --optimizer_type adamw8bit --learning_rate 1e-4
  --gradient_checkpointing --network_module networks.lora_krea2 --network_dim 32 --network_alpha 32
  --max_train_epochs 16 --save_every_n_epochs 1`. Doc 43's numbers (rank 32, alpha 16, 1e-4→5e-5,
  1500–2500 steps) sit inside this; the official alpha is 32.
- VRAM levers if needed: `--fp8_base --fp8_scaled` (halves DiT), `--blocks_to_swap N`,
  `--sage_attn` (installed on both boxes). On the 5090 at 32 GB none should be needed at batch 1–2.
- Sampling during training on Turbo (`--turbo_dit …`, mu 1.15, 8 steps, CFG off) — RAW previews
  look flat by design; judge on Turbo.

Community pitfalls worth carrying
([chengyansen-ai/krea2-lora-training](https://github.com/chengyansen-ai/krea2-lora-training)):
`timestep_type linear` never `sigmoid`; test with euler/simple before blaming training for face
drift; a non-unique trigger pollutes the base — `wrought style` is common English, so consider a
rarer trigger alongside it; keep what is *fixed* out of the captions and describe only what
varies — for a style LoRA that means the style never appears in the caption, which is what Doc 43
already says.

**The rig, ready to run once picks exist** (`C:/sv_musubi/musubi-tuner`, own venv, torch 2.10
cu128, verified importing; `krea2_*` scripts present):

```
scripts\devuild_wrought_picker.py                # runtime/wrought_night/_audit/picker/index.html: every frame, C + J marks, your own picks
scripts\dev\collect_wrought_picks.py picks.txt      # the picker's exported lines -> runtime/style/datasets/wrought_night_v1/train/
scripts\dev	rain_wrought_lora.ps1 -Name wrought_v1   # pre-cache + train, samples on Turbo; -DryRun prints the commands
```

**Blocker cleared 15:15 (2026-09-05).** `qwen3vl_4b_bf16.safetensors` pulled (8.27 GB, 8.9 min,
`pull_hf_file.py`): 713 tensors, all BF16, no scale tensors, HF layout. `train_wrought_lora.ps1
-CacheOnly` over eight captioned verification frames ran both pre-cache stages clean — latents at
native buckets (768×1024 / 768×1344, no upscale) and the encoder loaded strictly. The launcher
defaults to the bf16 file. The paragraph below is kept as the record of what was found.

**One blocker found by reading the loader, not by running it:** the only Qwen3-VL on disk is
`qwen3vl_4b_fp8_scaled.safetensors` (F:), and musubi's `_load_qwen3_vl_model` loads the state dict
strictly after key conversion — the 252 `weight_scale` tensors in a scaled-fp8 file are unexpected
keys and raise. Its fp8 path quantises *bf16* weights at load; it does not dequantise a pre-scaled
file. Training needs `qwen3vl_4b_bf16.safetensors` (Comfy-Org/Qwen3-VL, ~8 GB). Not downloaded —
that is a model pull and the rule is that those are the owner's call. The DiT is fine: Utopic
v20BF16 is bf16, and `-Fp8Dit` quantises it at load if VRAM needs it; the Quants DiT would hit the
same "already fp8" refusal and is not offered.

**Open before training:** the Bible lists 22 races (tiefling, tabaxi, wolf-folk…) and the
generator covers the 9 with culture files; the Bible has no dwarf at all. Confirm musubi loads the
Utopic merge (same layout — expected, not verified). Set the face-texture threshold from the
morning's labelled set before filtering on it.

---

## 9. Lessons, in the order they cost a render pass

1. **Read the owner's graded notes before authoring vocabulary.** §0.
2. **A negative prunes; only the positive builds.** Coverage, profile, attractiveness.
3. **Each feature has one owner clause.** Crest/hair, eye colour/lineage, light direction, tusks.
4. **A design fork written in three places cannot be varied.** Pull it into one table first.
5. **Measure the failure where the rule lives.** Photoreal is a skin rule → face region, native
   res. A whole-subject number for a per-material law has now been wrong five times.
6. **Calibrate on both classes.** 17 accepted plates encode their subject's accidents as laws;
   the probes are the first negative class the gate ever saw.
7. **One runner per endpoint, one output root per box.**
8. **Detach anything that outlives ten minutes.**
9. **The kemonomimi rule is for the world.** Don't carve exceptions the owner didn't ask for.

---

## 10. v2 build log

### 10.1 Gate calibration on the keeper set

Jarvis's sign-off condition (DIRECTION_V2 §8) is that the tells gate (`scripts/dev/wrought_tells.py`)
does not release a batch until it has been calibrated on the owner's own accepted work, and the
keeper rates are logged. Calibrated 2026-09-06 on the keeper set: the **17 locks** under
`C:/Users/xXste/OneDrive/Pictures/Game characters/_locks/` — `002_orc_teacher`, `bear_armor_w5` ×6,
`bearfolk_r3`, `goblin_keep` ×8, `human_002style`. Only 3 of the 17 files are literally named
`plate.png`; the rest carry their own filenames (`W5_1024_150NN.png`, `g0N_*.png`), so a flat
`*.png` glob on `_locks/` itself finds nothing. `_frames()` now falls back to `p.rglob("*.png")`
when a directory has no top-level PNGs, which serves this layout — one subfolder per lock, no PNG
at `_locks/` itself. It does NOT make the same call gate a Lane-A canvas-check root as one clean
batch: `wrought_comfy.upload_reference` saves a `<stem>_ref.png` beside every skin plate, so an
rglob over `canvas_check/` finds eighteen files for six pairs, not twelve — the same confound
§10.2's twelve-plate gate call sidesteps with an explicit skin+suit path list rather than a
directory. Hermetic tests: `tests/test_wrought_measures.py::test_frames_falls_back_to_rglob_when_the_top_level_has_no_pngs`
and `::test_frames_prefers_top_level_pngs_when_present`.

**Calibration ran twice** (`n=17` both times — `runtime/wrought_gate/keeper_rates.json` and
`keeper_rates_run2.json`, gitignored) because Jarvis's vision reading is not deterministic, and the
floor needed a measured spread rather than an invented one:

| tell | run 1 | run 2 | abs diff |
|---|---|---|---|
| plastic_skin | 0.588 | 0.529 | 0.059 |
| waxy_skin | 0.588 | 0.471 | 0.118 |
| perfect_symmetry | 0.882 | 0.824 | 0.059 |
| centered_stock_pose | 0.412 | 0.353 | 0.059 |
| light_from_everywhere | 0.471 | 0.235 | **0.235** |
| everything_in_focus | 0.412 | 0.353 | 0.059 |
| no_grain | 0.235 | 0.412 | 0.176 |
| oversaturated | 0.000 | 0.000 | 0.000 |
| glossy_sheen | 0.176 | 0.353 | 0.176 |
| generic_pretty_face | 0.941 | 0.941 | 0.000 |
| cluttered_ornament | 0.059 | 0.059 | 0.000 |

`FLOOR = max(0.15, ceil_to_0.05(max run-to-run diff))`. The largest swing was `light_from_everywhere`
at 0.235 (4 of 17 plates read differently between the two runs on the SAME images) → rounded up to
0.25. **`FLOOR` is now `0.25`** in `wrought_tells.py` (was `0.15`, a placeholder set before any real
keeper set existed) — a batch's rate for a tell has to clear the keeper rate by more than a quarter
before the gate calls it a regression, because that is how much a bare re-read of the same 17 images
moves on its own.

**Sanity check — gate the night run's beastfolk against the keepers.**
`wrought_tells.py gate runtime/wrought_night_b/beastfolk_woman --keeper runtime/wrought_gate/keeper_rates.json`
(100 frames) → **`GATE PASS []`**:

| tell | keeper (run 1) | limit (keeper + 0.25) | beastfolk batch | verdict |
|---|---|---|---|---|
| plastic_skin | 0.588 | 0.838 | 0.10 | ok |
| waxy_skin | 0.588 | 0.838 | 0.83 | ok — closest call, 0.008 under |
| perfect_symmetry | 0.882 | (capped at 1.0) | 0.88 | ok |
| centered_stock_pose | 0.412 | 0.662 | 0.40 | ok |
| light_from_everywhere | 0.471 | 0.721 | 0.21 | ok |
| everything_in_focus | 0.412 | 0.662 | 0.57 | ok |
| no_grain | 0.235 | 0.485 | 0.34 | ok |
| oversaturated | 0.000 | 0.250 | 0.00 | ok |
| glossy_sheen | 0.176 | 0.426 | 0.04 | ok |
| generic_pretty_face | 0.941 | (capped at 1.0) | 0.89 | ok |
| cluttered_ornament | 0.059 | 0.309 | 0.18 | ok |

`perfect_symmetry` (batch 0.88, keeper 0.88) and `generic_pretty_face` (batch 0.89, keeper 0.94) sit
almost exactly AT the keeper rate — **the locks carry the same tells**, so their limit sits above
1.0 and this gate structurally cannot detect a regression on either one, at any batch rate up to
100%. That is not a hole to patch by tightening the margin (the brief is explicit: do not tune the
margin to force a rejection) — it is what "the reference set already carries this tell" means. Those
two tells can only be moved by the PROMPT (less stock-symmetric posing, a less generically-pretty
face draw); the gate watches the other nine, where a real regression has room to show against the
keepers — and on this batch the closest of those nine is `waxy_skin`, 0.83 against a limit of 0.838,
0.008 under. Everything else clears with room.

### 10.2 Lane-A canvas check

Six Lane-A pairs at **1216×1728** (`variants.CANVAS_LANE_A`, unchanged) against the two races that
carry the night's own comparison numbers:

```
generate_wrought_dataset.py orc   --lane a --count 3 --seed 40001 --out runtime/wrought_v2/canvas_check
generate_wrought_dataset.py human --lane a --count 3 --seed 40101 --out runtime/wrought_v2/canvas_check
```

Model `loxsUtopicWorldKrea2_v10Quants`, 52 steps, CFG 3.5. Local endpoint idle-checked before and
after (GPU tenancy rule — no Jarvis call overlapped a render). Sheet: `evidence/v2_canvas_check_1216x1728.jpg`
(skin | suit, 6 rows). Per-pair gate print: orc 2/3 skin-pass, human 1/3 skin-pass — but that number
(from the runner's own summary) only ever counted the SKIN half; the table below is the full twelve.

**Per-criterion table, the twelve real plates** (`NNN_skin.png` / `NNN_suit.png` — excludes the
`NNN_skin_ref.png` downscaled upload copy `wrought_comfy.upload_reference` writes beside each skin
plate, which `check_wrought.py`'s own directory listing does NOT exclude and would otherwise silently
count as six extra, duplicate-content "plates"):

| plate | detail_mid | material_floor | gloss_fraction | face_fine_over_meso | gate (incl. floor) |
|---|---|---|---|---|---|
| orc 000 skin | 0.0412 | 0.177 | 0.0002 | 0.529 | WROUGHT |
| orc 000 suit | 0.0144 | 0.199 | 0.0001 | — (face 171px) | OFF-STYLE (detail_mid) |
| orc 001 skin | 0.0369 | 0.183 | 0.0000 | — (face 178px) | WROUGHT |
| orc 001 suit | 0.0281 | 0.197 | 0.0010 | 0.693 | OFF-STYLE (detail_mid) |
| orc 002 skin | 0.0438 | 0.082 | 0.0007 | 0.547 | OFF-STYLE (material_floor) |
| orc 002 suit | 0.0447 | 0.224 | 0.0011 | — (face 167px) | WROUGHT |
| human 000 skin | 0.0355 | 0.167 | 0.0000 | — (face 171px) | WROUGHT |
| human 000 suit | 0.0582 | 0.189 | 0.0000 | — (face 160px) | WROUGHT |
| human 001 skin | 0.0418 | 0.097 | 0.0000 | — (face 150px) | OFF-STYLE (material_floor) |
| human 001 suit | 0.0461 | 0.165 | 0.0001 | — (face 156px) | WROUGHT |
| human 002 skin | 0.0355 | 0.096 | 0.0001 | 0.771 | OFF-STYLE (material_floor) |
| human 002 suit | 0.0349 | 0.168 | 0.0000 | — (face 162px) | WROUGHT |

Pass rate **with `material_floor` gated: 7/12.** Pass rate **without `material_floor`
(`detail_mid` + `gloss_fraction` only, both organic-gated): 10/12** — exactly the brief's "Expected:
gate WROUGHT on ≥ 10 of 12." The three `material_floor` failures (0.082, 0.096, 0.097 — all SKIN
plates this time, not suit) confirm the Known measurement fact by a wider margin than the fact
itself states: it isn't only the suit's darker two-piece that can undershoot the locks' calibrated
floor, a skin plate can too. **Observed `material_floor` range across the twelve: 0.082 .. 0.224**
(locks: 0.134..0.222) — the number a future re-calibration of the 0.10 floor should start from; per
the task's own instruction, the threshold itself is NOT changed here.

The two `detail_mid` failures are both **orc suit** plates (0.0144, 0.0281 against the 0.030 floor) —
a new, narrower finding than the material-floor one: this batch's orc compression-suit renders came
back flatter/lower-frequency than every other plate in the twelve, orc skin included. Two frames is
too few to say whether this is an orc-specific or a suit-specific effect; worth a wider orc-suit
sample before trusting either reading.

**Gloss: 0/12 failures** (max observed 0.0011, the ≤0.045 organic ceiling not close to threatened) —
comfortably clears the decision rule's "gloss fails on more than 2 of 12" trigger.

**Face texture — measurable on only 4 of the 12** (the rest have a detected face under the 180 px
floor; a full-body A-pose canvas puts the face in a small fraction of the frame, unlike a portrait
crop). The four: orc 000 skin 0.529, orc 001 suit 0.693, orc 002 skin 0.547, human 002 skin 0.771 —
p50 (this repo's own convention, `audit_wrought_night.py`'s `faces[len(faces)//2]` on the sorted
list) = **0.693**, over the decision rule's 0.55 line, and over the locks' ceiling (≤0.501) and the
night's 768×1344 distribution (orc p50 0.476, human p50 0.445) quoted in the brief.

Read literally, this fires the decision rule. Before treating it as one, two checks:

1. **Is it a resolution artifact?** `face_texture()`'s fine/meso bands use FIXED pixel-space Gaussian
   sigmas (1.2 px / 6.0 px) on the face crop at whatever resolution the canvas produced — unlike
   `detail_mid`/`detail_high`, which are deliberately resampled to a common `SPECTRUM_HEIGHT` first
   (§5's own lesson, "AT A COMMON RESOLUTION..."). A higher-resolution face crop samples the same
   physical pore/meso structure at more pixels per unit, which could inflate `fine` relative to
   `meso` for a purely mechanical reason having nothing to do with the render. Tested directly:
   resampled each of the four faces to a fixed 256 px crop with the blur sigmas scaled to match, so
   the same physical feature size is measured regardless of native resolution —

   | plate | face_px | native ratio | resampled-to-256 ratio |
   |---|---|---|---|
   | orc 000 skin | 190 | 0.529 | 0.518 |
   | orc 001 suit | 519 | 0.693 | 0.621 |
   | orc 002 skin | 180 | 0.547 | 0.534 |
   | human 002 skin | 270 | 0.771 | 0.750 |

   The readings barely move. **The hypothesis is refuted, not confirmed** — the elevated numbers are
   not a resolution-normalization bug the way `detail_mid` once was; they reflect something the face
   crop genuinely carries at this size.
2. **Is n=4 enough to trust?** `runtime/wrought_v2_smoke2/human_woman/000.json` (Task 10's smoke
   pair, "pair 0", same 1216×1728 canvas) reads `face_fine_over_meso` **0.454** — in-band, close to
   the locks. Folding it in as a fifth same-resolution reading — `[0.454, 0.529, 0.547, 0.693,
   0.771]` — moves p50 to **0.547**, under the 0.55 line, by the same convention used above (and
   by a plain median, since n is now odd). A single additional data point flips the verdict, which is
   the file's own recurring lesson restated exactly ("a threshold set from four is the trap this gate
   keeps recording") — not refuted this time, DEMONSTRATED again, on this task's own numbers.

**Silhouette: 0/6 "ok" on this batch** (all under the `SILHOUETTE_LIMIT_PX_AT_1216 = 8.0` bar in
`wrought_measures.py`, none of them close) — and pair 0 was ALSO `"ok": false` (hip delta 144 px) at
this same canvas, so this is not a new regression, it is the pre-existing, explicitly PROVISIONAL
threshold (its own docstring: "restated once the first twenty real skin/suit pairs exist"; this
task's six pairs bring the running total to 7, not 20). Severity varies sharply, and the extremes
look like a measurement problem rather than a real 002-vs-canvas finding:
- `human_woman/000` measured a **945 px height delta** (skin mask height 1153, suit mask height
  **208**) — visually inspected `000_suit.png` directly: it is a full standing figure filling the
  frame, not a 208-px-tall subject. `dark_subject_mask`'s fixed `tolerance=28` luma/chroma cutoff is
  the likely cause — a mid-grey suit against a near-black void loses contrast in some lighting, and
  a fragmented mask keeps only its largest connected piece.
- `orc_woman/002` measured height almost identically (1689 vs 1686, 3 px apart — the two masks agree
  on where the body starts and ends) but a **284 px hip delta** — the `widths()` hip search (the
  widest row in the 0.50–0.70 height band) can land on a materially different row between the skin
  and suit crop when a small pose shift (the reference edit is not a pixel-identical repose) moves
  where legs join or split, which is a band-search brittleness rather than the same 8 px provisional
  bar being narrowly missed.
- `orc_woman/000` is the mild end: waist 1 px, height 21 px, hip 51 px — over the 8 px bar but not by
  an implausible margin, and plausibly a real (if small) proportion difference.

None of this is in Step 5's decision rule (only face p50 and gloss are), so it does not move the
canvas by itself, and `wrought_measures.py` is out of this task's file list — but it is a real,
now twice-observed finding (pair 0 + this batch) worth recording for whoever next touches the
silhouette measure or reaches the 20-pair mark it is waiting on.

**Tells gate on the twelve plates** (`wrought_tells.py gate <12 explicit skin+suit paths> --keeper
runtime/wrought_gate/keeper_rates.json`, n=12) → **`GATE PASS []`**. Closest tell:
`centered_stock_pose`, batch 0.667 against a limit of keeper 0.412 + max(0.25, 2σ) — at n=12 the
binomial term (0.284) beats the 0.25 floor, giving a threshold of 0.696, an 0.029 margin. Every
other tell clears with more room; `light_from_everywhere` read **0** of 12 (the single hard key is
holding at this canvas).

**Decision: `CANVAS_LANE_A` holds at 1216×1728.** Gloss (the robust half of the decision rule) clears
by a wide margin (0/12 vs. "≤2 of 12"); face texture (the other half) reads over the line on a
four-plate sample but the sign flips to under the line the moment a fifth same-resolution reading
(pair 0) is added, and a direct experiment ruled out the resolution-artifact explanation without
ruling in a genuine one — the honest read is "not enough same-canvas data yet to move a 002-paint
decision on this axis," not "fails." Combined with the gate-pass rate matching the brief's own
"≥10/12" expectation once `material_floor` (known to undershoot on Lane A "by construction") is set
aside, and the tells gate passing clean at n=12, nothing here clears the bar for the costly fallback
(re-rendering six more pairs at 1024×1456 would very likely reproduce the same thin-sample instability
in the opposite direction, at another ComfyUI+Jarvis pass, without answering the actual question).
Two concrete open items carried forward instead of masked by a re-render: `orc`-suit `detail_mid`
(2 of 2 orc-suit plates in this batch) and the silhouette measure's provisional 8 px bar (still short
of the 20 pairs it is waiting on, and carrying two now-documented measurement-brittleness cases).

**OWNER:** this decision rests on five measurable faces (four from this batch plus the smoke pair),
not the prescribed twelve; the literal rule fired on the four. If you would rather not extend the
sample this way, re-run Step 5's fallback at 1024×1456.

---

## Task 15 / 15B — five probe batches, read and gated

Task 15B split Task 15's five probe batches across two phases in one session: the local box was
mid-render on the dragonborn re-render (`dragonborn_woman_<lineage>`) and Jarvis (Ollama, local
GPU) cannot run beside a render (GPU tenancy rule). **Phase 1 was everything that does not need
Jarvis: the silhouette re-measure, the question constants + `covary` wiring in `wrought_tells.py`,
the drawn-side/registry/gate counts that come straight off disk, and four of the five evidence
sheets. Phase 2 (below, 2026-09-06, GPU idle, ComfyUI queue confirmed empty) is every Jarvis read,
the whole-mask overlap re-measure, the dragonborn read (both clause versions, the lineage-honoured
re-render), the tells gate on all five batches, and the fifth evidence sheet.** Both phases are
complete; every `[JARVIS PENDING]` / `[PHASE 2 PENDING]` below has been replaced with a read
number.

Two gates are named across these steps and they are NOT the same thing: the **numeric gate**
(`check_wrought.measure` → `verdict`, `detail_mid` + `material_floor`, advisory `gloss_fraction`
unless `--organic`) runs at RENDER time and is already stored in every `NNN.json`'s own `gate` /
`failed` / `metrics` fields — reading it needs no Jarvis, and §10.3–10.7 read it straight off disk
the same way §10.2 did. The **tells gate** (`wrought_tells.py gate <dir> --keeper
runtime/wrought_gate/keeper_rates.json --records`) is the Jarvis-vision, keeper-calibrated AI-look
gate from §10.1, run for real in Phase 2 on every batch below, with `covary`'s top three axis
values named for every offending tell on a REJECT.

### Silhouette re-derivation (Task 15B step 1 + Phase 2, offline once Jarvis-free)

Every Lane-A pair on both roots was re-measured with `wrought_measures.py` (Task 14b: kept
shadow-severed parts, `paired_rows` mapping the waist/hip rows from the skin plate onto the suit
plate by height fraction, crotch-gap rejection in the waist band). Phase 1 covered 54 pairs
(dragonborn excluded, mid re-render); Phase 2 added the 20 lineage-honoured re-render pairs and
the 20 `_batch1` pairs (disk shows **20** batch1 pairs — 12 named-places + 8 whole-body — not 19 as
first reported when this phase was dispatched; recorded as the correction it is) for **94 Lane-A
pairs total**, all tagged `"measure_version": "14b"`, written back atomically.

**The measure of record is now whole-mask overlap, not the two-row waist/hip deltas** — a second
task (`wrought_measures.silhouette_overlap`, IoU of the two subject masks + median row-extent
delta + `same_body` at IoU ≥ `SILHOUETTE_IOU_SAME_BODY = 0.85`) landed on this same file between
the two phases (commit `b326889`, "the silhouette measure of record is whole-mask overlap, not two
rows"), calibrated on one img2img pair that keeps the same body (IoU 0.906) against four
reference-edit pairs that are a different body by eye (IoU 0.39–0.54). `measures.overlap` was added
to all 94 records this phase, alongside the pre-existing (context-only) `measures.silhouette`:

| batch | n | IoU min | IoU p50 | IoU p90 | IoU max | same_body (≥0.85) |
|---|---|---|---|---|---|---|
| beastfolk | 24 | 0.273 | 0.405 | 0.516 | 0.564 | 0/24 |
| orc | 10 | 0.395 | 0.438 | 0.546 | 0.617 | 0/10 |
| human | 10 | 0.272 | 0.429 | 0.542 | 0.649 | 0/10 |
| dwarf | 10 | 0.328 | 0.443 | 0.544 | 0.558 | 0/10 |
| dragonborn batch1 | 20 | 0.222 | 0.401 | 0.513 | 0.593 | 0/20 |
| dragonborn re-render | 20 | 0.220 | 0.388 | 0.494 | 0.551 | 0/20 |
| **all 94** | **94** | **0.220** | — | — | **0.649** | **0/94** |

**Zero of 94 pairs score `same_body` — every one sits inside the 0.22–0.65 band the calibration
pair called "a different body by eye," none anywhere near the 0.906 an img2img (same-latent) suit
scores.** This holds across every race and both dragonborn groups equally; it is not a
per-vocabulary defect, it is the suit-generation PATH (a reference-edit call to the skin plate,
independently re-diffused) failing to preserve the body on this entire probe sample. **Task 15D is
already replacing this path** (`wrought_suit_probe.py`'s img2img + grey-init work, same commit
range) — that is the actual fix; this task does not touch it, and does not propose a px bar for the
two-row measure, per instruction. The two-row deltas stay in every record as context only (p50
waist 44–68 px, p50 hip 73–266 px across the six groups above — large everywhere, consistent with
the overlap finding, not contradicting it).

**A genuinely interesting split, not resolved by either measure alone:** §10.5 below reads
`SAME_PERSON_QUESTION` as **30/30 "same person, different clothes"** on these exact skin/suit
pairs — Jarvis's face-and-hair judgment says identity holds, while the pixel-level overlap says the
body does not. Both are true at once: the suit-generation path keeps the FACE but not the BODY. That
is precisely the shape of defect an img2img/grey-init suit path (Task 15D) is built to close.

### 10.3 Beastfolk subspecies — 24 Lane-A pairs, both roots

`BEAST_QUESTION` (`scripts/dev/wrought_tells.py`, verbatim from `task-15-brief.md` step 1):

> Answer in JSON only. "species": the animal the ears and tail suggest, one of ["leopard","bear",
> "lion","deer","panda","wolf","fox","other","none"]. "horns": true/false (horns or antlers on the
> head). "human_ears": true/false (a second, human ear pair on the sides of the head). "fur_body":
> true/false (fur covering the body rather than skin). {"species": s, "horns": b, "human_ears": b,
> "fur_body": b}

One frame's skin prompt (`beastfolk_woman/000`, local, lion, verbatim):

> A single strong directional key light in a dark studio, deep readable form shadows, almost no
> fill, no rim light, no set. Worked materials: tooled leather with flex creases and stitching,
> rivets seated in straps, beaten engraved metal that highlights only on its edges, matte chalky
> cloth with readable weave. Selective realism, not a photograph, not pore-level skin, not oil
> paint, not painterly, not cartoon. Full punchy earth and iron colour, not muted, not cinematic
> grade. a single beastfolk woman, a young adult in their mid-twenties, about twenty-five, curvy
> athletic, a human face, human skin, no animal head and no muzzle, a soft human face framed by the
> ears, smaller, more delicate ears than the men, unmistakably female, feminine facial structure, a
> defined waist above wide hips, hips broader than the ribcage, full bust, a soft layer over the
> muscle, smooth neck and shoulders without heavy trapezius bulk, **a lion beastfolk, a human face,
> only the pair of broad rounded lion ears on top of the head, no human ear pair, a tawny lion tail
> with a tufted tip, a warm tawny cast to the skin of the forearms and shoulders, no horns, the
> crown of the head bare between the ears**, warm tan skin, … key light from the upper left, palette
> of umber, deep forest green, clan-dye red, dappled green-gold, grounded stylized realism …

**Drawn subspecies distribution (both roots, 24 pairs)** — `subspecies_for` draws with
`rng.choice(sorted(table))`, uniform per frame, not round-robin, and it shows:

| leopard | bear | lion | deer | panda | wolf |
|---|---|---|---|---|---|
| 3 | 2 | 7 | 3 | 6 | 3 |

24 total, but **not** "4 per subspecies" as the batch was designed (`task-15-brief.md` step 1's own
title) — lion drew 7 and bear drew 2, and deer drew 6, not 4, which moves the "horns on non-deer"
denominator below. Nothing here needed Jarvis to see: it is a fact about the draw, recorded as the
miss it is. Not hand-fixed in this task; a future run of this batch would want a round-robin or
weighted draw across `SUBSPECIES` instead of a uniform per-frame choice.

**`BEAST_QUESTION` reads, real Jarvis, 24 skin plates:**

| check | result | expected | verdict |
|---|---|---|---|
| species matches drawn subspecies | **15/24 (62.5%)** | ≥18/24 | **miss** |
| horns on non-deer | **0/18** (deer drew 6, not the designed 4, so 18 non-deer not 20) | 0 | pass |
| human ear pair | **0/24** | ≤2/24 | pass |
| fur body | **1/24** | 0/24 | miss (`wrought_v2_b/beastfolk_woman/005`, lion) |

**Species accuracy by subspecies** is not uniform — this is the real story behind 15/24:

| leopard | deer | wolf | lion | bear | panda |
|---|---|---|---|---|---|
| 3/3 | 6/6 | 2/3 | 4/7 | **0/2** | **0/3** |

**Bear and panda are never correctly read (0/5 combined)**, misread as wolf/fox/none every time.
Both are the two subspecies whose `SUBSPECIES` row carries an EMPTY `"marks"` field by design ("bear
and panda carry no body marks at all" — the table's own comment) — under the default draw
(`fur=None`), their clause states only ears + tail + headgear, nothing on the skin, so there is
nothing left for Jarvis to read a bear/panda tell from beyond the ears themselves, and the ears
alone are not landing. Leopard and deer, whose clause states a skin-pattern `"marks"` phrase, read
perfectly (9/9 combined). This is a real vocabulary finding, not hand-fixed here: bear/panda likely
need SOME visible skin or coat cue beyond the ear shape to read correctly, independent of the fur
ladder (which is an opt-in axis for a different question — full-body coverage, not species
legibility).

**Numeric gate (`detail_mid`+`material_floor`, offline):** 48 plates (24 skin + 24 suit) — **31
WROUGHT / 17 OFF-STYLE**, all 17 on `material_floor` bar one on `detail_mid`.

**Tells gate: REJECT** (n=48). `centered_stock_pose` batch 0.688 vs keeper 0.412 + limit 0.25 =
0.662 threshold (0.026 over). `covary` top three: `subspecies=panda` (1.00), `subspecies=bear`
(1.00), `subspecies=wolf` (0.83) — the same two subspecies that fail the species read also read as
the most stock-posed (small n per value — 2–3 each — so this covaries with the sample, not
necessarily the clause; not hand-fixed).

Evidence: [`v2_beastfolk_subspecies.jpg`](evidence/v2_beastfolk_subspecies.jpg) — 6 columns
(leopard/bear/lion/deer/panda/wolf, `SUBSPECIES` order), 4 rows, one skin plate per cell, labelled
`subspecies root+index, read:<species> OK/MISS, horns:<bool>`; bear only fills 2 of 4 cells (drawn
count), the other two are the sheet helper's own labelled-gap fill, not a render failure.

**Vocabulary change:** none made in this task, but the finding is concrete enough to act on next:
give bear and panda a skin/coat cue (their `"marks"` field is empty by design; every subspecies that
has one reads correctly) — and fix the subspecies-draw imbalance (round-robin) so the next batch is
actually 4-per-subspecies.

### 10.4 Dragonborn skin and scale — three groups, 40 Lane-A pairs total

Three groups on disk, read separately as the before/after the whole-body clause fix is meant to
show: `dragonborn_woman_<lineage>_batch1/` (the FIRST Lane-A pass, wrong lineage in the dir name —
`--lineage` was not applied — split by its OWN skin prompt into **12 named-places** ["scales are a
pattern on that skin"] and **8 whole-body** ["one unbroken hide"] pairs, since both clause versions
are mixed into this one directory set) and `dragonborn_woman_<lineage>/` (the **20-pair re-render**,
verified: every record's `variation.lineage` matches its directory and every skin prompt carries
"one unbroken hide"). `lineage` was read from `variation.lineage`, never the directory name, per
the controller amendments.

`DRAGON_QUESTION` is wired in `wrought_tells.py` (verbatim from `task-15-brief.md` step 2, plus the
controller's added `scale_coverage` field for the whole/partial/none coverage read):

> Answer in JSON only. "face_skin": two words for the skin tone of the face (e.g. "deep brown",
> "pale", "olive"). "scales_on_skin": true/false. "scales_on_garment": true/false (a scale pattern
> on the clothing). "scale_colour": one word. "scale_coverage": one of ["whole","partial","none"]
> (how much of the body below the jaw shows scales). {"face_skin": s, "scales_on_skin": b,
> "scales_on_garment": b, "scale_colour": s, "scale_coverage": s}

**Reads, all three groups, real Jarvis:**

| group | n | face_skin family match | scales_on_garment true | scale_colour strict/loose match | scale_coverage |
|---|---|---|---|---|---|
| batch1 named-places | 12 | 0/12 | 0/12 | 3/12 / 3/12 | partial 12, whole 0, none 0 |
| batch1 whole-body | 8 | 3/8 | 0/8 | 2/8 / 3/8 | whole 3, partial 5, none 0 |
| re-render (whole-body, all 10 lineages) | 20 | 7/20 | 1/20 | 7/20 / 9/20 | whole 3, partial 17, none 0 |

(`face_skin family match`: drawn `variation.skin`'s tone word — tan/olive/pale/brown — bucketed
against Jarvis's free-text two-word read via keyword family, not exact string match, since "pale
peach" and "the face is pale human skin" are the same claim in different words. `scale_colour
strict` is an exact match to the lineage name; `loose` allows the stated synonyms, e.g. "orange" for
copper, "grey" for silver.)

**The whole-body clause fix did not clearly move the coverage read, and the full re-render reads
WORSE than the small whole-body slice already inside batch1**: 3/8 (37.5%) of batch1's own
whole-body pairs read `scale_coverage: "whole"`, against 3/20 (15%) of the dedicated, all-lineage,
lineage-correct re-render — the opposite of what a fix should show. `face_skin` and `scale_colour`
both move in the right direction (0/12 → 3/8 → 7/20 face; 3/12 → 3/8 → 9/20 colour loose), but none
of the three groups reaches the original plan's ≥14/20 (70%) target on either axis. **`scales_on_garment`
clears its own bar everywhere** (≤2/20 in every group, matching `DRAGONBORN_GARMENT`'s intent that
the armour stays plain). Read together: the "one unbroken hide, no bare skin below the jaw" clause
is not reliably rendering as whole-body coverage even when it is the only clause on the page — by
inspection of the evidence sheet, most re-render plates show scale texture on the arms and legs but
bare-looking skin across the torso, which is what "partial" is catching. Not hand-fixed in this
task; this is the concrete finding for whoever next touches `SKIN_SCALE_PLACEMENT`.

**Tells gate:**

- **batch1 (n=40, mixed clause): REJECT.** `no_grain` batch 0.575 vs keeper 0.235 + 0.25 = 0.485
  (0.09 over). `covary` top three: `nation=oathhold` (0.75), `light=key light from the upper left`
  (0.67), `light=key light from the upper right` (0.64) — correlates with nation/lighting, not the
  scale clause.
- **re-render (n=40, whole-body): REJECT.** `no_grain` batch 0.500 vs the same 0.485 threshold
  (0.015 over — the closer call). `covary` top three: `appearance=ordinary` (0.61),
  `nation=slatecoast` (0.60), `light=key light from the upper left` (0.56).

Evidence: [`v2_dragonborn_skin_scale.jpg`](evidence/v2_dragonborn_skin_scale.jpg) — the re-render,
10 columns (one per lineage, dir-name order), one skin plate each, labelled `lineage: drawn <tone> |
read <tone> | cov:<whole/partial/none>`.

**Vocabulary change:** none made in this task — the finding above (whole-body clause reads mostly
"partial" even at its most consistent) is handed forward rather than patched blind; a next pass
should look at whether the torso specifically needs its own explicit scale statement (the clause
already lists it, "neck, shoulders, chest, back, arms, hands, torso, legs, feet and tail" — so this
may be a rendering-adherence problem more than a wording one, which is a different fix).

### 10.5 Nations and identity — 30 Lane-A pairs, orc (local) + human + dwarf (node)

One frame's variation (`orc_woman/000`, local): nation **coastal**, marker *"bony ridges along the
brow and shoulders"*, skin *"slate-grey skin"* — from the skin prompt (verbatim excerpt):

> A single strong directional key light in a dark studio, deep readable form shadows, almost no
> fill, no rim light, no set. Worked materials: tooled leather with flex creases and stitching,
> rivets seated in straps, beaten engraved metal that highlights only on its edges, matte chalky
> cloth with readable weave. Selective realism, not a photograph, not pore-level skin, not oil
> paint, not painterly, not cartoon. Full punchy earth and iron colour, not muted, not cinematic
> grade. a single orc woman, a young adult in their mid-twenties, about twenty-five, amazon curvy,
> lower tusks, a strong jaw, sloping brow, …

**`identity_key` uniqueness across both registries** (`runtime/wrought_v2/_identities.json`,
`runtime/wrought_v2_b/_identities.json`, read directly — this is what the registry is FOR, no
Jarvis needed): **66 keys local + 32 keys node = 98 total, 0 collisions either within a registry
(each is a Python dict, so a re-drawn key would have overwritten in place) or across the two roots
(0 keys shared).** Every identity is unique, by construction, over both roots combined.

**Pairwise face NCC per race, skin plates only** (`wrought_measures.face_identity`, offline, the
same recomputation as the silhouette pass — 45 pairs per race, all 45 face-detected in all three):

| race | root | n | max off-diag NCC | mean NCC |
|---|---|---|---|---|
| orc | local | 10 | 0.8446 | 0.5369 |
| human | node | 10 | 0.8848 | 0.4502 |
| dwarf | node | 10 | 0.8144 | 0.3730 |

The brief's own caveat: the night's one-face batches (one identity repeated across the whole batch)
sit near 0.9 max off-diagonal; distinct faces should sit well below. All three maxes here (0.81–
0.88) sit close to, not clearly under, that line — a duplicate-identity **advisory**, not a
verdict, per the brief ("NCC is alignment-noisy").

**`SAME_PERSON_QUESTION` over the 30 skin/suit pairs (real Jarvis): 30/30 "same person, different
clothes" — orc 10/10, human 10/10, dwarf 10/10.** Read carefully, this settles a DIFFERENT question
than the NCC advisory above: `SAME_PERSON_QUESTION` compares the skin plate to its OWN suit plate
(does the two-plate contract hold for one character), and it holds cleanly on every pair by Jarvis's
face/hair judgment. It does not test whether two DIFFERENT drawn characters (e.g. orc/000 vs
orc/003) are confusably similar to each other — nothing in this task's question set does, so the
pairwise-NCC advisory above (are the ten drawn faces per race distinct FROM EACH OTHER) stands
unresolved; Phase 1's framing of `same_person` as "the read that actually settles it" was an
overreach and is corrected here. **The genuinely interesting result is the disagreement with
§'s silhouette overlap**: the same 30 pairs that read 30/30 "same person" score 0/30 `same_body`
(overlap section above) — Jarvis's identity judgment tracks the face and hair, not the body
silhouette, and the reference-edit suit path is failing exactly the axis `same_person` does not
check.

**Numeric gate**, read per race (offline):

| race | plates | WROUGHT | OFF-STYLE | reasons |
|---|---|---|---|---|
| orc | 20 | 14 | 6 | detail_mid ×4, material_floor ×2 |
| human | 20 | 16 | 4 | material_floor ×2, detail_mid ×2 |
| dwarf | 20 | 9 | 11 | material_floor ×7, detail_mid ×6, gloss_fraction ×1 |

Dwarf clears well under half — worth a look independent of anything Jarvis reads; not investigated
further in this phase.

**Tells gate: REJECT on all three races**, all on `centered_stock_pose` or `no_grain`:

| race | offending tell | batch rate | keeper+limit | `covary` top three |
|---|---|---|---|---|
| orc | centered_stock_pose | 0.700 | 0.662 | `light=key light from slightly above and in front` 1.00, `nation=lowland` 1.00, `appearance=ordinary` 0.83 |
| human | centered_stock_pose | 0.800 | 0.662 | `light=key light from slightly above and in front` 0.88, `appearance=ordinary` 0.83, `nation=republic` 0.83 |
| dwarf | no_grain | 0.550 | 0.485 | `light=key light from the upper right` 1.00, `appearance=striking` 1.00, `nation=ashvault` 0.75 |

Every top covary value here is a light angle or an appearance/nation axis — never the race or skin
vocabulary itself — so these three rejections read as a POSING/LIGHTING issue shared across the
Lane-A skin+suit contract, not a nations-specific defect.

Evidence: [`v2_nations_identity.jpg`](evidence/v2_nations_identity.jpg) — three rows of ten skin
plates (orc / human / dwarf), each labelled `race index nation/skin same:<same_person bool>`.

**Vocabulary change:** none — the NCC advisory is still open (needs a same-race, cross-index
identity question that this task did not ask), and the gate rejections above covary with pose/light,
not with anything in the nations vocabulary.

### 10.6 Wardrobe and hair variety — 24 Lane-B fit plates, human (12) + orc (12)

`OUTFIT_QUESTION` (`wrought_tells.py`, field list from `task-15-brief.md` step 4, put in the same
Answer-in-JSON-only template `BEAST_QUESTION`/`DRAGON_QUESTION` already use):

> Answer in JSON only. "outfit": five words naming the outfit. "hair": four words for the
> hairstyle. "candid": true/false (off-centre, weight on one hip, gaze off-axis). {"outfit": s,
> "hair": s, "candid": b}

One frame's prompt (`human_fit/000`, verbatim): monarchy noble landholder, tudor dialect —

> … a single human woman, middle-aged, athletic, the full human range of height, build and
> features, the full female human range, feminine proportion at every build, unmistakably female,
> … pale skin, an attractive, open face, a long jaw, flat wide cheekbones, straight brows, a long
> narrow nose, deep-set eyes, a wide mouth with thin lips, one eye a fraction narrower than the
> other, a healed nick on the left cheek, brown eyes, … a full head of black hair, straight or wavy,
> chin-length, a high ponytail, a carved wooden pin, wearing tudor, noble, costly dye in larger
> fields, disciplined: a long-sleeved chemise, a structured bodice, a full skirt, ankle boots, a
> simple circlet, a wide belt with a pouch, a strap twisted; wool, clean, high craft, fully clothed,
> … a deep blue and gold ribbon at the collar, full body standing, head to toe, weight on one hip,
> head turned a little, gaze off to one side, framed off-centre, key light from the upper right …

**Drawn-side counts (offline, the Phase-1 substitute for the Jarvis outfit/hair/candid read — these
are what was AUTHORED, not what a viewer would see):**

- **Outfit repeats:** a 6-slot signature (under/torso/legs/outer/feet/head) built from each
  record's own `outfit.slots` gives **24 distinct signatures out of 24 — zero repeats at all**,
  let alone more than twice. Comfortably clears "no five-word outfit string repeats more than
  twice."
- **Braid share:** `variation.hair` contains "braid" (case-insensitive) on **10 of 24 = 41.7%** —
  a hair over the "≤40%" guideline, on the drawn side. Flagged, not fixed; Phase 2's actual visual
  read may land above or below this (a drawn "braid" does not always read as visually obvious).
- **Candid share:** `variation.framing` is one of the two non-square `COMPOSITION_WEIGHTED` options
  on **10 of 24 = 41.7%** — inside the expected 30–50% band, and matches the authored weight
  (square 6 : candid 4 → 40% design target).

**`OUTFIT_QUESTION` reads, real Jarvis, vs. the drawn proxies above:**

| check | drawn (Phase 1 proxy) | Jarvis read (Phase 2) | expected | verdict |
|---|---|---|---|---|
| outfit repeats > twice | 0/24 exact 6-slot signatures | 0/24 five-word strings (23 distinct of 24 — one pair reads identically, count 2, still not >2) | ≤2 repeats | pass, both readings |
| braid share | 10/24 = 41.7% | **20/24 = 83.3%** | ≤40% | **large miss** |
| candid share | 10/24 = 41.7% | 10/24 = 41.7% | 30–50% | pass, both readings (same number, not verified to be the same 10 frames) |

**Braid is the headline finding of this batch: Jarvis reads twice as much braiding as was
authored.** Only 10 of 24 `variation.hair` strings contain the word "braid"; the vision read calls
20 of 24 hairstyles braided. Two explanations, not distinguished here: the render is putting
braid-like texture into styles that were not authored as braids (a rendering-adherence question),
or Jarvis defaults to "braid" as its catch-all word for any plaited/textured hair it cannot name
more precisely in four words (a reading-bias question). Either way, this is the batch's real miss,
not the outfit-repeat or candid counts (both clear cleanly on both readings).

**Numeric gate:** 24 plates, **23 WROUGHT / 1 OFF-STYLE** (`detail_mid`).

**Tells gate: REJECT** (n=24, the strongest rejection of all five batches). `centered_stock_pose`
batch 0.833 vs 0.662 threshold (0.171 over). `covary` top three: `framing=full body standing, head
to toe, weight on one hip, head turned a little, gaze off to one side, framed off-centre` (1.00),
`light=key light from the upper right` (1.00), `appearance=handsome` (1.00). **The framing option
authored specifically to escape a stock pose is the top covariate FOR the stock-pose tell** — every
frame drawn with that "off-centre" composition option still reads as `centered_stock_pose` to
Jarvis. The candid framing axis is not achieving what its name says, at least against this tell.

Evidence: [`v2_wardrobe_hair_variety.jpg`](evidence/v2_wardrobe_hair_variety.jpg) — 6×4, human then
orc, each cell labelled `race+index, outfit read, hair read, candid:<bool>`.

**Vocabulary change:** none made in this task — the braid over-read is real and large enough to act
on (either audit the render for unintended braid texture, or revisit whether "braid" is doing double
duty in Jarvis's own vocabulary); the candid-framing/stock-pose covariance is worth the same kind of
look before the next batch reuses `COMPOSITION_WEIGHTED` as a fix for anything.

### 10.7 Lane B asset plates — 36 dwarf plates, 6 each of outfit/weapon/shoes/armour/equipment/accessory

`FIGURE_QUESTION` (`wrought_tells.py`, field list from `task-15-brief.md` step 5, same template):

> Answer in JSON only. "figure_present": true/false (a headless mannequin is not a figure).
> "object": three words. {"figure_present": b, "object": s}

One frame's prompt (`dwarf_outfit/000`, verbatim caption: *"labourer romanesque outfit, a long-
sleeved chemise, a padded gambeson, a wide wool skirt, a lamellar of small leather plates laced in
rows, tall boots, a belt of linked plates, a wooden bead necklace, patched many times"*) — full
prompt:

> A single strong directional key light in a dark studio, deep readable form shadows, almost no
> fill, no rim light, no set. Worked materials: tooled leather with flex creases and stitching,
> rivets seated in straps, beaten engraved metal that highlights only on its edges, matte chalky
> cloth with readable weave. Selective realism, not a photograph, not pore-level skin, not oil
> paint, not painterly, not cartoon. Full punchy earth and iron colour, not muted, not cinematic
> grade. labourer romanesque clothes on an empty mannequin with no head, front view, the garments
> alone with no figure: a long-sleeved chemise, a padded gambeson, a wide wool skirt, a lamellar of
> small leather plates laced in rows, tall boots, a belt of linked plates, a wooden bead necklace;
> undyed, the colour of the sheep and the plant, no ornament, patched many times; materials: forged
> steel, wrought iron, cut stone, gold, deep-fired craft, grounded stylized realism …

**`FIGURE_QUESTION` reads, real Jarvis, 36 plates: `figure_present` true on 0/36 — exactly the
expectation**, confirming the Phase-1 by-eye spot check. `object` reads are legible and sensible
throughout (a sample: "medieval leather boot", "war hammer with a", "ornate metal cuirass", "leather
western saddle", "key ring necklace", "leather leather helmet" — the last a stutter in Jarvis's own
four-word budget, not a content error).

**Numeric gate (`detail_mid`+`material_floor`, offline — this is the SAME criterion step 5 asks
for, already computed at render time):**

| kind | plates | WROUGHT | OFF-STYLE | reasons |
|---|---|---|---|---|
| outfit | 6 | 5 | 1 | detail_mid |
| weapon | 6 | 4 | 2 | detail_mid, material_floor |
| shoes | 6 | 2 | 4 | detail_mid ×2, material_floor ×2 |
| armour | 6 | 6 | 0 | — |
| equipment | 6 | 5 | 1 | material_floor |
| accessory | 6 | 3 | 3 | material_floor ×2, detail_mid |
| **total** | **36** | **25** | **11** | detail_mid ×5, material_floor ×6 |

**25 of 36 clears the numeric gate — under the expected "≥ 30 of 36."** `gloss_fraction` never
fires as a hard failure across all 36 (expected: these are props, not organic subjects, so gloss is
advisory only, matching `check_wrought`'s own `--organic` gating). `shoes` and `accessory` are the
weakest kinds (2/6 and 3/6); worth a closer look before this batch is called done, independent of
the Jarvis figure/object read.

Evidence: [`v2_lane_b_assets.jpg`](evidence/v2_lane_b_assets.jpg) — 6 rows (kind) × 6 columns
(instance), each cell labelled `kind+index, fig:<bool>, object read`.

**Tells gate: PASS** (n=36, offending=[]) — the only clean pass of all five batches; `assets` is
also the only batch with no organic subject (props on a mannequin/void), consistent with §10.1's own
`FLOOR`/keeper design being built from character plates.

**Vocabulary change:** none needed on the Jarvis axis (figure/object both read clean); the
numeric-gate miss on `shoes`/`accessory` (§ above) is still worth a look, unrelated to anything
Jarvis reads.

### Status: both phases complete

Every batch has been read, gated (both gates), sheeted, and written up. Nothing was hand-fixed to
pass; every miss above is recorded as found. Concrete open items carried forward, none fixed in this
task:

1. **Beastfolk** — bear/panda species-read at 0/5 combined (their `SUBSPECIES` row has no skin
   `"marks"` clause, unlike every subspecies that reads correctly); the subspecies draw itself is
   uneven (needs round-robin); one `fur_body` false-positive.
2. **Dragonborn** — the whole-body scale clause does not clearly raise the `scale_coverage` read
   even in its own dedicated, lineage-correct re-render (3/20 "whole", actually lower than the 3/8
   inside batch1); face_skin/scale_colour agreement improves directionally but stays well under the
   ≥70% target in every group.
3. **Nations** — the cross-record identity-uniqueness question (are the ten drawn faces per race
   distinct from EACH OTHER) is still open; `same_person` answered a different, narrower question
   (skin vs. its own suit) and answered it 30/30 clean. Dwarf's numeric gate (9/20) is the weakest of
   the three races.
4. **Wardrobe/hair** — braid reads at 83.3% against 41.7% authored, the largest single miss in this
   task; the candid-framing option is the top covariate for `centered_stock_pose`, the opposite of
   its intent.
5. **Lane-B assets** — the only batch that passes the tells gate clean; its numeric gate still sits
   at 25/36 (`shoes` 2/6, `accessory` 3/6 the weakest kinds).
6. **Every batch but assets REJECTs the tells gate**, always on `centered_stock_pose` or `no_grain`,
   never on a vocabulary-specific tell, and `covary`'s top axis is consistently a light angle or a
   small-n appearance/nation value — worth a wider sample before reading any of these covary tops as
   a clause-specific verdict.
7. **The silhouette measure of record is now whole-mask overlap, not a px bar** — 0/94 pairs score
   `same_body` on this reference-edit suit path, all in the "different body by eye" band; Task 15D's
   suit-path replacement is the actual fix, not a number this task could set.
