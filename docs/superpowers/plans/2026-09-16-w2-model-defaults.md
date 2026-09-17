# W2 Model Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Selecting a checkpoint on any generation page lands *that model's own* published settings — steps, CFG, sampler, scheduler, shift, canvas size, frames, fps — so a Simple-mode user changes nothing and an Advanced-mode user sees the right values already filled in, with a caption saying where each came from.

**Architecture:** W1 already stores what each model wants in `<stem>.spellvision.json` and answers `model_recommended_settings`. W2 makes that command the single resolver (family operating point, then sidecar, then user, with hardware caps and an allowlist intersection), gives `MainWindow` a per-model-path async cache mirroring its existing per-family one, and applies the answer through the existing `applyOperatingPoint` path. The per-family C++ literals and the krea2 filename hack are deleted, so there is one table and one resolver.

**Tech Stack:** Python 3.12 stdlib, C++17/Qt6, existing worker TCP protocol, pytest + QTest.

**Spec:** `docs/superpowers/specs/2026-09-15-t2-t6-completion-design.md` §2. W1's plan and outcome: `docs/superpowers/plans/2026-09-16-w1-model-intelligence.md`. **Verbatim code map for every C++ site this plan touches: `docs/superpowers/specs/2026-09-15-t2-t6-research/w2-cpp-recon.md` — read the section named in each task rather than re-deriving it.**

## Global Constraints

- **Python 3.12, stdlib only.** C++17, Qt 6.10.2, no new dependencies.
- Every new module under 300 lines. `worker_service.py` gains nothing.
- Run Python tests: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/<file> -q` from the repo root. `PYTHONPATH=""` is required on this box.
- Python test files that import from `python/` need `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))`.
- Inside `python/model_intelligence/`, import siblings **absolutely**; export any new module from `__init__.py`.
- **C++ builds:** `.\scripts\dev\rebuild_ui.ps1`, and **always `Stop-Process -Name SpellVision` before rebuilding** or the link fails with `LNK1168`. A new C++ test target needs a `CMakeLists.txt` entry and bumps a count in `docs/design/53_consistency_and_robustness_audit.html`.
- **Qt test output is invisible without `QT_ASSUME_STDERR_HAS_CONSOLE` in the ctest environment** — the existing targets set it; copy that. And shell redirection (`*>`, `2>&1 |`) silently drops a QTest binary's output on this box: use QTest's own `-o <file>,txt`.
- A new worker command trips **four** ratchets: `worker_command_audience.py`, the wire-type registry in `python/worker_client.py`, protocol-doc counts (`tests/test_protocol_doc.py`), and `ARCHITECTURE.md` + the test-file count (`tests/test_governing_docs.py`). W2 adds no new command — it extends one — but changing a reply's shape still touches the protocol doc.
- **No `Co-Authored-By` trailer** on commits.
- **The full suite has 18 pre-existing failures that also fail on `main`** (verified in a clean worktree, 2026-09-16). Do not chase them. Your gate is the files you touch, plus `-m ratchet`.
- **Never invent a value.** Every field the resolver returns carries a `provenance`; a field with no source is absent.

## The measured result this wave exists to deliver

On the owner's real library (2026-09-16): every `Lox's Utopic World` variant on disk publishes **10 steps / CFG 1 / er_sde / simple** across its author's own example images, and the Krea2 LoRAs cluster at **8 steps / CFG 1**. `family_operating_points.py` renders that family at its default point `raw` = **52 / 3.5**. Today the app uses 52. After W2 it uses 10, and says so.

---

## File Structure

| File | Change |
|---|---|
| `python/family_operating_points.py` | Operating points gain `width, height, frames, fps, clip_skip, guidance`; the video literals currently living in C++ move in. |
| `python/model_intelligence/hf_lookup.py` | Fix the prose regex that yields `steps: 0`. |
| `python/model_intelligence/recommended.py` | Enforce the `n>=3` gate; refuse a forged `user` provenance from a card. |
| `python/model_intelligence/resolve.py` | **New.** The one resolver: family OP → sidecar → user, sampler intersected with the family allowlist, hardware caps applied as warnings. |
| `python/model_intelligence_commands.py` | `model_recommended_settings` delegates to `resolve.py`. |
| `qt_ui/MainWindow.{h,cpp}` | Per-model-path async cache + provider, mirroring the per-family one. |
| `qt_ui/ImageGenerationPage*.cpp` | Apply the resolved point on model change in both modes; provenance caption; canvas/frames/fps from the point; delete the literals and the krea2 hack. |
| `tests/cpp/test_model_defaults_apply.cpp` | **New.** |
| `tests/sweeps/rules.py` | **New rule** `sampling-defaults-are-data`. |

---

## Task 1: The operating-point schema grows the fields the C++ was holding

**Files:**
- Modify: `python/family_operating_points.py`
- Test: `tests/test_family_operating_points.py` (existing — add to it)

**Interfaces:**
- Produces: every entry in `FAMILY_OPERATING_POINTS[*]["operating_points"][*]` may now carry `width, height, frames, fps, clip_skip, guidance` alongside the existing `steps, cfg, sampler, scheduler, shift, lora, acceleration`.
- Produces: `family_operating_points.OPERATING_POINT_FIELDS: tuple[str, ...]` — the complete field vocabulary, for callers that iterate.

