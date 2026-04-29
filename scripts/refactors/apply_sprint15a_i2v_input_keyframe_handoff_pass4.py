from __future__ import annotations

from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def fail(message: str) -> None:
    print(f"[sprint15a-pass4] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: Path) -> str:
    if not path.exists():
        fail(f"Missing file: {path}")
    return path.read_text(encoding="utf-8")


def write_if_changed(path: Path, text: str) -> bool:
    old = read(path)
    if old == text:
        return False
    path.write_text(text, encoding="utf-8", newline="")
    return True


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        fail(f"Could not find patch target for {label}")
    return text.replace(old, new, 1)


def function_bounds(text: str, function_name: str) -> tuple[int, int] | None:
    match = re.search(rf"^def\s+{re.escape(function_name)}\s*\(", text, flags=re.MULTILINE)
    if not match:
        return None
    start = match.start()
    next_match = re.search(r"^def\s+\w+\s*\(", text[match.end():], flags=re.MULTILINE)
    if not next_match:
        return start, len(text)
    return start, match.end() + next_match.start()


def patch_function(text: str, function_name: str, patcher) -> str:
    bounds = function_bounds(text, function_name)
    if bounds is None:
        return text
    start, end = bounds
    original = text[start:end]
    patched = patcher(original)
    return text[:start] + patched + text[end:]


GEN_REQUEST_I2V_BLOCK = '''        if (draft.isVideoMode)\n        {\n            payload.insert(QStringLiteral("video_input_image"), draft.inputImage);\n            payload.insert(QStringLiteral("input_keyframe"), draft.inputImage);\n            payload.insert(QStringLiteral("keyframe_image"), draft.inputImage);\n            payload.insert(QStringLiteral("source_image"), draft.inputImage);\n        }\n'''

GEN_REQUEST_I2V_BLOCK_PATCHED = '''        if (draft.isVideoMode)\n        {\n            payload.insert(QStringLiteral("video_input_image"), draft.inputImage);\n            payload.insert(QStringLiteral("input_keyframe"), draft.inputImage);\n            payload.insert(QStringLiteral("keyframe_image"), draft.inputImage);\n            payload.insert(QStringLiteral("source_image"), draft.inputImage);\n            payload.insert(QStringLiteral("i2v_source_image"), draft.inputImage);\n            payload.insert(QStringLiteral("video_has_input_image"), !draft.inputImage.trimmed().isEmpty());\n        }\n'''


def patch_generation_request_builder() -> bool:
    path = ROOT / "qt_ui" / "generation" / "GenerationRequestBuilder.cpp"
    text = read(path)
    original = text

    if 'payload.insert(QStringLiteral("i2v_source_image"), draft.inputImage);' not in text:
        if GEN_REQUEST_I2V_BLOCK in text:
            text = text.replace(GEN_REQUEST_I2V_BLOCK, GEN_REQUEST_I2V_BLOCK_PATCHED, 1)
        elif 'payload.insert(QStringLiteral("source_image"), draft.inputImage);' in text:
            text = text.replace(
                '            payload.insert(QStringLiteral("source_image"), draft.inputImage);\n',
                '            payload.insert(QStringLiteral("source_image"), draft.inputImage);\n'
                '            payload.insert(QStringLiteral("i2v_source_image"), draft.inputImage);\n'
                '            payload.insert(QStringLiteral("video_has_input_image"), !draft.inputImage.trimmed().isEmpty());\n',
                1,
            )
        else:
            fail("Could not find the I2V input alias block in GenerationRequestBuilder.cpp. Apply Pass 3 first.")

    return write_if_changed(path, text) or (text != original)


VIDEO_INPUT_NORMALIZER = '''\n\ndef normalize_video_input_fields(req: dict[str, Any]) -> dict[str, Any]:\n    if not isinstance(req, dict):\n        return req\n\n    def _first(*keys: str) -> str:\n        for key in keys:\n            value = str(req.get(key) or "").strip()\n            if value:\n                return value\n        return ""\n\n    command = str(\n        req.get("command")\n        or req.get("task_command")\n        or req.get("task_type")\n        or req.get("workflow_task_command")\n        or ""\n    ).strip().lower()\n    media_type = str(req.get("workflow_media_type") or req.get("media_type") or "").strip().lower()\n    stack_kind = str(req.get("native_video_stack_kind") or req.get("video_stack_kind") or "").strip().lower()\n    is_video_context = command in {"t2v", "i2v", "comfy_workflow"} or media_type == "video" or bool(stack_kind)\n\n    input_image = _first(\n        "video_input_image",\n        "input_keyframe",\n        "keyframe_image",\n        "source_image",\n        "i2v_source_image",\n        "input_image",\n    )\n\n    if input_image:\n        for key in ("input_image", "video_input_image", "input_keyframe", "keyframe_image", "source_image", "i2v_source_image"):\n            req[key] = input_image\n        req["video_has_input_image"] = True\n        req.setdefault("video_input_name", os.path.basename(input_image))\n        req.setdefault("video_request_kind", "i2v" if is_video_context else str(req.get("video_request_kind") or ""))\n    elif command == "i2v" or str(req.get("video_request_kind") or "").strip().lower() == "i2v":\n        req.setdefault("video_has_input_image", False)\n        req.setdefault("video_request_kind", "i2v")\n\n    return req\n'''


def patch_worker_service() -> bool:
    path = ROOT / "python" / "worker_service.py"
    text = read(path)
    original = text

    if "def video_completion_diagnostics(" not in text:
        fail("worker_service.py does not contain Pass 3 video diagnostics helpers. Apply Pass 3 before Pass 4.")

    if "def normalize_video_input_fields(req: dict[str, Any]) -> dict[str, Any]:" not in text:
        marker = "def clone_request_snapshot(req: dict[str, Any]) -> dict[str, Any]:\n"
        text = replace_once(text, marker, VIDEO_INPUT_NORMALIZER + "\n" + marker, "video input normalizer insertion")

    old_clone = "def clone_request_snapshot(req: dict[str, Any]) -> dict[str, Any]:\n    return copy.deepcopy(req)\n"
    new_clone = "def clone_request_snapshot(req: dict[str, Any]) -> dict[str, Any]:\n    return normalize_video_input_fields(copy.deepcopy(req))\n"
    if old_clone in text:
        text = text.replace(old_clone, new_clone, 1)
    elif new_clone not in text:
        fail("Could not patch clone_request_snapshot for video input normalization")

    queue_payload_anchor = '            "metadata_output": self.request_snapshot.get("metadata_output"),\n'
    queue_payload_insert = (
        '            "metadata_output": self.request_snapshot.get("metadata_output"),\n'
        '            "input_image": self.request_snapshot.get("input_image"),\n'
        '            "video_input_image": self.request_snapshot.get("video_input_image") or self.request_snapshot.get("input_keyframe") or self.request_snapshot.get("source_image"),\n'
        '            "video_input_name": self.request_snapshot.get("video_input_name") or os.path.basename(str(self.request_snapshot.get("video_input_image") or self.request_snapshot.get("input_keyframe") or self.request_snapshot.get("source_image") or self.request_snapshot.get("input_image") or "")),\n'
        '            "video_has_input_image": bool(self.request_snapshot.get("video_has_input_image", False)),\n'
        '            "video_request_kind": self.request_snapshot.get("video_request_kind"),\n'
        '            "video_stack_kind": self.request_snapshot.get("native_video_stack_kind") or self.request_snapshot.get("video_stack_kind"),\n'
        '            "video_duration_label": self.request_snapshot.get("video_duration_label"),\n'
    )
    if '"video_input_name": self.request_snapshot.get("video_input_name")' not in text:
        text = replace_once(text, queue_payload_anchor, queue_payload_insert, "queue payload video diagnostics")

    if '        req = normalize_video_input_fields(req)\n' not in text:
        text = text.replace(
            'def run_comfy_workflow(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:\n',
            'def run_comfy_workflow(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:\n    req = normalize_video_input_fields(req)\n',
            1,
        )

    def patch_video_completion(func_text: str) -> str:
        if 'video_input_name' in func_text and 'video_completion_summary' in func_text:
            return func_text
        func_text = func_text.replace(
            '    input_image = video_input_image_for_request(req)\n',
            '    input_image = video_input_image_for_request(req)\n    input_name = os.path.basename(input_image) if input_image else ""\n',
            1,
        )
        func_text = func_text.replace(
            '        "video_input_image": input_image,\n',
            '        "video_input_image": input_image,\n        "video_input_name": input_name,\n        "video_completion_summary": (f"Image-to-video complete from keyframe {input_name}" if request_kind == "i2v" and input_name else ("Text-to-video complete" if request_kind == "t2v" else "Video generation complete")),\n',
            1,
        )
        return func_text

    text = patch_function(text, 'video_completion_diagnostics', patch_video_completion)

    def patch_comfy_waiting(func_text: str) -> str:
        if 'keyframe {input_name}' in func_text or 'mode_text' in func_text:
            return func_text
        old = '        stack_text = f" • {stack_kind}" if stack_kind else ""\n        return f"waiting for ComfyUI video render ({int(elapsed_seconds)}s • {timing}{stack_text})"\n'
        new = '        stack_text = f" • {stack_kind}" if stack_kind else ""\n        input_image = video_input_image_for_request(req)\n        input_name = os.path.basename(input_image) if input_image else ""\n        source_text = f" • keyframe {input_name}" if input_name else ""\n        request_kind = str(req.get("video_request_kind") or _video_request_command(req) or "video").strip().lower()\n        mode_text = "image-to-video" if request_kind == "i2v" or input_name else "text-to-video"\n        return f"waiting for ComfyUI {mode_text} render ({int(elapsed_seconds)}s • {timing}{stack_text}{source_text})"\n'
        return func_text.replace(old, new, 1)

    text = patch_function(text, 'comfy_waiting_message', patch_comfy_waiting)

    if '    video_input_name: str | None = None\n' not in text:
        text = text.replace(
            '    video_input_image: str | None = None\n    video_prompt_id: str | None = None\n',
            '    video_input_image: str | None = None\n    video_input_name: str | None = None\n    video_completion_summary: str | None = None\n    video_prompt_id: str | None = None\n',
            1,
        )

    if '        video_input_name=payload.get("video_input_name"),\n' not in text:
        text = text.replace(
            '        video_input_image=payload.get("video_input_image"),\n        video_prompt_id=payload.get("video_prompt_id"),\n',
            '        video_input_image=payload.get("video_input_image"),\n        video_input_name=payload.get("video_input_name"),\n        video_completion_summary=payload.get("video_completion_summary"),\n        video_prompt_id=payload.get("video_prompt_id"),\n',
            1,
        )

    complete_anchor = '    update_job_progress(job, job.progress.total or job.progress.current or 1, job.progress.total or 1, "generation complete")\n'
    if complete_anchor in text:
        replacement = (
            '    completion_message = "generation complete"\n'
            '    request_kind = str(payload.get("video_request_kind") or "").strip().lower()\n'
            '    if request_kind == "i2v":\n'
            '        completion_message = str(payload.get("video_completion_summary") or "image-to-video complete")\n'
            '    elif request_kind == "t2v" or payload.get("video_backend_type"):\n'
            '        completion_message = str(payload.get("video_completion_summary") or "video generation complete")\n'
            '    update_job_progress(job, job.progress.total or job.progress.current or 1, job.progress.total or 1, completion_message)\n'
        )
        text = text.replace(complete_anchor, replacement, 1)

    return write_if_changed(path, text) or (text != original)


def patch_image_generation_page() -> bool:
    path = ROOT / "qt_ui" / "ImageGenerationPage.cpp"
    text = read(path)
    original = text

    old_has_input = '''bool ImageGenerationPage::hasRequiredGenerationInput() const\n{\n    if (!isImageInputMode())\n        return true;\n\n    return inputImageEdit_ && !inputImageEdit_->text().trimmed().isEmpty();\n}\n'''
    new_has_input = '''bool ImageGenerationPage::hasRequiredGenerationInput() const\n{\n    if (!isImageInputMode())\n        return true;\n\n    if (!inputImageEdit_)\n        return false;\n\n    const QString path = inputImageEdit_->text().trimmed();\n    if (path.isEmpty())\n        return false;\n\n    const QFileInfo info(path);\n    return info.exists() && info.isFile();\n}\n'''
    if old_has_input in text:
        text = text.replace(old_has_input, new_has_input, 1)

    if 'Selected keyframe file is missing. Re-select the source image.' not in text:
        readiness_old = '    if (!hasRequiredGenerationInput())\n        return isVideoMode()\n                   ? QStringLiteral("Add an input keyframe to generate.")\n                   : QStringLiteral("Add an input image to generate.");\n'
        readiness_new = '''    if (isImageInputMode() && inputImageEdit_)\n    {\n        const QString inputPath = inputImageEdit_->text().trimmed();\n        if (!inputPath.isEmpty())\n        {\n            const QFileInfo info(inputPath);\n            if (!info.exists() || !info.isFile())\n                return isVideoMode()\n                           ? QStringLiteral("Selected keyframe file is missing. Re-select the source image.")\n                           : QStringLiteral("Selected input image is missing. Re-select the source image.");\n        }\n    }\n\n    if (!hasRequiredGenerationInput())\n        return isVideoMode()\n                   ? QStringLiteral("Add a source keyframe image to run image-to-video.")\n                   : QStringLiteral("Add an input image to generate.");\n'''
        text = replace_once(text, readiness_old, readiness_new, 'I2V readiness message')

    old_preview_a = '            isImageInputMode()\n                ? QStringLiteral("No source image loaded yet.\\n\\nDrop or browse an input image from the left rail.")\n'
    new_preview_a = '            isImageInputMode()\n                ? (isVideoMode()\n                       ? QStringLiteral("No keyframe loaded yet.\\n\\nDrop or browse a source keyframe from the left rail.")\n                       : QStringLiteral("No source image loaded yet.\\n\\nDrop or browse an input image from the left rail."))\n'
    if old_preview_a in text:
        text = text.replace(old_preview_a, new_preview_a, 1)

    old_preview_b = '                     ? QStringLiteral("No source image loaded yet.\\n\\nDrop an image into the Input Image card or browse for one to begin.")\n'
    new_preview_b = '                     ? (isVideoMode()\n                            ? QStringLiteral("No keyframe loaded yet.\\n\\nDrop a keyframe into the Input Image card or browse for one to begin image-to-video.")\n                            : QStringLiteral("No source image loaded yet.\\n\\nDrop an image into the Input Image card or browse for one to begin."))\n'
    if old_preview_b in text:
        text = text.replace(old_preview_b, new_preview_b, 1)

    set_input_old = '                                 : QStringLiteral("Current source image:\\n%1").arg(path));\n'
    set_input_new = '                                 : QStringLiteral(isVideoMode() ? "Current keyframe:\\n%1" : "Current source image:\\n%1").arg(path));\n'
    if set_input_old in text:
        text = text.replace(set_input_old, set_input_new, 1)

    if 'html += row(QStringLiteral("Keyframe"), shortDisplayFromValue(inputImagePath));' not in text:
        html_anchor = '        html += row(QStringLiteral("Backend"), hasVideoWorkflowBinding() ? QStringLiteral("Imported workflow") : QStringLiteral("Native video model"));\n'
        html_insert = '''        html += row(QStringLiteral("Backend"), hasVideoWorkflowBinding() ? QStringLiteral("Imported workflow") : QStringLiteral("Native video model"));\n        const QString inputImagePath = inputImageEdit_ ? inputImageEdit_->text().trimmed() : QString();\n        if (!inputImagePath.isEmpty())\n            html += row(QStringLiteral("Keyframe"), shortDisplayFromValue(inputImagePath));\n'''
        if html_anchor in text:
            text = text.replace(html_anchor, html_insert, 1)

    if 'plain << QStringLiteral("Keyframe: %1").arg(inputImagePath);' not in text:
        plain_anchor = '        plain << QStringLiteral("Backend: %1").arg(hasVideoWorkflowBinding() ? QStringLiteral("Imported workflow") : QStringLiteral("Native video model"));\n'
        plain_insert = '''        plain << QStringLiteral("Backend: %1").arg(hasVideoWorkflowBinding() ? QStringLiteral("Imported workflow") : QStringLiteral("Native video model"));\n        const QString inputImagePath = inputImageEdit_ ? inputImageEdit_->text().trimmed() : QString();\n        if (!inputImagePath.isEmpty())\n            plain << QStringLiteral("Keyframe: %1").arg(inputImagePath);\n'''
        if plain_anchor in text:
            text = text.replace(plain_anchor, plain_insert, 1)

    return write_if_changed(path, text) or (text != original)


def main() -> None:
    changed: list[str] = []
    if patch_generation_request_builder():
        changed.append("qt_ui/generation/GenerationRequestBuilder.cpp")
    if patch_worker_service():
        changed.append("python/worker_service.py")
    if patch_image_generation_page():
        changed.append("qt_ui/ImageGenerationPage.cpp")

    if not changed:
        print("Sprint 15A Pass 4 already applied or no changes were needed.")
        return

    print("Sprint 15A Pass 4 applied:")
    for item in changed:
        print(f" - {item}")


if __name__ == "__main__":
    main()
