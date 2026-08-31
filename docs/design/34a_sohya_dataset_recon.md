# Sohya_kk × SpellVision DatasetGeneration — Integration Recon

**Repos:** `C:\Users\xXste\Code_Projects\Sohya_kk\Sohya_kk`  
**SpellVision:** `C:\Users\xXste\Code_Projects\SpellVision`  
**No code modified.**

---

## 0. Critical product mismatch (read first)

| Surface | What it actually is |
|--------|----------------------|
| **Sohya_kk** | Beginner **LoRA / DreamBooth / TI trainer** GUI over **kohya_ss**. Dataset tab = **ZIP extract + folder validate**, not image synthesis. |
| **SpellVision `DatasetGenerationPage`** | Orphan UI for **synthetic dataset gen** (prompts → many images). Emits `command: generate_dataset`. |
| **SpellVision worker** | **Already implements** `generate_dataset` → fans out N×`t2i` queue jobs. |

Owner A1 (`docs/design/33_billion_dollar_rebuild_analysis_and_plan.md` §11b): *“Dataset generator page fully wired — Integrate/adapt from Sohya_kk”* **does not match Sohya’s capabilities**. Phase-1 wire of the orphan page must use **SpellVision worker `generate_dataset`**, not Sohya subprocess. Sohya is only relevant for a future **Train / LoRA** surface.

---

## 1. What Sohya_kk is

| | |
|--|--|
| **Purpose** | Desktop trainer for SD 1.5 / SDXL / SD2 / Flux LoRA & related modes |
| **Stack** | Python 3.11+, **PySide6/Qt6**, kohya_ss (+ sd-scripts), optional CUDA torch 2.7.1+cu128 |
| **Root** | `C:\Users\xXste\Code_Projects\Sohya_kk\Sohya_kk` |
| **Entry** | `main.py` → `MainWindow` |
| **Backend** | `sohya_kk/backend/trainer.py` (~2.5k LOC): `TrainingWorker`, `DatasetPrepWorker`, model discovery, kohya bootstrap |
| **Config** | `sohya_kk/config/defaults.py` — ParamInfo lists + PRESETS |
| **UI tabs** | Home → Dataset → Training → Run → Output → Settings |
| **Packaging** | PyInstaller `Sohya_kk.spec` → `dist\Sohya_kk.exe` |
| **License** | Apache-2.0 (kohya_ss separate) |

Architecture:

```
main.py
  └─ MainWindow (sidebar + QStackedWidget)
       ├─ DatasetTab  → DatasetPrepWorker (ZIP) / inspect_dataset_folder
       ├─ TrainingTab → get_config() dict
       ├─ RunTab      → TrainingWorker (QThread)
       │                 └─ normalize → TOML → subprocess:
       │                      [python, train_network.py|sdxl_…|flux_…, --config_file=…]
       ├─ OutputTab
       └─ SettingsTab → kohya path, theme, model dirs
```

---

## 2. How users generate / prepare datasets in Sohya

**Users do not generate images from prompts in Sohya.** Workflow:

1. **Dataset tab** — drop ZIP or pick folder of `image + optional .txt` captions  
2. **Training tab** — presets / Easy Mode / full params  
3. **Run** — Start Training (live logs / loss)  
4. **Output** — `.safetensors` under output dir  

**Access modes**

| Mode | How | Notes |
|------|-----|--------|
| GUI source | `python main.py` | Primary |
| Standalone | `dist\Sohya_kk.exe` | Built binary present |
| Headless CLI | **None** | No argparse training entry |
| Public HTTP API | **None** | Qt signals only |
| Import API | Partial | `TrainingWorker` / `DatasetPrepWorker` need QObject/Qt |

---

## 3. Exact entry points / commands / args

### 3.1 Sohya app

```bat
cd C:\Users\xXste\Code_Projects\Sohya_kk\Sohya_kk
.\.venv\Scripts\python.exe main.py
```

Deps: `requirements.txt` = only `PySide6`, `pyinstaller`. Real train needs kohya + CUDA torch in that venv.

### 3.2 Training subprocess (what Sohya actually runs)

```text
{sys.executable} {kohya}/[sd-scripts/]{script} --config_file={temp.toml}
```

Scripts (`resolve_training_script_name`):

