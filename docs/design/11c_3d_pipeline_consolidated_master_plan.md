# Doc 11c — 3D Game-Asset Pipeline: Consolidated Master Plan & v1 Ranking

> **Supersedes** the first 11b draft at the *planning* level. The L1 native-family
> code scaffolding (contracts, readiness, adapter, worker round-trip) in **11b §4
> still stands** — this document is the strategy, taxonomy, tool inventory, and
> build ranking that sits above it.
>
> **Confidence tiers** (carried from 11b): **STABLE** = mirrors proven patterns,
> safe to build against. **⚠️SURVEY** = model/node choice must be re-grounded from a
> live `/object_info` dump + real workflow at build-time. Any 3D model named here is
> a *swappable template component*, never load-bearing.

---

## 0. The two recorded decisions that shape everything

1. **Scope boundary.** The primary goal is *everything up to a rigged, game-ready,
   voice-bearing asset*. Baked **body-animation export is deferred**. The rig is the
   handoff point.
2. **"No Blender" means no *manual* Blender.** Headless `bpy` running invisibly on
   the backend as a compute library is **allowed and expected** — the user never
   opens or learns Blender. This is load-bearing: it's what makes rigging, draping,
   fur, retopology, baking, and export feasible in-house.

---

## 0.5 Two frozen technical decisions (the contracts)

**Decided, not open.** They exist because the two hardest integration points (rig import,
face blendshapes) only work against a *fixed* target — pick it once, globally.

1. **Canonical skeleton — Mixamo-compatible hierarchy, produced via Rigify, exported to
   glTF.** Y-up, right-handed, **max 4 influences per vertex**, pivot at feet, real-world
   scale (metres). A **separate quadruped hierarchy** (Rigify quadruped metarig) for
   animals. *The hierarchy is the contract, not the bone names* — matching Mixamo's
   parent/child structure makes any retarget a **rename map, not a rebuild**. UniRig
   (stage 5) *conforms* to this standard; it does not define it. This is exactly what the
   engine's skeleton importer targets ([Doc 23](23_engine_import_contract.md) Tier 1).

2. **Canonical head topology — Blender Studio Human Base Meshes head (CC0).** Clean quad
   topology, closed volume, UV-mapped, real-world scale, Blender-native (zero-friction for
   headless `bpy`). **CC0 is the strongest position** — users ship commercial games.
   **Explicitly rejected:** the MetaHuman-derived head ("study purposes only",
   Unreal-licensed — unusable). *Caveat:* built for general sculpting, so mouth/eye edge
   flow may need strengthening for blendshape deformation. (This is stage 5's conform
   target — but see §5, deformation transfer handles modest topology change, and emerging
   topology-independent transfer may retire the conform step entirely.)

---

## 1. Asset taxonomy & regime map

The central insight: **only animals ride the character spine.** Weapons are a lighter
hard-surface branch; buildings are a separate procedural subsystem.

| Asset type | Regime | Generation path | Fit / motion handling | Maturity |
|---|---|---|---|---|
| Humanoid character | Organic | Image→3D (quad topology) | Body rig + face rig | Strong |
| Garment (cloth) | **cloth** | Sewing-pattern gen | Cloth drape | Strong |
| Soft armor (leather) | **cloth** (stiff) | Sewing-pattern / hard-surface | Drape, high bending stiffness | Moderate |
| Rigid armor (plate) | **rigid** | Hard-surface part gen | Rigid bone-attach + joint collision | Moderate |
| Weapon | hard-surface (static) | Hard-surface part gen | Static + authored attach sockets | Strong |
| Laces/straps/cords/tassels/chains | **rod** | Procedural / curve | Cosserat-rod sim | Moderate |
| Building / environment | procedural / modular | Modular kit / procedural | N/A (assembled) | Separate subsystem |
| Animal / creature | Organic | Image→3D | Quadruped rig; fur + motion are gaps | Mixed |

