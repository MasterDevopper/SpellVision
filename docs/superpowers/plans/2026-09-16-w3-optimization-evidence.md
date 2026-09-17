# W3 Optimization Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every optimization SpellVision ships is timed against the same job run without it, on this machine, and the result is recorded where a person can read it — so "SageAttention is on" stops being a claim and becomes a number.

**Architecture:** Each render already records its seconds, twice over. What no render records is *which build it was*. W3 adds an `optimizations` provenance block beside `generation_time_sec`, lets the worker restart ComfyUI into a chosen arm, and adds a harness that runs the matrix through the product path and writes a results ledger the Runtime page and a generated document both read.

**Tech Stack:** Python 3.12 stdlib, C++17/Qt6, existing worker TCP protocol, live ComfyUI 0.34.0 on this box.

**Spec:** `docs/superpowers/specs/2026-09-15-t2-t6-completion-design.md` §3. **Two research files are load-bearing and each task names the one it needs:**
- `docs/superpowers/specs/2026-09-15-t2-t6-research/t4-context.md` — what the tree does today, with file:line.
- `docs/superpowers/specs/2026-09-15-t2-t6-research/t4-research.md` — the 2026 optimization landscape, what is reachable on this stack and what is not.

## Global Constraints

- **Python 3.12, stdlib only.** C++17, Qt 6.10.2. No new dependencies.
- Modules under 300 lines. `worker_service.py` gains nothing but a delegation.
- Python tests: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/<file> -q` from the repo root. `PYTHONPATH=""` is required.
- Test files importing from `python/` need `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))`.
- **`Stop-Process -Name SpellVision` before every C++ build** or the link fails `LNK1168`. Build: `.\scripts\dev\rebuild_ui.ps1`. `ctest` needs `-C Debug`.
- **Current gate to compare against: `ctest -C Debug` 30 of 31** (`shell_layout` pre-existing), and ~20 Python failures that also fail on a clean tree. Do not chase either; do not let them hide a new one.
- A new worker command trips four ratchets: `worker_command_audience.py`, the wire-type registry in `python/worker_client.py`, protocol-doc counts, and `ARCHITECTURE.md` + counts in `docs/design/53_consistency_and_robustness_audit.html`.
- **No `Co-Authored-By` trailer.**
- **Never invent a number.** This wave exists because a number was quoted that nothing measured; every figure it produces must name the run that produced it.

## What is already true, and what is not

**Already true** (`t4-context.md`): every render writes `generation_time_sec`, `steps_per_sec` and `cache_hit` into a sidecar (`worker_metadata.py:705-707`), and those persist twice — `runtime/state/job_archive.json` (rolling 200, FIFO) and `runtime/state/history/video_history.jsonl` (append-only). The stopwatch is built.

**Not true:** nothing records *which build* produced a number. All 59 history keys were checked and none matches `atten|sage|sdpa|accel|teacache|tiling|fp16|comfy`. The published SageAttention A/B is distinguishable only because a human typed `t4_sage` and `t4_sdpa` into two output filenames.

**And the published A/B does not survive contact with its own data.** `job_archive.json` holds a **third arm nobody mentioned**: `t4_sage_queue_3d2236390c95` at **159.27 s**, same seed, same steps, same size, about fifteen minutes before the 120.72 s sage run. So the three real numbers are 159.27 / 120.72 / 124.01, and the quoted "sage is 3% faster" is **smaller than the cold-load variance between two runs of the same arm.** That is the defect this wave fixes, and Task 5's harness is built around it: discard the first run of every configuration.

---

## File Structure

| File | Change |
|---|---|
| `python/optimization_provenance.py` | **New.** Reads the live build's identity from `/system_stats` + the venv, returns the block a sidecar carries. |
| `python/worker_metadata.py` | Writes that block beside `generation_time_sec`. |
| `python/comfy_launch_policy.py` | Accepts an explicit arm (attention, `--fast` features, DynamicVRAM, reserve) instead of reading only the environment. |
| `python/comfy_bootstrap.py`, `python/comfy_runtime_manager.py` | Thread the arm through; pass `env=launch_env()` to `Popen`. |
| `python/worker_service.py` | `restart_comfy_runtime` accepts the arm. |
| `python/optimization_results.py` | **New.** Append/read the results ledger. |
| `python/optimization_commands.py` | **New.** `optimization_results` command. |
| `scripts/dev/measure_optimizations.py` | **New.** The harness. |
| `qt_ui/ManagerPage.cpp` | Runtime page "Optimizations" panel. |
| `docs/design/60_t4_optimization_results.md` | **New.** Generated from the ledger. |

---

## Task 1: A render records which build made it

**Files:**
- Create: `python/optimization_provenance.py`
- Modify: `python/worker_metadata.py`
- Test: `tests/test_optimization_provenance.py` (new)

**Interfaces:**
- `optimization_provenance.probe(api_url: str | None = None, *, opener=None) -> dict` → `{comfy_version, comfy_argv, attention_backend, fast_flags, dynamic_vram, torch, cuda, python, packages: {sageattention, triton, comfy_kitchen, comfy_aimdo}, probed_at}`
- `optimization_provenance.attention_from_argv(argv: Sequence[str]) -> str` → `sage | flash | ck | split | quad | sdpa`
- `optimization_provenance.fast_from_argv(argv) -> list[str]`
- `worker_metadata.build_metadata_payload(...)` gains `optimizations: dict` in its output.

**Read first:** `t4-context.md` §"Recorded today" and §"Seconds already captured".

**The argv is the source of truth and it is already available.** Verified on this box: `GET /system_stats` returns `system.argv` (`['…/main.py', '--listen', '127.0.0.1', '--port', '8188', '--use-sage-attention']`), `system.pytorch_version`, `system.comfyui_version` and `system.comfy_package_versions`. Do not infer the arm from what the worker *intended* to launch — read what the running process actually got, because the two have diverged before (the Qt sage probe fails open to SDPA on a cold first launch, `RuntimeProfile.cpp:307`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_optimization_provenance.py`:

