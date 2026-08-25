# Canonical mesh output vs Path B (2026-08-18)

Owner asked: how does the Character Studio Canonical Mesh Output Plan
compare to the plan we have been running?

## Rec

**Adopt that plan as the product north star.** It is the same split we
already chose: SpellVision authors identity on SpellBound’s frozen cage.

Amend three lines so it cannot fork into a second topology or a second DCC:

1. **Export is a package, not a rewritten `female.glb`.**  
   `character_create.json` + `sliders.json` + plates + textures. Vertex
   order stays the freeze. SV must never write
   `assets/models/human/female.glb`.
2. **High-frequency sculpt lives in SpellBound Look / Blender coach.**  
   Do not build a second mesh editor in Qt Character Studio. Studio
   viewport may *preview* the 14517 cage later; it does not own topo.
3. **TRELLIS / Hunyuan wrap is a teacher only.**  
   Same as Path B: generated topology is never identity. Wrap or discard.

## Same

| Their plan | Live Path B |
|---|---|
| Never create new topology | Pixal/TRELLIS refused as identity |
| Canonical = `female.glb` | **14517** verts · `Human.rig` **53** · sha `03a9eabd…` |
| Plates are visual targets | Krea2 plates → Jarvis pack |
| MorphLayer values out | `sliders.json` + `plate_to_sliders` |
| 2000 cc stylistic ceiling | Hybrid breast Phase 0 already |
| No patient / iRBSM | RBSM 30999 is not a MorphLayer |
| Clothes/anim keep working | T4 + 53-bone LBS stay on freeze |

## What we already landed (their Phase 0–1, engine half)

- Freeze + joint lock measured.
- Character Studio **Create character** writes
  `spellbound.character-studio-create.v1`.
- Fail-closed solver: clothes ≠ WHR, no B1–B5.
- Whole-body coverage registry (`morph_coverage_complete=false`).
- First face family: `jaw_wide` / `jaw_narrow` (graph-distance, leak 0).

That is **not** their success test yet. A studio character does **not**
yet open in SpellBound and drive Present breast. Sliders stay empty on a
clothes+face pack. Coverage is incomplete.

## Gaps (their Phase 2–4, not started)

| Their item | Status | Honest next |
|---|---|---|
| Studio starts from loaded 14517 mesh | Missing | Preview in SB Look first; SV can show stills |
| Project plates onto cage | Missing | Engine MorphLayers + later Look projection |
| Guided I2-3D wrap | Missing / refused as identity | Adjunct props only |
| Texture / material package | Missing | After morph coverage |
| Hard export: vert count + joint names | Landed (`python/character_export_validate.py`) | `validated:true` only on 14517 / Human.rig 53 / Path B |
| Isolation masks in Studio | Engine-only today | Keep atlas in SB; SV must not invent one |
| Image-true slider solve | Gate only | Need remaining families (chin, proportion, breast axes) |

## What we were running that their plan omitted

A **deep MorphLayer stack** so plates can actually look like the image.
Without face / proportion / breast projection / glute axes, “export
MorphLayer values” is a beauty preset, not a character.

Their success criterion (“opens in SpellBound and Present breast works”)
needs:

1. Coverage families authored (in progress — jaw first).
2. Figure or honest face solve (not clothes-as-WHR).
3. Package import in Cast `create_from_pack` (gate is wired; import of
   SV `runtime/characters/<id>/` still thin).

AAA (hair cook, stills→mesh, I5) stays **after** that.

## Alts (rejected)

- SV writes a new `.glb` “same looking” cage — retarget forever.
- Qt sculpt DCC that edits verts — duplicates Look / Blender.
- Keep TRELLIS mesh as the character — glued clothes, no MorphLayers.

## Serial (fused)

0. Grounding — **done**.
1. Path B package (plates + contract + sliders.json) — **landed, cook false**.
2. Morph families until plates can drive identity — **in progress**.
3. SV export validator (14517 + 53 names) — **landed** (`character_export_validate`).
4. SB import of `runtime/characters/<id>/` as `create_from_pack` — next engine increment.
5. Optional: 14517 preview in Studio (read-only).
6. AAA lanes after owner A on image-true stack.
