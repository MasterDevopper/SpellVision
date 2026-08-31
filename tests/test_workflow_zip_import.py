"""A workflow shared as a ZIP imports, and an archive without one says so.

Civitai "Workflows"-type models frequently ship an archive containing the graph plus a README and
sample images -- and ``_pick_workflow_file`` already ranks ``.zip`` second, so this arrives through
the ordinary import path. Before this, the archive reached ``json.loads`` and the user was told the
link "did not return a workflow JSON file", which is the opposite of what happened: the right file
came down inside a container we refused to open.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from workflow_scanner import (  # noqa: E402
    _looks_like_workflow_payload,
    _workflow_from_zip,
    load_workflow_source,
)

GRAPH = {
    "nodes": [
        {"id": 1, "type": "CheckpointLoaderSimple", "widgets_values": ["m.safetensors"]},
        {"id": 2, "type": "KSampler", "widgets_values": [0, "randomize", 20, 8.0, "euler", "normal", 1.0]},
    ],
    "links": [],
}

API_GRAPH = {"3": {"class_type": "KSampler", "inputs": {"seed": 1}}}


def write_zip(path: Path, members: dict[str, bytes | str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in members.items():
            archive.writestr(name, body if isinstance(body, bytes) else body)
    return path


# --- the happy path ------------------------------------------------------------------------


def test_a_zip_holding_one_workflow_imports(tmp_path):
    path = write_zip(tmp_path / "pack.zip", {
        "Krea2 Two Image Edit.json": json.dumps(GRAPH),
        "README.md": "# how to use",
        "preview.png": b"\x89PNG not really",
    })
    source, payload = load_workflow_source(str(path))
    assert source.source_kind == "zip_archive"
    assert source.display_name == "pack.zip"
    assert payload == GRAPH


def test_the_graph_is_chosen_by_content_not_by_being_the_first_json(tmp_path):
    """A node pack's manifest, a Civitai metadata blob and a config are all ``.json``.

    Picking the first one -- or the alphabetically first -- imports a broken profile that fails
    much later with no visible connection to the archive.
    """
    path = write_zip(tmp_path / "pack.zip", {
        "aaa_config.json": json.dumps({"theme": "dark", "autosave": True}),
        "bbb_metadata.json": json.dumps({"modelId": 12345, "name": "Lox's Utopic World"}),
        "zzz_the_actual_workflow.json": json.dumps(GRAPH),
    })
    _, payload = load_workflow_source(str(path))
    assert payload == GRAPH


def test_an_api_format_prompt_in_a_zip_is_also_a_workflow(tmp_path):
    path = write_zip(tmp_path / "api.zip", {"prompt.json": json.dumps(API_GRAPH)})
    _, payload = load_workflow_source(str(path))
    assert payload == API_GRAPH


def test_a_nested_path_inside_the_archive_is_found(tmp_path):
    path = write_zip(tmp_path / "n.zip", {"pack/workflows/graph.json": json.dumps(GRAPH)})
    _, payload = load_workflow_source(str(path))
    assert payload == GRAPH


# --- refusing beats guessing ---------------------------------------------------------------


def test_two_workflows_in_one_archive_is_a_choice_not_a_pick(tmp_path):
    """Same rule as the version chooser and ``AmbiguousDownload``: when the archive holds several
    graphs, importing one silently picks for the user. The message names them so the user can."""
    path = write_zip(tmp_path / "two.zip", {
        "txt2img.json": json.dumps(GRAPH),
        "img2img.json": json.dumps(API_GRAPH),
    })
    with pytest.raises(ValueError) as excinfo:
        load_workflow_source(str(path))
    message = str(excinfo.value)
    assert "2 workflows" in message
    assert "txt2img.json" in message and "img2img.json" in message


def test_an_archive_with_no_workflow_says_what_was_in_there_instead(tmp_path):
    path = write_zip(tmp_path / "none.zip", {
        "config.json": json.dumps({"a": 1}),
        "notes.txt": "hello",
    })
    with pytest.raises(ValueError) as excinfo:
        load_workflow_source(str(path))
    message = str(excinfo.value)
    assert "No ComfyUI workflow" in message
    assert "1 JSON file(s) inside were something else" in message


def test_an_empty_archive_is_a_clear_message_not_an_index_error(tmp_path):
    path = write_zip(tmp_path / "empty.zip", {})
    with pytest.raises(ValueError, match="No ComfyUI workflow"):
        load_workflow_source(str(path))


def test_a_file_that_is_not_a_zip_says_so(tmp_path):
    path = tmp_path / "fake.zip"
    path.write_bytes(b"this is not an archive")
    with pytest.raises(ValueError, match="not a readable ZIP"):
        load_workflow_source(str(path))


def test_malformed_json_inside_the_archive_does_not_abort_the_scan(tmp_path):
    """One corrupt member must not hide a good graph sitting next to it."""
    path = write_zip(tmp_path / "mixed.zip", {
        "broken.json": "{ not json at all",
        "good.json": json.dumps(GRAPH),
    })
    _, payload = load_workflow_source(str(path))
    assert payload == GRAPH


def test_an_absurd_member_count_is_refused_rather_than_scanned(tmp_path):
    path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for i in range(250):
            archive.writestr(f"f{i}.json", "{}")
    with pytest.raises(ValueError, match="refusing to scan"):
        load_workflow_source(str(path))


def test_nothing_is_extracted_to_disk(tmp_path):
    """Members are read in memory. An archive is attacker-influenceable input and zip-slip is a
    path-traversal WRITE; a reader that never writes has no path to traverse."""
    path = write_zip(tmp_path / "slip.zip", {"../../escaped.json": json.dumps(GRAPH)})
    before = {p for p in tmp_path.rglob("*")}
    _, payload = load_workflow_source(str(path))
    assert payload == GRAPH
    assert {p for p in tmp_path.rglob("*")} == before
    assert not (tmp_path.parent / "escaped.json").exists()


# --- one predicate, not two ------------------------------------------------------------------


def test_the_zip_predicate_agrees_with_the_url_importer(tmp_path):
    """``workflow_scanner`` cannot import ``workflow_url_import`` (layering), so it carries its own
    copy of ``looks_like_workflow``. Two copies of a predicate drift; this pins them together --
    the same class of bug as the checker/doer split that produced 112 phantom substitutes."""
    from workflow_url_import import looks_like_workflow

    cases = [
        GRAPH,
        API_GRAPH,
        {},
        {"theme": "dark"},
        {"modelId": 12345, "name": "x"},
        {"nodes": "not a list"},
        {"1": {"class_type": "A"}, "2": {"inputs": {}}},
        {"1": {"class_type": "A"}, "2": "not a dict"},
    ]
    for case in cases:
        assert _looks_like_workflow_payload(case) == looks_like_workflow(case), case


# --- the URL lane ------------------------------------------------------------------------------


def test_a_downloaded_zip_is_detected_by_magic_bytes_not_by_suffix(monkeypatch):
    """A Civitai download link is ``/api/download/models/<id>`` -- no extension -- and the archive
    often arrives as a generic octet-stream. Suffix and content-type both say nothing here."""
    import workflow_url_import as wui

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("graph.json", json.dumps(GRAPH))
    body = buffer.getvalue()

    monkeypatch.setattr(wui, "_download", lambda url, **kw: (body, "application/octet-stream"))
    monkeypatch.setattr(wui, "resolve_civitai_workflow_url", lambda url, **kw: (url, ""))

    fetched = wui.fetch_workflow_from_url("https://civitai.com/api/download/models/1234")
    assert fetched.payload == GRAPH
    assert fetched.via == "zip_archive"
    assert any("ZIP" in note for note in fetched.notes)


def test_a_zip_with_no_workflow_reports_the_archive_reason_through_the_url_lane(monkeypatch):
    """The archive's own explanation must survive, not be replaced by the generic
    "did not return a workflow JSON file" that this whole branch exists to stop."""
    import workflow_url_import as wui

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "nothing here")
    monkeypatch.setattr(wui, "_download", lambda url, **kw: (buffer.getvalue(), "application/zip"))
    monkeypatch.setattr(wui, "resolve_civitai_workflow_url", lambda url, **kw: (url, ""))

    with pytest.raises(wui.WorkflowFetchError, match="No ComfyUI workflow"):
        wui.fetch_workflow_from_url("https://civitai.com/api/download/models/1234")


def test_the_display_name_drops_a_zip_suffix():
    from workflow_url_import import _name_from_url

    assert _name_from_url("https://civitai.com/x/Krea2%20Edit.zip") == "Krea2 Edit"