```python
"""What build produced this render.

Every render already records its seconds. None records which build made them, which is why the
only published A/B on this project is distinguishable solely because a human typed "t4_sage" and
"t4_sdpa" into two output filenames. A number without its arm is not evidence.

The arm is read from the RUNNING process's argv, never from what the launcher intended: the Qt
sage probe fails open to SDPA on a cold first launch, so intent and reality have diverged here
before.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

import optimization_provenance as op


class FakeResponse(io.BytesIO):
    status = 200


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.urls = []

    def open(self, request, timeout=None):
        self.urls.append(getattr(request, "full_url", str(request)))
        return FakeResponse(json.dumps(self.payload).encode("utf-8"))


LIVE = {
    "system": {
        "comfyui_version": "0.34.0",
        "pytorch_version": "2.10.0+cu128",
        "python_version": "3.12.7",
        "argv": ["C:/sv/ComfyUI/main.py", "--listen", "127.0.0.1", "--port", "8188",
                 "--use-sage-attention"],
        "comfy_package_versions": {"comfy-aimdo": "0.4.15", "comfy-kitchen": "0.2.31"},
    }
}


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["main.py", "--use-sage-attention"], "sage"),
        (["main.py", "--use-flash-attention"], "flash"),
        (["main.py", "--use-ck-attention"], "ck"),
        (["main.py", "--use-pytorch-cross-attention"], "sdpa"),
        (["main.py", "--use-split-cross-attention"], "split"),
        (["main.py", "--listen", "127.0.0.1"], "sdpa"),
    ],
)
def test_attention_is_read_from_the_running_argv(argv, expected):
    assert op.attention_from_argv(argv) == expected


def test_fast_flags_bare_means_every_feature():
    """`--fast` with no values enables all of them; the record must say which, not repeat the flag."""
    assert set(op.fast_from_argv(["main.py", "--fast"])) == set(op.ALL_FAST_FEATURES)


def test_fast_flags_named_are_recorded_as_named():
    assert op.fast_from_argv(["main.py", "--fast", "fp16_accumulation"]) == ["fp16_accumulation"]


def test_no_fast_flag_is_an_empty_list_not_none():
    assert op.fast_from_argv(["main.py", "--use-sage-attention"]) == []


def test_dynamic_vram_is_on_unless_disabled():
    assert op.dynamic_vram_from_argv(["main.py"]) is True
    assert op.dynamic_vram_from_argv(["main.py", "--disable-dynamic-vram"]) is False


def test_reserve_vram_is_recorded_when_given():
    assert op.reserve_vram_from_argv(["main.py", "--reserve-vram", "16"]) == 16.0
    assert op.reserve_vram_from_argv(["main.py"]) is None


def test_probe_reads_the_live_stats():
    block = op.probe("http://127.0.0.1:8188", opener=FakeOpener(LIVE))
    assert block["attention_backend"] == "sage"
    assert block["comfy_version"] == "0.34.0"
    assert block["torch"] == "2.10.0+cu128"
    assert block["cuda"] == "12.8"
    assert block["dynamic_vram"] is True
    assert block["packages"]["comfy_aimdo"] == "0.4.15"
    assert "--use-sage-attention" in block["comfy_argv"]


def test_probe_failure_is_a_block_that_says_it_does_not_know():
    """A render still has to be recordable when the probe fails -- but it must not claim SDPA."""

    class Broken:
        def open(self, request, timeout=None):
            raise OSError("comfy down")

    block = op.probe("http://127.0.0.1:8188", opener=Broken())
    assert block["attention_backend"] == "unknown"
    assert block["comfy_version"] is None
    assert block.get("probe_error")


def test_the_block_never_claims_a_default_it_did_not_read():
    block = op.probe("http://127.0.0.1:8188", opener=FakeOpener({"system": {}}))
    assert block["attention_backend"] == "unknown"
    assert block["comfy_argv"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="" ./.venv/Scripts/python.exe -m pytest tests/test_optimization_provenance.py -q`