**Why:** `applyOptimalVideoSamplingDefaults` (`qt_ui/ImageGenerationPage_video.cpp:219-278`, quoted in full in `docs/superpowers/specs/2026-09-15-t2-t6-research/w2-cpp-recon.md` §1a) hardcodes wan 14/14/shift 5.0/28/cfg 5.0/uni_pc/simple and an LTX and a FLUX.3 block in C++, duplicating and overriding the Python table. Two resolvers for one question is the defect Doc 50 rule 5 names. The values move to the data; the C++ keeps only the act of applying them.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_family_operating_points.py`:

```python
def test_every_operating_point_carries_a_complete_sampling_set():
    """A point the cockpit applies must say what to apply.

    Before W2 the video canvas/frames/fps values lived as literals in
    ImageGenerationPage_video.cpp while steps/cfg/sampler lived here, so the two could disagree
    and did. This asserts the table alone is sufficient.
    """
    from family_operating_points import FAMILY_OPERATING_POINTS, OPERATING_POINT_FIELDS

    required = {"steps", "cfg", "sampler", "scheduler"}
    for family, block in FAMILY_OPERATING_POINTS.items():
        for name, point in block["operating_points"].items():
            missing = required - set(point)
            assert not missing, f"{family}/{name} is missing {sorted(missing)}"
            unknown = set(point) - set(OPERATING_POINT_FIELDS)
            assert not unknown, f"{family}/{name} has unknown fields {sorted(unknown)}"


def test_video_families_carry_their_canvas_and_duration():
    """wan / ltx / hunyuan_video / mochi must name frames and fps, because the C++ that used to
    hold those numbers is being deleted in this wave."""
    from family_operating_points import FAMILY_OPERATING_POINTS

    for family in ("wan", "ltx", "hunyuan_video", "mochi"):
        block = FAMILY_OPERATING_POINTS[family]
        point = block["operating_points"][block["default_operating_point"]]
        assert point.get("frames"), f"{family} default point names no frames"
        assert point.get("fps"), f"{family} default point names no fps"
        assert point.get("width") and point.get("height"), f"{family} default point names no canvas"


def test_the_wan_numbers_that_were_in_cpp_are_now_in_the_table():
    """The exact values ImageGenerationPage_video.cpp:219-278 applied, so the move is lossless."""
    from family_operating_points import FAMILY_OPERATING_POINTS

    point = FAMILY_OPERATING_POINTS["wan"]["operating_points"][
        FAMILY_OPERATING_POINTS["wan"]["default_operating_point"]
    ]
    assert point["shift"] == 5.0
    assert point["width"] == 832 and point["height"] == 480
    assert point["frames"] == 81 and point["fps"] == 16
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_family_operating_points.py -q`
Expected: FAIL — `ImportError: cannot import name 'OPERATING_POINT_FIELDS'`

- [ ] **Step 3: Add the field vocabulary and fill the table**

In `python/family_operating_points.py`, above `FAMILY_OPERATING_POINTS`:

```python
# The complete vocabulary of an operating point. `steps/cfg/sampler/scheduler` are required of
# every point; the rest are optional and present where the family has a published answer.
#
# width/height/frames/fps arrived in W2. They were literals inside
# ImageGenerationPage_video.cpp::applyOptimalVideoSamplingDefaults, which meant the cockpit and this
# table could disagree about the same family -- and did, because each was edited without the other.
# The numbers below are exactly what that function applied; the C++ keeps only the act of applying.
OPERATING_POINT_FIELDS: tuple[str, ...] = (
    "steps", "cfg", "guidance", "sampler", "scheduler", "shift", "clip_skip",
    "width", "height", "frames", "fps", "lora", "acceleration",
)
```

Then add `width`, `height`, `frames`, `fps` to each video family's points, taking the values from `docs/superpowers/specs/2026-09-15-t2-t6-research/w2-cpp-recon.md` §1a (wan: shift 5.0, 832×480, 81 @ 16; ltx: 832×480, 97 @ 24 — check the recon for the exact ltx and flux3 numbers the C++ applied and carry them verbatim), and `width`/`height` to each image family (1024×1024 unless the family's own card says otherwise — `python/model_intelligence/family_seed_table.py` already holds the published per-family canvas and is the source to copy from).

**Do not change any existing `steps`/`cfg`/`sampler`/`scheduler` value.** This task is additive; a changed sampling value here would silently change every render.

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_family_operating_points.py tests/test_image_builders_operating_points.py tests/test_operating_point_reachability.py -q`
Expected: PASS. If a builder test fails, the new fields leaked into a request payload — they must be inert for anything that does not ask for them.

- [ ] **Step 5: Prove the completeness test bites**

Delete `frames` from the `wan` default point. Re-run. Expected: `test_video_families_carry_their_canvas_and_duration` FAILS naming wan. Revert; re-run: PASS.

- [ ] **Step 6: Commit**

```bash
git add python/family_operating_points.py tests/test_family_operating_points.py
git commit -m "feat(sampling): an operating point carries its canvas and duration too

width/height/frames/fps were literals inside applyOptimalVideoSamplingDefaults
while steps/cfg/sampler lived in the table, so the cockpit and the table could
disagree about the same family. The numbers here are exactly what the C++
applied; the C++ keeps only the act of applying them."
```

---

## Task 2: The four findings deferred from W1's final review

**Files:**
- Modify: `python/model_intelligence/hf_lookup.py`, `python/model_intelligence/recommended.py`
- Test: `tests/test_model_intelligence_hf.py`, `tests/test_model_intelligence_recommended.py`

These were found by W1's whole-branch review, judged latent (nothing passes `card_settings` yet) and deferred here **on the condition that they be written into this plan rather than carried as ambient knowledge**. W2 is the wave that starts consuming the recommended block, so they stop being latent now.

**I4 — the prose regex invents a value.** `hf_lookup.py`'s `("steps", re.compile(r"(\d{1,3})\s*(?:inference\s*)?steps\b", re.I))` matches "trained for 15000 steps" and yields `steps: 0` (the last three digits). It then outranks the family table. Violates "never invent a value".

**I5 — a card can forge a `user` provenance.** `recommended.py`'s `_offer` loop trusts `entry.get("provenance")` verbatim from `card_settings`, so a card entry claiming `"user"` outranks a unanimous site value and is then preserved forever by `sidecar.user_values`.

