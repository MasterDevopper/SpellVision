# 31 — Hybrid breast morph: SpellVision lock (Phase 0)

**Status:** Phase 0 **accepted** (2026-08-17). Phase 1+ **not** authorized.  
**Owner decisions recorded:** RBSM **A** (research-only teacher, offline only) · stylistic ceiling **2000 cc** · **ground everything before B1**.  
**Filename note:** `31_concept_reference_lab.md` is a different Doc 31 (Concept rail). This file is the hybrid lock.

Companion: [`31a_rbsm_license_ethics.md`](31a_rbsm_license_ethics.md)  
Engine tables: SpellBound `docs/character/HYBRID_BREAST_VOLUME_TABLE_2026-08-17.md`  
Promoted from: `.hermes/plans/2026-08-17_190523-hybrid-breast-morph-spellvision.md`

---

## What this document is

The legal / scientific **fail-closed lock** for any SpellVision work that mentions breast volume, RBSM / iRBSM / liRBSM, or “clinical” size. It is **not** a Character Studio feature, not plate bands, not a worker command, not a Comfy node.

SpellVision owns **plates and optional offline teacher jobs**.  
SpellBound Engine owns **frozen `female.glb` + MorphLayer**.  
Comfy is not a character body.

---

## Owner Phase 0 choice (binding)

| Item | Decision | Blank would have been |
|------|----------|------------------------|
| RBSM / iRBSM / liRBSM | **A — research-only teacher, offline only** | not A |
| Stylistic ceiling | **2000 cc**, labeled `stylistic` — never clinical | not 2000-as-medical |
| Sequence | Ground docs + engine tables **before** B1 six-view | not six-view first |
| Weights | **Do not download `.pth`** until a later explicit yes | not fetch-now |

Phase 2 worker wrap (`rbsm_teacher_*`) stays **gated**. Phase 0 A allows the *idea* of an offline teacher. It does **not** authorize weights, a Comfy node, or shipping any reconstructed mesh.

---

## Hard bans (fail closed)

These ship in **no** SpellVision preset, Dataset pack, Character Studio project, Gen3D output, or handoff into SpellBound `female.glb`:

1. **No patient mesh.** Huang patient-level data is restricted (ethics request only). We use **published summary statistics** only.
2. **No sampled iRBSM ply** as a character, preset, or second canonical body.
3. **No reconstructed video breast** (liRBSM monocular recon of a real person) as an NPC / heroine identity.
4. **No “clinically valid to 2000 cc”** (or any clinical claim above Huang max **919.2 ml**).
5. **No RBSM re-amp as size.** Teachers measure and clamp. They do not replace `female_breast_size.ron`.
6. **No live FE / Neo-Hookean Comfy node** as identity motion (`soft_breast` amp ≤ 0.15 in engine).

Artifacts, if a later Phase 2 is authorized, live only under `runtime/teachers/rbsm/` with `provenance.json` saying **not a game body**. Never into `assets/models/human/female.glb`.

---

## Huang 2017 — published summary only

Huang N-s et al., *PLoS ONE* 12(2): e0172122 (2017). DOI [10.1371/journal.pone.0172122](https://doi.org/10.1371/journal.pone.0172122).  
Cohort: **605 Chinese female patients** with **breast cancer or benign breast disease** (not a healthy game-body population). **1210 breasts**. Patient-level data **restricted**.

| Statistic | Published value | What we may do with it |
|-----------|-----------------|------------------------|
| Volume | **340.0 ± 109.1 ml** (range **91.8–919.2 ml**) | Clamp `data_adjacent` inside **~90–920 ml** |
| N–IMF (standing) | **7.5 ± 1.6 cm** | Ratio QA on authored keys, not UI copy |
| Base width | **14.3 ± 1.4 cm** (8.5–23.5 cm) | Same |
| Ptosis incidence | **22.8%** (274/1204) | Soft prior only |
| Cup-band volumes (published) | A 260.9 · B 328.0 · C 408.1 · ≥D 539.0 ml | Labels, not Beauty law |
| Volume risk ORs | height, post-menopause, BMI, breastfeeding 7–12 mo / >1 yr | Not product sliders |
| Ptosis risk ORs | post-menopause, BMI≥24.7, breastfeeding 7–12 mo / >1 yr | Soft prior; **not** monotonic sag-with-cc |

**Cannot** regress 1500 / 1800 / **2000 cc** from this paper. Above ~920 ml is **`hybrid_stylized` or `stylistic`**. 2000 cc is the owner **stylistic ceiling**, not a Huang number.

---

## Confidence bands (copy law — no UI yet)

| Band | cc | Confidence enum | UI copy if Phase 1 ever opens |
|------|----|-----------------|-------------------------------|
| Huang neighborhood | ≤ 920 | `data_adjacent` | Adjacent to published range — **not measured for this character** |
| Between papers and style | 920–1500 | `hybrid_stylized` | Stylized |
| Owner ceiling | 1500–**2000** | `stylistic` | Stylized. Never “clinical” |
| Above ceiling | > 2000 | **reject** | Fail closed |

Simple mode (if Phase 1): **small / mid / full** only — no cc math.

---

## RBSM family (see 31a)

| Asset | Code | Train data | Weights | Allowed now |
|-------|------|------------|---------|-------------|
| Classic RBSM (~110 scans, PCA) | project site, non-commercial | withheld | gated | License text + model cards only |
| iRBSM (168 subjects, implicit) | MIT `mweiherer/irbsm` | **not public** | gated, non-commercial | Code clone OK; **no `.pth`** |
| liRBSM (local implicit + video) | MIT `mweiherer/local-irbsm` | own-scan only | gated | Same; video recon ≠ NPC slider |

---

## SpellVision substrate (do not confuse with this lock)

- Character Studio is on the rail. Stage 0 Concept = Ready. Stages 1–8 stay Locked without a real mesher.
- Gen3D is **Comfy-only**. Never spawn Pixal/Trellis as a QProcess.
- Plate path if Phase 1 opens later: **Krea 2 raw default** (52 / CFG 3.5); turbo is the speed lane; LoRAs enabled, never required.
- Do **not** pause the generation engine for this morph work.

---

## Not in this phase

- Character Advanced volume band / confidence chip
- Dataset plate batches
- `rbsm_teacher.py` / worker commands
- Native I2-3D family
- Any Present slider or `breast_volume.rs`

Those stay in the plan. **Grounding first. B1 six-view is engine-side after this review.**

---

## Validation (Phase 0)

- [x] This lock exists
- [x] `31a_rbsm_license_ethics.md` exists
- [x] Owner **A** + 2000 cc stylistic ceiling recorded
- [x] No `.pth` in SpellVision git (site-packages `.pth` config files are not RBSM weights)
- [x] No “clinically valid to 2000 cc” in UI (no volume UI shipped)
