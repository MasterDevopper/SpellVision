# Dev Workflow — SpellVision

## Initial environment setup

### 1. Create the Python environment
Use the validated Python install for the project:

```powershell
& "C:\Program Files\Python312\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install runtime dependencies
SpellVision tracks the Python worker/runtime dependencies in `requirements.runtime.txt`.

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.runtime.txt
```

### 3. Confirm the environment
```powershell
python -V
python -c "import torch; print('torch=', torch.__version__, 'cuda=', torch.version.cuda, 'gpu=', torch.cuda.is_available())"
python -c "import diffusers, transformers, peft, PIL; print('diffusers=', diffusers.__version__, 'transformers=', transformers.__version__, 'peft=', peft.__version__)"
```

---

## Daily local workflow

### 1. Activate the project environment
```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Run backend sanity checks
Use this before debugging queue, worker, model, or LoRA issues.

```powershell
.\scripts\dev\run_backend_checks.ps1
```

This checks:
- Python environment
- syntax for `worker_service.py` and `worker_client.py`
- Torch / CUDA availability
- Diffusers / Transformers / PEFT imports
- queue backend responsiveness

### 3. Build and launch the UI
Use this for the normal local app workflow.

```powershell
.\scripts\dev\run_ui.ps1
```

This will:
- activate `.venv`
- run Python syntax checks
- configure Qt / CMake
- build the app
- launch `SpellVision.exe`

### 4. Rebuild without launching
Use this when you only want a compile check.

```powershell
.\scripts\dev\rebuild_ui.ps1
```

---

## Recommended workflow by change type

### Python worker changes
After editing:
- `python/worker_service.py`
- `python/worker_client.py`

Run:

```powershell
.\scripts\dev\run_backend_checks.ps1
```

If those pass, then run:

```powershell
.\scripts\dev\run_ui.ps1
```

### Qt UI changes
After editing:
- `qt_ui/MainWindow.cpp`
- `qt_ui/MainWindow.h`
- other Qt UI files

Run:

```powershell
.\scripts\dev\rebuild_ui.ps1
```

Then launch:

```powershell
.\build\Debug\SpellVision.exe
```

Or just use:

```powershell
.\scripts\dev\run_ui.ps1
```

### Queue / generation integration changes
When changing queue orchestration, job lifecycle, cancel/retry, or model loading behavior:

1. Run backend checks
2. Build and launch UI
3. Test:
   - enqueue multiple jobs
   - cancel active job
   - retry last generation
   - history refresh
   - telemetry visibility
   - output path uniqueness

### Dependency changes
When changing runtime dependencies:

1. Update `requirements.runtime.txt`
2. Reinstall in the active venv:

```powershell
python -m pip install -r requirements.runtime.txt
```

3. Re-run backend checks:

```powershell
.\scripts\dev\run_backend_checks.ps1
```

---

## Git workflow

### Check status
```powershell
git status
```

### Commit current work
```powershell
git add .
git commit -m "your message here"
git push
```

### Current branch strategy
- `sprint-7` = lifecycle/cancel/retry stable base
- `sprint-8-queue-orchestration` = queue work
- `sprint-8-5-optimization` = performance / optimization work

Keep new optimization work on the optimization branch unless you intentionally merge or cherry-pick.

---

## Common commands

### Queue status from PowerShell
```powershell
'{"command":"queue_status"}' | python .\python\worker_client.py
```

### Launch the built app directly
```powershell
.\build\Debug\SpellVision.exe
```

### Clean full rebuild
```powershell
if (Test-Path build) { Remove-Item -Recurse -Force build }
.\scripts\dev\run_ui.ps1
```

---

## Common troubleshooting

### Qt not found
Set the Qt environment before configure/build:

```powershell
$env:CMAKE_PREFIX_PATH = "C:\Qt\6.10.2\msvc2022_64"
$env:Qt6_DIR = "C:\Qt\6.10.2\msvc2022_64\lib\cmake\Qt6"
```

### App builds but UI does not open
Use the build scripts in `scripts/dev/` so deployment happens consistently. Do not rely on stale exes after failed builds.

### Python packages look missing in VS Code
Make sure VS Code is using:

```text
C:\Users\xXste\Code_Projects\SpellVision\.venv\Scripts\python.exe
```

### Queue or retry output naming looks wrong
Check recent worker changes around:
- queue item id suffixing
- retry suffixing
- original output path preservation

### Pip launcher looks broken after renaming a venv
Do not rename active virtual environments on Windows if you can avoid it. Recreate `.venv` directly and use:

```powershell
python -m pip install -r requirements.runtime.txt
```

instead of relying on an older `pip.exe` launcher.

---

## Good validation checklist before pushing

- backend checks pass
- UI builds successfully
- app opens
- one generation succeeds
- cancel works
- retry works
- queue status is healthy
- no output overwrite bug
- telemetry looks sane

---

## Repo housekeeping
Keep local-only artifacts out of Git:
- build outputs
- `.venv`
- model caches
- runtime logs
- local queue/output files

Use:
- `.gitignore`
- `.gitattributes`
- `scripts/dev/`
- `docs/`

to keep future sprints clean and repeatable.
