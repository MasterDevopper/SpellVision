from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "qt_ui" / "ImageGenerationPage.cpp"
CMAKE = ROOT / "CMakeLists.txt"

INCLUDE_LINE = '#include "generation/VideoReadinessPresenter.h"'
VIDEO_BLOCK = '''
    if (isVideoMode())
    {
        const QJsonObject videoPayload = buildRequestPayload();
        const QString videoBlockReason = spellvision::generation::VideoReadinessPresenter::blockingMessage(videoPayload);
        if (!videoBlockReason.isEmpty())
            return videoBlockReason;
    }
'''


def find_matching_brace(text: str, open_index: int) -> int:
    depth = 0
    in_string = False
    in_char = False
    escape = False
    in_line_comment = False
    in_block_comment = False

    for i in range(open_index, len(text)):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
            continue

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if in_char:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "'":
                in_char = False
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "'":
            in_char = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i

    raise RuntimeError("Could not find matching brace")


def patch_cmake() -> None:
    text = CMAKE.read_text(encoding="utf-8")
    if "qt_ui/generation/VideoReadinessPresenter.cpp" in text:
        return

    insert = "    qt_ui/generation/VideoReadinessPresenter.cpp\n    qt_ui/generation/VideoReadinessPresenter.h"
    anchors = [
        "    qt_ui/generation/VideoGenerationPolicy.h",
        "    qt_ui/generation/GenerationRequestBuilder.h",
        "    qt_ui/generation/GenerationRequestBuilder.cpp",
    ]

    for anchor in anchors:
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + insert, 1)
            CMAKE.write_text(text, encoding="utf-8", newline="")
            return

    raise RuntimeError("Could not find a CMake generation anchor for VideoReadinessPresenter")


def patch_image_generation_page() -> None:
    text = MAIN.read_text(encoding="utf-8")

    if INCLUDE_LINE not in text:
        anchor = '#include "generation/VideoGenerationPolicy.h"'
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + INCLUDE_LINE, 1)
        else:
            anchor = '#include "generation/GenerationRequestBuilder.h"'
            text = text.replace(anchor, anchor + "\n" + INCLUDE_LINE, 1)

    if "VideoReadinessPresenter::blockingMessage" in text:
        MAIN.write_text(text, encoding="utf-8", newline="")
        return

    signature = "QString ImageGenerationPage::readinessBlockReason() const"
    start = text.find(signature)
    if start < 0:
        raise RuntimeError("Could not find ImageGenerationPage::readinessBlockReason()")

    open_index = text.find("{", start)
    if open_index < 0:
        raise RuntimeError("Could not find readinessBlockReason opening brace")
    close_index = find_matching_brace(text, open_index)

    body = text[open_index + 1:close_index]
    final_return = body.rfind("return QString();")

    if final_return >= 0:
        body = body[:final_return] + VIDEO_BLOCK + "\n    " + body[final_return:]
    else:
        body = body.rstrip() + "\n" + VIDEO_BLOCK + "\n"

    text = text[:open_index + 1] + body + text[close_index:]
    MAIN.write_text(text, encoding="utf-8", newline="")


def main() -> None:
    patch_cmake()
    patch_image_generation_page()
    print("Sprint 15A Pass 2 video readiness UI diagnostics patch applied.")


if __name__ == "__main__":
    main()
