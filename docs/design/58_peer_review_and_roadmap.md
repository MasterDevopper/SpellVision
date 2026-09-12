# Doc 58 — Peer review, UI direction, and post-1.0 roadmap

**Status:** owner-facing review, not a ship certificate.  
**Source:** `SpellVision_Peer_Review_and_Roadmap_v1.docx` (v1.1, 11 Sep 2026), based on `docs/design/57_current_state_report.html`.  
**T7 / Grade S:** OPEN. Do not merge this onto `night/s-t7-bug-hunt` as product scope. Grade S dests first.

This is not a changelog. Competitive notes cite SwarmUI, InvokeAI, ComfyUI-Frontend, Krea.app, and the 2026 Krea 2 Control / Identity / Style-Reference ecosystem.

---

## 1. Verdict

SpellVision is the right kind of product: a Qt instrument that owns the graph while Comfy only executes. That is closer to a studio than Swarm’s Generate tab over nodes or raw Comfy spaghetti. It is not yet a next-gen showcase. Several surfaces still lie about intent, and the holes that burned the locked orc plate are the holes a stranger will hit on day one.

The gap is **intent language**, a short list of missing **verbs**, and a cockpit that still reads as a powerful settings panel instead of a look-dev bench. Themes and Lavish motion will not fix that. Named verbs, an honest still chip, a compare strip, and project folders will.

## 2. What is already strong — keep

- One cockpit for T2I / I2I / T2V / I2V. Simple reveals knobs in place and does not relocate them.
- Family operating points as an idea (Krea2 Raw 52/3.5 is not Lox 8–12/CFG 1). That is the correct abstraction.
- Asset Intelligence plus an allow-listed `WorkerRequestBuilder`. This is how the app stays a product instead of a node dump.
- Character rail already matches the WROUGHT separated-plate method: Concept → plates → clothes → fit.
- Ember + Matte Instrument is a real identity. Do not flatten it into Swarm violet or Invoke beige.
- The state report kept the I2V MAE 9.25 clip as a counterexample. That honesty is rare. Keep it.
- Command palette, custom title bar, and a flat left rail without fake CREATE/MANAGE headers.

## 3. Critical evaluation

### 3.1 T2I-with-still is a UX lie

The 84px chip looks like a reference encoder. The worker remaps the job to I2I. That is why the locked orc never turned: pixels of the frontal plate already decided the pose. Krea.app and Swarm treat style-ref, moodboard, and edit as different verbs. SpellVision has one dropzone and a silent remap.

**Binding for 1.0:** the remap stays (otherwise the worker never gets `input_image`). The chip and preflight must **name** Edit/I2I before Generate. Silent remap without a banner is the lie.

### 3.2 Denoise is an engineer knob pretending to be a creative verb

I2I at 0.30 locked identity. 0.60 still would not rotate her and started a cousin. Users need named bands — Lock / Drift / Recompose — mapped to family-safe ranges. A raw 0–1 slider implies “more denoise equals more pose.” That is false on Krea 2 / Lox.

### 3.3 History is a job log, not a studio

KEEP/NO exists, but type-ahead eats K/N. Dests dump into OneDrive Pictures. There is no A/B strip, no look folder (`orc_f_v1` / `tudor_wall` / `village_empty`), and no “this seed + this stack” as a first-class object.

### 3.4 LoRA stack is a list, not a manager

No trigger auto-inject. No family compatibility badge. No recipe (“WROUGHT house 0.75 + Character design 0.7 for sheets only”). Detailer / Eyes / Curvier sitting disabled is correct for look-dev and dangerous as anyone else’s default. Stage-2 LoRA Manager is the real 1.1 product.

### 3.5 Train is a door to someone else’s app

Sohya_kk as a launcher is acceptable for 1.0. It is not a studio. Official Krea path is train on RAW and validate on Turbo or Lox.

### 3.6 Character / Concept / Comic overlap

Three rails can produce a person. Concept “Send → Character” is the right arrow. Collapse in the user’s head even if the code stays split: one Character contract, views as jobs.

### 3.7 Video is the Grade S landmine

I2V that ignores the keyframe is not S. LTX frame 0 missing the prompt is not S. Shipping T2I-pretty while I2V lies will define the app as the image box that also has a broken video tab.

### 3.8 No canvas

Invoke still wins artists on inpaint, outpaint, and regional edit in one surface. 1.1 does not need their whole canvas. It needs one edit verb that is not full-frame I2I. Kit-on-body and village composites need it by 1.2.

### 3.9 Simple is not yet proven optimal

Doc 57 says the family × page operating-point matrix is unproven. If Simple on Lox does not land Er SDE / Simple / 8–12 / CFG 1, Simple is a trap.

## 4. Generation verbs that must exist

Product verbs, not changelog rows. Build the UI around them.

| Verb | User intent | Implementation |
|------|-------------|----------------|
| **Lock** | Keep her face | I2I denoise ~0.25–0.35 on Lox. Plate is init. Chip says Lock. |
| **Restyle** | Same woman, new kit | Identity Edit / ref-latent path. Not silent I2I. |
| **Turn** | Three-quarter / profile / back | OpenPose or DWPose control LoRA. Never raise denoise to rotate. |
| **Mood** | This world, not that one | Style Reference LoRA + multi-ref. Chip says Moodboard. |
| **Sheet** | Dataset for a LoRA | Character Design trigger on, then off. Character-rail job. |
| **Compare** | Which sister is closer | Side-by-side + KEEP with project tags. |

## 5. UI improvements (summary)

Ember stays. The work is hierarchy, labeling, and empty states — not a sixth palette.

