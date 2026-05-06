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


set_busy_replacement = r'''
void ImageGenerationPage::setBusy(bool busy, const QString &message)
{
    const QString normalizedMessage = message.trimmed();
    const bool stateChanged = busy_ != busy;
    const bool messageChanged = busyMessage_ != normalizedMessage;

    if (!stateChanged && !messageChanged)
        return;

    // Pass 28G:
    // Message-only busy updates must not touch geometry, preview refresh, styles,
    // splitter state, or side-panel content. Keep the new text internally and
    // return. Direct worker telemetry owns progress display elsewhere.
    if (busy && !stateChanged && messageChanged)
    {
        busyMessage_ = normalizedMessage;
        return;
    }

    auto lockHeightForBusy = [](QWidget *widget) {
        if (!widget)
            return;

        if (widget->property("svBusyHeightLocked").toBool())
            return;

        const int currentHeight = widget->height();
        if (currentHeight < 120)
            return;

        widget->setProperty("svBusyOldMinHeight", widget->minimumHeight());
        widget->setProperty("svBusyOldMaxHeight", widget->maximumHeight());
        widget->setMinimumHeight(currentHeight);
        widget->setMaximumHeight(currentHeight);
        widget->setProperty("svBusyHeightLocked", true);
    };

    auto unlockHeightForBusy = [](QWidget *widget) {
        if (!widget)
            return;

        if (!widget->property("svBusyHeightLocked").toBool())
            return;

        const QVariant oldMin = widget->property("svBusyOldMinHeight");
        const QVariant oldMax = widget->property("svBusyOldMaxHeight");

        widget->setMinimumHeight(oldMin.isValid() ? oldMin.toInt() : 0);
        widget->setMaximumHeight(oldMax.isValid() ? oldMax.toInt() : QWIDGETSIZE_MAX);

        widget->setProperty("svBusyHeightLocked", false);
        widget->setProperty("svBusyOldMinHeight", QVariant());
        widget->setProperty("svBusyOldMaxHeight", QVariant());
    };

    QWidget *canvasCard = findChild<QWidget *>(QStringLiteral("CanvasCard"));

    if (stateChanged && busy)
    {
        lockHeightForBusy(canvasCard);
        lockHeightForBusy(previewStack_);
    }
    else if (stateChanged && !busy)
    {
        unlockHeightForBusy(previewStack_);
        unlockHeightForBusy(canvasCard);
    }

    busy_ = busy;
    busyMessage_ = normalizedMessage;

    if (!busy_)
    {
        generateSubmitLocked_ = false;
        busyMessage_.clear();
    }

    if (busy_)
    {
        const bool hasCurrentPreviewVideo =
            mediaPreviewController_ && !mediaPreviewController_->currentVideoPath().trimmed().isEmpty();

        if (generatedPreviewPath_.trimmed().isEmpty() && !hasCurrentPreviewVideo)
        {
            if (imagePreviewController_)
                imagePreviewController_->clearCache(false);
        }
    }

    updatePrimaryActionAvailability();
    updatePreviewEmptyStateSizing();

    if (savePresetButton_)
        savePresetButton_->setEnabled(!busy_);
    if (clearButton_)
        clearButton_->setEnabled(!busy_);

    schedulePreviewRefresh(busy_ ? 120 : 30);
}
'''

text = replace_function(text, "void ImageGenerationPage::setBusy(bool busy, const QString &message)", set_busy_replacement)


# While busy, do not let resizeEvent-triggered adaptive layout passes continue mutating rails/cards.
guard_marker = '''    const bool adaptiveModeChanged = mode != lastAdaptiveLayoutMode_;
    adaptiveCompact_ = mode == AdaptiveLayoutMode::Compact;
'''

guard_replacement = '''    const bool adaptiveModeChanged = mode != lastAdaptiveLayoutMode_;
    adaptiveCompact_ = mode == AdaptiveLayoutMode::Compact;

    // Pass 28G:
    // If generation is active and the adaptive mode did not actually change,
    // do not re-run the full adaptive rail/card sizing pass. Repeated internal
    // resize events during progress updates were causing visible in-window
    // breathing even after the outer window stopped resizing.
    if (busy_ && !adaptiveModeChanged)
        return;
'''

if "If generation is active and the adaptive mode did not actually change" not in text:
    if guard_marker not in text:
        raise SystemExit("Could not find updateAdaptiveLayout adaptiveModeChanged marker.")
    text = text.replace(guard_marker, guard_replacement, 1)


# During busy state, resize events should not schedule preview refreshes. The terminal result path will refresh.
resize_old = '''void ImageGenerationPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updateAdaptiveLayout();
    schedulePreviewRefresh(60);
}'''

resize_new = '''void ImageGenerationPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updateAdaptiveLayout();

    // Pass 28G:
    // Resize-driven preview refresh during active generation can repeatedly
    // mutate the preview stack and cause in-window breathing. Worker terminal
    // messages and setPreviewImage() refresh the preview when a real output
    // arrives.
    if (!busy_)
        schedulePreviewRefresh(60);
}'''

if "Resize-driven preview refresh during active generation" not in text:
    if resize_old not in text:
        raise SystemExit("Could not find resizeEvent block.")
    text = text.replace(resize_old, resize_new, 1)


# If a result arrives while the busy lock is still active, unlock before binding the new output.
set_preview_sig = "void ImageGenerationPage::setPreviewImage(const QString &imagePath, const QString &caption)\n{\n"
if "Pass 28G result output unlocks busy canvas geometry" not in text:
    if set_preview_sig not in text:
        raise SystemExit("Could not find setPreviewImage start.")
    text = text.replace(
        set_preview_sig,
        set_preview_sig + '''    // Pass 28G result output unlocks busy canvas geometry before binding a new preview.
    auto unlockHeightForResult = [](QWidget *widget) {
        if (!widget || !widget->property("svBusyHeightLocked").toBool())
            return;

        const QVariant oldMin = widget->property("svBusyOldMinHeight");
        const QVariant oldMax = widget->property("svBusyOldMaxHeight");

        widget->setMinimumHeight(oldMin.isValid() ? oldMin.toInt() : 0);
        widget->setMaximumHeight(oldMax.isValid() ? oldMax.toInt() : QWIDGETSIZE_MAX);

        widget->setProperty("svBusyHeightLocked", false);
        widget->setProperty("svBusyOldMinHeight", QVariant());
        widget->setProperty("svBusyOldMaxHeight", QVariant());
    };

    unlockHeightForResult(previewStack_);
    unlockHeightForResult(findChild<QWidget *>(QStringLiteral("CanvasCard")));

''',
        1,
    )

path.write_text(text, encoding="utf-8")

print("Applied Pass 28G: active generation locks canvas geometry and suppresses resize-driven preview churn.")