| Mode / family | Script |
|---------------|--------|
| LoRA default | `train_network.py` |
| SDXL LoRA | `sdxl_train_network.py` |
| Flux LoRA | `flux_train_network.py` |
| DreamBooth* | `train_db.py` / `sdxl_train.py` |
| TI | `train_textual_inversion.py` |

Key config keys from `TrainingTab.get_config()` + normalize:

- `dataset_path` / staged `train_data_dir`
- `pretrained_model_name_or_path`, `output_dir`, `model_name`
- `learning_rate`, `max_train_epochs`, `train_batch_size`, `resolution` → `"W,H"`
- LoRA: `network_dim`, `network_alpha`, `network_module` (+ lycoris args)
- memory: `mixed_precision`, `xformers`, `cache_latents`, `gradient_checkpointing`
- optional sample prompts file

Demo fallback if kohya missing: simulated epochs (no real weights).

### 3.3 Dataset prep worker

```python
DatasetPrepWorker(zip_path, output_dir).run()
# finished(success: bool, msg: str, out_path: str)
inspect_dataset_folder(path) -> image_count, caption_count, missing_captions, ...
```

### 3.4 SpellVision worker (the real dataset **generator**)

**Already wired in Python:**

- `QueueManager.enqueue_dataset` — `python/worker_service.py` ~2001–2059  
- TCP: `command == "generate_dataset"` → `handle_generate_dataset_command`  
- Client: `worker_client.CONTROL_COMMANDS` includes `generate_dataset`

**Request shape (page + worker):**

```json
{
  "command": "generate_dataset",
  "prompts": "line1\nline2",
  "output_root": "C:/path/dataset_out",
  "images_per_prompt": 5,
  "seed_start": 42,
  "width": 512,
  "height": 512,
  "shuffle_prompts": true,
  "save_metadata": true,
  "model": "<checkpoint path or id>",
  "negative_prompt": "",
  "steps": 20,
  "cfg_scale": 7.0
}
```

Worker accepts `prompts` as string (split lines) or list; also `prompt`, `dataset_root` alias, `seed`.

**Per-image fan-out:** enqueues `task_command: t2i` jobs with:

- `output` = `{output_root}/images/dataset_{p:03d}_{i:03d}.png`
- `metadata_output` = `{output_root}/metadata/{stem}.json`
- `seed` = `seed_start + n`

**Invoke from Python worker / shell:**

```bash
# one-shot via worker_client (same path UI uses)
C:/Users/xXste/Code_Projects/SpellVision/.venv/Scripts/python.exe \
  C:/Users/xXste/Code_Projects/SpellVision/python/worker_client.py \
  '{"command":"generate_dataset","prompts":"a cat\na dog","images_per_prompt":2,"seed_start":42,"output_root":"C:/Users/xXste/Code_Projects/SpellVision/output/dataset_smoke","width":512,"height":512,"model":"<required for real t2i>"}'
```

Worker must already be up on `127.0.0.1:8765`.

**Do not** `import sohya_kk` into SpellVision worker for gen.

---

## 4. I/O paths & formats

### Sohya_kk

| Path | Role |
|------|------|
| `C:\Users\xXste\Code_Projects\Sohya_kk\Sohya_kk\sohya_kk_outputs\` | Default train outputs (`.safetensors`) |
| `C:\Users\xXste\Code_Projects\Sohya_kk\Sohya_kk\kohya_ss\` | Bundled/cloned kohya |
| `C:\Users\xXste\.sohya_kk\` | `settings.json`, model library cache |
| `test_dataset\` | Smoke images + paired `.txt` |
| User dataset | Flat or kohya `N_name/` leaf; flat auto-staged to `num_repeats_modelname/` |
| Formats | Images: jpg/png/webp/bmp; captions: sidecars `.txt`; models: safetensors/ckpt/pt/bin |

### SpellVision `generate_dataset` outputs

```
{output_root}/
  images/dataset_001_001.png
  metadata/dataset_001_001.json
