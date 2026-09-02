"""The four feature small-fixes of the v1.0 lane, pinned at the source level.

Each one is a small piece of plumbing between two ends that already existed: the download captured
trigger words and the import dropped them; the download lane existed and the Models page could not
reach it; the render's sidecar held the recipe and Inspire forwarded only the prompt; the comic
caption reached the manifest and never the page. These assert the middle now exists, and that the
names on both ends still agree -- the failure mode for all four was a key that one side wrote and
the other never read.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tests"))


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


# --- (iii) Inspire forwards the recipe, and its names agree with both ends ------------------------

def _recipe_pairs() -> list[tuple[str, str]]:
    src = _read("qt_ui/InspirationPage.cpp")
    start = src.index("kRecipeKeys = {")
    block = src[start:src.index("};", start)]
    return re.findall(r'\{QStringLiteral\("([a-z_]+)"\), QStringLiteral\("([a-z_]+)"\)\}', block)


def test_inspire_send_to_carries_the_recipe_not_only_the_prompt() -> None:
    src = _read("qt_ui/InspirationPage.cpp")
    for fn in ("void InspirationPage::sendToT2I()", "void InspirationPage::sendToI2I()"):
        body = src[src.index(fn):src.index("\n}\n", src.index(fn))]
        assert "recipeDraft()" in body, f"{fn} still sends only the prompt"
    pairs = _recipe_pairs()
    forwarded = {dst for _src, dst in pairs}
    for needed in ("checkpoint", "sampler", "scheduler", "steps", "cfg", "seed", "width", "height"):
        assert needed in forwarded, f"the recipe does not carry {needed}"


def test_every_sidecar_key_inspire_reads_is_one_the_worker_writes() -> None:
    """The sidecar side of each pair must be a key build_metadata_payload emits, or Inspire reads
    a name nobody writes and silently forwards nothing."""
    meta_src = _read("python/worker_metadata.py")
    start = meta_src.index("def build_metadata_payload")
    body = meta_src[start:start + 12000]
    written = set(re.findall(r'^\s+"([a-z_0-9]+)":', body, re.MULTILINE))
    for sidecar_key, _draft_key in _recipe_pairs():
        assert sidecar_key in written, f"Inspire reads sidecar key {sidecar_key!r}, which the worker never writes"


def test_every_draft_key_inspire_writes_is_one_the_cockpit_reads() -> None:
    """And the other end: the draft side of each pair must be a key applyWorkflowDraft consults."""
    from cpp_source import find_definition

    _path, body = find_definition("applyWorkflowDraft", qualifier="ImageGenerationPage")
    read = set(re.findall(r'QStringLiteral\("([a-z_]+)"\)', body))
    for _sidecar_key, draft_key in _recipe_pairs():
        if draft_key == "strength":
            continue  # i2i-only; consulted by the I2I path, not by applyWorkflowDraft's literal set
        assert draft_key in read, f"Inspire writes draft key {draft_key!r}, which applyWorkflowDraft never reads"


def test_the_prompt_fields_stay_authoritative() -> None:
    """The user may have edited the prompt on the Inspire page. It overrides the sidecar's."""
    src = _read("qt_ui/InspirationPage.cpp")
    fn = src[src.index("void InspirationPage::sendToT2I()"):]
    fn = fn[:fn.index("\n}\n")]
    assert fn.index("recipeDraft()") < fn.index('QStringLiteral("prompt")'), "prompt must be inserted AFTER the recipe so it wins"


# --- (ii) the Models page reaches the download lane and can delete -------------------------------

def test_the_models_page_reaches_the_existing_download_lane() -> None:
    mw = _read("qt_ui/MainWindow.cpp")
    assert "ModelManagerPage::downloadModelRequested" in mw
    block = mw[mw.index("ModelManagerPage::downloadModelRequested"):]
    block = block[:block.index("});")]
    assert "startModelDownload(reference" in block, "the Models page must use the same lane as Flows, not a second one"


def test_delete_goes_through_the_worker_and_refreshes() -> None:
    mw = _read("qt_ui/MainWindow.cpp")
    block = mw[mw.index("ModelManagerPage::deleteModelRequested"):]
    block = block[:block.index("60000);")]
    assert 'QStringLiteral("delete_model")' in block
    assert "refreshInventory()" in block
    assert "showWorkerFailure(" in block, "a failed delete must use the shared failure dialog"


def test_delete_asks_first_and_defaults_to_cancel() -> None:
    src = _read("qt_ui/ModelManagerPage.cpp")
    fn = src[src.index("void ModelManagerPage::onDeleteModelClicked()"):]
    fn = fn[:fn.index("\n}\n")]
    assert "setDefaultButton(QMessageBox::Cancel)" in fn
    assert "QMessageBox::DestructiveRole" in fn
    assert fn.index("box.exec()") < fn.index("emit deleteModelRequested")


# --- (iv) the comic page is lettered -------------------------------------------------------------

def test_the_comic_export_draws_the_caption_and_a_balloon() -> None:
    src = _read("qt_ui/studios/ComicStudioPage.cpp")
    export = src[src.index("void ComicStudioPage::exportPage()"):]
    export = export[:export.index("\n}\n")]
    assert "drawPanelLettering(painter, rect, panels_[i].dialogue, panels_[i].caption)" in export
    helper = src[src.index("void ComicStudioPage::drawPanelLettering("):]
    helper = helper[:helper.index("\n}\n")]
    assert "caption" in helper and "dialogue" in helper
    assert "addRoundedRect" in helper, "dialogue is a balloon, not a rectangle"
    assert "tail" in helper.lower(), "a balloon has a tail into the art"
    # The old subtitle rectangle is gone.
    assert "QColor(255, 255, 255, 220)" not in export


# --- (i) the import writes the sidecar the page reads --------------------------------------------

def test_import_and_page_agree_on_the_sidecar_shape() -> None:
    py = _read("python/model_import.py")
    cpp = _read("qt_ui/assets/ModelSidecar.cpp")
    assert '"trainedWords"' in py and 'QStringLiteral("trainedWords")' in cpp
    assert '"civitai"' in py and 'QStringLiteral("civitai")' in cpp
    assert '.metadata.json' in py and 'QStringLiteral("metadata.json")' in cpp