Highest-priority UI fix: **replace the anonymous 84px dropzone with a labeled intent chip** (None / Lock / Restyle / Turn / Mood / Keyframe). Dropping a still onto T2I must change the mode label **before** Generate. Never silently remap without that label.

Denoise as language: Lock / Drift / Recompose three-segment control; Advanced still reveals the raw float. Lox defaults: Lock 0.30, Drift 0.45, Recompose 0.65 — Recompose must warn “identity will drift; pose may still not rotate.”

Other 1.0.1 chrome (no new graphs): context label includes intent; Customize Layout moved to Settings; VRAM chip “held” vs “used”; empty-state copy that names the verbs; I2V without keyframe disables Generate; Train tooltip “Opens Sohya_kk.”

Full visual/shell/inspector/Home/Character/motion notes live in the source docx §§5.1–5.17. Do not invent a sixth theme before Ivory is actually light and Ember is the demo look.

## 6. Version slots

Do not bump CMake off 1.0.0 until 1.0 ships.

| Version | Role |
|---------|------|
| **1.0 (this branch)** | Grade S dests. I2V follows keyframe or Generate disabled. LTX frame 0 or mark Partial. Simple OP actually fires. Dest unlink. T2 drop pictured once. Honesty banner if still remaps. No GL overlay. |
| **1.0.1** | Chrome polish, no new graphs. Intent in context label. Empty-state honesty. Layout in Settings. VRAM “held”. EffectDirector park protocol **before** motes. Dest settle, KEEP ring, honesty flash (CPU). |
| **1.1.0 Intent layer** | Named still verbs + denoise bands. Turn house (OpenPose). Restyle house (Identity Edit 2761113). Moodboard (ostris 2764349). Depth sibling. Sheet house (2815175 + Forge 2877997). Prompt blocks. LoRA Manager v1. History as look library. Extract Identity Edit from Pro Grade 2726952 — do not ship V17 whole. |
| **1.2.0 Studio** | Unified edit canvas (mask → local I2I). In-app trainer v1 (train RAW, validate Turbo/Lox). Character contract collapse. SeedVR2 / Ultimate SD Upscale as Simple. Qwen-Image / Z-Image Turbo chips. CivitAI/HF browser in Models. |
| **1.3.0+** | TRELLIS.2 for kit pieces only. Chain unhide when I2V is Grade S. Control Space / 3D pose. Storyflow card only if daily. Dual-PC after Enable is real. Installer + tutorial after 1.0. LLM cleaner / comic→I2V unscheduled until image verbs are honest. |

## 7. Do not add

- FaceDetailer / DetailedEyes / Curvier as WROUGHT defaults.
- Stock Turbo INT8 as the house checkpoint.
- Skin-beauty / Pro Realism graphs as the look-dev path.
- Dumping Lonecat V17 whole.
- Replacing Comfy with pure Diffusers.
- Claiming NVPAIR or 32+24 GB as one VRAM pool.
- A sixth theme before Ivory is actually light and Ember is the demo look.

## 8. Build order after Grade S

1. Still-chip verbs + no silent remap (stops the orc-pose class for every user)
2. Preflight sentence above Generate
3. Look folders + compare strip + KEEP fix
4. Turn house (OpenPose / DWPose)
5. Restyle house (Identity Edit)
6. LoRA Manager v1 + recipes
7. Moodboard / style-ref
8. Canvas + trainer (1.2, after verbs exist)

## 9. Ember Field (motion that yields VRAM)

Idle beauty is allowed. Fighting Comfy for the same 32 GB is not. One scene graph (`EmberFieldView`), not per-widget timers.

**Yield contract:** Park and destroy GPU objects **before** Comfy’s first alloc (typical prepare 0.4–2.5 s). Hook `WorkerRequestBuilder` about-to-enqueue — worker ACK is too late. Resume 400 ms after dest, only when Ready AND queue == 0.

| Tier | Particles | VRAM | When |
|------|-----------|------|------|
| Minimal | 0 | 0 | No timers |
| Standard | 0 idle | 0 | Dest settle + KEEP ring |
| Rich | 40–80 | 8–20 MB | Idle field |
| Lavish | 120–220 | 25–60 MB | Full field; 60 Hz idle / 0 parked |
| Parked | 0 GPU | ~0 | Arming → Ready+idle |

Hard rules: never sample the dest into the field. Half-res only. Auto-demote above 85% used VRAM. `SPELLVISION_FIELD=0` nuke. Reduced-motion → Minimal. Prefer QPainter motes on Standard/Rich; one QOpenGLWidget for Lavish.

**This branch (1.0):** nothing that adds a GL overlay. Honesty flash may land as `QPropertyAnimation` on the chip (CPU).

Full park/resume timings, effect catalog, and Qt implementation: original docx §11.

## 10. Sources

- `docs/design/57_current_state_report.html` — live Ember session, 2026-09-11
- Krea 2 OpenPose ControlNet LoRA (thedeoxen); facok / ostris-edit; HF Patil/Krea-2-depth-controlnet
- CivitAI 2761113 Identity Edit; 2764349 Style Reference; 2815175 Character Design; 2877997 Character Forge; 2726952 Pro Grade; 2752799 Depth; 2906958 Storyflow
- SwarmUI / InvokeAI / ComfyUI / Krea.app 2026
- Official Krea 2: train LoRA on RAW, infer on Turbo

## 11. Revision

| Date | Change |
|------|--------|
| 11 Sep 2026 | v1.0 peer review from doc 57 plus look-dev lessons (Lox plate, I2I 0.30, silent remap) |
| 11 Sep 2026 | v1.1 §11 Ember Field park/resume VRAM-yield protocol |
| 11 Sep 2026 | Landed in-repo as Doc 58 from the attached docx |