Expected: FAIL — no module named `optimization_provenance`

- [ ] **Step 3: Write `python/optimization_provenance.py`**

Write it against those tests. Points the tests do not state but the module must honour:

- **Cache the probe per `api_url` with a short TTL** (a render should not pay an HTTP round trip for its own metadata), but invalidate on restart — `invalidate_comfy_object_info` already exists as the precedent for that pattern.
- The attention flags are mutually exclusive in `comfy/cli_args.py`; if two appear, record both and mark the block ambiguous rather than picking one.
- `ALL_FAST_FEATURES = ("fp16_accumulation", "fp8_matrix_mult", "cublas_ops", "autotune")`, from the live `PerformanceFeature` enum documented in `t4-research.md` §1.
- Read the venv package versions from `comfy_package_versions` when `/system_stats` supplies them, and do not shell out to pip.

- [ ] **Step 4: Attach it to every render**

In `worker_metadata.build_metadata_payload` (signature at `:624`), add an `optimizations` key beside `generation_time_sec` (`:705`). It must be present on **every** render path — `comfy_prompt_client`, `image_runners`, `native_runners` all call through here; confirm by grepping rather than assuming.

Also record the two request-side switches the wave can already see: `vae_tiling` (from the request) and `fp16_cast` (the `CAST_FP32_TO_FP16` constant, `worker_runtime.py:23`), plus `wrapper_attention_mode` where the family uses it (`native_video_graphs.py:1877-1889`).

- [ ] **Step 5: Add the ratchet**

A new sweep rule `every-render-names-its-argv`: a sidecar-writing path that records `generation_time_sec` must also record `optimizations`. Follow `tests/sweeps/rules.py`'s existing shape and write its self-test in `tests/test_sweeps.py` — **this one is not optional, W2 shipped a rule whose self-test was never written and the final review caught it.**

- [ ] **Step 6: Prove it bites**

Delete the `optimizations` key from the payload; run the new tests and the ratchet; both must fail. Restore; both pass. Paste all four outputs.

- [ ] **Step 7: Commit**

```bash
git add python/optimization_provenance.py python/worker_metadata.py tests/test_optimization_provenance.py tests/sweeps/rules.py tests/test_sweeps.py
git commit -m "feat(telemetry): a render records which build made it

Every render already recorded its seconds; none recorded its arm. The only
published A/B on this project is distinguishable solely because a human typed
t4_sage and t4_sdpa into two output filenames -- and the archive holds a third
arm nobody mentioned, at 159.27s against the quoted 120.72s, which makes the
published 3% smaller than the variance between two runs of the SAME arm.

The arm is read from the running process's argv, never from what the launcher
intended: the Qt sage probe fails open to SDPA on a cold first launch, so the
two have diverged here before."
```

---

## Task 2: The worker can restart ComfyUI into a chosen arm

**Files:**
- Modify: `python/comfy_launch_policy.py`, `python/comfy_bootstrap.py`, `python/comfy_runtime_manager.py`, `python/worker_service.py`, `docs/SPELLVISION_WORKER_PROTOCOL.md`
- Test: `tests/test_comfy_launch_policy.py` (existing, add to it), `tests/test_optimization_arm_restart.py` (new)

**Interfaces:**
- `comfy_launch_policy.build_launch_command(..., arm: dict | None = None)` where `arm` is `{attention, fast: [...], dynamic_vram: bool, vram_headroom: float|None}`
- `handle_restart_comfy_runtime_command(req)` accepts the same keys and returns the argv it launched.