**Three physical regimes drive the composition layer** — every generated part carries
a tag that routes it:
- `cloth` → drape (ContourCraft / HOOD)
- `rigid` → bone-attach + collision
- `rod` → Cosserat sim (PyElastica)

Plus `static` (weapons/props) and the separate `procedural` track (environments).
**Material (PBR) is orthogonal** — metal vs. leather vs. fabric is a texture-stage
concern (metalness/roughness/normal), not geometry, and applies across all regimes.

---

## 2. The pipeline spine (ordered stages)

Each character-class asset flows through these. Per stage: keystone tool · in-house
mechanism · maturity.

| # | Stage | Keystone tool(s) | In-house mechanism | Maturity |
|---|---|---|---|---|
| 1 | **Concept image** | SpellVision T2I (existing) | Already built — closes the "can't draw" loop | ✅ |
| 2 | **Base mesh gen** | Hunyuan3D / PolyGen (quad-dominant), TRELLIS | `native_comfy_template` family | ✅ |
| 3 | **Part decomposition** | PartCrafter, HoloPart; sewing-patterns for garments | ComfyUI node / family | ⚠️ research-grade |
| 4 | **Material / PBR** | Hunyuan3D PBR, Meta AssetGen-style, texture diffusion | Texture stage in graph | ✅ |
| 5 | **Body rig** | UniRig (humans/animals/objects); Rigify (quadruped) | Headless `bpy` service | ✅ (humanoid), ✅ (quadruped via Rigify) |
| 6 | **Face rig + ARKit blendshapes** | Deformation transfer (Sumner & Popović 2004) from an **open** ARKit source set | `bpy` **script** on the canonical head (§0.5) — no artist, no purchase | ✅ **a script, not an art task** (see §5) |
| 7 | **Fit / compose** | ContourCraft+HOOD (cloth), rigid attach+collision, PyElastica (rod) | Chain Studio regime routing | cloth ✅, rigid ⚠️ (placement glue), rod ✅ |
| 8 | **Hair / fur groom** | DiffLocks / TANGLED / Perm (human scalp) | Strand groom; **animal fur = procedural/hair-cards** | human ⚠️, **animal ❌-gap** |
| 9 | **Voice identity** | Qwen3-TTS (voice design); license-safe TTS | Audio pipeline (doc 12) | ✅ |
| 10 | **Game-ready optimization** | Instant Meshes / QuadRemesher | retopo→UV→bake→LOD→collision via `bpy` | ✅ **(the backbone)** |
| 11 | **Export + license metadata** | GLB / FBX / USD | `bpy` export; per-asset license record | ✅ |

