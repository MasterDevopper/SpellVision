# Doc 11d — Character Creation, End to End (Runbook)

> The concrete beginning-to-end flow for one humanoid character, using the clean-open
> default stack. Companion to the 11c master plan. Tags: **[primary]** = in the "before
> animation" goal · **[deferred]** = later layer · **[added]** = a stage your list
> implied but didn't name, and that breaks the result if skipped.
>
> **Two places I resequenced your order** (dependency reasons, noted inline):
> 1. Inserted a **face rig** stage — it's the voice/lip-sync prerequisite and isn't the
>    same thing as body rigging.
> 2. Pulled **voice identity** ahead of **animation**, because voice is [primary] and
>    baked animation is [deferred] per the scope boundary.
>
> **Confidence:** clean-open defaults named; ⚠️ marks a stage that's research-grade or
> carries real integration cost today.

---

## The flow at a glance

```
0  Concept lock ─▶ 1  16-view expansion ─▶ 2  Base mesh (TRELLIS 2)
   ─▶ 3  Geometry refine (UltraShape) ─▶ 4  Retopo/UV/bake/LOD/collision
   ─▶ 5  Standardized head pass ─▶ 6  Garments + armor + weapons (regime-tagged)
   ─▶ 7  Fit / compose onto body ─▶ 8  Hair groom + gravity settle
   ─▶ 9  Body rig + skin (garments, weapon sockets, hair) ─▶ 10  Face rig + ARKit
   ─▶ 11  Voice identity ─▶ [12 Animation]* ─▶ [13 Lip-sync preview]*
   ─▶ 14  Validate ─▶ 15  Export + license metadata
                                              (* = deferred layer)
```

Each numbered stage is one Chain Studio node or one call into the ComfyUI-family / headless-`bpy` service. Everything between stages is a file artifact on disk (mesh, texture set, rig, sidecar) — decisive, inspectable gates, not visual guesswork.

---