**I6 — the spec's `n>=3` gate is not implemented.** Spec §1.3 says the image-meta mode needs `n≥3`. A 1-of-4 example currently outranks a card snippet and the family table.

**I7 — the recommended sampler is never intersected with the family allowlist.** A site-sourced `dpm_2_ancestral` on an SDXL model will be refused at generate time by `FAMILY_SAMPLER_ALLOWLISTS`, so the cockpit would show a default the graph rejects.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_model_intelligence_hf.py`:

```python
def test_a_training_step_count_is_not_an_inference_step_count():
    """"trained for 15000 steps" is provenance for the model, not a recommendation for the user.

    The old pattern matched the last three digits and produced steps: 0 -- a value no one wrote,
    outranking the family table. Never invent a value.
    """
    found = hf_lookup.settings_from_readme("This checkpoint was trained for 15000 steps on 8xA100.")
    assert "steps" not in found


def test_a_plausible_inference_step_count_is_still_read():
    assert hf_lookup.settings_from_readme("We recommend 28 steps.")["steps"]["value"] == 28


def test_zero_steps_is_never_returned():
    for text in ("0 steps", "trained for 1000 steps", "100000 steps of training"):
        assert hf_lookup.settings_from_readme(text).get("steps", {}).get("value") != 0
```

Add to `tests/test_model_intelligence_recommended.py`:

```python
def test_a_card_cannot_claim_the_user_provenance():
    """Only the user is the user. A card entry claiming "user" would outrank a unanimous site
    value AND be preserved forever by sidecar.user_values -- a permanent wrong default written by
    a third party's README."""
    block = recommended.build(
        civitai_version=_version("civitai_checkpoint_combined_sampler"),
        card_settings={"steps": {"value": 999, "provenance": "user"}},
        family="krea2",
    )
    assert block["steps"]["value"] == 10
    assert block["steps"]["provenance"] == "site:image-meta-mode"


def test_a_card_provenance_outside_the_vocabulary_is_ignored():
    block = recommended.build(
        civitai_version=None,
        card_settings={"steps": {"value": 999, "provenance": "totally-made-up"}},
        family="krea2",
    )
    assert block["steps"]["provenance"] == "table:family-default"


def test_a_lone_example_does_not_outrank_a_card_snippet():
    """The spec's n>=3 gate. One uploader's single example is evidence, not a recommendation."""
    block = recommended.build(
        civitai_version=_version("civitai_controlnet_sparse_meta"),  # steps present in 1 of 4
        card_settings={"steps": {"value": 28, "provenance": "card:snippet-regex"}},
        family=None,
    )
    assert block["steps"]["value"] == 28
    assert block["steps"]["provenance"] == "card:snippet-regex"


def test_a_lone_example_still_beats_nothing():
    """Below the gate it is demoted, not discarded -- it still outranks the family floor."""
    block = recommended.build(
        civitai_version=_version("civitai_controlnet_sparse_meta"),
        card_settings=None,
        family="krea2",
    )
    assert block["steps"]["value"] == 8
    assert block["steps"]["provenance"] == "site:image-meta-weak"
    assert block["steps"]["n"] == 1


def test_three_agreeing_examples_clear_the_gate():
    version = {"images": [{"meta": {"steps": 7}} for _ in range(3)]}
    block = recommended.build(civitai_version=version, card_settings=None, family=None)
    assert block["steps"]["provenance"] == "site:image-meta-mode"
```

- [ ] **Step 2: Run to verify they fail**

Run both files. Expected: the five new tests FAIL.

- [ ] **Step 3: Fix the prose regex**

In `hf_lookup.py`, replace the `steps` prose pattern so a training-step count cannot match, and bound the result:

```python
    # "trained for 15000 steps" is not a recommendation, and the old \d{1,3} pattern matched its
    # last three digits and produced steps: 0 -- a value nobody wrote, outranking the family table.
    # Require a word boundary before the number, reject a leading "trained/training for", and keep
    # the result inside a range any sampler would accept.
    ("steps", re.compile(r"(?<!\d)(?<!train)(?<!trained for )(\b\d{1,3}\b)\s*(?:inference\s*)?steps\b", re.I)),
```

and in the extraction loop, discard a `steps` value outside `1..300`:

```python
        if field == "steps" and not (1 <= float(value) <= 300):
            continue
```

Design the exact regex yourself against the three test strings — the shape above is a sketch, and the tests are the specification. Whatever you write, a number immediately preceded by "trained for" must not match and `0` must never be returned.

- [ ] **Step 4: Fix the provenance forgery and add the `n>=3` gate**

In `recommended.py`:

```python
# Provenances a CARD may claim. "user" is deliberately absent: only the user is the user, and a
# card entry claiming it would outrank a unanimous site value and then be preserved forever by
# sidecar.user_values -- a permanent wrong default written by a third party's README.
CARD_PROVENANCES: frozenset[str] = frozenset(
    {"card:frontmatter", "card:snippet-regex", "card:prose-regex"}
)

# Example images needed before their mode counts as a recommendation rather than an observation.
# Spec section 1.3. Below it the value is kept but DEMOTED -- one uploader's single render is
# evidence, and evidence still beats a generic family floor.
MODE_QUORUM = 3
```

Add `"site:image-meta-weak"` to `PROVENANCE_ORDER`, ranked **below** `card:prose-regex` and **above** `table:family-default`. In `build`, offer the site mode as `site:image-meta-mode` when `mode["n"] >= MODE_QUORUM`, otherwise as `site:image-meta-weak`. In the card loop, accept a provenance only if it is in `CARD_PROVENANCES`.

- [ ] **Step 5: Run to verify they pass**

Run both files, and the whole model-intelligence set:
`PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_*.py -q`
Expected: PASS. **The house-checkpoint test must still read 10 steps at `site:image-meta-mode`** — its n is 10, well over the quorum. If it now reads `weak`, the gate is inverted.

- [ ] **Step 6: Prove the gate and the forgery guard bite**

Set `MODE_QUORUM = 1`; re-run: `test_a_lone_example_does_not_outrank_a_card_snippet` FAILS. Revert.
Add `"user"` to `CARD_PROVENANCES`; re-run: `test_a_card_cannot_claim_the_user_provenance` FAILS. Revert. Paste all four outputs.

- [ ] **Step 7: Commit**

```bash
git add python/model_intelligence/hf_lookup.py python/model_intelligence/recommended.py tests/test_model_intelligence_hf.py tests/test_model_intelligence_recommended.py
git commit -m "fix(models): a training step count is not a recommendation, and a card is not the user

