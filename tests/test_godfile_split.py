"""God-file size and home contracts. Lower the ceilings as slices land."""
import ast
import builtins
import symtable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "python" / "worker_service.py"
QUEUE = ROOT / "python" / "worker_queue.py"
TCP = ROOT / "python" / "worker_tcp.py"
IGP = ROOT / "qt_ui" / "ImageGenerationPage.cpp"
HELPERS_H = ROOT / "qt_ui" / "generation" / "CockpitWidgetKit.h"
IMAGE_GRAPHS = ROOT / "python" / "native_image_graphs.py"
VIDEO_GRAPHS = ROOT / "python" / "native_video_graphs.py"
GRAPH_HELPERS = ROOT / "python" / "comfy_graph_helpers.py"
LTX_JOBS = ROOT / "python" / "ltx_prompt_api_jobs.py"
RUNNERS = ROOT / "python" / "native_runners.py"
COMFY_CLIENT = ROOT / "python" / "comfy_prompt_client.py"
IMAGE_RUNNERS = ROOT / "python" / "image_runners.py"
WORKFLOW_CMDS = ROOT / "python" / "workflow_library_commands.py"
RUNTIME = ROOT / "python" / "worker_runtime.py"
METADATA = ROOT / "python" / "worker_metadata.py"
CMAKE = ROOT / "CMakeLists.txt"

# Ratcheted after workflow / runtime / metadata extracts.
WORKER_MAX = 2800
IGP_MAX = 3000


def _lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def test_worker_service_is_below_first_cut_ceiling():
    assert WORKER.is_file()
    n = _lines(WORKER)
    assert n <= WORKER_MAX, f"worker_service.py is {n} lines; first-cut ceiling is {WORKER_MAX}"


def test_native_graph_modules_exist_and_are_reexported():
    assert GRAPH_HELPERS.is_file()
    assert IMAGE_GRAPHS.is_file()
    assert VIDEO_GRAPHS.is_file()
    worker = WORKER.read_text(encoding="utf-8")
    assert "from comfy_graph_helpers import" in worker or "import comfy_graph_helpers" in worker
    assert "from native_image_graphs import" in worker
    assert "from native_video_graphs import" in worker
    images = IMAGE_GRAPHS.read_text(encoding="utf-8")
    videos = VIDEO_GRAPHS.read_text(encoding="utf-8")
    assert "def _build_krea2_image_prompt" in images
    assert "def _build_native_wan_dual_noise_video_prompt" in videos
    assert "def _build_krea2_image_prompt" not in worker
    assert "def _build_native_wan_dual_noise_video_prompt" not in worker


def test_worker_queue_and_tcp_extracted():
    assert QUEUE.is_file()
    assert TCP.is_file()
    worker = WORKER.read_text(encoding="utf-8")
    assert "from worker_queue import" in worker
    assert "from worker_tcp import" in worker
    assert "class QueueManager" not in worker
    assert "class WorkerTCPHandler" not in worker
    assert "class QueueManager" in QUEUE.read_text(encoding="utf-8")
    assert "class WorkerTCPHandler" in TCP.read_text(encoding="utf-8")
    assert "class EventEmitter" in TCP.read_text(encoding="utf-8")
    assert "class EventEmitter" not in WORKER.read_text(encoding="utf-8")


def test_native_runners_and_ltx_jobs_extracted():
    assert LTX_JOBS.is_file()
    assert RUNNERS.is_file()
    worker = WORKER.read_text(encoding="utf-8")
    assert "from ltx_prompt_api_jobs import" in worker
    assert "from native_runners import" in worker
    assert "def run_native_image" not in worker
    assert "def run_native_video" not in worker
    assert "def _ltx_prompt_api_job_payload" not in worker
    assert "def run_native_image" in RUNNERS.read_text(encoding="utf-8")
    assert "def _ltx_prompt_api_job_payload" in LTX_JOBS.read_text(encoding="utf-8")


def test_comfy_prompt_client_extracted():
    assert COMFY_CLIENT.is_file()
    worker = WORKER.read_text(encoding="utf-8")
    assert "from comfy_prompt_client import" in worker
    assert "def run_comfy_workflow" not in worker
    assert "def _poll_comfy_history" not in worker
    assert "def _submit_comfy_prompt" not in worker
    client = COMFY_CLIENT.read_text(encoding="utf-8")
    assert "def run_comfy_workflow" in client
    assert "def _poll_comfy_history" in client


