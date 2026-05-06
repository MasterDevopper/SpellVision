from pathlib import Path

path = Path("qt_ui/ImageGenerationPage.cpp")
text = path.read_text(encoding="utf-8")

def replace_function(text: str, signature: str, replacement: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"Could not find function signature: {signature}")

    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"Could not find opening brace for: {signature}")

    depth = 0
    end = None
    in_string = False
    in_char = False
    escaped = False

    for index in range(brace, len(text)):
        ch = text[index]

        if escaped:
            escaped = False
            continue

        if ch == "\\":
            escaped = True
            continue

        if ch == '"' and not in_char:
            in_string = not in_string
            continue

        if ch == "'" and not in_string:
            in_char = not in_char
            continue

        if in_string or in_char:
            continue

        if ch == "{":
            depth += 1
            continue

        if ch == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break

    if end is None:
        raise SystemExit(f"Could not find closing brace for: {signature}")

    return text[:start] + replacement.rstrip() + "\n" + text[end:]


replacement = r'''
void ImageGenerationPage::updatePreviewEmptyStateSizing()
{
    if (!previewLabel_)
        return;

    const bool hasRenderedPreview = !generatedPreviewPath_.trimmed().isEmpty() && QFileInfo::exists(generatedPreviewPath_.trimmed());
    const bool hasInputPreview = isImageInputMode() && inputImageEdit_ && !inputImageEdit_->text().trimmed().isEmpty();

    // Pass 28E:
    // Busy state must not collapse or reshape the preview canvas.
    // Visual empty-state styling can ignore busy, but geometry should be based on
    // whether there is a usable preview/input asset. This prevents the window from
    // breathing while progress/status messages arrive during generation.
    const bool visualEmptyState = !busy_ && !hasRenderedPreview && !hasInputPreview;
    const bool geometryNeedsEmptyCanvas = !hasRenderedPreview && !hasInputPreview;

    bool changed = false;

    if (imagePreviewController_)
    {
        const bool before = previewLabel_->property("emptyState").toBool();
        imagePreviewController_->setEmptyState(visualEmptyState);
        changed = changed || (before != visualEmptyState);
    }
    else if (previewLabel_->property("emptyState").toBool() != visualEmptyState)
    {
        previewLabel_->setProperty("emptyState", visualEmptyState);
        changed = true;
    }

    const AdaptiveLayoutMode mode = currentAdaptiveLayoutMode();
    const int desiredMinHeight = geometryNeedsEmptyCanvas
        ? (mode == AdaptiveLayoutMode::Compact ? 340 : 420)
        : 0;

    if (previewLabel_->minimumHeight() != desiredMinHeight)
    {
        previewLabel_->setMinimumHeight(desiredMinHeight);
        changed = true;
    }

    if (previewLabel_->maximumHeight() != QWIDGETSIZE_MAX)
    {
        previewLabel_->setMaximumHeight(QWIDGETSIZE_MAX);
        changed = true;
    }

    if (changed)
        repolishWidget(previewLabel_);
}
'''

text = replace_function(text, "void ImageGenerationPage::updatePreviewEmptyStateSizing()", replacement)

# Also make preview widgets ignore pixmap size hints so image dimensions cannot drive layout.
if "Pass 28E preview surface geometry lock" not in text:
    text = text.replace(
        '''    previewLabel_->setMinimumSize(0, 0);
    previewLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);''',
        '''    // Pass 28E preview surface geometry lock:
    // Generated image pixmap dimensions must not become the QLabel size hint that
    // resizes the splitter/window. The layout owns the canvas size; refreshPreview()
    // scales the pixmap into the existing canvas.
    previewLabel_->setMinimumSize(0, 0);
    previewLabel_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Ignored);''',
        1,
    )

path.write_text(text, encoding="utf-8")

print("Applied Pass 28E: preview geometry no longer breathes during busy/status updates.")