Three findings W1's review deferred here, now that W2 starts consuming the
recommended block. The prose regex matched 'trained for 15000 steps' and
returned steps: 0 -- a value nobody wrote, outranking the family table. A
card claiming provenance 'user' outranked a unanimous site value and was
then preserved forever as if the user had set it. And the spec's n>=3 quorum
on the example-image mode was never implemented, so one uploader's single
render outranked a model card. Below the quorum the value is demoted, not
discarded: evidence still beats a generic floor."
```

---

## Task 3: One resolver, with the allowlist and the caps

**Files:**
- Create: `python/model_intelligence/resolve.py`
- Modify: `python/model_intelligence_commands.py` (delegate), `python/model_intelligence/__init__.py` (export)
- Test: `tests/test_model_defaults_resolve.py` (new)

**Interfaces:**
- Produces: `resolve.resolve_model_defaults(*, path, family, mode, sidecar_payload, live_samplers=None, live_schedulers=None, vram_gb=None, host_ram_gb=None) -> dict` returning `{"settings": {field: {value, provenance, confidence, n, total}}, "family": str|None, "warnings": [str], "operating_point": str|None}`.

**Precedence, and it is the whole point of the file:** `user` > `site:image-meta-mode` > `card:snippet-regex` > `card:prose-regex` > `site:image-meta-weak` > `table:family-operating-point` > `table:family-default`. Note `table:family-operating-point` — the runtime table the app renders with — sits *above* `table:family-default`, the published floor, because the former is tuned by this project's own render comparisons.

**Two rules that make the answer usable rather than merely correct:**
1. **The sampler and scheduler are intersected with the family's allowlist.** A site-sourced sampler the family's graph cannot accept is dropped to the family default with a warning, because a cockpit showing a default the generate path will refuse is worse than showing the family's.
2. **Hardware caps snap with a warning, never silently** (spec §2, Doc 54 T5).

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_defaults_resolve.py`:

```python
"""One resolver for "what settings should this page show for this model".

Four sources and two tables disagree, so the order lives in exactly one place. The two rules that
make the answer usable rather than merely correct:

  * a sampler the family's graph cannot accept is not offered -- a cockpit showing a default the
    generate path will refuse is worse than showing the family's own;
  * a hardware cap snaps with a warning, never silently (Doc 54 T5).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import resolve, sidecar

FIXTURES = Path(__file__).parent / "fixtures" / "model_intelligence"


def _sidecar_with(recommended: dict) -> dict:
    return {"schema": sidecar.SCHEMA, "identity": {"family": "krea2", "kind": "checkpoint"},
            "display": {}, "recommended": recommended}


def _entry(value, provenance, n=None, total=None):
    return {"value": value, "provenance": provenance, "confidence": 1.0, "n": n, "total": total}


def test_the_sidecar_beats_the_family_operating_point():
    """The headline: the house checkpoint says 10 steps, the runtime table says 52."""
    out = resolve.resolve_model_defaults(
        path="F:/models/loxsUtopicWorldKrea2_v20Quants.safetensors",
        family="krea2", mode="t2i",
        sidecar_payload=_sidecar_with({"steps": _entry(10, "site:image-meta-mode", 10, 10),
                                       "cfg": _entry(1.0, "site:image-meta-mode", 10, 10)}),
    )
    assert out["settings"]["steps"]["value"] == 10
    assert out["settings"]["steps"]["provenance"] == "site:image-meta-mode"
    assert out["settings"]["cfg"]["value"] == 1.0


def test_the_family_operating_point_fills_what_the_model_did_not_say():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="krea2", mode="t2i",
        sidecar_payload=_sidecar_with({"steps": _entry(10, "site:image-meta-mode", 10, 10)}),
    )
    assert out["settings"]["sampler"]["provenance"] == "table:family-operating-point"
    assert out["settings"]["sampler"]["value"] == "er_sde"


def test_with_no_sidecar_the_family_operating_point_is_the_answer():
    out = resolve.resolve_model_defaults(path="F:/models/x.safetensors", family="krea2",
                                         mode="t2i", sidecar_payload=None)
    assert out["settings"]["steps"]["value"] == 52
    assert out["settings"]["steps"]["provenance"] == "table:family-operating-point"


def test_a_user_value_beats_the_model_and_both_tables():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="krea2", mode="t2i",
        sidecar_payload=_sidecar_with({"steps": _entry(24, "user"),
                                       "cfg": _entry(1.0, "site:image-meta-mode", 10, 10)}),
    )
    assert out["settings"]["steps"]["value"] == 24
    assert out["settings"]["steps"]["provenance"] == "user"


def test_a_sampler_the_family_cannot_run_is_dropped_with_a_warning():
    """Krea2's allowlist does not contain dpm_2_ancestral. Offering it would produce a cockpit
    default the generate path refuses."""
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="wan", mode="t2v",
        sidecar_payload={"schema": sidecar.SCHEMA, "identity": {"family": "wan"}, "display": {},
                         "recommended": {"sampler": _entry("dpm_2_ancestral", "site:image-meta-mode", 5, 5)}},
    )
    assert out["settings"]["sampler"]["value"] != "dpm_2_ancestral"
    assert out["settings"]["sampler"]["provenance"] == "table:family-operating-point"
    assert any("dpm_2_ancestral" in w for w in out["warnings"])


def test_a_sampler_the_family_can_run_survives():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="wan", mode="t2v",
        sidecar_payload={"schema": sidecar.SCHEMA, "identity": {"family": "wan"}, "display": {},
                         "recommended": {"sampler": _entry("uni_pc", "site:image-meta-mode", 5, 5)}},
    )
    assert out["settings"]["sampler"]["value"] == "uni_pc"
    assert out["warnings"] == [] or not any("uni_pc" in w for w in out["warnings"])


def test_a_live_sampler_list_narrows_the_allowlist_further():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="wan", mode="t2v",
        sidecar_payload={"schema": sidecar.SCHEMA, "identity": {"family": "wan"}, "display": {},
                         "recommended": {"sampler": _entry("uni_pc", "site:image-meta-mode", 5, 5)}},
        live_samplers=["euler", "dpmpp_2m"],
    )
    assert out["settings"]["sampler"]["value"] != "uni_pc"
    assert any("uni_pc" in w for w in out["warnings"])


def test_a_canvas_beyond_the_vram_budget_snaps_with_a_warning_not_silently():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="wan", mode="t2v",
        sidecar_payload={"schema": sidecar.SCHEMA, "identity": {"family": "wan"}, "display": {},
                         "recommended": {"width": _entry(3840, "site:image-meta-mode", 5, 5),
                                         "height": _entry(2160, "site:image-meta-mode", 5, 5)}},
        vram_gb=8,
    )
    assert out["settings"]["width"]["value"] < 3840
    assert any("3840" in w for w in out["warnings"])
    assert out["settings"]["width"]["provenance"].endswith(":capped")


def test_no_cap_is_applied_when_the_hardware_is_not_known():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family="wan", mode="t2v",
        sidecar_payload={"schema": sidecar.SCHEMA, "identity": {"family": "wan"}, "display": {},
                         "recommended": {"width": _entry(3840, "site:image-meta-mode", 5, 5)}},
        vram_gb=None,
    )
    assert out["settings"]["width"]["value"] == 3840
    assert out["warnings"] == []


def test_an_unknown_family_yields_whatever_the_sidecar_said_and_no_more():
    out = resolve.resolve_model_defaults(
        path="F:/models/x.safetensors", family=None, mode="t2i",
        sidecar_payload=_sidecar_with({"steps": _entry(10, "site:image-meta-mode", 10, 10)}),
    )
    assert out["settings"]["steps"]["value"] == 10
    assert "sampler" not in out["settings"]


def test_every_returned_field_declares_a_provenance():
    out = resolve.resolve_model_defaults(path="F:/models/x.safetensors", family="krea2",
                                         mode="t2i", sidecar_payload=None)
    assert out["settings"]
    for field, entry in out["settings"].items():
        assert entry.get("provenance"), field
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_defaults_resolve.py -q`
Expected: FAIL — cannot import `resolve`

