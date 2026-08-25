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
| Video generation | LTX (t2v+i2v), Wan t2v, **Wan 2.2 dual-noise i2v**, Wan 2.1 i2v fallback, Hunyuan (t2v+i2v), Mochi t2v render on the product surface | dev | |
| Cockpit | T2I/I2I/T2V/I2V fit-viewport, Simple/Advanced in place, generate→canvas, red-pill errors, send-to | owner eyes | |
| Current rail | Home, Character, Comic, Concept, Gen3D, Dataset, Inspire, Train, Runtime, Flows, History, Models, Prefs — no dead chrome; generate/handoff or an honest gap | owner eyes | |
| Character product (B) | Mesh, garments, hair, beauty gates work on the Character surface (not a T4 tunic stand-in, not “coming soon”) | owner eyes | |
| Worker ⇄ Comfy | App-owned worker start/adopt/teardown; one persisted runtime profile; native-template submit; poll; sidecar | dev | |
| Hybrid first-run | Stranger machine with the engine payload can reach Generate after picking/downloading models; no `run_ui.ps1` required | dev + owner | |
| Settings / theme | QSettings survive restart; theme presets apply | dev | |
| Clean-machine smoke | The above on a machine that never had the dev stack | owner | |
| Cut list respected | No half-built v2 surface reachable without an honest label | owner | |

## 2. LICENSING / COMPLIANCE gates

| Gate | Assertion | Owner | Evidence |
|---|---|---|---|
| GPL / copyleft | Bundled Comfy + custom-node packs audited; process-separation vs linking recorded | owner/legal | |
| Non-commercial surfaced | Hunyuan **and Anima** show a badge; commercial-use setting on → **soft warn on generate** (not a hard block) | dev | |
| Bundled licenses | Each shipped engine pack (Comfy core + custom nodes + fonts) has redistribution permission + shipped license text | owner | |
| Per-asset sidecars | Resolver flags license at download-time | dev | |
| Trademark / fonts | App name, icon, Space Grotesk / Inter / JetBrains Mono cleared | owner | |
| NOTICE | Aggregate third-party attributions shipped | dev | |

## 3. SECURITY gates

| Gate | Assertion | Owner | Evidence |
|---|---|---|---|
| Pinned stack scanned | torch 2.10+cu128 / kornia 0.8.2 / sageattention / triton-windows recorded + CVE-scanned at ship | dev | |
| First-run downloads | Sources enumerated (HF, git); HTTPS + checksum; no silent arbitrary-URL fetch | dev | |
| Custom-node installs | Pinned reviewed commits, not floating `main`; Comfy interpreter ≠ worker interpreter | dev | |
| Model-file trust | Prefer `.safetensors`; pickle formats gated + documented | dev | |
| Loopback only | Worker `:8765` and Comfy `:8188` bind 127.0.0.1 | dev | |
| Env injection | `PYTHONUTF8=1` launch sets nothing exploitable | dev | |
| Update path | Comfy auto-update is **out of v1**; noted, not shipped | — | |

## 4. CUT LIST (deferred — deliberate)

- [x] **Audio pipeline depth** — v2.0
- [x] **LLM node-orchestration** — v2+
- [x] **Comfy auto-update** — post-v1
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