**Read first:** `t4-context.md` §"Launch policy" — it names three launch sites and two real defects in them.

**Two defects to fix while you are here, both recorded and neither speculative:**
1. `bootstrap_comfy_runtime` (`comfy_bootstrap.py:302-311`) **has no `vram_headroom` parameter**, so the worker-managed launch can never pass `--reserve-vram`. Its own `extra_args` seam has no caller.
2. `ComfyRuntimeManager.start` calls `subprocess.Popen(command, cwd=…)` with **no `env=`** (`comfy_runtime_manager.py:299-306`), so `launch_env()` — which the module docstring calls load-bearing, and which sets `PYTHONUTF8=1` — never reaches the Python-managed launch. `launch_env` is referenced only by tests today.

- [ ] **Step 1: Write the failing test**

Create `tests/test_optimization_arm_restart.py` asserting: an arm naming `sdpa` produces `--use-pytorch-cross-attention` and no `--use-sage-attention`; an arm naming `sage` when sageattention is absent raises rather than silently falling back (the existing `resolve_attention_backend` contract, `:205-212`); `fast: ["fp16_accumulation"]` produces `--fast fp16_accumulation`; `dynamic_vram: False` produces `--disable-dynamic-vram`; `vram_headroom: 16` produces `--reserve-vram 16`; an arm of `None` reproduces today's environment-driven behaviour byte-for-byte; and `Popen` receives an `env` containing `PYTHONUTF8=1`.

Write the assertions against the real functions — read them first; do not trust this paragraph over the source.

- [ ] **Step 2-4: Run, implement, re-run** — thread `arm` through the three launch sites, keeping the default path unchanged.

- [ ] **Step 5: Extend the command**

`restart_comfy_runtime` gains the arm keys, and its reply gains `argv` (what actually launched) so a caller can verify rather than assume. Update the protocol doc; run `tests/test_protocol_doc.py`.

- [ ] **Step 6: Prove the env fix bites**

Assert `Popen` is called with an `env` carrying `PYTHONUTF8`. Remove the `env=` argument; the test fails. Restore; it passes. Paste both.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(runtime): the worker can restart Comfy into a named arm, and its launch keeps UTF-8

Three launch sites, two of them already broken: bootstrap could not pass
--reserve-vram at all (no parameter, and extra_args had no caller), and the
Python-managed Popen had no env=, so launch_env() -- which the module docstring
calls load-bearing and which sets PYTHONUTF8=1 -- reached only the tests.