- [ ] **Step 3: Write `python/model_intelligence/resolve.py`**

Write it against the tests above. Structure:

```python
"""The one answer to "what should this page show for this model".

Two tables and four sources disagree, so the order lives here and nowhere else:

    user
      > site:image-meta-mode          (>= MODE_QUORUM of the model's own example images)
      > card:snippet-regex > card:prose-regex
      > site:image-meta-weak          (fewer examples than the quorum -- evidence, not advice)
      > table:family-operating-point  (this project's own render comparisons)
      > table:family-default          (what the family's publisher states)

`table:family-operating-point` outranks `table:family-default` because the former was chosen by
measuring renders on this hardware and the latter is a generic published figure.

Two rules make the answer usable rather than merely correct. A sampler the family's graph cannot
accept is dropped to the family's own default with a warning -- a cockpit offering a default the
generate path refuses is worse than one offering the family's. And a hardware cap snaps with a
warning, never silently: the user has to be able to see that the number they are looking at is not
the number the model asked for.
"""
```

Use `family_operating_points.operating_point_params(family, point)` for the runtime table, `family_operating_points.FAMILY_SAMPLER_ALLOWLISTS` (plus `live_samplers`/`live_schedulers` when given) for the intersection, `family_seed_table.seed_for` for the published floor, and `sidecar.read`-shaped payloads for the model's own. The variant (`raw` vs `turbo`) comes from the sidecar's identity when it names one, else from the path substring, else the family's `default_operating_point` — and **record which operating point was chosen in the result**, because the cockpit's Speed chip needs to agree with it.

A capped field keeps its original provenance with `":capped"` appended, so the caption can say the value was reduced.

For the VRAM cap, keep it simple and honest: a table of `family → max pixels at a given VRAM budget` is a guess this project has not measured, so cap only on a clearly-unrunnable basis (e.g. more pixels than the budget could hold at a conservative bytes-per-pixel) and say in the warning that the cap is a heuristic. **Do not invent precise per-family memory figures** — the repo's own history (CLAUDE.md §6) records a VRAM claim that was read off a number that was never a requirement.

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_defaults_resolve.py -q`
Expected: PASS

- [ ] **Step 5: Delegate the command to the resolver**

Rewrite `handle_model_recommended_settings_command` in `python/model_intelligence_commands.py` to call `resolve.resolve_model_defaults`, passing the request's `family`, `mode`, `live_samplers`, `live_schedulers`, `vram_gb` and `host_ram_gb` when present. Keep the reply's existing keys (`ok, type, path, family, settings, warnings`) and add `operating_point`. Keep the containment check on `path`. Update `docs/SPELLVISION_WORKER_PROTOCOL.md` for the new field and re-run `tests/test_protocol_doc.py`.

- [ ] **Step 6: Prove the precedence and the allowlist bite**

Move `table:family-operating-point` above `site:image-meta-mode` in the order; re-run: the headline test FAILS with 52 != 10. Revert.
Delete the allowlist intersection; re-run: `test_a_sampler_the_family_cannot_run_is_dropped_with_a_warning` FAILS. Revert. Paste all four.

- [ ] **Step 7: Run the whole set and commit**

```bash
PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_model_intelligence_*.py tests/test_model_defaults_resolve.py tests/test_protocol_doc.py -q
git add python/model_intelligence/resolve.py python/model_intelligence/__init__.py python/model_intelligence_commands.py docs/SPELLVISION_WORKER_PROTOCOL.md tests/test_model_defaults_resolve.py
git commit -m "feat(models): one resolver for what a page should show for a model

