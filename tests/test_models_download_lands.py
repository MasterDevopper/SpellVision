"""W5 Task 5 -- a download from the Models page ends up IN the library.

W1 Task 10 built the post-download hook and tested it at the manager's own door: given a
``models_root``, the finished weight is moved under the right subdirectory and identified. What
nothing tested is the sentence that hook's docstring opens with -- *"None means the file stays
wherever the materializer put it"* -- against the app that calls it.

It stayed. No caller in ``qt_ui/`` ever sent ``models_root``, so every download the app started,
from the Models page's own button and from a Civitai or Hugging Face link dropped on the page,
succeeded into ``python/.cache/assets/...``: a directory the Models page does not scan. The
download bar filled, the log said "done", and the model was not in the library. A success message
over a file the user cannot find is the exact shape Doc 50 names, and it is invisible to a test
that starts at ``DownloadManager.start(models_root=...)``.

So the cases here start one layer out, at the worker command the UI actually sends, and the last
two hold the two UI call sites to sending it -- because the hook being correct was never the
problem.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import download_commands  # noqa: E402
from download_manager import COMPLETED, DownloadManager  # noqa: E402


class _Asset:
    def __init__(self, local_path: str, cache_hit: bool = False):
        self.local_path = local_path
        self.value = local_path
        self.metadata = {"cache_hit": cache_hit}


class _OfflineCivitai:
    """The site answering "I do not know this hash" -- a real miss, not a failed lookup.

    Which is the honest offline stand-in: a *failed* lookup deliberately leaves identity alone, so
    stubbing it that way would prove nothing about whether a sidecar gets written.
    """

    def __init__(self, *args, **kwargs):
        pass

    def by_hash(self, digest):  # noqa: D401 - protocol shape, not prose
        return None


@pytest.fixture
def lane(tmp_path, monkeypatch):
    """The real command handler over a real DownloadManager with a fake transfer."""
    source = tmp_path / "cache" / "assets" / "houseMix_v1.safetensors"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"not a real weight, but a real file")

    def materialize(reference, *, asset_type="model", progress_cb=None, cancel_cb=None, **kw):
        if progress_cb:
            progress_cb(1, 1)
        return _Asset(local_path=str(source))

    manager = DownloadManager(materializer=materialize)
    monkeypatch.setattr(download_commands, "_manager", lambda: manager)
    # No network, and no credential store either: a public by-hash read needs neither.
    monkeypatch.setattr("model_intelligence.refresh.CivitaiClient", _OfflineCivitai)
    monkeypatch.setattr("model_intelligence_commands.CivitaiClient", _OfflineCivitai, raising=False)
    return manager, source


def _settled(manager, download_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = manager.records[download_id]
        if record.state == COMPLETED:
            return record
        time.sleep(0.01)
    raise AssertionError(f"download never completed: {manager.records[download_id].state}")


def test_a_download_the_page_starts_lands_in_the_library_with_a_sidecar(tmp_path, lane, monkeypatch):
    manager, source = lane
    models_root = tmp_path / "AI_ASSETS" / "models"

    monkeypatch.setattr("model_intelligence.civitai_lookup.CivitaiClient", _OfflineCivitai)
    reply = download_commands.handle_start_download_command({
        "command": "start_download",
        "reference": "https://civitai.com/api/download/models/12345",
        "models_root": str(models_root),
    })
    assert reply["ok"] is True
    record = _settled(manager, reply["download_id"])

    placed = models_root / "checkpoints" / "houseMix_v1.safetensors"
    assert placed.exists(), "the weight is still in the asset cache, where the Models page cannot see it"
    assert not source.exists(), "a placed download should be moved, not duplicated"
    assert record.placed_path == str(placed)

    # And it is IDENTIFIED -- the sidecar is what the card reads its kind, name and picture from.
    # An unidentified weight still gets one: "the site does not know this hash" is an answer, and
    # only the sidecar's existence separates it from a file nobody has ever looked at.
    sidecar = placed.with_suffix("").with_suffix(".spellvision.json")
    if not sidecar.exists():
        sidecar = placed.parent / (placed.stem + ".spellvision.json")
    assert sidecar.exists(), "no sidecar beside the placed weight"
    document = json.loads(sidecar.read_text(encoding="utf-8"))
    identity = document.get("identity", {})
    assert identity.get("file_name") == "houseMix_v1.safetensors"
    # The hash IS the identity: it is what a later refresh looks the weight up by, and what the
    # overlay store keys a favourite on. A sidecar without one is a placeholder.
    assert identity.get("hashes", {}).get("sha256")


def test_without_a_models_root_the_weight_never_leaves_the_cache(tmp_path, lane):
    """The pre-W5 behaviour, pinned so nobody reads the hook's presence as the fix.

    This is not a bug in the lane -- it is the documented default, and it is precisely why the
    caller sending ``models_root`` is the whole of Task 5.
    """
    manager, source = lane
    reply = download_commands.handle_start_download_command({
        "command": "start_download",
        "reference": "https://civitai.com/api/download/models/12345",
    })
    record = _settled(manager, reply["download_id"])
    assert source.exists()
    assert record.placed_path is None
    assert record.local_path == str(source)


def test_a_download_needs_no_api_key(tmp_path, lane, monkeypatch):
    """Same requirement as the refresh, one lane over.

    ``_credentials`` reads the DPAPI store and a locked or empty one must not become a refusal --
    a public Civitai or Hugging Face file downloads anonymously. The store is made to raise here,
    which is what a locked one does.
    """
    manager, _source = lane

    def locked(*args, **kwargs):
        raise RuntimeError("credential store is locked")

    monkeypatch.setitem(sys.modules, "credential_store", type(sys)("credential_store"))
    sys.modules["credential_store"].get_credential = locked

    reply = download_commands.handle_start_download_command({
        "command": "start_download",
        "reference": "https://huggingface.co/org/repo/resolve/main/model.safetensors",
        "models_root": str(tmp_path / "models"),
    })
    assert reply["ok"] is True
    _settled(manager, reply["download_id"])


# --- the two call sites, held to sending it ------------------------------------------------
#
# Source properties rather than literals: each asks whether ONE function body contains the wire
# field it has to send. That is the thing that was missing -- the hook, the command and the manager
# were all correct and complete, and the request the app built simply did not carry the field.


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    # To the next closing brace in column 0: these are free functions / methods at file scope.
    end = source.index("\n}", start)
    return source[start:end]


def test_the_apps_download_request_names_the_library_it_should_land_in():
    source = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8", errors="replace")
    body = _function_body(source, "void MainWindow::beginModelDownload(")
    assert '"start_download"' in body
    assert '"models_root"' in body, (
        "beginModelDownload builds the only start_download request the app sends; without "
        "models_root every download finishes into the asset cache and never reaches the library"
    )


def test_a_civitai_or_hugging_face_link_dropped_on_the_page_uses_that_same_lane():
    """The owner's drag-and-drop requirement.

    A dropped URL must not grow a second download path -- one that would have to learn placement,
    identification and the variant dialog all over again. It goes through the page's existing
    download signal, which is the request the test above holds.
    """
    source = (ROOT / "qt_ui" / "ModelManagerPage.cpp").read_text(encoding="utf-8", errors="replace")
    body = _function_body(source, "void ModelManagerPage::handleDroppedReference(")
    assert re.search(r'startsWith\(QStringLiteral\("https://"\)', body)
    assert "emit downloadModelRequested(trimmed);" in body