def test_image_runners_extracted():
    assert IMAGE_RUNNERS.is_file()
    worker = WORKER.read_text(encoding="utf-8")
    assert "from image_runners import" in worker
    assert "def run_t2i" not in worker
    assert "def run_i2i" not in worker
    assert "def maybe_load_lora" not in worker
    runners = IMAGE_RUNNERS.read_text(encoding="utf-8")
    assert "def run_t2i" in runners
    assert "def run_i2i" in runners
    assert "def maybe_load_lora" in runners


def test_workflow_runtime_metadata_extracted():
    assert WORKFLOW_CMDS.is_file()
    assert RUNTIME.is_file()
    assert METADATA.is_file()
    worker = WORKER.read_text(encoding="utf-8")
    assert "from workflow_library_commands import" in worker
    assert "from worker_runtime import" in worker
    assert "from worker_metadata import" in worker
    assert "def handle_import_workflow_command" not in worker
    assert "def handle_discover_comfy_workflows_command" not in worker
    assert "def build_pipelines" not in worker
    assert "def get_or_load_pipelines" not in worker
    assert "def unload_cached_pipelines" not in worker
    assert "def prepare_runtime_for_request" not in worker
    assert "def build_history_entry" not in worker
    assert "def build_metadata_payload" not in worker
    assert "def save_metadata" not in worker
    assert "def output_finalization_contract" not in worker
    assert "VIDEO_LOW_MODEL_KEYS =" not in worker
    assert "class NativeFamilyPlugin" not in worker
    assert "NATIVE_IMAGE_FAMILIES =" not in worker
    assert "def handle_import_workflow_command" in WORKFLOW_CMDS.read_text(encoding="utf-8")
    assert "def unload_cached_pipelines" in RUNTIME.read_text(encoding="utf-8")
    assert "def build_history_entry" in METADATA.read_text(encoding="utf-8")


def test_extracted_worker_modules_have_no_unbound_runtime_globals():
    """A split module can import cleanly yet fail only when a moved function runs."""
    modules = (QUEUE, TCP, IMAGE_RUNNERS, RUNNERS, COMFY_CLIENT, RUNTIME, METADATA, WORKFLOW_CMDS, LTX_JOBS)
    allowed = {
        # These two names are intentionally guarded by ``'<name>' in locals()``
        # before evaluation in the image finalization compatibility branch.
        IMAGE_RUNNERS.name: {"metadata_output", "output_path"},
        # Python injects __file__ into imported modules.
        METADATA.name: {"__file__"},
        WORKFLOW_CMDS.name: {"__file__"},
    }

    for path in modules:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        module_defs: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                module_defs.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                module_defs.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                module_defs.update(target.id for target in targets if isinstance(target, ast.Name))

        missing: set[str] = set()

        def visit(table: symtable.SymbolTable) -> None:
            for symbol in table.get_symbols():
                name = symbol.get_name()
                if (
                    symbol.is_referenced()
                    and symbol.is_global()
                    and name not in module_defs
                    and name not in dir(builtins)
                ):
                    missing.add(name)
            for child in table.get_children():
                visit(child)

        visit(symtable.symtable(text, str(path), "exec"))
        assert missing <= allowed.get(path.name, set()), (
            f"{path.name} references unbound runtime globals: "
            f"{sorted(missing - allowed.get(path.name, set()))}"
        )


def test_image_generation_page_is_below_first_cut_ceiling():
    assert IGP.is_file()
    n = _lines(IGP)
    assert n <= IGP_MAX, f"ImageGenerationPage.cpp is {n} lines; first-cut ceiling is {IGP_MAX}"


def test_igp_split_units_registered():
    cmake = CMAKE.read_text(encoding="utf-8").replace("\\", "/")
    for name in (
        "qt_ui/generation/CockpitWidgetKit.cpp",
        "qt_ui/ImageGenerationPage_preview.cpp",
        "qt_ui/ImageGenerationPage_video.cpp",
        "qt_ui/ImageGenerationPage_catalog.cpp",
    ):
        assert name in cmake, f"missing CMake source {name}"
    assert HELPERS_H.is_file()
    header = HELPERS_H.read_text(encoding="utf-8")
    assert "configureComboBox" in header