Two tables and four sources disagreed and the order lived nowhere. It lives
here now, with the runtime operating point ranked above the published family
floor because the former was chosen by measuring renders on this hardware.
A sampler the family's graph cannot accept is dropped to the family default
with a warning: a cockpit offering a default the generate path refuses is
worse than one offering the family's own. A hardware cap snaps with a warning
and keeps its provenance, so the caption can say the number was reduced."
```

---

## Task 4: `MainWindow` learns to ask about one model

**Files:**
- Modify: `qt_ui/MainWindow.h`, `qt_ui/MainWindow.cpp`
- Test: covered by Task 8's C++ test

**Interfaces:**
- Produces: `void MainWindow::fetchModelDefaultsAsync(const QString &modelPath, const QString &family, const QString &mode, std::function<void()> completion)`
- Produces: `QJsonObject MainWindow::modelDefaultsFor(const QString &modelPath) const`
- Produces: `ImageGenerationPage::setModelDefaultsProvider(std::function<QJsonObject(const QString &modelPath)>)` and `ImageGenerationPage::refreshModelDefaults()`

**Read first:** `docs/superpowers/specs/2026-09-15-t2-t6-research/w2-cpp-recon.md` §3 quotes `fetchOperatingPointsAsync`, `operatingPointsForFamily`, their declarations, their cache members, and the `setOperatingPointsProvider` + `fetchOperatingPointsAsync(...)` wiring in `ensureGenerationPageBuilt` — **in full**. Mirror that pattern exactly.

**The one structural difference, and the recon calls it out:** the existing four members express *one* global single-flight (`operatingPointsFetched_`, `operatingPointsFetchInFlight_`, one waiter vector). A per-model cache needs a **keyed** equivalent: `QHash<QString, QJsonObject> modelDefaultsByPath_`, a `QSet<QString> modelDefaultsInFlight_`, and `QHash<QString, std::vector<std::function<void()>>> modelDefaultsWaiters_`. A second request for a path already in flight must attach a waiter, not issue a second request.

- [ ] **Step 1: Add the cache members and declarations**

In `MainWindow.h`, beside the existing operating-point members, with a comment explaining why this one is keyed where that one is not.

- [ ] **Step 2: Implement `fetchModelDefaultsAsync`**

Mirroring `fetchOperatingPointsAsync` (recon §3a): return immediately if the path is cached; register the completion; single-flight per path; send `{"command": "model_recommended_settings", "path": …, "family": …, "mode": …}` via `sendWorkerRequestAsync` with the same 12000 ms budget; on success store the whole reply under the path; on failure store nothing and still fire the waiters (so the page falls back to the family point rather than hanging). Normalise the key the same way both sides do (`QDir::fromNativeSeparators` + lowercase) so a path spelled two ways is one cache entry.

- [ ] **Step 3: Implement `modelDefaultsFor`** — cache-only, exactly like `operatingPointsForFamily` (recon §3b).

- [ ] **Step 4: Wire the provider in `ensureGenerationPageBuilt`**

Beside the existing `setOperatingPointsProvider` call (recon §3e), add `setModelDefaultsProvider`. Do **not** add a fetch here — a page has no model selected at construction. The fetch is triggered by the page on model change (Task 5).

- [ ] **Step 5: Build**

```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
.\scripts\dev\rebuild_ui.ps1
```
Expected: clean build. (`LNK1168` means the exe was still running.)

- [ ] **Step 6: Commit**

```bash
git add qt_ui/MainWindow.h qt_ui/MainWindow.cpp qt_ui/ImageGenerationPage.h
git commit -m "feat(cockpit): MainWindow can ask what one model wants

Mirrors the per-family operating-point fetch, with one structural change the
per-family version did not need: the single-flight is KEYED. Each model path
is its own request, so a second ask for a path already in flight attaches a
waiter instead of issuing a duplicate."
```

---

## Task 5: The page applies it, in both modes, and says where it came from

**Files:**
- Modify: `qt_ui/ImageGenerationPage.h`, `qt_ui/ImageGenerationPage.cpp`, `qt_ui/ImageGenerationPage_video.cpp`, `qt_ui/ImageGenerationPage_catalog.cpp`

**Read first:** recon §1 (the four apply functions in full), §2a (the `setSelectedModel` funnel and its `QTimer::singleShot(0, …)` re-entrancy hazard), §6 (how `advanced_` gates visibility), §7 (where the Sampling tab is assembled and the existing one-line-caption precedents).

**The hook point, from recon §2a:** every path through `setSelectedModel` converges on `updateOperatingPointSelector()` — directly for image modes, and via `resolveAndApplyVideoComponents()` for video. That is the single place to trigger the per-model fetch.

**The re-entrancy hazard is load-bearing.** The recon quotes the existing comment: a worker round-trip from inside a combo-change handler runs a nested event loop and crashes with the popup open, which is why the video branch already defers with `QTimer::singleShot(0, …)`. The model-defaults fetch must be deferred the same way.

- [ ] **Step 1: Trigger the fetch on model change**

In `updateOperatingPointSelector()`, after the existing family work, if a model path is selected, `QTimer::singleShot(0, this, [...]{ ... })` into a new `requestModelDefaults()` that calls the provider's fetch with a `QPointer`-guarded completion calling `applyModelDefaults()`.

- [ ] **Step 2: Implement `applyModelDefaults()`**

Read the cached reply via the provider. For each field present in `settings`, write it into the same widget `applyOperatingPoint` writes (recon §1d shows every one). **Apply in both Simple and Advanced** — spec ruling R2.1: Simple applies because the user will not change it, Advanced applies because a pre-filled correct value is the point, and the user edits in place afterwards. Do not relocate any control; this is a value change, not a layout change.

Order matters: apply the family operating point first (existing behaviour), then overlay the model's, so a field the model does not mention keeps the family's.

- [ ] **Step 3: Add the provenance caption**

A single `QLabel` under the Sampling card (recon §7a shows the assembly, §7b shows the existing one-line-caption precedents to match for styling — use a theme token, not a literal colour). Text shape:

- model-sourced: `Defaults from this model's CivitAI examples · 10 of 10 agree`
- card-sourced: `Defaults from the model card`
- family: `Family defaults (this model has no published settings)`
- capped: append ` · reduced to fit VRAM`
- no sidecar: `Family defaults · run Refresh metadata on the Models page to use this model's own`

