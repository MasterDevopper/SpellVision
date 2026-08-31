# 31a — RBSM / iRBSM / liRBSM license and ethics

**Status:** Binding Phase 0 record (2026-08-17).  
**Owner choice:** **A — research-only teacher, offline only.** Weights are **not** fetched.  
**Parent:** [`31_hybrid_breast_morph_spellvision.md`](31_hybrid_breast_morph_spellvision.md)

This file is the license/ethics note the Phase 0 plan required. It is **not** permission to download checkpoints.

---

## Split that must not collapse

| Layer | What it is | License posture |
|-------|------------|-----------------|
| **Inference code** | `sample.py` / `reconstruct.py` and helpers | **MIT** (Weiherer 2024) |
| **Training data** | Clinical 3D breast scans | **Not public.** iRBSM README: “we can't make our training data public.” Huang patient-level data restricted to Fudan ethics request. |
| **Gated weights** | `.pth` / official model packs on rbsm.re-mic.de | **Non-commercial research / eval / testing only.** No sublicense, no distribution, no warranty. Commercial inquiries: Christoph Palm. |

MIT on the *code* does **not** relicense the weights or the patients.

---

## Official sites (license text + model cards only)

Recorded 2026-08-17 from public pages. **No weight download.**

| Model | Pages | Stated grant (project site) |
|-------|-------|-----------------------------|
| Classic RBSM (explicit PCA) | https://rbsm.re-mic.de/ · https://rbsm.re-mic.de/explicit/ | Internal, **non-commercial** research / evaluation / testing. Manufacturing or selling products from the model **prohibited**. **No distribution** in whole or part. Provided *as is*. |
| iRBSM (implicit, 168 subjects) | https://rbsm.re-mic.de/implicit/ · https://rbsm.re-mic.de/implicit/download/ | Same non-commercial grant on the download page. |
| liRBSM (local implicit + monocular video) | https://rbsm.re-mic.de/local-implicit/ | Same family; video recon of a **specific person**, not an NPC slider. |
| Hub | https://rbsm.re-mic.de/ | “Licenses granted for the models are for **non-commercial use only**.” Commercial: **Christoph Palm**. |

Code repos (MIT, software only):

- https://github.com/mweiherer/irbsm — LICENSE Copyright (c) 2024 Maximilian Weiherer
- https://github.com/mweiherer/local-irbsm — same

---

## What each model is (so we do not ship the wrong thing)

| Model | Scientific object | Allowed use under A | Forbidden |
|-------|-------------------|---------------------|-----------|
| Classic RBSM | ~110 scans, explicit α, mean + U, registration-heavy | Landmark / volume-from-mesh *study* after a later weight yes | Runtime verts; second `female.glb` |
| iRBSM | Deep implicit SDF; 168 subjects; 4 landmarks (sternal notch, navel, L/R nipple) | Offline `sample.py` / `reconstruct.py` → teacher ply + JSON under `runtime/teachers/rbsm/` **after** a later weight yes | Character preset; beauty key; public Dataset pack |
| liRBSM | Localized implicit + **monocular RGB video** recon | Scan pipeline for a **specific** consented subject, offline | Identity of a real person as Wrought NPC |

---

## Owner A — operational meaning

**Now**

- Keep this note.
- Do **not** fetch `.pth`.
- Do **not** vendor weights into git, installer, or MSI payload.
- Code clone of MIT repos is allowed for reading APIs. Do not commit large checkpoints.
- Huang: published table only (see Doc 31).

**Later (needs a new explicit yes — blank ≠ yes)**

- One owner-authorized offline sample.
- Worker command dry-run tests **without** weights may be written in Phase 2; they must fail closed if the checkpoint is missing.
- Output: `.ply` + `landmarks.json` + `provenance.json` (repo SHA, checkpoint hash, “not a game body”).
- Device: CUDA optional; official `chunk_size` default 100_000.

**Never under A**

- Patient mesh, sampled ply, or video breast inside a SpellVision preset or SpellBound `female.glb`.
- Comfy custom node in v1.
- Commercial ship of RBSM weights (site grant is non-commercial; product is intended to ship openly — **do not bundle**).

---

## Ethics

- Training subjects are **patients / clinical scans**, not art-reference models.
- Huang cohort is **diseased** (cancer or benign breast disease). Medical mean **340 ml** is not the Wrought heroine.
- Reconstructing a real woman’s breast from video (liRBSM) is a **biometric of that person**. It is not a race-pack offset.
- No “clinically valid” copy in any UI, tooltip, Dataset sidecar, or proof pack.

---

## Verification

- [x] License split recorded (MIT code ≠ gated weights ≠ private data)
- [x] No RBSM `.pth` added to either repo
- [x] Owner A recorded; commercial bundle forbidden
- [ ] Weight download — **not done**, not authorized
