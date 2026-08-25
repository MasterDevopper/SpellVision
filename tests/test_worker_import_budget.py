from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent.parent
PYTHON_DIR = ROOT / "python"


def test_worker_import_does_not_eagerly_load_generation_pipelines() -> None:
    heavyweight_modules = [
        "diffusers.pipelines.auto_pipeline",
        "diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion",
        "diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion_img2img",
        "diffusers.pipelines.stable_diffusion_xl.pipeline_stable_diffusion_xl",
        "diffusers.pipelines.stable_diffusion_xl.pipeline_stable_diffusion_xl_img2img",
        "diffusers.pipelines.stable_diffusion_3.pipeline_stable_diffusion_3",
        "diffusers.pipelines.flux.pipeline_flux",
        "diffusers.schedulers.scheduling_euler_discrete",
        "diffusers.schedulers.scheduling_dpmsolver_multistep",
    ]
    script = (
        "import json,sys; "
        f"sys.path.insert(0, {str(PYTHON_DIR)!r}); "
        "import worker_service; "
        f"print(json.dumps([name for name in {heavyweight_modules!r} if name in sys.modules]))"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert json.loads(completed.stdout.strip().splitlines()[-1]) == []


def test_scheduler_is_loaded_on_first_use() -> None:
    sys.path.insert(0, str(PYTHON_DIR))
    try:
        import worker_service
    finally:
        sys.path.pop(0)

    pipe = SimpleNamespace(scheduler=SimpleNamespace(config={}))
    result = worker_service.apply_sampler_and_scheduler(
        pipe,
        {"sampler": "euler", "scheduler": "karras"},
    )

    assert result == {
        "applied": True,
        "sampler": "euler",
        "scheduler": "karras",
        "scheduler_class": "EulerDiscreteScheduler",
    }
    assert type(pipe.scheduler).__name__ == "EulerDiscreteScheduler"


def test_scheduler_import_failure_keeps_existing_scheduler(monkeypatch) -> None:
    sys.path.insert(0, str(PYTHON_DIR))
    try:
        import worker_service
    finally:
        sys.path.pop(0)

    original_scheduler = SimpleNamespace(config={})
    pipe = SimpleNamespace(scheduler=original_scheduler)

    def broken_import(_module_name: str):
        raise RuntimeError("broken optional dependency")

    monkeypatch.setattr(worker_service.importlib, "import_module", broken_import)
    result = worker_service.apply_sampler_and_scheduler(
        pipe,
        {"sampler": "euler", "scheduler": "normal"},
    )

    assert result == {"applied": False, "sampler": "euler", "scheduler": "normal"}
    assert pipe.scheduler is original_scheduler