```

Default page text `./dataset_output` is relative/cwd-fragile — Phase-1 should default to  
`{SpellVision}/output/datasets/<stamp>/`.

---

## 5. Dependencies

### Sohya

- Python 3.11+, PySide6, NVIDIA GPU for real train  
- kohya_ss tree + deps (auto-bootstrap via git)  
- Project venv has accelerate/diffusers stack  
- Torch pin in trainer: 2.7.1 + cu128 index  

### SpellVision dataset gen

- Existing stack: Qt UI + `worker_service` + Comfy (`C:\sv_comfynext\ComfyUI`)  
- Worker venv: `C:\Users\xXste\Code_Projects\SpellVision\.venv`  
- Models: `D:/AI_ASSETS/models` (per project skill)  
- **No Sohya venv / GPU second process required for Phase-1 gen**

---

## 6. What SpellVision DatasetGenerationPage already has

| Item | Status |
|------|--------|
| `qt_ui/DatasetGenerationPage.cpp` | **Exists** (~7.8KB) |
| `DatasetGenerationPage.h` | **MISSING** (cpp includes it) |
| `CMakeLists.txt` | **Not listed** (not compiled) |
| Rail / `ShellNavigationController` | **No** `dataset` modeId |
| `MainWindow::buildPages` | **Not constructed / not stacked** |
| Signal `generateDatasetRequested` | Emitted; **no consumer** |
| Progress UI | **Fake** `QTimer` 0→50→100 |
| Model / sampler / negative | **Absent** (required for real t2i) |
| Worker `generate_dataset` | **Implemented** |
| `worker_client` action map | **Implemented** |
| Docs | Orphan / dead; A1 owner-approved to wire |

**Page payload fields today:**  
`command, prompts, output_root, images_per_prompt, seed_start, width, height, shuffle_prompts, save_metadata`  
Worker uses most of these; **ignores shuffle** unless UI shuffles before send; **does not require** save_metadata flag (always writes metadata paths). Extra t2i fields must be added on the request for real renders.

**Live rail (`ShellNavigationController::railButtonSpecs`):**  
home, chain*(hidden)*, t2i, i2i, t2v, i2v, character, concept, comic, workflows, history, inspiration*(hidden)*, models, settings.

---

## 7. Recommended integration mode

| Option | Verdict |
|--------|---------|
| **SpellVision TCP/JSON `generate_dataset` via `worker_client` / `sendWorkerRequest`** | **Phase-1 choice** — already implemented server-side |
| Import Sohya modules into worker | **No** — wrong product, Qt coupling, separate venv |
| Subprocess `Sohya_kk.exe` / `main.py` | **No** for generator; only later Train studio |
| New HTTP server around Sohya | **No** — no API exists; overbuild |
| Subprocess kohya `train_network.py` | Future **Train** feature only |

Mirror studios pattern: page builds JSON → MainWindow `sendWorkerRequest` → `python/worker_client.py` → worker NDJSON.

---

## 8. Minimal Phase-1 wire plan

### 8.1 Scope

Wire **synthetic dataset generation** end-to-end. **Do not** embed Sohya. Optionally later: “Open folder in trainer” / Train studio using Sohya as external tool.

### 8.2 Files / symbols

| Step | Where | Action |
|------|--------|--------|
| 1 | `qt_ui/DatasetGenerationPage.h` | **Create** (class, members, `generateDatasetRequested(QJsonObject)`) |
| 2 | `qt_ui/DatasetGenerationPage.cpp` | Fix include; kill fake timers; optional model line; absolute default output |
| 3 | `CMakeLists.txt` | Add `.h` + `.cpp` to SpellVision target |
| 4 | `ShellNavigationController.cpp` | Rail: `{ "dataset", "Data", "Dataset Generation", manage, "Ctrl+Shift+D" }`; `pageContextForMode` |
| 5 | `MainWindow.h/.cpp` | Member `datasetPage_`; `buildPages` construct + `pageStack_->addWidget` + `modePages_["dataset"]`; connect signal → submit |
| 6 | `MainWindow` submit helper | `sendWorkerRequest(payload)` with `command=generate_dataset`; resolve `output_root` under `resolveProjectRoot()/output/datasets/...`; inject default model from settings/last t2i if missing |
| 7 | Progress | Listen queue_ack + job_update / queue_snapshot (or poll queue_status); map completed/total → bar; drop QTimer lie |
| 8 | Payload completeness | Ensure width/height/model/negative/steps/cfg land on fan-out `base_request` (enqueue_dataset already clones leftover keys onto each t2i job) |

### 8.3 modeId / rail

```text
modeId: "dataset"
section: Manage (with Flows / History / Models)
label: "Data" / tooltip "Dataset Generation"
```

v1 gate: **not** in `kV1HiddenModes` if shipping A1 now; or hide behind `SPELLVISION_SHOW_ALL_MODES` until smoke-proven.

### 8.4 Worker command shape (final)

```json
{
  "command": "generate_dataset",
  "prompts": "…",
  "output_root": "C:/Users/xXste/Code_Projects/SpellVision/output/datasets/run_YYYYMMDD_HHMMSS",
  "images_per_prompt": 5,
  "seed_start": 42,
  "width": 512,
  "height": 512,
  "model": "D:/AI_ASSETS/models/…/xxx.safetensors"
}
```

Ack: `queue_ack` with `queued_count`, `queue_item_ids`, `dataset_root`, `images_dir`, `metadata_dir`.

### 8.5 Runtime paths

| Resource | Path |
|----------|------|
| Repo | `C:\Users\xXste\Code_Projects\SpellVision` |
| Worker | `.venv\Scripts\python.exe` + `python\worker_service.py` `:8765` |
| Client bridge | `python\worker_client.py` |
| Dataset out | `{repo}\output\datasets\<run_id>\` |
| Comfy | `C:\sv_comfynext\ComfyUI` |
| Models | `D:\AI_ASSETS\models` |

### 8.6 How Python worker invokes (no Sohya)

Already internal: `QUEUE_MANAGER.enqueue_dataset(req)` → repeated `enqueue(t2i)`. No new process. GPU/Comfy same as normal t2i.

### 8.7 Sohya role (Phase-2+, optional)

| Idea | Approach |
|------|----------|
| Train LoRA studio | External launch `Sohya_kk\main.py` or exe with dataset path env; **or** reimplement thin TOML+subprocess using kohya only |
| Reuse prep only | Copy `inspect_dataset_folder` / ZIP-slip logic (~100 LOC) — do not drag whole app |
| Headless train from SV | New thin CLI wrapping `_write_config_file` + `_build_command` patterns — **not present today** |

---

## 9. Risks / blockers

| Risk | Severity | Notes |
|------|----------|--------|
| **Sohya ≠ dataset generator** | High | Owner A1 wording misleading; integrating Sohya ships trainer UI, not orphan page intent |
| Missing `.h` + CMake | High | Page is non-buildable orphan |
| Fake progress | Med | Will claim complete without jobs |
| No model on payload | High | t2i jobs fail without checkpoint |
| Relative `./dataset_output` | Med | Wrong cwd under packaged exe |
| VRAM contention | Med | Dataset batch = many t2i; queue is correct pattern |
| Dual PySide apps | Med | If both open, two Qt event loops / GPU users |
| Sohya no headless CLI | High | Blocks clean Train integration without new code |
| kohya vs Comfy stacks | High | Separate venvs/torch; do not merge lightly |
| `shuffle_prompts` / `save_metadata` | Low | UI flags not fully honored by worker |
| Caption sidecars for LoRA | Med | Worker writes JSON metadata; kohya wants `.txt` next to images — add Phase-1.5 converter if Train handoff matters |
| Doc drift | Low | FEATURE_MATRIX / Doc 33 recon say orphan; worker already done |

---

## 10. Status summary

| Layer | Status |
|-------|--------|
| Sohya_kk app | **Implemented** trainer + dataset prep GUI |
| Sohya headless/API | **Absent** |
| SV worker `generate_dataset` | **Implemented** |
| SV orphan page | **Stub / unwired / incomplete artifact** |
| SV rail + MainWindow | **Not connected** |
| Phase-1 path | Wire page → existing worker; **ignore Sohya for gen** |
| Sohya value | Future Train / prep UX or code borrow only |

---

## 11. One-paragraph recommendation

**Phase-1:** Treat A1 as “wire SpellVision Dataset Generation,” not “embed Sohya.” Restore `DatasetGenerationPage` (header + CMake + rail `dataset` + MainWindow connect + real `sendWorkerRequest`), require model/output absolute paths, drive progress from queue acks. **Sohya_kk** remains a separate kohya trainer at `C:\Users\xXste\Code_Projects\Sohya_kk\Sohya_kk`; consider it only for a later Train surface or for copying dataset-folder inspection utilities—not as the synthetic dataset engine.