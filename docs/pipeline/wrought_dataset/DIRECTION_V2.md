# Wrought dataset v2 — direction (APPROVED 2026-09-05, evening)

Companion to `README.md` (v1 night run and its lessons). This file is the design the v2 build follows.
Status: **approved by the owner** after a two-round review with Jarvis (reason role, no standing
disagreements). Evidence sheet: `evidence/v2_defects_measured_2026-09-05.jpg`.

## 0. Owner decisions (verbatim, 2026-09-05)

| # | question | owner |
|---|---|---|
| 1 | the two attached dragonborn images | "grokAI imagine generated to show that the skin/scales are not a part of the armor" — a target for scale placement (scales on SKIN, armour plain), not a look target |
| 2 | deer antlers / horns | "small antlers on the female deer, no horns on the other 5" |
| 3 | clan / nation names | "region placeholders until I name them" |
| 4 | Lane A = compression suit | question back: "if we put a compression suit on the body how do we show the details underneath?" — answered in §9 (Jarvis + Claude) |
| 5 | dataset = Lane A + Lane B (fit plates 1:1), no dressed-hero share | "yes" |
| 6 | 20-sheet RAW-native reference test before any download | "run the test" |
| 7 | sheet lighting if the path cannot re-light to flat | "accept" a directional-soft key that is flat enough for 3D |
| 8 | Lane-A canvas | "whatever is best to lead up to a 3D asset" — decided in §9 |
| 9 | candid composition on dressed frames, suit frames square | "whatever is best" — decided in §9 |

The remainder is the reviewed draft as it stood at approval (sections 1-6), then Jarvis's two review
rounds (7-8), then the Q4 resolution and the canvas/composition decisions (9).

---


Date 2026-09-05. Status: DRAFT, nothing implemented. Teacher plate = 002 (orc swordswoman) is the
in-game look truth; PICK.md + 002_REPEATABLE_FACTORS are the acceptance criteria. Krea 2 family
(loxsUtopicWorldKrea2 on the Krea 2 architecture: Qwen3-VL-4B encoder, single-stream DiT, Qwen VAE),
52 steps / CFG 3.5 / euler simple / AuraFlow shift 1.15, 768x1344 figure / 768x1024 portrait.

## 1. What the owner named today, and what was measured

Owner's six points: (1) frames still look like AI images; (2) beastfolk are six subspecies — leopard,
bear, lion, deer, panda, wolf — and every frame has horns; (3) dragonborn skin colour does not adhere
and scales land on the clothing; (4) skin diversity = nationalities/clans, no two characters alike;
(5) wardrobe repeats and hair is weak; (6) everything must translate to a reference sheet, then to a
3D character / clothing / hair / weapons / shoes; minimal-clothing character concepts, assets separate.

Measured this morning (Jarvis vision, gemma4:12b, 12 random night frames x 6 races + the 002 plate,
fixed vocabulary of tells):

| race | AI-score median (1-10) | top tells (of 12) |
|---|---|---|
| beastfolk | 8 | symmetry 12, generic pretty face 10, waxy skin 10 |
| dragonborn | 8 | symmetry 12, generic face 10, waxy 6, everything in focus 4, light everywhere 4 |
| orc | 8 | waxy 11, cluttered ornament 5, all-in-focus 5, symmetry 5 |
| human | 7.5 | generic face 12, symmetry 11, waxy 11 |
| high elf | 8 | generic face 12, symmetry 11, waxy 8, plastic 4 |
| dwarf | 7.5 | symmetry 10, waxy 9, centred stock pose 5 |
| 002 teacher | 8 | symmetry, light everywhere, glossy sheen, generic face |

So: the three dominant tells are PERFECT SYMMETRY, GENERIC PRETTY FACE, WAXY SKIN — and the teacher
plate carries them too. A vision LLM's AI-score cannot be the gate (it would fail 002); it ranks tells.
The target is "fewer named tells than 002", not a photograph.

