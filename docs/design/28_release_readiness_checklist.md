# Doc 28 — v1.0 Release-Readiness Checklist

*The bar the rest of Arc 3 builds toward. **RUN LAST** (Doc 27 item 13). Authoring ≠ executing.*

*Status: FILLED 2026-08-17 from owner lock. Each gate is a checkable assertion. Evidence links start empty until the gate is run.*

**Owner lock (2026-08-17):** hybrid installer (engines in the box, models on demand); current rail is in v1; Character/Comic/later extras must be **product-complete and** Character must reach mesh / garments / hair / beauty; Wan 2.2 dual-noise i2v before ship; license = badge + soft warn. First public wrap is MSI of a **proven** hybrid payload — never a shell-only exe.

---

## 0. How to use

- Each item is a **checkable assertion** (true/false, with evidence), not a vibe.
- Three dimensions — **functional**, **licensing/compliance**, **security** — must all pass.
- The **cut list** (§4) records what was deliberately deferred so the gate ratifies a *decision*, not an omission.

---

## 1. FUNCTIONAL gates

| Gate | Assertion | Owner | Evidence |
|---|---|---|---|
| Image generation | SDXL/Pony, Flux (t2i+i2i), PixArt, Lumina, Z-Image, Anima render on the product surface | dev | |
| Video generation | LTX (t2v+i2v), Wan t2v, **Wan 2.2 dual-noise i2v**, Wan 2.1 i2v fallback, Hunyuan (t2v+i2v), Mochi t2v render on the product surface | dev | **Wan 2.2 dual-noise i2v RENDER-PROVEN 2026-08-28** — 49f@832×480, 20 steps (10/10), 130.4s, frame-0 MAE 5.19, coherent to last frame, `wan_2.1_vae` correctly selected. Others previously proven; see CLAUDE.md §6. |
| Cockpit | T2I/I2I/T2V/I2V fit-viewport, Simple/Advanced in place, generate→canvas, red-pill errors, send-to | owner eyes | |
| Current rail | Home, Character, Comic, Concept, Gen3D, Dataset, Inspire, Train, Runtime, Flows, History, Models, Prefs — no dead chrome; generate/handoff or an honest gap | owner eyes | |
| Character product (B) | Mesh, garments, hair, beauty gates work on the Character surface (not a T4 tunic stand-in, not “coming soon”) | owner eyes | |
| Worker ⇄ Comfy | App-owned worker start/adopt/teardown; one persisted runtime profile; native-template submit; poll; sidecar | dev | |
| Hybrid first-run | Stranger machine with the engine payload can reach Generate after picking/downloading models; no `run_ui.ps1` required | dev + owner | |
| Settings / theme | QSettings survive restart; theme presets apply | dev | |
| Clean-machine smoke | The above on a machine that never had the dev stack | owner | |
| Cut list respected | No half-built v2 surface reachable without an honest label | owner | |
| **Workflow from a link** | Paste a real Civitai/GitHub workflow URL on a machine that has never seen it → its node packs resolve, install pinned, and it renders. Every install and every substitution shown; nothing downloaded on a guess. See Doc 46. | dev + owner | |
| **Dependency honesty** | No workflow reports *Ready* without having been preflighted; a class that is present is never reported missing; "could not check" never renders as "fine" | dev | |
| **Responsive matrix** | Doc 30's 7-surface × 4-state matrix actually **run and recorded** (it is defined and has never been executed) | owner eyes | |
| **Visual sign-off** | The chosen art direction is implemented and the owner has signed it off side by side against the mockups; WCAG contrast passes `ThemeManager::runContrastSelfCheck()` on every shipped preset | owner | |

## 2. LICENSING / COMPLIANCE gates

