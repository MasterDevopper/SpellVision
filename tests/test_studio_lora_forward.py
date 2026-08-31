"""C3: studio loras[] must resolve to a worker lora path.

Studios send {path,name,weight,enabled}. The builder historically only
forwarded lora_summary → lora. This contract is the worker-side fail-closed
normalize so either shape works.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from request_payload import resolve_request_lora, studio_effective_mode


def test_plain_lora_string_still_wins():
    path, scale = resolve_request_lora({"lora": "house.safetensors", "lora_scale": 0.8})
    assert path == "house.safetensors"
    assert scale == 0.8


def test_studio_loras_array_path_and_weight():
    path, scale = resolve_request_lora(
        {
            "loras": [
                {"path": "D:/AI_ASSETS/models/loras/house.safetensors", "name": "house", "weight": 0.85, "enabled": True}
            ]
        }
    )
    assert path.endswith("house.safetensors")
    assert scale == 0.85


def test_disabled_and_empty_loras_are_ignored():
    path, scale = resolve_request_lora(
        {
            "loras": [
                {"path": "off.safetensors", "enabled": False, "weight": 1.0},
                {"path": "on.safetensors", "enabled": True, "weight": 0.4},
            ]
        }
    )
    assert path.endswith("on.safetensors")
    assert scale == 0.4


def test_no_lora_returns_none():
    path, scale = resolve_request_lora({"prompt": "x"})
    assert path is None
    assert scale == 1.0


def test_t2i_with_input_image_flips_to_i2i():
    assert studio_effective_mode("t2i", {"input_image": "C:/ref.png"}) == "i2i"


def test_explicit_i2i_stays_i2i():
    assert studio_effective_mode("i2i", {"input_image": "C:/ref.png"}) == "i2i"


def test_t2i_without_image_stays_t2i():
    assert studio_effective_mode("t2i", {"prompt": "hero"}) == "t2i"


def test_native_i2v_no_longer_falls_back_to_t2v():
    from pathlib import Path

    text = Path(__file__).resolve().parent.parent.joinpath("python", "native_runners.py").read_text(
        encoding="utf-8"
    )
    assert "falling back to t2v" not in text
    assert "refusing t2v fallback" in text


# --- C4 / C10 / C15 C++ source-scan contracts ---

_REPO = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return _REPO.joinpath(rel).read_text(encoding="utf-8")


def _cpp_function(src: str, signature: str) -> str:
    start = src.index(signature)
    nxt = src.find("\nvoid ", start + len(signature))
    nxt2 = src.find("\nQJsonObject ", start + len(signature))
    cuts = [c for c in (nxt, nxt2) if c != -1]
    end = min(cuts) if cuts else len(src)
    return src[start:end]


def test_c4_studio_preview_is_job_id_qhash_not_one_slot():
    header = _read("qt_ui/MainWindow.h")
    cpp = _read("qt_ui/MainWindow.cpp")
    assert "QHash<QString,PendingStudioPreview>" in header.replace(" ", "")
    assert "pendingStudioPreviews_" in header
    assert "studioMode" in header
    assert "comicPanelIndex" in header
    assert "pendingStudioMode_" not in header
    sync = _cpp_function(cpp, "void MainWindow::syncStudioPreviewsFromQueue()")
    assert "pendingStudioPreviews_" in sync
    assert "workerJobId" in sync
    assert "item.id" in sync
    assert "newestCompleted" not in sync
    submit = _cpp_function(cpp, "void MainWindow::submitStudioGenerationRequest")
    assert "pendingStudioPreviews_" in submit
    assert "queue_item_id" in submit or "queueId" in submit or "queueItemId" in submit


def test_c10_generate_all_panels_loops_and_emits_unique_index():
    cpp = _read("qt_ui/studios/ComicStudioPage.cpp")
    body = _cpp_function(cpp, "void ComicStudioPage::generateAllPanels()")
    assert "for (int i = 0; i < panels_.size(); ++i)" in body
    assert "emit generateRequested" in body
    assert "_comic_panel_index" in body
    assert "generateSelectedPanel();" not in body
    assert "re-run Generate all for the next incomplete panel" not in body
    # Early-return after the first queued panel was the C10 defect.
    queue_loop = body[body.rfind("for (int i = 0; i < panels_.size(); ++i)") :]
    assert "return;" not in queue_loop.split("}")[0] or "_comic_panel_index" in queue_loop
    assert "return;" not in queue_loop[queue_loop.find("{") : queue_loop.rfind("}")]


def test_c15_comic_sampler_uses_userdata_else_current_text():
    cpp = _read("qt_ui/studios/ComicStudioPage.cpp")
    payload = _cpp_function(cpp, "QJsonObject ComicStudioPage::buildPanelPayload")
    assert "currentData" in payload or "comboStoredValue" in payload or "UserRole" in payload
    assert "samplerHintCombo_->currentText()" not in payload
    # Keep the small allow-list — do not invent a 49-item menu.
    assert cpp.count("addItem(") >= 3 or "euler" in cpp
    assert "lms_ancestral" not in cpp
    assert "heunpp2" not in cpp


def test_c14_character_concept_uses_content_mode_not_hardcoded_sfw():
    cpp = _read("qt_ui/studios/CharacterStudioPage.cpp")
    header = _read("qt_ui/studios/CharacterStudioPage.h")
    payload = _cpp_function(cpp, "QJsonObject CharacterStudioPage::buildConceptPayload")
    assert "currentContentMode()" in payload
    assert "ConceptContentMode::Sfw" not in payload
    multi = _cpp_function(cpp, "void CharacterStudioPage::generateMultiViewPrompts")
    assert "currentContentMode()" in multi
    assert "contentModeCombo_" in header
    assert "currentContentMode" in header
