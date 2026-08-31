---
title: Owner Decision Log
type: log
updated: 2026-08-17
---

# Owner Decision Log

Minimal durable checkpoints for interactive decisions. Newest first.

## 2026-08-17 — Comic page → video is v2

| ID | Decision |
|----|----------|
| **Home** | Comic Studio |
| **When** | **v2.0.** Not now. Not a v1 ship gate. |
| **What** | Upload comic/page → crop panels → I2V → optional stitch |
| **Spec** | `docs/design/40_comic_page_to_video_v2.md` |

v1 Comic stays script → stills → `page.png`.

## 2026-08-17 — v1.0 lock (close the plan)

Elicited in-session. Blank was not treated as yes.

| ID | Decision |
|----|----------|
| **v1 product** | Current rail stays. Character, Comic, Concept, Gen3D, Dataset, Inspire, Train, Runtime are **in** v1. |
| **Polish depth** | **A + B.** Product-complete (no dead chrome, generate/handoff works, honest gaps) **and** full Character product: mesh, garments, hair, beauty gates. |
| **Q1 installer** | **Hybrid.** Ship engines (Qt exe + worker + isolated Comfy/CUDA venv). Models download / Locate on demand. No fake MSI of today's exe. |
| **Q3 Wan 2.2 dual-noise i2v** | **Build before any ship.** Cell is no longer “optional quality upgrade.” |
| **Q4 license** | **Badge + soft warn on generate** when commercial-use is on. Not a hard block. Hunyuan **and Anima**. |
| **This session** | Close plan docs, then implement **one persisted runtime profile + app-owned worker bootstrap**. Not MSI. |

Still open: **Q2** Hunyuan i2v live truth post-cutover; **Q8** mode-aware history schema details.

## 2026-07-25 — Brain bootstrap

- Created Obsidian brain under `brain/` synthesizing CLAUDE.md, design docs 25–29, architecture, contracts, and live tree layout.
- No new product-scope decisions elicited in this pass; open items remain in [[Open Questions Register]].

## Prior (from docs, not re-elicited)

- Wan i2v: Option A done + Option B scheduled (Doc 26) — **superseded 2026-08-17: Option B is now a ship gate**
- Comfy cutover live on C: sv_comfynext (Doc 25)
- v1.0 forks: 3D/studios ship-label v2.0 — **superseded 2026-08-17**