| Gate | Assertion | Owner | Evidence |
|---|---|---|---|
| GPL / copyleft | Bundled Comfy + custom-node packs audited; process-separation vs linking recorded | owner/legal | **PARTIAL 2026-09-02.** Audited and recorded in `NOTICE` §3/§4/§5: ComfyUI 0.34.0 (`12d5279`) is GPL-3.0 reached by process separation over HTTP with a separate interpreter; Qt 6.10.2 is LGPL with the relinking obligation and its three packaging constraints written down; libwebp v1.5.0 (BSD-3-Clause) is the only statically-linked third party. **Not green:** the legal review of that analysis is still an owner item (`NOTICE` §9 item 11), and three required/adjacent packs are unresolved — see the row below. |
| Non-commercial surfaced | Hunyuan **and Anima** show a badge; commercial-use setting on → **soft warn on generate** (not a hard block) | dev | **GREEN 2026-09-02.** Badge + warn now derive from `model_registry`'s `commercial_use` / `license_note` — one answer, generated into `qt_ui/assets/FamilyLicenseTable.h`, no family named by hand in C++. Previously both were decided by `hay.contains("anima") \|\| hay.contains("hunyuan")`, which badged animagine/animatediff and would have gone silent for a third non-commercial family. Badge on model cards, on all three studio surfaces, and the tooltip carries the licence note; warn is proceed-capable with the proceeding button as the default and reaches the chain path too. Ratchets: `tests/test_family_license_surfaced.py` (16), `tests/cpp/test_family_license.cpp` (ctest `family_license`). |
| Bundled licenses | Each shipped engine pack (Comfy core + custom nodes + fonts) has redistribution permission + shipped license text | owner | |
| Per-asset sidecars | Resolver flags license at download-time | dev | |
| Trademark / fonts | App name, icon, Space Grotesk / Inter / JetBrains Mono cleared | owner | |
| NOTICE | Aggregate third-party attributions shipped | dev | **SHIPPED 2026-09-02** — `./NOTICE`, compiled from the live tree (Qt 6.10.2, libwebp v1.5.0, ComfyUI 0.34.0 `12d5279`, the four packs the v1 families require with pinned commits, both venvs, fonts, and what is deliberately not bundled). Ratchet `tests/test_notice_file.py` (12) derives the Qt version, the libwebp tag and the payload classes from the tree and from §5 of this document, and pins the §9 open-questions list to the flags in the body so neither can lose the other. **11 items in §9 need an owner decision — three of them block families.** |

## 3. SECURITY gates

| Gate | Assertion | Owner | Evidence |
|---|---|---|---|
| Pinned stack scanned | torch 2.10+cu128 / kornia 0.8.2 / sageattention / triton-windows recorded + CVE-scanned at ship | dev | |
| First-run downloads | Sources enumerated (HF, git); HTTPS + checksum; no silent arbitrary-URL fetch | dev | |
| Custom-node installs | Pinned reviewed commits, not floating `main`; Comfy interpreter ≠ worker interpreter. **Met by `node_pack_installer`:** GitHub archive at the `ver` the workflow declares (no git dependency), requirements under a torch constraints file with a post-install assert, and an unpinned fallback is reported as unpinned rather than passed off as the requested revision | dev | |
| **Workflow-link fetch** | Workflow URLs are https-only from a host allowlist, redirects are re-checked against it, the Civitai token is never forwarded off civitai.com, bodies are size-capped against a lying `Content-Length`, and a downloaded archive cannot write outside `custom_nodes` (zip-slip + symlink members refused) | dev | |
| Model-file trust | Prefer `.safetensors`; pickle formats gated + documented | dev | **GREEN 2026-09-04 — and the honest finding is that the gate was already met by the stack while nothing recorded it.** Measured: **702** `.safetensors` under the model root against **10** pickle-format files (`.pt`/`.pth`/`.bin`), and **0** `torch.load` calls in SpellVision's own tree. Every loader that reads those ten already refuses to unpickle: `comfy/utils.py` uses `weights_only=True`, `UpscaleModelLoader` passes `safe_load=True` (which matters most — `4x-UltraSharp.pth` is the upscale tier's **Auto** pick, i.e. the pickle the product reaches for by default), diffusers passes `weights_only=True`, and torch has defaulted it since 2.6 against this box's 2.10. **Deliberately NOT shipped: a warning badge.** Telling a user to fear a file whose loader cannot execute it is theatre, and theatre in a security surface spends attention a real warning will later need. What ships instead is evidence and two guards, because all four facts above are **third-party defaults we do not control** and a torch downgrade or a ComfyUI patch could flip any of them with no line changing here: `tests/test_model_file_trust.py` (4) pins them, and the sweep rule `torch-load-cannot-execute-a-checkpoint` (baseline **0**, watched failing both ways) keeps our own tree from adding the first unguarded load. |
| Loopback only | Worker `:8765` and Comfy `:8188` bind 127.0.0.1 | dev | |
| Env injection | `PYTHONUTF8=1` launch sets nothing exploitable | dev | |
| Update path | Comfy **auto**-update stays out of v1. **AMENDED 2026-08-27:** update *detection and notification* ships (Runtime shows installed vs latest and offers the guided procedure); the live install is still never mutated and never `git pull`ed, so the assertion is "no unattended update path exists, and the update button cannot touch the running install" | dev | |