**The caption is visible in both modes.** It is the honesty surface for a value the user did not choose.

- [ ] **Step 4: Build and run the responsive gate**

```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
.\scripts\dev\rebuild_ui.ps1
ctest --test-dir build -R responsive_matrix --output-on-failure
```
Expected: clean build, `responsive_matrix` green with Clipped 0. A new label that pushes a page over its minimum will fail here — fix the label (elide it), never the gate.

- [ ] **Step 5: Commit**

```bash
git add qt_ui/ImageGenerationPage*.cpp qt_ui/ImageGenerationPage.h
git commit -m "feat(cockpit): a model's own settings land when you pick it, and the page says so

Applied in BOTH modes: Simple because the user will not change it, Advanced
because a pre-filled correct value is the point and editing in place is the
rule. The fetch is deferred with singleShot(0) for the reason the video
branch already was -- a worker round-trip from inside a combo handler runs a
nested event loop and crashes with the popup open.

The caption is the honesty surface: a default the user did not choose has to
say where it came from, and how many of the model's own examples agreed."
```

---

## Task 6: Canvas, frames and fps come from the same answer

**Files:**
- Modify: `qt_ui/ImageGenerationPage_catalog.cpp` (`ensureCanvasSizeDefault`, recon §5a), `qt_ui/ImageGenerationPage_video.cpp`

**Today** (recon §5a) the canvas default is mode-based only: 832×480 for video, 1024×1024 for image, with no family or model input.

- [ ] **Step 1: Take width/height/frames/fps from the resolved point**

In `applyModelDefaults()`, write `width`/`height` into the canvas widgets and `frames`/`fps` into the video duration widgets when the resolved settings carry them. **Snap to the family's multiple** using the constraints already enforced in `LtxVideoAdapter.prepare_request` and its siblings — width/height divisible by 32 for LTX, frame length `(N×8)+1`, and the per-family rules the builders already apply. Do not re-derive those rules: if a C++-side copy does not exist, snap on the Python side inside `resolve.py` and let the C++ write what it is given.

- [ ] **Step 2: Preserve the user's own canvas**

If the user has already typed a size for this session and this mode, a model change must not overwrite it. Follow whatever `ensureCanvasSizeDefault`'s existing "has the user touched this" logic is (recon §5a) — and if there is none, add a `canvasTouchedByUser_` flag set by the widgets' `editingFinished`, because silently resizing someone's canvas is the same class of defect as silently changing their steps.

- [ ] **Step 3: Simple-mode orientation still works**

Portrait/Landscape in Simple swaps the resolved pair rather than overriding it with a literal. Verify against the orientation control the recon locates in §5.

- [ ] **Step 4: Build, then commit**

```bash
git commit -m "feat(cockpit): the canvas comes from the model too, and a typed size survives

The canvas default was mode-based only -- 832x480 or 1024x1024, with no
family or model input -- while the model's own page states a size. A size
the user typed is never overwritten by a model change: silently resizing
someone's canvas is the same defect as silently changing their steps."
```

---

## Task 7: Delete the second resolver

**Files:**
- Modify: `qt_ui/ImageGenerationPage_video.cpp` (`applyOptimalVideoSamplingDefaults`), `qt_ui/ImageGenerationPage_units.h` (the krea2 hack), `qt_ui/ImageGenerationPage_video.cpp:1085-1106` (its call site)
- Create: a sweep rule in `tests/sweeps/rules.py`
- Test: `tests/test_sweeps.py`

- [ ] **Step 1: Gut `applyOptimalVideoSamplingDefaults`**

It keeps its name and its callers, and loses its literals: it now reads the family operating point through the provider and applies it. Every number in recon §1a must be gone from the C++.

- [ ] **Step 2: Delete `krea2OperatingPointForPath`**

`ImageGenerationPage_units.h:171-177` decides `raw` vs `turbo` by testing whether the path contains "turbo". The sidecar now names the variant and `resolve.py` picks the operating point, so the hack is not merely redundant — it is wrong for a model like `loxsUtopicWorldKrea2_v20Quants`, whose author publishes 10 steps and whose filename says neither word. Delete it and its call site, and make sure the krea2 values hardcoded at its call site (recon §1e) go with it.

- [ ] **Step 3: Add the sweep rule**

A new rule `sampling-defaults-are-data`: no numeric literal assigned to a sampling widget (`stepsSpin`, `cfgSpin`, shift spins, frames, fps) inside `qt_ui/`. Follow the existing rule shape in `tests/sweeps/rules.py` and baseline any legitimate remaining site **with a stated reason per site**, not a blanket exemption. Write its self-test in `tests/test_sweeps.py` the way the `_import_edges` regression test was written.

- [ ] **Step 4: Prove the rule bites**