The restart reply now carries the argv it actually launched, because an A/B
whose arms are asserted rather than read is how the published one went wrong."
```

---

## Task 3: The results ledger

**Files:**
- Create: `python/optimization_results.py`, `python/optimization_commands.py`
- Modify: `python/worker_tcp.py`, `worker_command_audience.py`, `python/worker_client.py`, protocol doc, `ARCHITECTURE.md`
- Test: `tests/test_optimization_results.py` (new)

**Interfaces:**
- `optimization_results.append(row: dict) -> Path` and `.read(limit=None) -> list[dict]`, over `runtime/state/optimization_results.jsonl`
- Row: `{family, mode, lever, arm, seconds: [..], mean, baseline_mean, delta_pct, warm, quality: {...}, provenance: {...}, dest, job_id, recorded_at}`
- Command `optimization_results` → `{ok, type, rows, families, levers}`

**The rules the schema exists to enforce, and they are not decoration:**
- `seconds` is a **list**, never a scalar. A single timing is not a measurement.
- `warm` is explicit. The archive's third arm (159.27 s cold vs 120.72 s warm, same configuration) is why.
- `baseline_mean` travels **with** the row, so a delta cannot be computed against a baseline from a different session or a different build.
- A row whose `provenance.attention_backend` is `unknown` is recorded and **excluded from any delta** — the harness must be able to say "this ran but I cannot tell you on what".

- [ ] Steps: failing test → implement → register the command (four ratchets) → prove a row with `unknown` provenance is excluded from deltas → commit.

---

## Task 4: The harness

**Files:**
- Create: `scripts/dev/measure_optimizations.py`
- Test: `tests/test_measure_optimizations.py` (new — the row-building and arm-sequencing logic, not a live render)

**Read first:** `t4-research.md` §"Recommended matrix" and §"Baseline vs opt-in" and §"Discipline".

**The measurement rules, which are the substance of this task:**
1. **Vary the seed every run.** ComfyUI's node cache returns a cached result for an identical prompt, and the recorded trap is a "12.1 s / 23.62 GB" that was a cache hit. Changing only the output filename is not enough.
2. **Discard the first run of every configuration** and record it as `warm: false`. Then take **two** timed runs.
3. **Restart ComfyUI between arms**, and read the argv back from the restart reply to confirm the arm actually took.
4. **VRAM is not comparable under DynamicVRAM** — it expands to fill what is available, so a peak measures availability, not need. Report memory only for cells run at a fixed `--reserve-vram`, and say so in the row.
5. **Every row carries a quality guard**, not just seconds: frame-0 MAE for i2v, a black-frame detector for attention overflow (SageAttention's documented failure mode), and a visible-artefact check for the caching levers. A lever that is faster and wrong is not a win.
6. Run **through the worker**, not around it — the product path — so each row is also a real job with a sidecar.

**The initial lever set** (from `t4-research.md`, reachable on core 0.34.0 + torch 2.10/cu128): SDPA baseline, SageAttention (**note: the installed `sageattention` is 1.0.6, which is SA1 Triton kernels — the research says the SA2.2 wheel is the first real measurement, so the harness must record which is installed**), `--fast fp16_accumulation`, `--fast fp8_matrix_mult` on fp8 checkpoints, Comfy-Kitchen INT8 attention, EasyCache, VAE tiling, the fp16 cast, PrunaVAED for LTX, and DynamicVRAM off. **Cut, with the reason recorded in the generated document:** SA3 (needs torch 2.12/cu131), NVFP4 (needs cu130 and is slower on cu128), FlashAttention (no verified wheel for this stack), TeaCache and MagCache (both dead since the 2026-01-05 core change), GGUF, radial/sparse attention.

- [ ] Steps: failing tests for row-building and arm sequencing → implement → `--dry-run` proving the matrix and arm order without rendering → commit.

---

## Task 5: Run it, and publish what it says

**Files:**
- Create: `docs/design/60_t4_optimization_results.md` (generated)
- Modify: `docs/design/55_t7_ship_walkthrough.html` (T4 section)

- [ ] **Step 1: Run the matrix on this box.** It is long — hours — so run it in the background and check the ledger as rows land. Start with the family that renders fastest so a failure in the harness surfaces in minutes rather than at the end.
- [ ] **Step 2: Generate the document from the ledger** (`--write-doc`), including the cut list with its reasons and the measurement rules.
- [ ] **Step 3: Correct the published A/B.** `docs/design/55_t7_ship_walkthrough.html` currently quotes sage 120.72 s vs SDPA 124.01 s as a ~3% win. The archive holds a third arm at 159.27 s. **Say so.** Whatever the new measurement shows, the old claim's evidence was weaker than it looked and the record should carry that correction.
- [ ] **Step 4: Write the honest verdict.** A lever that measures no difference is a result, not a failure — record it as measured-and-flat rather than quietly dropping it. A lever that could not be run (missing checkpoint, OOM) is recorded as not-run with the reason.

---

## Task 6: The Runtime page shows it

**Files:** `qt_ui/ManagerPage.cpp`, `tests/cpp/test_optimization_panel.cpp` (new), `CMakeLists.txt`

One row per lever: **installed** (venv probe) · **active** (live argv) · **measured** (best delta from the ledger, or "not timed") · **verdict** (used / skipped / broke). Reads through the `optimization_results` command.

The panel's honesty rule: a lever that is installed but not active must not read as a benefit, and a lever with no measurement must say "not timed" rather than showing a blank that looks like zero.

- [ ] Steps: C++ test first (a fake ledger drives the rows) → implement → build → `ctest -C Debug` at 31/32 → commit.

---

## Self-Review

**Spec §3 coverage:** provenance block (1) · restart-with-argv (2) · `launch_env` reaching `Popen` (2) · results ledger (3) · harness with seed variation, warm discard, restart-between-arms, quality guards (4) · generated document + walkthrough correction (5) · Runtime panel (6).

**Deliberately not here:** installing the SageAttention 2.2 wheel. The research says it is the cheapest real win available, but swapping a package in the live ComfyUI venv is a change to the owner's render environment, not a code change, and it belongs to a decision the owner makes rather than a wave that assumes. The harness records which version is installed so the choice is informed.

**Carried in from W2, to be scheduled not forgotten:** `test_godfile_split` fails at `ImageGenerationPage.cpp` 3135 lines against a 3000 ceiling — pre-existing, and W2 moved it 25 lines further away. It is not W3's subject, but W3 must not move it further either.