## 4. CUT LIST (deferred — deliberate)

- [x] **Audio pipeline depth** — v2.0
- [x] **LLM node-orchestration** — v2+
- [x] **Comfy auto-update** — post-v1. **Narrowed 2026-08-27:** what is cut is the *unattended* update. Detection + notification + the guided parallel-instance procedure are in v1 (owner: "my real intent"). See §3 Update path and Doc 46 §5.
- [ ] **Model tiers 2–4** (name search with a picker, architecture-compatible substitution — Doc 45) — **NOT YET DECIDED.** Tier 0/1 ship (present locally, workflow-declared URL). A workflow naming a model that is absent and undeclared currently reports "the workflow names this model but gives no source", which is honest but leaves the user to find it. Decide before sign-off whether that is acceptable for v1. **Note:** the planned "exact identity via hash/AIR" tier was dropped — measured across all 81 workflows, **0** carry an AIR identifier and **0** carry a model hash; the "~12%" in the plan was a substring false positive (`air` inside "hair"/"chair"). See Doc 46 §9.
- [x] **Streamed install/download progress** — **CLOSED 2026-09-03.** The entry above was half stale when it was written: multi-GB MODEL fetches already had byte-level progress on a background lane (`download_manager.py`). What was still a blob was INSTALLS, and measuring the ten `subprocess` call sites in `python/` found a distribution with a gap in it rather than a threshold anyone chose — compliant probes at 8 s / 30 s / 120 s, and three blind sites at **180 s** (a Blender run), **900 s** (git and pip for the Comfy manager) and **1800 s** (`pip install -r` for a node pack). All three captured output whole, so they produced nothing at all until they finished: a user installing packs for a workflow they had just pasted watched a still screen for up to half an hour, and a still screen reads as a crash. All three now run through `python/streamed_process.py`, which reads both pipes on their own threads and forwards each line as it arrives, and the sweep rule `long-processes-report-while-they-run` holds the property tree-wide (baseline **0**, watched failing by restoring the blob). Caveat recorded in the module: pip and git draw download bars with carriage returns, so those arrive late — what arrives promptly is the step narration, which is what says the machine is working. **This unblocks driving the guided ComfyUI update from inside the app**, which was the other thing it was holding up.
- [x] **Worker / ImageGenerationPage god-file split** — health, not a ship gate
- [x] **Family-aware duration layer (Doc 24)** — design-only
- [x] **Chain Studio** — remains nav-hidden unless `SPELLVISION_SHOW_ALL_MODES=1`
- [x] **Rust / cxx-qt SpellBound arc** — not SpellVision v1
- [ ] ~~3D Phase D / Character mesh~~ — **NO LONGER CUT.** Owner lock 2026-08-17 put mesh / garments / hair / beauty in the v1 bar.
- [ ] ~~Character / Comic as v2.0-only~~ — **NO LONGER CUT.** On rail; product-complete + Character B required.

## 5. Hybrid payload (what is “in the box”)

**Ships with the installer (engines):**

- `SpellVision.exe` + Qt runtime (`windeployqt`)
- Worker (`python/worker_service.py` + project venv)
- Isolated ComfyUI venv (torch/CUDA, kornia 0.8.2, PYTHONUTF8=1)
- Custom-node packs required by v1 families (pinned commits)

**Does not ship; first-run download / Locate:**

- Family checkpoints, VAEs, text encoders, clip-vision, LoRAs
- Optional hosted FLUX.3 (`BFL_API_KEY`)

**Must be proven before MSI wrap:**

1. One persisted runtime profile
2. App-owned worker start / adopt matching worker / stop only owned process
3. `comfy_python_executable` ≠ worker `python_executable`
4. Direct `SpellVision.exe` launch completes one known-good generation
5. Then wrap *that* layout

## 6. Sign-off

- [ ] All FUNCTIONAL gates green (or on the cut list)
- [ ] All LICENSING/COMPLIANCE gates green
- [ ] All SECURITY gates green
- [ ] Cut list reviewed + accepted
- [ ] **Ship**
