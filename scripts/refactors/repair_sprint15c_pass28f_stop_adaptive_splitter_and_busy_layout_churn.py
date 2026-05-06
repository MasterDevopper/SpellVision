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

    // Pass 28F:
    // Progress/status messages can arrive many times during one generation.
    // Updating the full readiness/intelligence/preview layout for message-only
    // changes causes the visible generation workspace to breathe. Keep the
    // latest message internally, but do not mutate layout unless the busy state
    // itself changes.
    if (busy && !stateChanged && messageChanged)
    {
        busyMessage_ = normalizedMessage;
        return;
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
        // Starting/progress updates should not destroy an existing preview. For video,
        // tearing down QMediaPlayer here causes the same completed/partial MP4 to reload
        // on every queue/status refresh. Leave generatedPreviewPath_ and the current
        // player source intact; refreshPreview() will show the busy text only when there
        // is no usable output to show.
        const bool hasCurrentPreviewVideo = mediaPreviewController_ && !mediaPreviewController_->currentVideoPath().trimmed().isEmpty();
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


update_adaptive_replacement = r'''
void ImageGenerationPage::updateAdaptiveLayout()
{
    const AdaptiveLayoutMode mode = currentAdaptiveLayoutMode();
    const bool adaptiveModeChanged = mode != lastAdaptiveLayoutMode_;
    adaptiveCompact_ = mode == AdaptiveLayoutMode::Compact;

    if (adaptiveModeChanged)
    {
        if (mode == AdaptiveLayoutMode::Compact)
            rightControlsVisible_ = false;
        else if (lastAdaptiveLayoutMode_ == AdaptiveLayoutMode::Compact)
            rightControlsVisible_ = true;

        lastAdaptiveLayoutMode_ = mode;
        QTimer::singleShot(0, this, [this]() {
            if (leftScrollArea_ && leftScrollArea_->verticalScrollBar())
                leftScrollArea_->verticalScrollBar()->setValue(0);
        });
    }

    if (leftScrollArea_)
    {
        if (mode == AdaptiveLayoutMode::Compact)
        {
            leftScrollArea_->setMinimumWidth(330);
            leftScrollArea_->setMaximumWidth(390);
        }
        else if (mode == AdaptiveLayoutMode::Medium)
        {
            leftScrollArea_->setMinimumWidth(360);
            leftScrollArea_->setMaximumWidth(420);
        }
        else
        {
            leftScrollArea_->setMinimumWidth(380);
            leftScrollArea_->setMaximumWidth(440);
        }
    }

    const bool showRightControls = (mode != AdaptiveLayoutMode::Compact) || rightControlsVisible_;
    setRightControlsVisible(showRightControls);

    if (rightScrollArea_)
    {
        if (mode == AdaptiveLayoutMode::Compact)
        {
            rightScrollArea_->setMinimumWidth(360);
            rightScrollArea_->setMaximumWidth(440);
        }
        else if (mode == AdaptiveLayoutMode::Medium)
        {
            rightScrollArea_->setMinimumWidth(390);
            rightScrollArea_->setMaximumWidth(470);
        }
        else
        {
            rightScrollArea_->setMinimumWidth(410);
            rightScrollArea_->setMaximumWidth(500);
        }
    }

    applyRightPanelReflow(mode);

    const int leftRailWidth = leftScrollArea_ ? leftScrollArea_->viewport()->width() : 0;
    const int leftRailHeight = leftScrollArea_ ? leftScrollArea_->viewport()->height() : height();
    const bool narrowLeftRail = (mode == AdaptiveLayoutMode::Compact) || leftRailWidth < 390;
    const bool wideLeftRail = (mode == AdaptiveLayoutMode::Wide) && leftRailWidth >= 410;
    const bool constrainedLeftHeight = leftRailHeight > 0 && leftRailHeight < 900;
    const bool veryConstrainedLeftHeight = leftRailHeight > 0 && leftRailHeight < 780;
    const bool shortGenerationRail = leftRailHeight > 0 && leftRailHeight < 960;
    Q_UNUSED(veryConstrainedLeftHeight);
    Q_UNUSED(shortGenerationRail);

    auto configureStackedGroup = [narrowLeftRail](QBoxLayout *layout) {
        if (!layout)
            return;
        layout->setDirection(QBoxLayout::TopToBottom);
        layout->setSpacing(narrowLeftRail ? 3 : 4);
    };
    auto configureAdaptivePair = [wideLeftRail, constrainedLeftHeight](QBoxLayout *layout) {
        if (!layout)
            return;
        const bool useTwoColumns = wideLeftRail && !constrainedLeftHeight;
        layout->setDirection(useTwoColumns ? QBoxLayout::LeftToRight : QBoxLayout::TopToBottom);
        layout->setSpacing(useTwoColumns ? 8 : 3);
    };

    configureStackedGroup(samplerSchedulerLayout_);
    configureAdaptivePair(sizeLayout_);
    configureAdaptivePair(stepsCfgLayout_);
    configureStackedGroup(seedBatchLayout_);

    if (QFrame *quickControlsCard = findChild<QFrame *>(QStringLiteral("QuickControlsCard")))
        quickControlsCard->setToolTip(QStringLiteral("High-frequency generation controls stay prioritized in the left inspector."));

    if (QFrame *outputQueueCard = findChild<QFrame *>(QStringLiteral("OutputQueueCard")))
    {
        const bool outputAutoCollapsed = true;
        const bool collapseOutput = outputAutoCollapsed && !outputQueueForceOpen_;
        outputQueueCard->setMinimumHeight(collapseOutput ? 58 : 0);
        outputQueueCard->setMaximumHeight(collapseOutput ? 58 : QWIDGETSIZE_MAX);
        outputQueueCard->setToolTip(collapseOutput
            ? QStringLiteral("Output / Queue is collapsed to protect prompt and canvas space. Click Open to expand.")
            : QStringLiteral("Output / Queue details."));
        if (outputQueueToggleButton_)
        {
            outputQueueToggleButton_->setVisible(true);
            outputQueueToggleButton_->setMinimumWidth(collapseOutput ? 72 : 74);
            outputQueueToggleButton_->setText(collapseOutput ? QStringLiteral("Open") : QStringLiteral("Close"));
            outputQueueToggleButton_->setToolTip(collapseOutput
                ? QStringLiteral("Expand output and queue details.")
                : QStringLiteral("Collapse output and queue details."));
        }
    }

    if (QFrame *advancedCard = findChild<QFrame *>(QStringLiteral("AdvancedControlsCard")))
    {
        const bool advancedAutoCollapsed = true;
        const bool collapseAdvanced = advancedAutoCollapsed && !advancedForceOpen_;
        advancedCard->setMinimumHeight(collapseAdvanced ? 58 : 0);
        advancedCard->setMaximumHeight(collapseAdvanced ? 58 : QWIDGETSIZE_MAX);
        advancedCard->setToolTip(collapseAdvanced
            ? QStringLiteral("Advanced controls are collapsed by default to keep the prompt rail usable.")
            : QStringLiteral("Advanced controls."));
        if (advancedToggleButton_)
        {
            advancedToggleButton_->setVisible(advancedCard->isVisible());
            advancedToggleButton_->setMinimumWidth(collapseAdvanced ? 72 : 74);
            advancedToggleButton_->setText(collapseAdvanced ? QStringLiteral("Open") : QStringLiteral("Close"));
            advancedToggleButton_->setToolTip(collapseAdvanced
                ? QStringLiteral("Expand advanced controls.")
                : QStringLiteral("Collapse advanced controls."));
        }
    }

    if (promptEdit_)
    {
        const bool shortRail = leftRailHeight > 0 && leftRailHeight < 820;
        const int promptMin = shortRail ? 112 : (mode == AdaptiveLayoutMode::Wide ? 148 : (isVideoMode() ? 118 : 140));
        promptEdit_->setMinimumHeight(promptMin);
        promptEdit_->setMaximumHeight(promptMin + 18);
    }
    if (negativePromptEdit_)
    {
        const bool shortRail = leftRailHeight > 0 && leftRailHeight < 760;
        const int negativeMin = shortRail ? 68 : (mode == AdaptiveLayoutMode::Wide ? 84 : 76);
        negativePromptEdit_->setMinimumHeight(negativeMin);
        negativePromptEdit_->setMaximumHeight(negativeMin + 16);
    }

    updatePreviewEmptyStateSizing();

    // Pass 28F:
    // Do not reset splitter sizes on every resizeEvent/layout pass. The previous
    // behavior reapplied hard splitter sizes continuously, which caused the
    // visible workspace to breathe while generation status updates were flowing.
    // Only seed splitter geometry on first use or when the adaptive mode changes.
    bool splitterNeedsInitialSizes = true;
    if (contentSplitter_)
    {
        const QList<int> sizes = contentSplitter_->sizes();
        int total = 0;
        for (int size : sizes)
            total += size;
        splitterNeedsInitialSizes = sizes.isEmpty() || total <= 0;
    }

    if (adaptiveModeChanged || splitterNeedsInitialSizes)
        applyAdaptiveSplitterSizes(mode);
}
'''

text = replace_function(text, "void ImageGenerationPage::updateAdaptiveLayout()", update_adaptive_replacement)

path.write_text(text, encoding="utf-8")

print("Applied Pass 28F: busy message-only updates and resizeEvent no longer reset layout/splitters.")
