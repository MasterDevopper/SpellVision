"""Workflow import contract tests — source-identity persistence (dedupe key).

Step 1 of the "auto-discover ComfyUI workflows" feature embeds a stable dedupe
key in every imported ``profile.json``:

  * ``discovery_source_path``   — the normalized absolute path of the ORIGINAL
                                  source graph (not the copied workflow.json)
  * ``discovery_source_sha256`` — sha256 of the original source file's bytes

Step 2's discovery command cross-references these two fields to decide whether a
ComfyUI graph under D:/AI_ASSETS has already been imported. These tests pin that
contract so later refactors of the importer cannot silently drop the key.

The worker is exercised as a black-box subprocess via the ``worker_client``
fixture, exactly as the C++ shell talks to it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


# A minimal ComfyUI *API-prompt* workflow (numeric node-id dict). This is the
# same shape as the real D:/AI_ASSETS ltx_api.json the discovery feature targets.
def _minimal_api_prompt_workflow(prompt_text: str = "a calm mountain lake") -> dict:
    return {
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "model.safetensors"},
            "_meta": {"title": "Load Checkpoint"},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt_text, "clip": ["4", 1]},
            "_meta": {"title": "Positive"},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "blurry", "clip": ["4", 1]},
            "_meta": {"title": "Negative"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 512, "batch_size": 1},
            "_meta": {"title": "Empty Latent"},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 1,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
            "_meta": {"title": "KSampler"},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "_meta": {"title": "VAE Decode"},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "SpellVision", "images": ["8", 0]},
            "_meta": {"title": "Save Image"},
        },
    }


def _sha256_bytes(data: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def _import_result(messages: list[dict]) -> dict:
    """Pull the import-result payload (the message carrying ``artifacts``) out
    of the worker stream, robust to any envelope wrapping."""
    for msg in messages:
        if isinstance(msg, dict) and isinstance(msg.get("artifacts"), dict):
            return msg
    raise AssertionError(
        "no workflow_import_result with artifacts in stream; types/keys seen: "
        + repr([(m.get("type"), sorted(m.keys())) for m in messages if isinstance(m, dict)])
    )


def _run_import(worker_client, *, source: Path, dest_root: Path, comfy_root: Path) -> dict:
    messages = worker_client(
        {
            "command": "import_workflow",
            "source": str(source),
            "destination_root": str(dest_root),
            # Hermetic + offline: build dependency PLANS against an empty comfy
            # root, but never apply them (no git clone / no model downloads).
            "comfy_root": str(comfy_root),
            "auto_apply_node_deps": False,
            "auto_apply_model_deps": False,
        },
        timeout=120.0,
    )
    return _import_result(messages)


@pytest.mark.contract
def test_import_persists_discovery_identity(worker_client, tmp_path):
    """profile.json must carry the original source path + sha256 (the dedupe key)."""
    raw = json.dumps(_minimal_api_prompt_workflow(), indent=2).encode("utf-8")
    source = tmp_path / "lake_t2i.json"
    source.write_bytes(raw)

    dest_root = tmp_path / "imported"
    comfy_root = tmp_path / "comfy_empty"
    comfy_root.mkdir()

    result = _run_import(worker_client, source=source, dest_root=dest_root, comfy_root=comfy_root)

    assert result.get("ok") is True, f"import not ok: {result!r}"

    profile_path = Path(result["artifacts"]["profile_path"])
    assert profile_path.is_file(), f"profile.json not written at {profile_path}"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    # The original source identity — NOT the copied workflow.json inside import_root.
    assert profile.get("discovery_source_path") == str(source.resolve()), (
        f"discovery_source_path mismatch.\n got: {profile.get('discovery_source_path')!r}\n"
        f"want: {str(source.resolve())!r}"
    )
    assert profile.get("discovery_source_sha256") == _sha256_bytes(raw), (
        "discovery_source_sha256 does not match the source bytes"
    )
    # Guard against regressing to the copied path being used as the dedupe path.
    assert Path(profile["discovery_source_path"]).name == "lake_t2i.json"
    assert profile.get("workflow_source", "").endswith("workflow.json")


@pytest.mark.contract
def test_reimport_same_bytes_keeps_stable_key(worker_client, tmp_path):
    """Re-importing identical bytes yields the identical dedupe key (idempotent)."""
    raw = json.dumps(_minimal_api_prompt_workflow(), indent=2).encode("utf-8")
    source = tmp_path / "stable.json"
    source.write_bytes(raw)

    dest_root = tmp_path / "imported"
    comfy_root = tmp_path / "comfy_empty"
    comfy_root.mkdir()

    first = _run_import(worker_client, source=source, dest_root=dest_root, comfy_root=comfy_root)
    second = _run_import(worker_client, source=source, dest_root=dest_root, comfy_root=comfy_root)

    p1 = json.loads(Path(first["artifacts"]["profile_path"]).read_text(encoding="utf-8"))
    p2 = json.loads(Path(second["artifacts"]["profile_path"]).read_text(encoding="utf-8"))

    assert p1["discovery_source_sha256"] == p2["discovery_source_sha256"] == _sha256_bytes(raw)
    assert p1["discovery_source_path"] == p2["discovery_source_path"] == str(source.resolve())
    # Same source name -> same slug -> overwrite in place, not a duplicate folder.
    assert first["import_slug"] == second["import_slug"]


@pytest.mark.contract
def test_discover_splits_imported_vs_new(worker_client, tmp_path):
    """discover_comfy_workflows reports imported files as already_imported and the rest as discovered.

    Hermetic: a temp workflows dir with two graphs; import one via import_workflow
    (Step 1 stamps its dedupe key), then discovery must cross-reference by hash.
    """
    workflows_dir = tmp_path / "comfy_workflows"
    workflows_dir.mkdir()
    raw_a = json.dumps(_minimal_api_prompt_workflow("alpha graph"), indent=2).encode("utf-8")
    raw_b = json.dumps(_minimal_api_prompt_workflow("beta graph"), indent=2).encode("utf-8")
    wf_a = workflows_dir / "alpha.json"
    wf_b = workflows_dir / "beta.json"
    wf_a.write_bytes(raw_a)
    wf_b.write_bytes(raw_b)

    dest_root = tmp_path / "imported"
    comfy_root = tmp_path / "comfy_empty"
    comfy_root.mkdir()

    # Import only alpha.json.
    _run_import(worker_client, source=wf_a, dest_root=dest_root, comfy_root=comfy_root)

    messages = worker_client(
        {
            "command": "discover_comfy_workflows",
            "workflows_dir": str(workflows_dir),
            "destination_root": str(dest_root),
        },
        timeout=60.0,
    )
    disco = next(m for m in messages if m.get("type") == "comfy_workflow_discovery")

    assert disco["ok"] is True
    assert disco["workflows_dir_exists"] is True
    assert disco["already_imported_count"] == 1
    assert disco["discovered_count"] == 1

    imported = disco["already_imported"][0]
    assert imported["filename"] == "alpha.json"
    assert imported["sha256"] == _sha256_bytes(raw_a)
    assert imported["already_imported"] is True
    assert imported["path_changed"] is False
    assert imported.get("import_slug")

    new = disco["discovered"][0]
    assert new["filename"] == "beta.json"
    assert new["sha256"] == _sha256_bytes(raw_b)
    assert new["already_imported"] is False


@pytest.mark.contract
def test_discover_flags_path_changed_on_move(worker_client, tmp_path):
    """If the same content is imported then re-appears at a new path, flag path_changed."""
    comfy_root = tmp_path / "comfy_empty"
    comfy_root.mkdir()
    dest_root = tmp_path / "imported"

    raw = json.dumps(_minimal_api_prompt_workflow("moved graph"), indent=2).encode("utf-8")

    # Import from the original location.
    original_dir = tmp_path / "orig"
    original_dir.mkdir()
    original = original_dir / "graph.json"
    original.write_bytes(raw)
    _run_import(worker_client, source=original, dest_root=dest_root, comfy_root=comfy_root)

    # The same bytes now live in a different workflows dir / path.
    moved_dir = tmp_path / "moved"
    moved_dir.mkdir()
    moved = moved_dir / "graph_renamed.json"
    moved.write_bytes(raw)

    messages = worker_client(
        {
            "command": "discover_comfy_workflows",
            "workflows_dir": str(moved_dir),
            "destination_root": str(dest_root),
        },
        timeout=60.0,
    )
    disco = next(m for m in messages if m.get("type") == "comfy_workflow_discovery")

    assert disco["already_imported_count"] == 1
    assert disco["discovered_count"] == 0
    entry = disco["already_imported"][0]
    assert entry["already_imported"] is True
    assert entry["path_changed"] is True
    assert entry["imported_source_path"] == str(original.resolve())


@pytest.mark.contract
def test_discover_missing_dir_is_empty_and_safe(worker_client, tmp_path):
    """A non-existent workflows dir returns empty lists, ok=True, and writes nothing."""
    missing = tmp_path / "does_not_exist"
    dest_root = tmp_path / "imported_missing"  # also non-existent on purpose

    messages = worker_client(
        {
            "command": "discover_comfy_workflows",
            "workflows_dir": str(missing),
            "destination_root": str(dest_root),
        },
        timeout=30.0,
    )
    disco = next(m for m in messages if m.get("type") == "comfy_workflow_discovery")

    assert disco["ok"] is True
    assert disco["workflows_dir_exists"] is False
    assert disco["discovered_count"] == 0
    assert disco["already_imported_count"] == 0
    # Pure read: discovery must not create the destination root.
    assert not dest_root.exists(), "discover_comfy_workflows must not create the profiles root"


@pytest.mark.contract
def test_edited_source_changes_hash(worker_client, tmp_path):
    """Editing the source changes the sha256 so discovery can detect drift."""
    source = tmp_path / "edited.json"
    dest_root = tmp_path / "imported"
    comfy_root = tmp_path / "comfy_empty"
    comfy_root.mkdir()

    raw_v1 = json.dumps(_minimal_api_prompt_workflow("version one"), indent=2).encode("utf-8")
    source.write_bytes(raw_v1)
    r1 = _run_import(worker_client, source=source, dest_root=dest_root, comfy_root=comfy_root)
    h1 = json.loads(Path(r1["artifacts"]["profile_path"]).read_text(encoding="utf-8"))["discovery_source_sha256"]

    raw_v2 = json.dumps(_minimal_api_prompt_workflow("version two — changed"), indent=2).encode("utf-8")
    source.write_bytes(raw_v2)
    r2 = _run_import(worker_client, source=source, dest_root=dest_root, comfy_root=comfy_root)
    h2 = json.loads(Path(r2["artifacts"]["profile_path"]).read_text(encoding="utf-8"))["discovery_source_sha256"]

    assert h1 == _sha256_bytes(raw_v1)
    assert h2 == _sha256_bytes(raw_v2)
    assert h1 != h2, "sha256 did not change after the source was edited"


def _readiness_result(messages: list[dict]) -> dict:
    res = next((m for m in messages if m.get("type") == "workflow_readiness_result"), None)
    assert res is not None, (
        "no workflow_readiness_result; types="
        + repr([m.get("type") for m in messages if isinstance(m, dict)])
    )
    return res


@pytest.mark.contract
@pytest.mark.needs_comfy  # reaches ComfyUI THROUGH the worker; the socket guard cannot see a subprocess
def test_check_readiness_rechecks_builtin_nodes(worker_client, tmp_path):
    """The cheap re-check rewrites the profile/scan_report and never flags builtin
    nodes as missing (the 'already installed / known' case)."""
    raw = json.dumps(_minimal_api_prompt_workflow(), indent=2).encode("utf-8")
    source = tmp_path / "builtin.json"
    source.write_bytes(raw)
    dest_root = tmp_path / "imported"
    comfy_root = tmp_path / "comfy_empty"
    comfy_root.mkdir()

    imp = _run_import(worker_client, source=source, dest_root=dest_root, comfy_root=comfy_root)
    import_root = imp["artifacts"]["import_root"]

    messages = worker_client(
        {"command": "check_workflow_launch_readiness", "import_root": import_root, "comfy_root": str(comfy_root)},
        timeout=120.0,
    )
    res = _readiness_result(messages)

    assert res["ok"] is True, res
    # Minimal workflow is builtin-only -> nothing flagged as a missing custom node.
    assert res["missing_node_classes"] == []
    assert res["node_counts"]["checked"] == 0
    # scan_report.json (the source the UI counts from) is rewritten to the re-checked set.
    sr = json.loads(Path(import_root, "scan_report.json").read_text(encoding="utf-8"))
    assert sr["missing_custom_nodes"] == []
    # profile carries a fresh last_launch_readiness block + cleared missing list.
    prof = json.loads(Path(import_root, "profile.json").read_text(encoding="utf-8"))
    assert prof["metadata"]["missing_custom_nodes"] == []
    assert "last_launch_readiness" in prof["metadata"]


@pytest.mark.contract
@pytest.mark.needs_comfy  # reaches ComfyUI THROUGH the worker; the socket guard cannot see a subprocess
def test_check_readiness_flags_unknown_custom_node(worker_client, tmp_path):
    """A genuinely-unknown custom node (absent from comfy_root) stays flagged after
    the live re-check; it is NOT silently dropped, and not 'already_installed'."""
    workflow = _minimal_api_prompt_workflow()
    workflow["999"] = {"class_type": "TotallyFakeCustomNodeXYZ", "inputs": {}, "_meta": {"title": "fake"}}
    raw = json.dumps(workflow, indent=2).encode("utf-8")
    source = tmp_path / "fake.json"
    source.write_bytes(raw)
    dest_root = tmp_path / "imported"
    comfy_root = tmp_path / "comfy_empty"
    comfy_root.mkdir()

    imp = _run_import(worker_client, source=source, dest_root=dest_root, comfy_root=comfy_root)
    import_root = imp["artifacts"]["import_root"]

    before = json.loads(Path(import_root, "scan_report.json").read_text(encoding="utf-8"))["missing_custom_nodes"]
    assert "TotallyFakeCustomNodeXYZ" in before  # static scan flagged it

    messages = worker_client(
        {"command": "check_workflow_launch_readiness", "import_root": import_root, "comfy_root": str(comfy_root)},
        timeout=120.0,
    )
    res = _readiness_result(messages)

    assert res["ok"] is True, res
    assert "TotallyFakeCustomNodeXYZ" in res["missing_node_classes"]
    assert res["node_counts"]["already_installed"] == 0


@pytest.mark.contract
def test_delete_workflow_profile_refuses_outside_root(worker_client, tmp_path):
    """The delete handler must refuse any path that is not a <slug> folder directly
    under the imported-workflows root (path-traversal / wrong-folder guard)."""
    victim = tmp_path / "not_a_profile"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep me", encoding="utf-8")

    messages = worker_client(
        {"command": "delete_workflow_profile", "import_root": str(victim)},
        timeout=30.0,
    )
    res = next(m for m in messages if m.get("type") == "workflow_delete_result")
    assert res["ok"] is False
    assert "Refusing to delete" in (res.get("error") or "")
    assert victim.exists(), "guard must not delete paths outside the imported-workflows root"


def test_model_resolver_honors_extra_model_paths(tmp_path):
    """build_model_install_plan must count a model as present when it is only
    reachable via comfy_root/extra_model_paths.yaml (including a subfolder), and
    still flag genuinely-absent models. Pure resolver unit test, no worker."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
    from workflow_scanner import scan_workflow
    from model_dependency_resolver import build_model_install_plan

    # comfy_root has an EMPTY models/checkpoints, but extra_model_paths maps
    # checkpoints to an external dir that holds the file in a subfolder.
    comfy_root = tmp_path / "comfy"
    (comfy_root / "models" / "checkpoints").mkdir(parents=True)
    external = tmp_path / "external_models"
    (external / "checkpoints" / "sub").mkdir(parents=True)
    (external / "checkpoints" / "sub" / "present_model.safetensors").write_bytes(b"x")
    (comfy_root / "extra_model_paths.yaml").write_text(
        f"mymap:\n  base_path: {external.as_posix()}\n  checkpoints: checkpoints\n",
        encoding="utf-8",
    )

    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "sub/present_model.safetensors"}, "_meta": {"title": "present"}},
        "2": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "totally_absent_model.safetensors"}, "_meta": {"title": "absent"}},
    }
    report = scan_workflow(workflow)
    plan = build_model_install_plan(report, comfy_root=str(comfy_root), auto_materialize=False)

    by_value = {d.source_value: d for d in plan.dependencies}
    # Reachable only via the yaml mapping (and in a subfolder) -> already_present.
    assert by_value["sub/present_model.safetensors"].install_action == "already_present"
    # Genuinely absent -> still flagged as a missing install action.
    assert by_value["totally_absent_model.safetensors"].install_action != "already_present"

    missing = [a["source_value"] for a in plan.install_actions]
    assert "totally_absent_model.safetensors" in missing
    assert "sub/present_model.safetensors" not in missing
