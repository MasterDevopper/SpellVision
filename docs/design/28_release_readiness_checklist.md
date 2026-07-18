# Doc 28 — v1.0 Release-Readiness Checklist

*STUB — skeleton to fill in. This is the checklist the roadmap's Arc-3 gate references (it was mis-cited as "Doc 13"; Doc 13 is the disclosure doc). **Authored EARLY** (Doc 27 Arc-3 item 9) so it sets the bar the rest of Arc 3 builds toward; **RUN LAST** (Doc 27 Arc-3 item 13) as the final gate before ship. Authoring ≠ executing — this file is the bar; the gate-run is the execution against it.*

*Status: SKELETON. Fill each gate with a concrete, checkable assertion + owner + evidence link as v1.0 firms up.*

---

## 0. How to use

- Each item is a **checkable assertion** (true/false, with evidence), not a vibe.
- Three dimensions below — **functional**, **licensing/compliance**, **security** — are ALL required to pass; a green functional column with a red license column is NOT shippable.
- The **cut list** (§4) records what was deliberately deferred out of v1.0 so the gate ratifies a *decision*, not an omission.

---

## 1. FUNCTIONAL gates (per subsystem)

*Does each subsystem actually work, on a clean machine, at ship quality?*

- [ ] **Generation — image:** SDXL/Pony, Flux (t2i+i2i), PixArt, Lumina, Z-Image, Anima render on the product surface (not just headless).
- [ ] **Generation — video:** LTX (t2v+i2v), Wan t2v + i2v (2.1 single-model min; 2.2 dual-noise i2v if Option B lands), Hunyuan (t2v+i2v), Mochi t2v render on the product surface.
- [ ] **Cockpit:** T2I/I2I/T2V/I2V fit-viewport, Simple/Advanced disclosure, generate→canvas, error surfacing (red pill), send-to routing.
- [ ] **Home / Model Library / Flows / History:** each loads, populates from real data, no dead affordances (note: Chain + Inspire hidden for v1.0 — nav gate, reversible).
- [ ] **Worker ⇄ ComfyUI:** managed runtime start/health, native-template submit, poll, asset download, metadata sidecar.
- [ ] **Settings / theme / persistence:** QSettings survive restart; theme presets apply.
- [ ] **Clean-machine smoke:** the whole above passes on a machine that never had the dev stack (ties the installer + first-run gate).
- [ ] **Cut list respected:** no half-built v2.0 surface reachable (3D, Chain/Inspire, audio).

## 2. LICENSING / COMPLIANCE gates

*Can this legally ship, and does it tell the user the truth about what they're allowed to do?*

- [ ] **GPL / copyleft boundary:** audit every bundled dependency + custom-node pack for GPL/AGPL; confirm the SpellVision distribution model (bundling ComfyUI + packs) respects each license's boundary (process-separation vs linking).
- [ ] **Non-commercial families surfaced:** Hunyuan ships in **2 families** (T2V + i2v) under the Tencent Community (non-commercial) license — the UI must badge this + warn on commercial-use flows (Doc 26 §4). Mochi/LTX permissive; the distinction must be visible.
- [ ] **Bundled ComfyUI + custom-node packs:** the installer bundles ComfyUI core **+ 5+ custom-node packs** (HunyuanVideoWrapper, LTXVideo, KJNodes, VideoHelperSuite, RES4LYF, …) — **each has its own license**; enumerate them + confirm redistribution is permitted, ship the license texts.
- [ ] **Per-asset license sidecars:** models the user downloads (or that ship) carry a license note; the dependency resolver flags license at download-time (Doc 27 item 10).
- [ ] **Trademark / branding:** app name, icon, any bundled fonts (Space Grotesk / Inter / JetBrains Mono) cleared for redistribution.
- [ ] **Attribution / NOTICE file:** aggregate third-party attributions shipped.

## 3. SECURITY gates

*What could a bundled or downloaded artifact do to the user's machine?*

- [ ] **Bundled dep versions pinned + scanned:** the pinned torch 2.10+cu128 / **kornia 0.8.2** / sageattention / triton-windows stack (Doc 25) — record exact versions, scan for known CVEs at ship time.
- [ ] **First-run network downloads:** anything the first-run wizard / dependency resolver pulls over the network — enumerate sources (HuggingFace repos, node installs via git), verify HTTPS + (ideally) checksum/signature; no silent arbitrary-URL fetches.
- [ ] **Custom-node install path:** node packs are git-cloned + `pip install`'d — confirm the source repos are pinned to reviewed commits, not floating `main`; a compromised node pack runs arbitrary code in the worker.
- [ ] **Model-file trust:** `.pt`/`.ckpt` (pickle) vs `.safetensors` — prefer safetensors; if any pickle format is loaded, note the code-exec risk + gate.
- [ ] **Worker surface:** the worker binds `127.0.0.1:8765` — confirm loopback-only, no unauthenticated remote exposure; same for ComfyUI `:8188`.
- [ ] **PYTHONUTF8 / env injection:** the launch env (PYTHONUTF8=1, path injection) sets nothing exploitable.
- [ ] **Update path:** if ComfyUI auto-update ships (post-v1.0), it's safety-gated (out of v1.0 scope; note here).

## 4. CUT LIST (deferred out of v1.0 — deliberate, not forgotten)

- [ ] 3D pipeline (Phase D) — v2.0.
- [ ] Comic / Character Studio (Chain child pages) — v2.0.
- [ ] Chain Studio + Inspire — hidden from nav (built spine/engine retained, reversible).
- [ ] Audio pipeline — stub, v2.0.
- [ ] Deeper upscaling beyond the v1.0 engine — v2.0 (the engine itself is v1.0, Doc 27 C1).
- [ ] Family-aware duration layer wiring (Doc 24) — design-only; render-verified in harness, not shipped.
- [ ] Worker god-file decomposition (Doc 21) — health, not a ship gate.
- [ ] LLM node-orchestration — v2+.

---

## 5. Sign-off

- [ ] All FUNCTIONAL gates green (or on the cut list).
- [ ] All LICENSING/COMPLIANCE gates green.
- [ ] All SECURITY gates green.
- [ ] Cut list reviewed + accepted.
- [ ] **Ship.**