## 0. Concept lock  `[primary]`
- **Goal:** turn your mental image of the character into a locked concept sheet — "close, then increment to perfect."
- **Tool:** SpellVision's existing T2I (your Flux/SDXL stack). Already built.
- **Runs on:** existing image path.
- **The increment-to-perfect loop:** generate a batch → you pick the closest → refine by (a) prompt edits, (b) img2img at moderate denoise to keep the silhouette, (c) inpaint to fix specific regions (face, hands), (d) **seed-lock** once it's close so further edits don't lose the identity. Converge, then **freeze** a canonical front view.
- **In → Out:** your idea (text/refs) → one locked hero image (front, clean background, neutral A/T-pose ideally).
- **You:** this is the *one* stage that's fully yours — visual judgment, no technical skill. Everything downstream inherits this image, so the lock gate matters.
- **Watch:** a busy pose or cluttered background poisons every later stage. Aim for a clean, upright, evenly-lit subject.
- **⚠️ Art-style consistency lives HERE (a first-class UNSOLVED problem — 11c §5).** This is where twenty assets are made to look like the *same game*. The target is **stylized-realistic**, the *hardest* band for generative 3D (pure stylized cleans up easily; pure realistic leans on scan detail; the middle wants deliberate forms + readable silhouettes, which generated meshes are worst at). The levers are all at this stage: a **house-style LoRA**, a **fixed prompt scaffold**, and **reference discipline** across every concept. Lock the *style*, not just the subject — the mesh chain inherits whatever this produces, and there is no downstream fix (only stages 4/15's material/shader treatment reinforces it).

## 1. Sixteen-view expansion  `[primary]`
- **Goal:** give the 3D generator real angles instead of forcing it to hallucinate the back.
- **Tool:** a multi-view diffusion step (or several guided T2I generations) seeded from the locked hero image.
- **Runs on:** ComfyUI family.
- **In → Out:** 1 hero image → up to **16 consistent views** (TRELLIS 2's max; your 5090 has the VRAM to use far more than the default 4).
- **You:** hands-off, but review the back/occluded views — this is where consistency drifts.
- **Watch:** multi-view *consistency* is the failure mode — if the back invents detail that contradicts the front, fix it here, not downstream.

## 2. Base mesh generation  `[primary]`
- **Goal:** first real 3D geometry.
- **Tool:** **TRELLIS 2 / TRELLIS.2-4B (MIT)** — the clean-open default. Feed the 16 views.
- **Runs on:** ComfyUI `native_comfy_template` family (the 11b L1 scaffolding).
- **In → Out:** 16 views → structured-latent mesh + base PBR (albedo/metallic/roughness).
- **Watch:** output is dense, triangle-heavy, and not yet game topology. That's expected — stages 3–4 handle it. Don't judge topology here.

## 3. Geometry refinement  `[primary]` ⚠️
- **Goal:** add high-frequency geometric detail and sharpen structure that TRELLIS over-smooths.
- **Tool:** **UltraShape 1.0** (coarse→fine refiner; ComfyUI-wrapped).
- **Decision — KEEP in v1 (resolves the earlier "cut it" position).** A fresh survey closed the doc's open concerns: **license = Apache 2.0** — clean for MIT/Apache, *not a blocker*; **maturity acceptable** — real paper (PKU-YuanGroup, arXiv 2512.21185), two independent ComfyUI wrappers (`jtydhr88/ComfyUI-UltraShape1` — updated Mar 2026, ~160★, Manager-installable, 10 nodes; `Hahihula/comfyui-ultrashape` — Docker image), production affordances (low-VRAM mode, chunked processing, configurable octree resolution, fp16/bf16/fp32, batch, GLB/OBJ/PLY/STL export).
- **Why it's real, not marginal — and NOT redundant with retopo.** Retopo+bake (stage 4) can only bake detail that *already exists* in the source; it faithfully preserves mush. UltraShape adds **genuine geometric detail *before* the bake** ("unlike remeshing tools, adds real geometric detail, not just smoothing"), so the bake has something worth capturing. Its "sharpens salient features" behaviour aims directly at the stylized-realistic weakness (§0 / 11c art-style).
- **Notable:** a **topology-preserving mode** exists ("consistent vertex indexing for rigging or blendshapes") — directly relevant to stages 5/10.
- **Runs on:** ComfyUI family, chained after stage 2.
- **In → Out:** coarse mesh → detailed high-res mesh.
- **You:** keep it **optional/toggleable per-asset**; validate it *sharpens* rather than *drifts* from the concept.
- **Watch:** the remaining ⚠️ is *integration cost*, not viability — optional deps (`cubvh`, `flash_attn`, `pymeshlab`) and OOM tuning are real.

## 4. Retopo → UV → bake → LOD → collision  `[added / primary]` ⚠️
- **Goal:** the game-ready pass. Nothing ships without this — generative meshes are *visual, not physical*.
- **Steps:** auto-retopo to clean quads (**Instant Meshes**, GPL) → auto-UV unwrap (Blender smart UV) → **bake** the refined mesh's detail + PBR onto the clean low-poly (retopo destroys the original UVs, so you re-bake — this is where material survives) → generate **LODs** → generate a **collision mesh**.
- **Runs on:** **headless `bpy` service** (Blender 5.2 LTS) + Instant Meshes.
- **In → Out:** detailed mesh + base PBR → clean quad mesh + baked normal/PBR maps + LOD chain + collider.
- **⚠️ Tangent basis = the single highest-priority engine hazard ([Doc 23](23_engine_import_contract.md) Tier 0).** The bake produces **normal maps**, and the engine currently fabricates an arbitrary, non-UV-aligned tangent when `TANGENT` is absent → **normal maps render WRONG, silently.** `bpy` bakes against **MikkTSpace**, so **export explicit MikkTSpace `TANGENT`** (and have the engine generate MikkTSpace-on-import) so the two bases match. Nothing else on the engine list matters more.
- **LOD + collision are engine *conventions*, not just outputs (Doc 23 Tier 3):** the pipeline generates the LOD chain + collider; the engine just loads them — agree **separate-GLB vs. glTF `extras`** and tell `bpy` which.
- **Watch:** this is the backbone stage. Edge loops must land at deformation joints (elbows, knees, shoulders) or stage 9 skinning deforms badly.

## 5. Standardized head pass  `[added / primary]`
- **Goal:** conform the head to a fixed, known topology so the face rig (stage 10) and ARKit blendshapes actually work.
- **Tool — DECIDED (11c §0.5):** deformation/retopo onto the **Blender Studio Human Base Meshes head — CC0**, via headless `bpy`. CC0 is the strongest position (users ship commercial games); Blender-native = zero-friction for headless `bpy`. The MetaHuman-derived head is **rejected** (Unreal-licensed, "study purposes only").
- **Why it's here:** ARKit blendshape transfer is most reliable on consistent head topology. Decide this once, globally.
- **Caveat:** the CC0 head was built for general sculpting — mouth/eye edge flow may need strengthening for blendshape deformation.
- **⚠️ May become UNNECESSARY (build-time survey item):** deformation transfer handles *modest* topology change on its own (stage 10), and emerging **topology-independent semantic transfer** (OmniFaceRig, 2026) could retire this conform step entirely. Re-check at build time — classical conform-then-transfer stays the default until that's proven.
- **Watch:** skip this (without the topology-independent path) and stage 10 risks per-character cleanup instead of an automated transfer.

## 6. Garments, armor, weapons  `[primary]` ⚠️
- **Goal:** generate the wearables and props as **separate** meshes, each tagged with its physical regime.
- **Tools by regime:**
  - Garments (cloth) → sewing-pattern gen / **Dress-1-to-3** approach → tag `cloth`
  - Soft armor (leather) → sewing-pattern or hard-surface, stiff → tag `cloth (stiff)`
  - Rigid armor (plate) → hard-surface part gen (TRELLIS/PartCrafter) → tag `rigid`
  - Weapon → hard-surface gen → tag `static` + author **attach sockets** (grip, muzzle)
  - Laces / straps / cords → tag `rod`
- **Runs on:** ComfyUI families (each part is its own generation), each then getting its own mini stage-3/4 (refine + retopo + material).
- **You:** generate each part from a clean image of *just that item* — that's what keeps it separable rather than fused to a body.
- **Watch:** garment sewing-pattern gen is the research-grade, headline-risk stage. Weapons are the easy one.

## 7. Fit / compose onto the body  `[primary]` ⚠️
- **Goal:** the "on, not glued" step — each part sits correctly on the body.
- **Tools by regime (routed by tag):**
  - `cloth` → **ContourCraft + HOOD** drape (resolves interpenetration)
  - `rigid` → placement + collision settle (bone-anchored in stage 9)
  - `rod` → **PyElastica** Cosserat sim
  - `static` weapon → parked at its socket (bound in stage 9)
- **Runs on:** **Chain Studio** orchestration with regime routing + headless `bpy`.
- **Watch:** rigid-armor *placement* is authored logic (landmark + settle), not a one-click model. Cloth drape is the mature part.

## 8. Hair groom + gravity settle  `[primary]` ⚠️
- **Goal:** hair that looks real and hangs under gravity.
- **Tools:** groom geometry from **DiffLocks** (single-image → strands; human scalp) → **settle under gravity** as a rest pose (PyElastica Cosserat sim, or Blender 5.2's native node-based hair physics) → output guide strands or hair cards + PBR hair shading.
- **Runs on:** ComfyUI (groom) + `bpy`/PyElastica (settle).
- **Watch:** "gravity" here = a static settle for the rest pose; live per-pose dynamics is the engine's groom system at runtime (or a baked step). Full Cosserat per-strand isn't run live.

## 9. Body rig + skin  `[primary]`
- **Goal:** one skeleton driving the whole assembled character.
- **Tool:** **UniRig** (or **Rigify** quadruped/human metarig) via headless `bpy`.
- **Skeleton contract — DECIDED (11c §0.5):** conform to the **canonical Mixamo-compatible hierarchy** (Rigify-produced, glTF-exported): Y-up, right-handed, **max 4 influences per vertex**, pivot at feet, real-world metres; a **separate quadruped hierarchy** for animals. *The hierarchy is the contract, not the bone names* — matching Mixamo's parent/child makes any retarget a rename map. UniRig **conforms** to this; it doesn't define it.
- **What "skin" covers here:** rig the body skeleton → **transfer skin weights** to the already-fitted garments/armor so they deform with the body → **rigidly bind** the weapon to the hand bone/socket → **bind** hair to the head bone.
- **In → Out:** dressed static character → rigged, skinned, animation-ready character on one shared skeleton.
- **⚠️ Engine blocker (Track B — [Doc 23](23_engine_import_contract.md) Tier 1):** the engine ignores `JOINTS_0`/`WEIGHTS_0` and has *no* skeleton import today, so the skinned mesh this stage produces **cannot be loaded** until that engine work lands. This is why the character spine waits on Track B while static props (Track A) ship now.
- **Watch:** weight transfer to loose garments needs the clean edge loops from stage 4; sloppy retopo shows up as clipping here.

## 10. Face rig + ARKit blendshapes  `[added / primary]`
- **Goal:** a face that *can* move — the prerequisite for voice-driven mouth motion.
- **MAJOR CORRECTION — this is a SCRIPT, not an art task.** The earlier draft implied the face rig carries manual-authoring cost. That's **wrong**, and it's the most important correction in this runbook. **Deformation transfer** (Sumner & Popović 2004) is the kernel of every production system in this space — a *geometric algorithm*, not a model to train, and it handles modest topology change.
- **Tool / sources:** open ARKit source sets — **ICT-FaceKit**, the **Kite & Lightning** ARKit set — driven through deformation transfer; reference implementation **`vasiliskatr/deformation_transfer_ARkit_blendshapes`** generates all 52 for any face. Corroborating systems: **SAiD** (deformation-transfers from an ARKit source), **NVIDIA Audio2Face-3D** (transfers generic ARKit poses onto subject meshes), **OmniFaceRig (2026)** (calls deformation transfer *"the kernel our blendshape transfer stage builds upon"*). Runs on `bpy` against the stage-5 head.
- **So stage 10 is:** source blendshapes → deformation transfer → the character's head → 52 ARKit shapes. **No Blender skill, no artist, no purchase.**
- **In → Out:** rigged character → same character with 52 ARKit blendshapes on the face.
- **Emerging (promising, NOT proven):** topology-independent semantic transfer (OmniFaceRig) may eventually make stage 5 (head conform) unnecessary — a build-time survey item; classical conform-then-transfer stays the default.
- **Action:** verify **ICT-FaceKit's license** at build time (users ship commercial games).
- **Watch:** the engine must support **morph targets** to load these ([Doc 23](23_engine_import_contract.md) Tier 2). What makes it tractable is the *fixed head topology* (stage 5), **not** manual work.

## 11. Voice identity  `[primary]`
- **Goal:** a unique, novel voice bound to the character.
- **Tool:** **voice design** — Qwen3-TTS (free-form design) or license-clean Kokoro (Apache) / Chatterbox (MIT). Store a voice profile (seed/description), not a fixed clip.
- **Runs on:** the audio pipeline (doc 12).
- **Watch:** synthetic/novel voices only — not clones of real people. Pick a commercially-clean model since users may ship.

## 12. Animation  `[deferred]`
- **Goal:** make it move. *Not in the primary goal — the rig (stage 9) is the handoff point.*
- **Tools:** **Mesh2Motion** (CC0, bakes animations into GLB) for shipped clips; **MotionBricks** (NVIDIA, engine-side runtime) for smart motion in-engine.
- **Watch:** deferred by decision. The character is *animation-ready* after stage 9 regardless.

## 13. Lip-sync preview  `[deferred / early-win]`
- **Goal:** drive the face blendshapes from the voice.
- **Tool:** **Audio2Face-3D** (ARKit blendshape output) — reads stage 11's voice, drives stage 10's face.
- **Note:** baked lip-sync export is deferred, but running it as an **in-app preview** (hear the voice, watch the mouth) is a cheap, high-impact early feature.

## 14. Validate  `[added / primary]`
- **Goal:** a decisive game-ready gate before export.
- **Checks (artifact-based):** quad-dominant topology; edge loops at joints; non-overlapping UVs; PBR channels present and in-range (metals ~0.95–1.0, dielectrics 0); consistent normals; pivot at feet; real-world scale; LOD chain + collider present; rig binds clean; blendshapes present.
- **Runs on:** `bpy` script — pass/fail, not eyeballing.

## 15. Export + license metadata  `[primary]`
- **Goal:** the character leaves the studio, engine-ready and license-clear. **"Engine-ready" = the custom engine's as-built import contract ([Doc 23](23_engine_import_contract.md) §1), NOT generic glTF** — real-world scale (no `normalize_height` surprise), explicit **MikkTSpace tangents**, `alphaMode` for hair/foliage, and (for characters) `JOINTS_0`/`WEIGHTS_0` + morph targets the engine can actually read.
- **Tool:** GLB / FBX / USD export via `bpy`.
- **Art-style consistency closes here too (§0 / 11c §5):** a **consistent material/shader treatment** across every asset is half of what makes twenty assets look like *one game* (the other half is the stage-0 concept style). Export with one house PBR convention.
- **Added — the duty-of-care step:** write a **per-asset license sidecar** recording which model produced each component and what its license permits downstream (since your app is free but users may sell their game). Surface it; don't rule on it.
- **In → Out:** validated character → engine files + license sidecar.

---

## VRAM staging (the cross-cutting practical note)

A full character is many sequential model loads (multi-view → TRELLIS → UltraShape → garment gen → drape → rig → face → …). On the 5090's 32GB, **stage the loads** — load/unload each model between stages rather than holding all resident. Chain Studio should treat each node as load → run → free. This is the difference between the pipeline running and OOM-ing mid-character.

## What was on your list, mapped

Idea→image ✔ (0) · 16 views ✔ (1) · 3D model ✔ (2) · refine+retopo ✔ (3–4) · clothes+weapons ✔ (6) · put them on ✔ (7) · hair look+gravity ✔ (8) · rig+skin ✔ (9) · animation ✔ (12, deferred) · voice ✔ (11) · export ✔ (15). **"Everything else I forgot"** = the [added] stages: the full game-ready pass (UV/bake/LOD/collision) inside "retopo" (4), the standardized head (5), the face rig + ARKit blendshapes (10), the validate gate (14), and the license sidecar (15).

## One-line summary

**Locked concept → 16 views → TRELLIS 2 → UltraShape → game-ready retopo/bake → standardized head → separable garments/armor/weapons → drape/attach/settle → rig + skin → ARKit face → voice → validate → export.** Animation and lip-sync sit just past the finish line, animation-ready by construction.
