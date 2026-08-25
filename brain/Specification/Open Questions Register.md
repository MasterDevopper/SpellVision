---
title: Open Questions Register
type: spec
status: living
updated: 2026-08-17
---

# Open Questions Register

Numbered, contiguous. Empty response ≠ approval.

## P0 — blocks architecture or next ship wave

### Q1 — Installer bundle strategy
**Why:** Arc-3 critical path unknown difficulty (multi-GB CUDA+Comfy isolated venv).
**Options:** (A) Full offline bundle (B) Thin client + first-run downloads (C) Hybrid pinned runtime cache (D) Dev-only zip defer public installer.
**Recommend:** C hybrid — ship managed runtime layout matching Doc 25, download models on demand.
**Status:** **resolved 2026-08-17 — C hybrid.** Engines in the box; models on demand. MSI wraps a proven payload only. See [[Owner Decision Log]] + Doc 28 §5.

### Q2 — Hunyuan i2v truth post cutover
**Why:** Doc 26 vs `video_family_contracts` disagree; license-sensitive family.
**Options:** (A) Contract correct — still blocked (B) Doc 26 correct — unstick contract notes (C) Partial: one wrapper path only.
**Recommend:** Live render probe on current Comfy; update both surfaces same day.
**Status:** open

## P1 — blocks complete subsystem/release spec

### Q3 — Wan 2.2 dual-noise i2v in v1.0?
**Why:** Quality upgrade vs schedule; cell already green via 2.1.
**Options:** (A) Defer to post-v1.0 (B) Build before ship (C) Ship behind Advanced experimental flag.
**Recommend:** A unless marketing needs flagship i2v — Doc 26 already green via A.
**Status:** **resolved 2026-08-17 — B. Build before any ship.**

### Q4 — License gate strength
**Why:** Hunyuan non-commercial must be honest.
**Options:** (A) Badge only (B) Soft warn on generate when commercial toggle on (C) Hard block commercial toggle.
**Recommend:** B per Doc 26.
**Status:** **resolved 2026-08-17 — B.** Badge + soft warn. Also applies to Anima.

### Q5 — Character/Comic in v1.0 nav?
**Why:** Code exists; roadmap said v2.0 ship.
**Options:** (A) Hide nav (Chain pattern) (B) Ship as preview (C) Fully polish into v1.0.
**Recommend:** A for clean cut list unless demo needs them.
**Status:** **resolved 2026-08-17 — C, as A+B.** Current rail stays. Product-complete **and** Character mesh / garments / hair / beauty are v1 gates.

## P2 — phase-local

### Q6 — Quantized LTX / offload for higher native res
**Why:** Softness vs 32GB ceiling.
**Status:** parked optimization thread

### Q7 — God-file decomposition timing
**Why:** Health vs feature velocity.
**Status:** explicitly out of families-done bar

### Q8 — Mode-aware history schema details
**Why:** Arc-2 #12 load-bearing; needs core + per-mode payload design ratification in implementation.
**Status:** **implemented 2026-08-17** — `history_schema.py` v2 (`mode` + `mode_payload.image|video`). UI Detail column no longer borrows Duration. Owner eyes still close the History surface.

### Q9 — Comic upload → video
**Why:** Owner wants Comic Studio to ingest a page and emit I2V clips.
**Options:** (A) Build in v1 (B) Bank as v2 (C) Never.
**Recommend:** B — I2V rail already exists; ingest/crop/batch is a product slice, not a v1 ship gate.
**Status:** **resolved 2026-08-17 — B / v2.** Spec: `docs/design/40_comic_page_to_video_v2.md`. Do not implement now.

## Related

[[Owner Decision Log]] · [[v1.0 Roadmap Synthesis]] · [[Contradiction Ledger]]