**Geometry refinement (UltraShape) — an optional stage between 2 and 10, KEPT in v1.**
Retopo+bake (stage 10) can only bake detail that *already exists* in the source mesh — it
faithfully preserves TRELLIS's over-smoothed mush. **UltraShape adds real geometric detail
*before* the bake** (it is **not** redundant with retopo — "adds detail, not just
smoothing"), and its sharpen-salient-features behaviour aims directly at the
stylized-realistic weakness (§5). Apache-2.0 (clean), two ComfyUI wrappers, production
affordances (low-VRAM, chunked, octree resolution, fp16/bf16). A **topology-preserving
mode** exists (consistent vertex indexing) — directly relevant to stages 5/10. Keep it
**optional/toggleable per-asset**; validate it *sharpens* rather than *drifts* from the
concept. Full treatment: 11d §3.

**Deferred animation layer** (sits on top of the rig handoff, stage 5/6):
- Body motion: **MotionBricks** (engine-side, runtime), **Mesh2Motion** (CC0, baked GLB), text-to-motion (MDM/MoMask)
- Lip-sync motion: **Audio2Face-3D** (ARKit blendshape output) — *preview can come early, baked export deferred*

---

## 3. How it lands in SpellVision's architecture

- **Generation stages (2–4)** → `native_comfy_template` families through ComfyUI,
  per the Wan/LTX reference and the 11b §4 scaffolding. Hunyuan3D is the first new
  family; weapons/animals reuse the same family machinery (different prompts/markers).
- **`bpy` stages (5, 6, 7-bake, 8-fur, 10, 11)** → a new **headless Blender compute
  service**, structured like the existing managed-ComfyUI runtime manager but for
  `bpy` (start/health/dispatch). This is the single biggest *new* infrastructure
  piece the "no manual Blender" decision requires. UniRig's existing ComfyUI wrapper
  (which itself bundles headless Blender) is the proof-of-pattern.
- **Composition (7)** → **Chain Studio** orchestration. Each part is a standalone
  generation carrying a **`physical_regime` tag** (`cloth`/`rigid`/`rod`/`static`);
  the chain routes each down its fit branch and assembles onto one shared rig. This
  is what turns "separable garments + armor" from manual work into an automatable
  graph — and it's why composition is Chain mechanics, not a single model call.
- **Voice (9)** → extends the **audio pipeline (doc 12)** with a voice-design stage;
  each character stores a voice profile (design seed/description).
- **Environments** → a *separate* procedural subsystem (Infinigen-style /
  WorldGen-style), not the `native_comfy_template` path. Treat as its own track.
- **New cross-cutting primitives:** the `physical_regime` tag; a **standardized head
  topology** (so ARKit blendshape transfer is reliable); **per-asset license
  metadata**; and `media_type="mesh"` plumbed through asset extraction + preview
  (the 11b §2.6 ripple).

---

## 4. v1 vs. Deferred — the ranking

**Ranking principle:** dependency order × maturity × value to a non-technical user,
gated by *"what produces one usable, game-ready, riggable asset first."* The minimal
viable spine is **generate → optimize → material → rig → export** — a textured,
rigged, engine-importable asset. Everything else layers onto that.

**Two tracks, meeting at the rig (corrected — see 11b §3 and
[Doc 23](23_engine_import_contract.md)).** The engine-import contract splits v1 in two:

- **Track A — static props.** concept → TRELLIS 2 → (optional UltraShape) → retopo/UV/bake
  → export → **loads in the custom engine and looks right.** A textured, game-ready prop —
  no rig, no face, no garments. Runs against the engine's *as-built* contract **today**, so
  it **proceeds now**. This is the real D1 gate; **"first `.glb` round-trips" is not a
  milestone** — a `.glb` the engine chokes on is a demo.
- **Track B — the character spine.** Everything skinned. **Blocked on engine work:**
  `JOINTS_0`/`WEIGHTS_0` + skeleton import + tangents + alphaMode (Doc 23 Tiers 0–1). The
  body rig (item 7 below), face rig, and garments can only *land in-engine* after Track B
  does. **Do A first.**

### v1 — the spine (build first, in roughly this order)

| Priority | Item | Why v1 |
|---|---|---|
| 1 | **Headless `bpy` compute service** | Enables stages 5/10/11; nothing ships without it |
| 2 | **Single-asset Image→3D family** (TRELLIS 2, 11b L1) | The generator; the milestone is **loads in the custom engine and looks right** (Track A gate), *not* "a `.glb` exists" |
| 3 | **Game-ready optimization layer** (retopo/UV/bake/LOD/collision) | The backbone — gates whether *any* asset is usable in-engine |
| 4 | **PBR material** (metal/leather/fabric) | Cheap, mature, needed by every asset |
| 5 | **Mesh output surface** (viewer, thumbnail, `media_type="mesh"`, routing) | The 11b D2 work; the user must *see* the result |
| 6 | **Export + license metadata** (GLB/FBX/USD) | The asset has to leave the studio |
| 7 | **Body rig** (UniRig; Rigify for quadrupeds) | Mature; the deferred-animation handoff point. **Engine-gated (Track B):** the skinned mesh cannot load until the engine reads `JOINTS_0`/`WEIGHTS_0` + imports a skeleton (Doc 23 Tier 1). Conform to the canonical skeleton (§0.5) |
| 8 | **Hard-surface weapons** | Rides items 2–6 + authored attach sockets; near-free given the spine |

> **HISTORY INTEGRATION (item 5 — Mesh output surface):** 3D plugs its detail schema + renderer
> into the **mode-aware history spine** (see the polish backlog's *MODE-AWARE HISTORY MANAGER*, Phase 1).
> The 3D detail payload = `{poly count, texture res, format, rig status, UV/bake state}` with a
> 3D-specific renderer (list columns + detail pane). **Do NOT add a mode-specific history hack** — add a
> detail payload + renderer to the established framework. **If the spine isn't built yet when 3D ships,
> building it is a prerequisite** — otherwise 3D history becomes another widen-hack (today's image/video
> history widens the *video* schema, which has no field to borrow for "poly count").

v1 delivers: **textured, rigged, game-ready characters / animals / weapons**, exported
with license metadata. A non-artist can make and ship these.

### v1.x — second wave (high value, moderate complexity, depends on the spine)

| Item | Why second, not first |
|---|---|
| **Separable garments** (sewing-pattern gen + cloth drape: Dress-1-to-3 / ContourCraft) | The headline "clothes not glued"; depends on rig (7) + composition |
| **Composition layer** (Chain Studio regime routing) — incl. **rigid armor attach** | Depends on rig + regime tags; the assembly engine for multi-part assets |
| **Face rig + ARKit blendshapes** | A **script** (deformation transfer, §5), *not* an art task — cheap once the canonical head (§0.5) exists. Second only because it needs engine morph-target support (Doc 23 Tier 2) + the head topology |
| **Voice identity** (voice design) | Independent and mature, but not on the critical "make a mesh" path |
| **Cosserat rod sim** (PyElastica) — laces/straps/cords + hair dynamics | Depends on composition; PyElastica is in-house-ready |

### Deferred — later additions / weaker maturity / engine-side

| Item | Reason deferred |
|---|---|
| **Baked body-animation export** (MotionBricks / Mesh2Motion / text-to-motion) | Explicit scope decision; engine-side or post-rig |
| **Lip-sync export** (Audio2Face-3D) | Animation layer — *but an in-app preview is a cheap early win* |
| **Buildings / environments** (Infinigen / WorldGen) | Large *separate* procedural subsystem; different regime |
| **Animal fur groom** | Genuine gap — no generative model; procedural/hair-card stopgap only |
| **Quadruped animation** | No MotionBricks equivalent; preset-clip retarget only |
| **Talking animals** | Off the human ARKit path; needs custom muzzle rig |
| **Tileable materials / trim sheets, terrain + foliage, SFX/music/ambience, asset variation & sets** | Real value, but additive once the spine + environments exist |

---

## 5. Honest gaps & risks (carry through every phase)

- **AI geometry is visual, not physical.** Collision meshes, nav meshes, spawn/trigger
  points, and LODs are *not* generated — they're authored or post-processed. Biggest
  risk for the environments track; handled for assets by the optimization layer (v1 #3).
- **The animal soft spots** are real and recurring: **fur** (no generative groom),
  **quadruped motion** (no generative model), **talking animals** (no ARKit path). Set
  expectations accordingly — animals are mesh+rig ✅, the rest is stopgap.
- **ARKit-blendshapes-on-a-generated-head is a SCRIPT, not an art task** (major correction
  — it was previously mis-read as manual authoring cost, the single most important fix
  here). **Deformation transfer** (Sumner & Popović 2004) is the kernel of every production
  system in this space — a *geometric algorithm*, not a model to train, and it handles
  modest topology change. Open ARKit source sets exist (**ICT-FaceKit**; the **Kite &
  Lightning** ARKit set); reference implementation
  **`vasiliskatr/deformation_transfer_ARkit_blendshapes`** generates all 52 for any face.
  Corroborated by **SAiD**, **NVIDIA Audio2Face-3D**, and **OmniFaceRig (2026)** (which
  calls deformation transfer *"the kernel our blendshape transfer stage builds upon"*). So
  stage 6/10 = source blendshapes → deformation transfer → the character's head → 52
  shapes: **no Blender skill, no artist, no purchase.** The only remaining cost is the
  *fixed head topology* (§0.5) that keeps the transfer reliable — **not** authoring.
  **Emerging (promising, NOT proven):** topology-independent *semantic* transfer
  (OmniFaceRig) may eventually retire the head-conform stage (5) entirely — a build-time
  survey item; classical conform-then-transfer stays the default. **Action:** verify
  ICT-FaceKit's license at build time (users ship commercial games).
- **Art-style consistency is a first-class UNSOLVED problem.** Nothing in the plan makes
  twenty generated assets look like they belong in the *same game*. The target is
  **stylized-realistic** — the *hardest* band for generative 3D: pure stylized cleans up
  easily, pure realistic leans on scan detail, but the middle wants deliberate forms and
  readable silhouettes, which generated meshes are worst at. It lives at **stage 0** (locked
  concept *style* — house-style LoRA, fixed prompt scaffold, reference discipline) and
  **stages 4 / 11** (consistent material/shader treatment). This is what separates "I
  generated assets" from "I made a game that looks like something." **No solution yet —
  recorded, not handled.**
- **"Engine-ready" ≠ "valid glTF."** The target engine has its own **as-built import
  contract ([Doc 23](23_engine_import_contract.md))** — stricter than the spec, and it
  *silently* mis-handles pipeline output: an **arbitrary tangent basis renders baked normal
  maps WRONG with no error** (the top engine task is MikkTSpace-on-import), max-extent scale
  normalization breaks A/T-pose characters, and skinning / morph targets / alpha are unread.
  Measure "game-ready" against Doc 23 §1, not the glTF spec.
- **Research-grade maturity:** ComfyUI node availability varies (UniRig wrapped;
  Hunyuan3D/PartCrafter/Dress-1-to-3 need integration). A full chain is several
  sequential model loads — the 5090's 32GB helps, but plan VRAM staging.
- **Voice ethics:** synthetic/novel voices only (voice *design*), never cloning real
  identifiable people. Pick commercial-safe TTS (Kokoro/Chatterbox/Orpheus/Qwen3-TTS
  permissive; XTTS/F5/Fish non-commercial).
- **IP for users shipping games:** in the US, pure AI-generated content isn't
  copyrightable; significant human modification grants copyright. Track license per
  generated asset (item v1 #6) and surface it.
- **Live-survey discipline (hard rule):** re-ground every ComfyUI node class name and
  model choice from a live `/object_info` dump + the real workflow at build-time. The
  models named here are placeholders for "best-in-class at D-start."

---

## 6. Live-survey checklist (run at each new family's build-start)

1. Re-survey best-in-class model + node-pack versions for the stage.
2. Install; pull a live `/object_info` dump; import the official workflow JSON via
   Flows and confirm a manual round-trip (Path A before Path B).
3. Fill: adapter `required_nodes`, every `_first_available_class(...)` candidate tuple,
   graph wiring, save-node class + format enums, asset-extraction bucket keys, model
   filenames/repo IDs/sources, output folder + extension.
4. For `bpy` stages: confirm the headless Blender version + addon availability
   (Rigify, QuadRemesher/Instant Meshes, deformation-transfer).
5. Smoke-test end-to-end; flip the contract `planned → validated`; open the gate.

---

## 7. One-line summary

**v1 = a textured, rigged, game-ready, exportable asset (character / animal / weapon),
with the headless-`bpy` optimization backbone underneath.** Garments, armor, composition,
face-rig, and voice are the strong second wave. Animation, environments, and the animal
fur/motion gaps are deferred.