Add `stepsSpin_->setValue(28);` to a page file. Run the sweep. Expected: the rule reports it. Remove it; re-run: clean. Paste both.

- [ ] **Step 5: Build, run every gate, commit**

```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
.\scripts\dev\rebuild_ui.ps1
ctest --test-dir build --output-on-failure
```
```bash
PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest -m ratchet -q
git commit -m "refactor(cockpit): one sampling table, and the krea2 filename hack is gone

applyOptimalVideoSamplingDefaults held wan/ltx/flux3 numbers that duplicated
and overrode the Python table. krea2OperatingPointForPath picked raw vs turbo
by testing the filename for 'turbo' -- which is wrong for the owner's own
loxsUtopicWorldKrea2_v20Quants, whose author publishes 10 steps and whose
filename says neither word. A new ratchet keeps sampling numbers in data."
```

---

## Task 8: The C++ test, and the live proof

**Files:**
- Create: `tests/cpp/test_model_defaults_apply.cpp`
- Modify: `CMakeLists.txt`, `docs/design/53_consistency_and_robustness_audit.html`, `docs/design/55_t7_ship_walkthrough.html`

**Read first:** recon §8 quotes `tests/cpp/test_sampling_controller.cpp` and `test_canvas_size_default.cpp` and the CMake entry that registers a target. Copy that shape, including `QT_ASSUME_STDERR_HAS_CONSOLE` in the ctest environment.

- [ ] **Step 1: Write the C++ test**

Cases, each of which must fail against a plausible wrong implementation:
1. A fake provider returns a model with `steps=10, provenance=site:image-meta-mode, n=10`; selecting that model in **Simple** sets the steps widget to 10.
2. The same in **Advanced** sets the same widget to 10 — a plant that applies only in Simple must fail this.
3. A model whose settings omit `sampler` keeps the family operating point's sampler — a plant that clears unmentioned fields must fail this.
4. The caption names the provenance and the agreement count.
5. A user-typed canvas survives a model change.
6. A provider that returns nothing (worker down) leaves the family defaults in place and does not clear the widgets.

- [ ] **Step 2: Register the target in `CMakeLists.txt`** and bump the count in `docs/design/53_consistency_and_robustness_audit.html` that `tests/test_governing_docs.py` enforces.

- [ ] **Step 3: Build and run**

```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
.\scripts\dev\rebuild_ui.ps1
ctest --test-dir build -R model_defaults --output-on-failure
```

- [ ] **Step 4: Prove the Advanced case bites**

Make `applyModelDefaults()` return early when `advanced_` is true. Rebuild, re-run. Expected: case 2 FAILS. Revert, rebuild, re-run: PASS. Paste both. **Rebuild between the plant and the revert** — a stale object file makes this prove nothing.

- [ ] **Step 5: The live proof**

Launch the app (`.\scripts\dev\run_ui.ps1`), go to T2I, select `loxsUtopicWorldKrea2_v20Quants`, and capture the cockpit in **Simple** and in **Advanced**. Both must show **10 steps / CFG 1 / er_sde / simple** and the caption naming the model's examples. Then select a model with no sidecar and capture the family-defaults caption. Then **generate once** at the applied defaults and record the dest path and the wall time — the previous pictured krea2 dest ran 52 steps in 179.9 s, so this is also the first measurement of what the correct defaults cost.

- [ ] **Step 6: Write the proof into the walkthrough**

Add a T5 section to `docs/design/55_t7_ship_walkthrough.html` with those captures and the before/after numbers. **Do not paint T5 green** — the owner's bar is every page × every family, and this is one page and one family. Say exactly which pages and families are proven and which are not.

- [ ] **Step 7: Commit**

```bash
git add tests/cpp/test_model_defaults_apply.cpp CMakeLists.txt docs/design/
git commit -m "test(cockpit): a model's defaults land in both modes, and the walkthrough shows it

Six cases, each written to fail against a plausible wrong implementation --
most importantly that Advanced applies them too, since the tempting shortcut
is to treat pre-filling as a Simple-mode convenience.

The live capture is one page and one family. T5 stays open."
```

---

## Self-Review

**Spec §2 coverage:**

| Spec item | Task |
|---|---|
| OP schema gains width/height/aspect/frames/fps/clip_skip/guidance | 1 |
| C++ `applyOptimalVideoSamplingDefaults` values move into the table | 1, 7 |
| krea2 filename hack deleted | 7 |
| One Python resolver: family OP overlaid by sidecar overlaid by user | 3 |
| Hardware caps snap with a warning, never silently | 3 |
| Async per-model request on every checkpoint change | 4, 5 |
| Ruling R2.1: applies in Simple AND Advanced | 5, and test case 2 in 8 |
| Provenance caption | 5 |
| Canvas from the resolved point; Simple orientation swaps the pair | 6 |
| Preset guard (never names a model) | inherited — the resolver returns settings only |
| Ratchet `no sampling literals in C++` | 7 |
| Live proof | 8 |
| W1's deferred I4-I7 | 2 (I4, I5, I6), 3 (I7) |

**Deliberately not in W2:** the studios' own checkpoint pickers. Recon §9 establishes whether they route through `setSelectedModel`; if they do they inherit this for free, and if they do not, wiring them is a W5 task listed there rather than smuggled in here.

**Type consistency:** `resolve.resolve_model_defaults` keywords match between Tasks 3 and its command caller; `fetchModelDefaultsAsync`/`modelDefaultsFor`/`setModelDefaultsProvider` match between Tasks 4, 5 and 8; the `settings` entry shape (`value, provenance, confidence, n, total`) is the same one W1's `recommended.build` produces and `sidecar` stores.

**Placeholder scan:** the C++ tasks give anchors, signatures and the recon section to read rather than full transcription, because the surrounding code is long and the recon holds it verbatim. Every Python task carries complete code or a complete test that specifies it.
