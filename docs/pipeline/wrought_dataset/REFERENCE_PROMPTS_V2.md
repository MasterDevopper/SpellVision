# Wrought v2 — owner reference-image prompts (2026-09-06)

The owner generates these in Grok. They are **placement, proportion and coverage targets, not look
targets**: the Wrought paint still comes from `_locks/002_orc_teacher/plate.png` and the style block.
What each image settles is *what the body is* — how far the fur or the scales go, what the face and
the hands are, how the race is proportioned — which is exactly what the first v2 batch got wrong
(DIRECTION_V2 §10: a clause that names places renders as a garment).

Every prompt below is one paragraph, ready to paste. They all open with the same **plate contract**
so the images are directly comparable with the Lane-A skin plates the pipeline renders.

---

## The plate contract (identical in every prompt)

> Full body, head to feet, both feet fully inside the frame, nothing cropped. She stands straight
> and square to the camera in a neutral A-pose: arms held about thirty degrees out from her sides,
> palms turned toward her thighs, fingers relaxed and slightly apart, legs about shoulder width
> apart, weight even on both feet. Neutral expression, mouth closed, looking at the camera. She
> wears a plain matte mid-grey sports bra and plain matte mid-grey fitted shorts to mid-thigh, no
> logos, no seams, no embellishment; barefoot, arms bare to the shoulder, neck and collarbones
> bare. Plain near-black studio void behind her, no set, no floor pattern, no props, no weapon, no
> armour, no cloak, no jewellery, no text. A single strong directional key light from slightly above
> and in front, deep readable shadows, almost no fill, no rim light. Tall portrait frame, roughly
> 2:3. Grounded stylized realism with physically based materials, not a photograph, not painterly,
> not cartoon, not anime, no gloss and no plastic sheen. One character only, an adult woman in her
> mid-twenties.

Why these choices: the two-piece and bare limbs are what let an image show skin, fur or scale
coverage over the whole body, which is the thing being decided. The A-pose and the dark void are
what the silhouette measure reads. The 2:3 frame matches the 1216×1728 canvas.

---

## 1. Orc

> [plate contract] She is an orc: tall and powerfully built, heavy muscle under a soft layer, lower
> tusks rising from the jaw, a strong jaw and a sloping brow, pointed ears. Her skin is olive-green.
> Black hair, coarse and thick, in braids with white warpaint streaks through them.

Nation swaps (replace the last sentence):
- **highland** — olive-green or grey-green slate skin; coarse thick hair; white warpaint streaks through the braids.
- **lowland** — forest-green or deep green skin; coarse straight hair; red ritual tattoo-ink lines along the forearms.
- **coastal** — dark brown skin with a green cast, or slate-grey; coarse wavy hair; bony ridges along the brow and the shoulders.

## 2. Goblin

> [plate contract] She is a goblin: small and wiry, with adult proportions and an adult head-to-body
> ratio, never a doll or a child. A broad nose, long pointed ears, a wide mouth with small sharp
> teeth, a small delicate face and a small nose. Her skin is mossy green. Wiry black hair with
> clan-dyed teal streaks, and ears ragged at the edges.

Nation swaps:
- **warren** — mossy or grey-green skin; wiry hair; ragged ear edges, teal clan dye.
- **scrapyard** — dull olive-yellow or chartreuse skin; coarse spiky hair; sharply spiked ears, bright pink clan dye.
- **marsh** — sallow yellow-green or pale grey-green skin; fine wiry hair; floppy ears and faint bioluminescent freckles across the cheeks.

## 3. Dwarf

> [plate contract] She is a dwarf: about four and a half feet tall but as heavy as a tall human,
> stocky proportions of roughly five and a half heads tall, short limbs against a long deep torso,
> extremely broad for her height, a heavy brow and a strong nose, thick hair. Her skin is ruddy. Red
> hair, thick and straight, with temple braids bound in iron rings.

Nation swaps:
- **deephold** — ruddy or pale freckled skin; thick straight hair; temple braids bound in iron rings.
- **foothill** — warm tan or olive skin; thick wavy hair; a maker's mark tattooed on the back of each hand.
- **ashvault** — deep brown or dark umber skin; thick coiled hair; beads of cut stone threaded through the hair.

## 4. Human

> [plate contract] She is a human woman of an ordinary athletic build, no fantasy features of any
> kind. Her skin is warm brown. Dark brown hair, coiled and thick, worn loose.

Human nations read only through skin tone and hair on a plate this bare (their markers are cloth,
and the plate has none). Worth one image each if you want the three peoples to look distinct:
- **monarchy** — pale, fair freckled, olive or warm brown skin; straight or wavy hair.
- **parliament** — olive, golden tan, deep brown or pale skin; wavy or curly hair.
- **republic** — warm brown, deep brown, golden tan or fair skin; coiled or curly hair.

## 5. High elf

> [plate contract] She is a high elf: tall and slender, fine-boned but never boyish, long swept-back
> pointed ears, high cheekbones, smooth hairless skin, an upright unhurried carriage. Her skin is
> pale porcelain. Platinum blonde hair, fine and straight, under a thin silver circlet.