Beastfolk: horns on 5/12; species read as fox 6, wolf 5, leopard 1 — the core says "sometimes small
horns" and names no species, so the model filled fox/wolf and rolled horns.
Dragonborn (records checked against the readings): the prompts drew face skin pale 30 / warm tan 27 /
deep brown 23 / olive 20 of 100, but Jarvis read the face as pale on all 12 sampled — including all 7
whose prompt said tan, olive or deep brown. Skin adherence 0/7 in the sample. Scale garments were
drawn in only 6/100 prompts, yet scales sit on the garment in 5/12 — the model puts them there unasked,
fed by the lineage scale sentence and the culture's "lacquered scale" material. Scales on skin 12/12,
horns 12/12 (correct).
Beastfolk hair: the hair axis gives beastfolk FUR ("a ruff of longer fur at the throat" 22/100, "a
thick mane" 11, "short dense fur" 14) instead of human hair — wrong for kemonomimi, where the head is
human and only the ear pair is animal.
Wardrobe: Jarvis named "leather and fur warrior armour/tunic" on the large majority of frames in all
six races regardless of drawn tier — the 002-lead materials sentence (tooled leather, rivets, beaten
metal) is the strongest wardrobe signal in the prompt and the 26-line CLOTHING table has no dialect, no
register, no slots, no dye. Hair: "braided" on ~60% (6 of 15 HAIR entries are braids).
Face identity: STRIKING/HANDSOME are the same sentence on every frame ("smooth clear skin, full cheeks,
large bright eyes, full lips, elegant even features") — a generic-pretty-face generator by construction;
APPEARANCE_NEGATIVE contains "asymmetric eyes", which enforces the symmetry tell.

## 2. Research — the model family

- Krea 2 (technical report): trained with ALL AI-generated images filtered out ("even a small proportion
  introduces biases"), SFT stage aimed at "high-saturation and texture issues". The base is anti-AI-look
  by design; the look we get comes from the Utopic finetune and from OUR prompt.
- Encoder = Qwen3-VL-4B, multilayer aggregation: natural prose, grammar, possessives, spatial relations;
  keyword lists and (word:1.3) weighting do nothing (owner's own KREA2 note agrees). Official length
  guidance: 30-80 words controlled, 80-140 complex; we run ~250+ — past ~300 words signal stops adding.
- Negatives: real on RAW at CFG 3.5 (what we run); "no negatives" advice is for Turbo at CFG 0.
  KJNodes Krea2PromptWeight (installed) removes concepts at the attention level "(horns:-1)" at CFG 1 —
  a candidate tool for "no horns" that works below the text encoder.
- Photoreal skin LoRAs (inline skin, realism V2) = pores = the photoreal failure. Not for Wrought.
- Reference/edit tooling on this core (v0.34.0): native Krea 2 ref_latents + ReferenceLatent +
  TextEncodeQwenImageEditPlus. QuadView_krea2_v1 (Alissonerdx, Turbo, 1536x1024, 10 steps CFG 1) makes
  face + front/side/back from ONE image; needs the krea2edit custom nodes (not installed) and says
  "consistency not 100%". A community identity/style reference path (KonokoAz nodes + a reference
  LoRA) exists. AI Toolkit trains Krea 2 EDIT LoRAs from paired input-to-target images — the way to
  train our own "Wrought plate -> flat A-pose sheet" or "-> garment-only plate" later.
- SpellBound's contract already exists: CHARACTER_IMAGE_INPUT_SPEC (A-pose, F/B/L/R, flat light, plain
  ground, >=1024 px on subject, separate clean-body and clothed sets, known height) and
  CONCEPT_TO_ASSET_PIPELINE (stage 2a sheet != stage 2b LoRA set; the look lives in the lighting law and
  does NOT survive the sheet, by design; garments fit-to-base; props parametric; hair is a curve system).

## 3. Anti-AI-look, adapted to Wrought (NOT the photo recipe)

The owner's pasted guide is right about the tells and wrong-for-us about the cure: camera bodies, film
stocks, grain and "candid phone snapshot" push toward the photograph 002 forbids. Keep the diagnosis,
translate the cure:

1. No quality/beauty adjectives anywhere ("gorgeous", "smooth clear skin", "elegant even features",
   "flawless"). Beauty stays a weighted tier but is spoken as proportion and structure.
2. Every face gets ONE drawn distinguishing mark and a stated slight asymmetry (one brow a little
   higher, a crooked front tooth, a mole, freckle cluster, a healed nick). Drop "asymmetric eyes" from
   the negative.
3. Skin clause = the Look Matrix Class C living-skin signal, verbatim: tone deepens into shadow and
   lightens on lit planes, warm reddish undertone where tissue is thin (ears, nose, knuckles, lips),
   meso mottle, no pores, no gloss. This is what "not waxy" means in Wrought; 002 does it.
4. Composition axis with weight: straight-and-square (kept for suit/measurement frames) vs candid
   (off-centre, weight on one hip, head turned, gaze off-axis, mid-gesture) for dressed concept frames.
   Stage 0 exploration is allowed any pose; only the sheet is rigid.
5. Kit imperfections named at meso scale: sleeve creased at the elbow, a scuffed boot toe, one rivet
   dented, a strap twisted — the "named imperfections" rule applied to Class A/B, where Wrought wants
   its detail.
6. One key, shadow side to near-black, no fill — already law; keep. "Everything in focus" is not a
   Wrought fault (no bokeh in 002; the pipeline doc says bokeh is fatal to a reference).
7. Prompt length down toward ~150 words by removing restatement; the encoder reads grammar, not volume.

Measure (revised with Jarvis, round 1): the tells probe is a CHANGE-DETECTION GATE against the locks,
not a score threshold. Calibrate first on a locked keeper set (owner-kept frames + 002, same probe,
same model) to record per-tell rates and their spread; a batch is rejected when any tell's rate
exceeds the keeper rate by more than the calibrated margin; the generator logs the prompt clause
that co-varies with the tell, one retry fires with that clause swapped, two failures flag the owner.

## 4. Vocabulary v2 (wrought_variants.py)

- SUBSPECIES["beastfolk"] = leopard / bear / lion / deer / panda / wolf. Each owns: ear shape, tail,
  fur-marking pattern on skin (leopard rosettes at forearms/shoulders, lion tawny + tail tuft, wolf
  grey/black guard hair, deer dappled fawn spots, panda black eye patches + black ears, bear round ears),
  hair-colour family, and headgear: NONE except deer (small antlers — OWNER TO CONFIRM; the deer row
  fires a build-log warning until confirmed). Kemonomimi: human face, ONLY the animal ear pair on top,
  no human ear pair (the owner's bear-lock wording). "sometimes small horns" leaves the core. Table
  shape (Jarvis, round 1, with Claude's bear/panda edit — the owner's W5 bear lock is "smooth warm
  brown skin, no body fur, ONLY a pair of round tan bear ears"):

      leopard: ears tall rounded black-tipped | tail long ringed | marks rosettes at forearms+shoulders (skin pattern) | hair warm black coarse | headgear none
      bear:    ears round small tan            | tail short stub  | marks NONE (ears only)                              | hair dark brown thick  | headgear none
      lion:    ears broad rounded              | tail tawny tufted| marks warm tawny cast at forearms+shoulders (skin pattern) | hair golden wavy mane-length | headgear none
      deer:    ears tall narrow fawn-lined     | tail short white-tipped | marks dappled fawn spots at shoulders         | hair light brown wavy  | headgear small antlers [TBD-owner]
      panda:   ears round black                | tail short black-tipped | marks black eye patches only                  | hair black straight coarse | headgear none
      wolf:    ears tall pointed black-tipped  | tail bushy grey-black | marks grey-black mottled markings at forearms (skin pattern) | hair grey straight coarse | headgear none

  Beastfolk take ordinary human HAIR (the fur-hair branch of hair_for goes).
- Dragonborn garment clause (positive, replaces the "lacquered scale" material reference): "Her
  garment is plain worked leather and woven cloth with visible stitch lines and a matte finish; there
  is no scale pattern, no scale texture, and no lacquered surface on the clothing."
- Face-bundle clause (replaces every STRIKING/HANDSOME sentence): "Her face is structured, not styled:
  [jaw], [cheek structure], [brow shape, one brow set a little higher], [nose bridge], [lip fullness].
  One small mark: [healed nick on the left cheek / freckle cluster on the right temple / crooked front
  tooth / mole under the right eye]. The skin is living tissue: tone deepens into shadow and lightens
  on lit planes; a warm reddish undertone shows where the skin is thin over the ears, the nose tip and
  the knuckles; fine mottling at close range; no gloss, no pore detail, no plastic sheen."
- Dragonborn: SKIN owns the whole skin ("her skin is warm tan; the scales are a pattern ON that skin at
  temples, jaw, neck, forearms, backs of the hands"); LINEAGE owns scale colour, eyes, horn only;
  wardrobe for dragonborn excludes scale garments and the culture's "lacquered scale" material is
  spoken as armour PLATE, not scale; positive "the garment is plain worked leather and cloth with no
  scale pattern".
- NATION/CLAN per race (3-6 peoples each): skin-tone family from the Bible ranges (orc olive/forest/
  dark brown/grey-green/slate + some bloodlines with bony ridges + glowing ritual ink; goblin green/
  olive/chartreuse/yellow-green/grey-green + clan-dyed hair + clan ear shape; human "all tones" by
  kingdom Monarchy/Parliament/Republic + region; dwarf ruddy/brown/freckled; elves by Bible), hair
  texture, a clan marker (dye, braid style, tattoo ink, scar culture, bead colour). Ships NOW with one
  fully worked nation per race; the remaining slots are TBD(owner) in code with a build-log warning,
  and until they are named the uniqueness hash collapses to (race, skin, hair, face bundle, mark).
- Face bundle drawn per frame: eye shape, brow, lips, cheek, jaw, chin, nose bridge + the one mark +
  asymmetry. Beauty tier reweights the bundle, never re-words it.
- Uniqueness: identity tuple (race, nation, skin, hair colour+texture, eyes, face bundle, mark) hashed;
  a batch refuses a repeat; the audit reports nearest-duplicate pairs.
- Wardrobe generator = dialect (Gothic, Tudor, Vernacular first; race dialects from the culture files)
  x register (rank band, profession, institution, occasion, condition) x garment slots (under, torso,
  legs, outer, feet, hands, head, belt, one accessory) x dye law (saturation by class) x race material
  logic. The Clothing Production Guide already defines all of this in prose; none of it is in code.
- Hair generator = texture (straight/wavy/coily/coarse) x length x style from the Bible's per-race
  style lists (orc warrior braids / half-shaved undercut (men) / high ponytail / long free mane; goblin
  messy bun / short spikes / side-shave / high ponytail with scrap clips; human braids / buns / long
  curls) x adornment (beads, rings, cord, clan dye streaks). "A full head of" stays.
- Negative cleanup: remove "asymmetric eyes"; keep the house negative; add nothing photographic.

## 5. Two dataset lanes (the owner's split) and the sheet path

- LANE A — character concepts in the compression suit: body, face, race, skin, nation. Square to camera,
  head to toe, 768x1344. This is the subject that becomes the 3D character and the input to the sheet.
- LANE B — asset concepts: clothing sets, shoes, weapons, armour, equipment, accessories as standalone
  plates on an empty mannequin / neutral ground under the Wrought light law (Clothing Guide 7.5 and
  the Character Guide weapon-only pattern), front + back. Wardrobe generator feeds this lane.
- Dressed plates are a Lane-B SUB-LANE, not a share of Lane A: garment-on-body fit plates at 1:1 with
  garment-alone plates, so the LoRA (and stage 5, garments fit-to-base) sees cloth on a body and cloth
  alone in equal measure.
- Sheet (stage 2a): from a Lane-A suit plate -> Krea 2 reference path -> F/B/L/R ->
  prepare_reference_sheet.py -> check_reference_sheet.py against the input spec. Flat light for the
  sheet, by contract. Test order: (1) RAW/Utopic-native ReferenceLatent + TextEncodeQwenImageEditPlus,
  already in the core, no download; measured on 20 sheets for identity and re-lighting; (2) only if
  that fails, QuadView_krea2_v1 on Turbo (914 MB + krea2edit nodes, owner approval). Garments
  likewise: plate -> front/back product views. The >=1024 px subject rule is enforced on the SHEET
  views (1216x1728) as a hard filter; Lane-A plates are input, not sheet output.
- Training snapshot is FROZEN: new plates go to a candidate pool; retrain only from the frozen set
  plus owner-approved additions (Jarvis: self-reinforcing drift).
- Krea2PromptWeight "(horns:-1)" is a PROBE tool (needs CFG 1, off the house recipe): test on 10
  beastfolk frames before any production use.

## 6. Open questions for the owner
Q1 the two attached images — night frames, own renders, or targets? what in them is wanted?
Q2 deer: small antlers on women or bare head? confirm no horns on the other five.
Q3 clan / nation names — exist, or use region placeholders?
Q4 dataset = A + B only, or A + B + thin dressed set?
Q5 approve installing krea2edit nodes + pulling QuadView_krea2_v1 + a reference LoRA for the sheet test?
Q6 Lane A = compression suit (not bikini armour) — confirm.
Q7 candid composition allowed on dressed concept frames; suit frames stay square — confirm.
Q8 (Jarvis) sheet lighting: the concept is one-key/shadow-to-black, the sheet contract is flat. If the
   reference path cannot re-light, accept a "directional soft" key that is flat enough for 3D, or hold
   the flat rule and fail such sheets? Changes what check_reference_sheet.py validates.
Q9 (Jarvis) Lane-A canvas: keep 768x1344 (subject ~1100-1200 px) or move to 1024x1792 so a plate
   itself clears the >=1024 px subject rule? Changes GPU cost per batch.


## 7. Jarvis review — round 1 (his critique of the draft)

### Agree

1. **Three-tell diagnosis and ranker-not-gate stance.** 002 scores 8, so a hard threshold fails the truth. Correct call.
2. **Beastfolk: delete "sometimes small horns," lock six subspecies, kemonomimi head rule (human face, only the animal ear pair, no human ears).** The model rolled fox/wolf and horns because the prompt left it open. Sealing the table is the only fix.
3. **Dragonborn skin-ownership restructure.** SKIN owns the whole skin; scales are a *pattern on* that skin at named locations. Scales-on-garment 5/12 with scales-in-prompt only 6/100 proves the lineage sentence is the source, not the garment instruction.
4. **Anti-AI-look: keep the diagnosis, drop the photograph cure.** No camera bodies, no film stocks, no grain. Wrought's "not waxy" = Class C living-skin signal, verbatim from the Look Matrix. Correct translation.
5. **Two-lane split (A: character in compression suit; B: asset plates on mannequin).** This is the only architecture that makes the 3D handoff tractable.
6. **Prompt length to ~150 words.** The Qwen3-VL-4B encoder reads grammar and spatial relations, not keyword volume. 250+ words is past the useful range and the extra text is restatement.
7. **Wardrobe generator: dialect × register × slots × dye × race material.** The Clothing Guide defines all of this in prose; none of it is in code. Building it is the point.
8. **Drop "asymmetric eyes" from APPEARANCE_NEGATIVE.** It is actively enforcing the number-one tell.

### Disagree

1. **"Advisory ranker" is too weak.** If it doesn't block a batch, it's a dashboard nobody reads at 2 a.m. **Replacement:** the tells probe runs on every batch of 12; if the median AI-score is ≥ 002's baseline (8) *or* any single tell count exceeds 002's by ≥ 3, the batch is **rejected**, the generator logs which prompt clause correlated, and one retry fires with that clause swapped. Two retries → flag to owner. It is a *change-detection* gate against the teacher, not a pass/fail score.
2. **Nation/clan as "region placeholders until the owner names them" is a placeholder for a placeholder.** The table ships empty and the hash degrades. **Replacement:** the table ships **now** with one fully-worked nation per race (skin-tone family, hair texture, one clan marker, one dialect, one register default). Remaining slots are `TBD(owner)` in code with a build-log TODO. If the owner doesn't name them in two weeks, the single worked nation is the default and the dedup hash collapses to `(race, skin, hair, face-bundle, mark)`.
3. **"Thin dressed set ~20%" is the wrong ratio and the wrong purpose.** 20% dressed plates in a character-concept set teaches the LoRA that garments are optional accessories. **Replacement:** the dressed set is **not** a percentage of Lane A. It is a sub-lane of Lane B: "garment-on-body fit plates" at a **1:1 count** with the garment-off-body plates. The LoRA needs cloth-on-body and cloth-alone in equal measure to learn the fit relationship.
4. **Sheet path on Turbo (10 steps, CFG 1, 1536×1024) while concepts are RAW (52 steps, CFG 3.5, 768×1344).** Different model, different light response, different resolution. The sheet will not match the concept. **Replacement:** test the sheet path on **RAW first** using native `ref_latents` + `ReferenceLatent` at matching step/CFG. Turbo-QuadView is the fallback. Measure identity consistency on 20 sheets before pulling the 914 MB LoRA.

### Risks Claude missed

1. **Self-reinforcing drift.** If Lane-A plates are the LoRA training set, and the LoRA generates more Lane-A plates, the distribution collapses toward the first-batch mean. The LoRA training set must be a **frozen snapshot**; new plates go to a candidate pool; retrain at most monthly from the frozen set + owner-approved additions.
2. **Pixel-height spec violation.** The input spec requires ≥ 1024 px on the subject. At 768×1344 a head-to-toe figure lands at roughly 1100–1200 px — barely over. A slightly smaller composition drops under. Add a post-gen bounding-box height check as a **hard filter** before a plate enters the set.
3. **KJNodes attention-level negatives on Krea 2.** The `(horns:-1)` syntax is documented for SD1.5/SDXL attention graphs. Krea 2 is a single-stream DiT with a Qwen3-VL-4B encoder; the removal may not map. Test on 10 beastfolk frames before baking it in.
4. **Light-law contradiction at the sheet stage.** Concepts: one key, shadow to near-black, no fill. Sheet: flat light, by contract. The same character under two incompatible regimes looks like two different characters. If the reference/edit path can't re-light, the sheet carries the concept's single-key shadow and **fails the flat-light spec**.

### My additions

**Beastfolk subspecies table (`wrought_variants.py`), concrete shape:**

```
"leopard": {"ears":"tall, rounded, black-tipped","tail":"long, ringed",
            "fur_marks":"rosettes forearms + shoulders","hair":"warm black, coarse",
            "headgear":"none"},
"bear":    {"ears":"round, small","tail":"short stub",
            "fur_marks":"broad chest band","hair":"dark brown, thick","headgear":"none"},
"lion":    {"ears":"broad, rounded","tail":"tawny, tufted tip",
            "fur_marks":"tawny, no pattern","hair":"golden, wavy, mane-length","headgear":"none"},
"deer":    {"ears":"tall, narrow, fawn-lined","tail":"short, white-tipped",
            "fur_marks":"dappled fawn spots","hair":"light brown, wavy",
            "headgear":"small antlers [TBD-owner]"},
"panda":   {"ears":"round, black","tail":"short, black tip",
            "fur_marks":"black eye patches + black ears","hair":"black, straight, coarse","headgear":"none"},
"wolf":    {"ears":"tall, pointed, black-tipped","tail":"bushy, grey-black guard",
            "fur_marks":"grey-black guard hair","hair":"grey, straight, coarse","headgear":"none"}
```
The horns sentence is deleted. No subspecies has horns. The deer row fires a build-log warning until the owner confirms.

**Dragonborn garment-exclusion clause (positive prompt, replaces the "lacquered scale" material reference):**
> *"Her garment is plain worked leather and woven cloth with visible stitch lines and a matte finish; there is no scale pattern, no scale texture, and no lacquered surface on the clothing."*

**Face-bundle anti-AI clause (replaces every "striking / handsome" sentence):**
> *"Her face is structured, not styled: [jaw], [cheek structure], [brow shape, one a half-degree higher], [nose bridge], [lip fullness]. One small mark: [healed nick on left cheek / freckle cluster on right temple / crooked front tooth / mole under right eye]. The skin is living tissue: tone deepens into shadow and lightens on lit planes; a warm reddish undertone shows where the skin is thin over the ears, the nose tip, and the knuckles; fine mottling is visible at close range; there is no gloss, no pore detail, no plastic sheen."*

### Questions for the owner

1. **Pixel height.** The 768×1344 generation puts a head-to-toe figure at ~1100–1200 px; the spec says ≥ 1024. Do you want a bounding-box height check as a hard post-gen filter, and if a plate fails, auto-bump to 1024×1792 and regenerate? This changes GPU cost per batch.
2. **Sheet lighting.** The concept spec is one-key / shadow-to-black; the sheet spec is flat light. These are incompatible regimes. Do you want the sheet path to **re-light** (the reference/edit path may not support this), or do you accept a "directional soft" key that is flat *enough* for 3D reference but still has a key/shadow split? This changes what `check_reference_sheet.py` validates.

### Verdict

Agree with the changes above — specifically the change-detection gate, the 1:1 dressed-plate ratio, the RAW-first sheet test, and the frozen-LoRA training-set rule — pending the owner's answers on pixel height and sheet lighting.

## 8. Jarvis review — round 2 (final joint position, signed off)

### Standing disagreements

none

### Final rules we both hold

1. **Gate:** calibrate per-tell rates on a locked keeper set (owner's kept frames + 002, same 12B vision model, same probe); a batch is rejected when any tell's rate exceeds the keeper rate by more than a margin derived from the calibration spread; generator logs the co-varying prompt clause; one retry fires with that clause swapped; two failures flag the owner. Change-detection against locks, not a score threshold.
2. **Nation table:** ships now with one fully worked nation per race; remaining slots are `TBD(owner)` in code with a build-log warning; dedup hash collapses to `(race, skin, hair, face-bundle, mark)` until named.
3. **Dressed plates:** Lane-B sub-lane, garment-on-body at 1:1 count with garment-alone; not a percentage of Lane A; provides fit evidence for stage 5.
4. **Sheet path:** test RAW / Utopic-native first (ReferenceLatent + TextEncodeQwenImageEditPlus, already in core, no download) on 20 sheets; QuadView / Turbo is fallback; nothing downloaded without owner approval.
5. **LoRA training set:** frozen snapshot; new plates go to a candidate pool; retrain only from frozen set + owner-approved additions.
6. **Light-law test:** the 20-sheet measurement is the light-law check—can the reference path re-light to flat while holding identity; the owner's re-lighting question ships as written.
7. **Beastfolk subspecies table:** six rows, no horns, kemonomimi head rule (human face, animal ear pair only); bear and panda carry **ears only**, no body-fur marks (owner's W5 lock, 21 Aug); leopard / lion / wolf / deer marks stay as forearm-and-shoulder skin pattern.
8. **Dragonborn garment clause:** plain worked leather / woven cloth, visible stitch lines, matte finish, no scale pattern / texture / lacquered surface on clothing.
9. **Face-bundle clause:** structured-not-styled jaw / cheek / brow / nose / lip; one small mark; living-tissue skin signal; "one brow set a little higher" (prose, not a number); replaces every "striking / handsome" sentence.
10. **Krea2PromptWeight:** installed node is Krea-2-specific (Qwen3-VL encoder, CFG 1.0); probe tool, not a production clause, until the 10-frame beastfolk test says otherwise; cannot ride the CFG-3.5 house recipe.
11. **Pixel-height check:** hard filter on sheet views (stage 2a, 1216×1728) via `check_reference_sheet.py` subject-box measurement; Lane-A concept plates at 768×1344 are reference input, not sheet output, and are not re-rendered for it.
12. **Prompt length:** ~150 words; Qwen3-VL-4B reads grammar and spatial relations, not keyword volume.
13. **Anti-AI-look:** Class C living-skin signal verbatim from the Look Matrix; no camera bodies, film stocks, grain, or photograph vocabulary.
14. **APPEARANCE_NEGATIVE:** "asymmetric eyes" removed.

### Owner questions

1. Deer antlers: confirm or delete the row's `[TBD-owner]` headgear before it ships as default?
2. Bear / panda marks: confirm ears-only (no body-fur pattern) per the 21 Aug W5 lock?
3. Remaining nation / clan slots: name them within two weeks or the single worked nation becomes the default?
4. Sheet lighting: does the reference path re-light to flat while holding identity, or do you accept a "directional soft" key that is flat enough for 3D reference but still has a key / shadow split? This changes what `check_reference_sheet.py` validates.
5. Lane-A canvas: move from 768×1344 to 1024×1792 to give headroom above the 1024 px subject-box floor, or keep 768×1344 and let the sheet-stage check be the only hard filter?
6. Krea2PromptWeight: approve the 10-frame beastfolk probe before any production use?
7. Keeper set for gate calibration: confirm the exact frame list (your kept frames + 002) before the first calibration run?
8. RAW-first sheet test: approve measuring 20 sheets on the native path before downloading the 914 MB QuadView / Turbo LoRA?

### Sign-off

Agreed, with the single condition that the gate's calibration run is completed and the per-tell keeper rates are logged before any subsequent batch is released to the candidate pool.


## 9. Q4 resolved — what is under the suit; canvas; composition (2026-09-05, late)

### Jarvis's answer (reason role, verbatim)

### Recommendation

**Option (a).** The suit plate is the blockout/measurement truth; the skin plate is the material-and-identity truth. They solve non-overlapping problems. (b) fails because 3D decal placement and MorphLayer banding need *full-body* skin context—crops with "markings inferred" can't anchor a dragonborn scale patch to forearm UV. (c) discards the millimetre-precision that justified the suit and returns to prose-stated silhouette, the exact failure the pipeline is escaping. Two renders per character is the minimum cost to get both signals from one identity anchor.

### Plate list per character

| # | Plate | Framing / Canvas |
|---|-------|-----------------|
| 1 | **SKIN** — neutral A-pose, plain black sports bra + fitted black shorts, barefoot | Full-body, 1024 × 1536 |
| 2 | **SUIT** — matte compression suit, same pose, ReferenceLatent edit of plate 1 | Full-body, 1024 × 1536 |
| 3a | Face crop (head-and-shoulders) | 768 × 1024, cropped from plate 1 |
| 3b | Forearm + hand crop | 768 × 1024, cropped from plate 1 |
| 3c | Foot / lower-leg crop | 768 × 1024, cropped from plate 1 |

Crops are **not** separate renders; they are the owner's section-6 detail plates sourced from the skin plate where markings are already visible.

### Prompt clauses

**Skin plate wardrobe:**
"Plain matte black sports bra, plain matte black fitted athletic shorts, hem mid-thigh, no logos, no seams visible, no embellishment, barefoot, bare arms to shoulder, bare neck, neutral expression, standing A-pose, full-body framing, Wrought v2 key light, neutral grey studio backdrop."

**Suit edit (single-step ReferenceLatent):**
"Replace the sports bra and shorts with a matte black full-body compression suit, full coverage mid-thigh to neck, no exposed skin except face and hands, identical pose, identical framing, identical identity, no change to head, jaw, or expression."

### Measurements

- **Silhouette delta:** hip-width and waist-width in px, suit vs two-piece at 1024 px canvas width. Accept < 4 px; reject > 8 px (drift → re-run).
- **Identity lock:** ArcFace cosine similarity on face regions of both plates; threshold ≥ 0.85.
- **Marking legibility:** each race marking's bounding box in the skin plate ≥ 12 % of canvas width (ensures LoRA can sample it).
- **Crop fidelity:** forearm crop must show ≥ 3 distinct features (scale patch, scar, striation) each ≥ 64 px.

### Risk

- **Two-piece fan-service drift.** "Plain, matte, no embellishment" suppresses but doesn't eliminate it. Hard-reject any plate where hem drops below mid-thigh or neckline dips below sternum.
- **Edit-path identity shift.** ReferenceLatent can nudge jaw/eye geometry over multi-step edits. Single-step only; verify ArcFace ≥ 0.85 before accepting.
- **Coverage flag.** Sports bra + fitted shorts is the industry-standard measurement wardrobe ("fully clothed, designed coverage"). State this in the sheet header to preempt content-safety flags.
- **Cost.** 2 renders/character vs 1 for (b)/(c), but (b)/(c) produce a sheet the 3D team bounces back—2–3× rework cost. Two renders now is cheaper.

### Claude's decision, with two corrections to the above

**Adopted: option (a), two plates per Lane-A character, one identity.**

1. **SKIN plate first.** Plain matte black sports bra + fitted black shorts to mid-thigh, barefoot, arms
   bare to the shoulder, neck bare; neutral A-pose (arms 30-45 degrees out, legs apart, square to
   camera), full body head to toe. This plate establishes identity, the race markings on skin
   (dragonborn scale patches at temples/neck/forearms/backs of hands; beastfolk ear pair + skin-pattern
   marks at forearms/shoulders; orc bony ridges; goblin speckling; clan ink; scars; the living-skin tone
   map) and the muscle/soft-layer read. It is the source of the face / forearm / foot crops (crops, not
   renders).
2. **SUIT plate second, as a single-step ReferenceLatent edit of the skin plate** (native core path):
   "replace the sports bra and shorts with a matte dark grey full-body compression suit, full coverage
   neck to ankle, identical pose, framing, identity". The suit plate is the proportion/silhouette
   truth for the blockout and the MorphLayer bands; the skin plate is the material truth for the
   Class C skin and the decal plan. This edit IS the first case of the 20-sheet reference test.
3. **Correction 1 — background.** Jarvis wrote "neutral grey studio backdrop". No: Lane-A plates carry
   the LOOK (they train the LoRA), so they keep the Wrought law — dark studio, one hard key, shadow
   side to near-black. The flat-lit, plain-ground versions are the stage-2a SHEET views, derived from
   these plates by the reference path and checked by `check_reference_sheet.py`. Same rule as before:
   the look does not survive the sheet, by contract.
4. **Correction 2 — canvas (owner Q8: "whatever is best to lead up to a 3D asset").** Jarvis proposed
   1024x1536. The A-pose needs WIDTH (the sheet script found arms reaching the frame edge on a tall
   narrow canvas and widened to 1216x1728). Lane-A plates therefore render at **1216x1728** — the
   proven A-pose canvas, ~2.1 MP, subject ~1500 px tall (clears the >=1024 px rule with headroom, and a
   full-body frame still yields a usable face crop). The Wrought recipe was locked at 768x1024 /
   768x1344, so the first six Lane-A plates are a paint check against 002 (gloss, face texture, tells)
   before the size is committed. Lane B keeps the owner-locked 768x1024 (asset plates) and 768x1344
   (fit plates).
5. **Composition (owner Q9: "whatever is best").** Lane A is technical: A-pose, square, no candid.
   The anti-AI composition axis lives in Lane B's garment-on-body FIT plates: square front 60 / candid
   40 (off-centre, weight on one hip, head turned, gaze off-axis, mid-gesture). Garment-alone plates
   are product views, front + back, square.
6. **Measurements (Jarvis's list, made runnable here):** silhouette delta suit-vs-two-piece at hip and
   waist in px on the same canvas (accept < 4 px, reject > 8 px); identity between the two plates — a
   face-embedding cosine if `insightface` is available, otherwise the vision judge's same-person
   verdict plus face-crop MAE, recorded, threshold set after the first 20 pairs (Doc 50 rule 1);
   marking legibility — each race marking's box >= 12% of canvas width on the skin plate; two-piece
   coverage — hem at mid-thigh and neckline above the sternum, hard reject otherwise (advisory vision
   read, then eye).
7. **Coverage rule.** Sports bra + fitted shorts is the industry measurement wardrobe: designed
   coverage, "fully clothed" in the Look Matrix's own phrasing (revealing wardrobe is an option, not the
   default; this is not revealing, it is measurement). Stated in the plate header.

**Cost:** two renders per Lane-A character (skin + suit edit) instead of one; the crops are free.
