from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="")


def patch_cmake() -> None:
    path = ROOT / "CMakeLists.txt"
    text = read(path)
    if "qt_ui/generation/VideoGenerationPolicy.cpp" in text:
        return

    insert = "    qt_ui/generation/VideoGenerationPolicy.cpp\n    qt_ui/generation/VideoGenerationPolicy.h\n"
    anchors = [
        "    qt_ui/generation/GenerationRequestBuilder.h\n",
        "    qt_ui/generation/GenerationRequestBuilder.cpp\n",
    ]
    for anchor in anchors:
        if anchor in text:
            text = text.replace(anchor, anchor + insert, 1)
            write(path, text)
            return

    raise RuntimeError("Could not find GenerationRequestBuilder anchor in CMakeLists.txt")


def patch_generation_request_builder() -> None:
    path = ROOT / "qt_ui" / "generation" / "GenerationRequestBuilder.cpp"
    text = read(path)

    if '#include "VideoGenerationPolicy.h"' not in text:
        text = text.replace(
            '#include "GenerationRequestBuilder.h"\n',
            '#include "GenerationRequestBuilder.h"\n#include "VideoGenerationPolicy.h"\n',
            1,
        )

    marker = '        payload.insert(QStringLiteral("enable_vae_tiling"), draft.enableVaeTiling);\n'
    if 'video_readiness_ok' not in text:
        injection = '''        const VideoGenerationPolicySnapshot videoPolicy = VideoGenerationPolicy::evaluate(draft);\n        QJsonArray videoWarnings;\n        for (const QString &warning : videoPolicy.warnings)\n            videoWarnings.append(warning);\n\n        payload.insert(QStringLiteral("video_request_kind"), videoPolicy.requestKind);\n        payload.insert(QStringLiteral("video_requires_input_image"), videoPolicy.requiresInputImage);\n        payload.insert(QStringLiteral("video_has_input_image"), videoPolicy.hasInputImage);\n        payload.insert(QStringLiteral("video_has_workflow_binding"), videoPolicy.hasWorkflowBinding);\n        payload.insert(QStringLiteral("video_has_native_stack"), videoPolicy.hasNativeVideoStack);\n        payload.insert(QStringLiteral("video_stack_ready"), videoPolicy.stackReady);\n        payload.insert(QStringLiteral("video_stack_kind"), videoPolicy.stackKind);\n        payload.insert(QStringLiteral("video_dimensions_valid"), videoPolicy.dimensionsValid);\n        payload.insert(QStringLiteral("video_frame_count_valid"), videoPolicy.frameCountValid);\n        payload.insert(QStringLiteral("video_fps_valid"), videoPolicy.fpsValid);\n        payload.insert(QStringLiteral("video_duration_label"), videoPolicy.durationLabel);\n        payload.insert(QStringLiteral("video_readiness_ok"), videoPolicy.ready);\n        payload.insert(QStringLiteral("video_diagnostic_summary"), videoPolicy.diagnosticSummary);\n        payload.insert(QStringLiteral("video_readiness_warnings"), videoWarnings);\n'''
        if marker not in text:
            raise RuntimeError("Could not find video payload insertion anchor in GenerationRequestBuilder.cpp")
        text = text.replace(marker, marker + injection, 1)

    write(path, text)


def main() -> None:
    patch_cmake()
    patch_generation_request_builder()
    print("Sprint 15A video generation policy pass 1 applied.")


if __name__ == "__main__":
    main()