Nation swaps:
- **citadel** — pale porcelain or warm ivory skin; fine straight hair; a thin silver circlet.
- **coast** — pale golden or light olive skin; fine wavy hair; a single rune inked at the wrist.

## 6. Wood elf

> [plate contract] She is a wood elf: trim and athletic, pointed ears, full cheeks and never gaunt.
> Her skin is coppery. Dark brown hair, thick and wavy, dyed leaf-green at the tips.

Nation swaps:
- **greenwood** — coppery or tan olive skin; thick wavy hair; leaf-green dye at the tips of the hair.
- **highcanopy** — warm brown or deep copper skin; thick coiled hair; a bark-brown tattoo band around the upper arm.

## 7. Dark elf

> [plate contract] She is a dark elf: slighter and finer than a surface elf, long pointed ears, and
> pupil-less luminous eyes that carry against the dark skin. Her skin is obsidian-black with a violet
> cast. Stark white hair, silky and straight, with a crescent ornament in it.

Nation swaps:
- **undercity** — obsidian-black with a violet cast, or deep slate skin; silky straight hair; a crescent hair ornament.
- **deepmarch** — dusky grey, cool violet-grey or midnight-blue skin; silky gently wavy hair; faint glowing rune-lines at the collarbone.

---

## 8. Beastfolk — six subspecies, and the two ladders

Two things are still open here, and the images decide both.

**Ladder A — fur coverage.** Pick a level and say it in the prompt. These are the exact six the
generator now carries, so whatever you pick becomes the setting:

| level | wording to paste |
|---|---|
| none | smooth human skin over the whole body, no fur anywhere but the ears and the tail |
| down | a fine peach-fuzz down of body fur over the whole body from the neck down, so fine the skin tone shows through everywhere |
| velvet | short flat body fur over the whole body from the neck down, fine and dense as a horse's summer hair, the skin no longer showing through |
| short | short dense body fur over the whole body from the neck down, a few millimetres deep, every contour of the body still readable through it |
| plush | medium plush body fur over the whole body from the neck down, a centimetre deep, softening the contours, longer at the collar and the backs of the arms |
| long | long full body fur over the whole body from the neck down, thick and shaggy, a heavy ruff at the neck and shoulders |

**Ladder B — how animal the face and hands are.** This is the one you said you might push further.
Three rungs; paste one:

| rung | wording to paste |
|---|---|
| human (today) | a fully human face and human hands and feet, the body fur thinning to bare skin on the palms and the soles |
| part-animal | a human face shape with animal details: a short broad nose with a leathery nose pad, slightly forward cheekbones, animal-coloured eyes with a narrowed pupil, no muzzle; hands of human shape with soft pads on the palm and fingertips and short blunt claws, fur running to the second knuckle |
| full muzzle | a short animal muzzle on a humanlike skull, a wet nose pad, a lipped animal mouth, animal eyes with a narrowed pupil; paw-shaped hands with thick pads and curved claws, fur to the fingertips |

**Worth doing:** one subspecies (wolf reads clearest) at all three rungs of ladder B, so the range is
visible. Everything else at whichever rung you want.

Each subspecies prompt, with `[fur]` and `[face]` replaced from the tables above:

- **Leopard** — > [plate contract] She is a leopard beastfolk. Tall rounded leopard ears, black-tipped, on top of her head and no human ear pair; a long ringed leopard tail. [fur], leopard rosettes patterning it everywhere. [face]. Warm black hair, thick, with clan beads braided into it. Warm tan skin where it shows. No horns.
- **Bear** — > [plate contract] She is a bear beastfolk. Small round tan bear ears on top of her head and no human ear pair; a short stub tail. [fur], plain dark brown. [face]. Dark brown hair, thick, with clan beads braided into it. Brown skin where it shows. No horns.
- **Lion** — > [plate contract] She is a lion beastfolk. Broad rounded lion ears on top of her head and no human ear pair; a tawny lion tail with a tufted tip. [fur], plain tawny and darker along the spine. [face]. Golden hair, thick and long. Warm tan skin where it shows. No horns.
- **Deer** — > [plate contract] She is a deer beastfolk. Tall narrow fawn-lined deer ears on top of her head and no human ear pair; a short white-tipped deer tail; small antlers rising from her brow. [fur], dappled with fawn spots. [face]. Light brown hair, thick. Warm tan skin where it shows.
- **Panda** — > [plate contract] She is a panda beastfolk. Round black panda ears on top of her head and no human ear pair; a short black-tipped tail. [fur], black and white in the panda pattern: black arms and legs, a white torso. [face]. Black hair with white streaks, thick. Pale skin where it shows. No horns.
- **Wolf** — > [plate contract] She is a wolf beastfolk. Tall pointed black-tipped wolf ears on top of her head and no human ear pair; a bushy grey-black wolf tail. [fur], grey-black agouti and paler at the throat and the belly. [face]. Grey hair, coarse. Olive skin where it shows. No horns.

