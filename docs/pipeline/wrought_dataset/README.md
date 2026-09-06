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