Standing rules that hold at every rung: **no muzzle unless you pick the full-muzzle rung**, the ears
are the only ear pair (no human ears beside them), the hair on her head is hair and not fur, and
deer is the only one with headgear.

---

## 9. Dragonborn — the hide, the head, the lineage

Three independent axes. The default the generator ships is *kemonomimi head + whole-body scale hide*.

**The hide** (this is the part the first batch got wrong, so it is the important one):

> from the jaw down her whole body is one unbroken hide of fine scales: neck, shoulders, chest,
> back, arms, hands, torso, legs, feet and tail, with no bare skin below the jaw and no scale
> pattern on the clothing

**The head** — five forks, paste one:

| fork | wording |
|---|---|
| kemonomimi (default) | a human face with a human nose and mouth, draconic features added rather than replacing them, no muzzle, long ridged horns above the ears sweeping back, long pointed ears, slit-pupil eyes, ordinary human hair |
| short muzzle | a short blunt draconic muzzle barely longer than the jaw, a broad frontal face, large forward-facing slit-pupil eyes set wide beneath a smooth scaled brow, small swept-back horns, fine scales, no external ears |
| flat faced | no muzzle at all, a flat scaled face on humanlike proportions, a low draconic nose ridge, large slit-pupil eyes, scaled brow and cheek plates, a lipless mouth, swept-back horns, no external ears |
| draconic | a fully draconic head, a tapered scaled muzzle with the nostrils at its tip, a heavy scaled brow ridge over slit-pupil eyes, swept-back horns rising from the skull, no external ears, no lips |
| crested | a fully draconic head on a long elegant neck, a slender tapered muzzle, a fanned membranous crest sweeping back from the skull in place of hair, fine iridescent scales, large luminous slit-pupil eyes, slim curving horns following the crest |

The full prompt, with the head fork pasted in:

> [plate contract] She is a dragonborn: tall and strong, well over six feet, clawed hands, a heavy
> tail, fine smooth scales and a slimmer neck. [head fork]. Her face is warm tan human skin, and
> from the jaw down her whole body is one unbroken hide of fine scales: neck, shoulders, chest,
> back, arms, hands, torso, legs, feet and tail, with no bare skin below the jaw and no scale
> pattern on the clothing. [lineage]. Dark red hair, thick and straight, with an oath-mark inked
> along her forearm.

**Lineage** changes only the scale colour, the eye colour and the horn colour. One image per lineage
is optional; two (one chromatic, one metallic) is enough to set the treatment:

| lineage | wording |
|---|---|
| black | matte charcoal-black scales with a faint oily green sheen along the ridges, deep green eyes, black horns and claws |
| blue | deep slate-blue scales paling to blue-grey at the throat and belly, pale gold eyes, dark blue-grey ridged horns |
| green | dull olive and moss-green scales darkening along the spine, amber-gold eyes, dark horn |
| red | deep oxblood-red scales darkening to near-black at the ridges and brightening at the throat, burning amber eyes, black horns and claws |
| white | pale bone-white and cold grey matte scales with no shine, ice-blue eyes, pale translucent horns |
| brass | warm dull brass scales gone green at the edges with age, dark amber eyes, weathered horn |
| bronze | dark bronze scales with a verdigris cast at the joints, gold eyes, dark ridged horns |
| copper | dull copper-red scales with green patina in the seams, blue-green eyes, dark horn |
| gold | muted old-gold scales, deep gold eyes, pale gold horns |
| silver | pale pewter-silver matte scales, dull and unpolished, pale grey eyes, white-grey horns |

Face skin, for the kemonomimi head, is one of: warm tan, olive, pale, deep brown, golden brown, dark
umber. Nation adds a marker only: **oathhold** an oath-mark inked along the forearm, thick straight
hair; **slatecoast** a lineage seal on a bronze collar, thick wavy hair.

---

## What to send back, and what happens to it

The minimum that settles everything open: **7 race images** (orc, goblin, dwarf, human, high elf,
wood elf, dark elf), **6 beastfolk** at your chosen fur and face rungs, **1 wolf set of 3** across
ladder B, and **2 dragonborn** (one head fork you want, one chromatic and one metallic lineage).
More is welcome; nations are optional and can come later.

Name each file for what it is, or just tell me the order. Anything works: `orc_highland.png`,
`beastfolk_wolf_plush_part-animal.png`, `dragonborn_red_kemonomimi.png`.

Then I read them against the vocabulary and rewrite the clauses to match what the images actually
show, one axis at a time, the way the whole-body scale clause was rewritten from your kemonomimi
reference. **The part that is not automatic:** a more animal face and hands has to survive the
render through `loxsUtopicWorldKrea2` at 52 steps / CFG 3.5, which is a separate question from
whether Grok can draw it. So the first thing I do with the ladder-B set is render the same rung
through our own path and compare; if the model will not hold it, the images still tell us which
rung to aim at and we solve it with a LoRA or a lower rung rather than guessing.
