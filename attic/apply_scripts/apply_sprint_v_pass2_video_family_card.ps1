$patch = @'
"""
Sprint V Pass 2: build the VideoFamily card above promptCard.

Inserts a new card at the top of the left rail (visible only in video
modes) containing a single combo: Auto / LTX / WAN. Wires it to
updateVideoFamilyUi() and adds the resolution helpers. Also tightens
ltxLaunchOptionsPanel_->setVisible() so that LTX-only fields are hidden
when the resolved family is WAN.

This pass is purely additive. Existing field names, request payload
shape, and the videoStackModeCombo_ behavior are untouched.

Pass 3 will hide WAN-specific rows when the family resolves to LTX,
and make the Components panel family-aware.
"""
from pathlib import Path
path = Path("qt_ui/ImageGenerationPage.cpp")
text = path.read_text(encoding="utf-8")

# --- Insertion 1: build the videoFamilyCard above promptCard ---
#
# We insert AFTER the leftLayout creation and BEFORE the promptCard
# creation, so the card lands at position 0 in the left rail.

needle1 = '''    auto *leftContainer = new QWidget(leftScrollArea_);
    auto *leftLayout = new QVBoxLayout(leftContainer);
    leftLayout->setContentsMargins(0, 0, 4, 0);
    leftLayout->setSpacing(8);
    leftLayout->setSizeConstraint(QLayout::SetMinAndMaxSize);

    auto *promptCard = createCard(QStringLiteral("PromptCard"));'''

replacement1 = '''    auto *leftContainer = new QWidget(leftScrollArea_);
    auto *leftLayout = new QVBoxLayout(leftContainer);
    leftLayout->setContentsMargins(0, 0, 4, 0);
    leftLayout->setSpacing(8);
    leftLayout->setSizeConstraint(QLayout::SetMinAndMaxSize);

    // Sprint V Pass 2:
    // VideoFamily card. Top-of-left-rail so the family choice is the
    // first decision users see in T2V/I2V. Visible only in video modes.
    // The combo's currentData() is one of {"auto", "ltx", "wan"}; Auto
    // resolves via resolvedVideoFamily() which builds on the existing
    // suggestedVideoStackMode() (path hints + modelFamilyByValue_).
    videoFamilyCard_ = createCard(QStringLiteral("VideoFamilyCard"));
    {
        auto *familyLayout = new QVBoxLayout(videoFamilyCard_);
        familyLayout->setContentsMargins(12, 12, 12, 12);
        familyLayout->setSpacing(8);
        familyLayout->addWidget(createSectionTitle(QStringLiteral("Video Family"), videoFamilyCard_));

        videoFamilyCombo_ = new ClickOnlyComboBox(videoFamilyCard_);
        videoFamilyCombo_->setEditable(false);
        videoFamilyCombo_->addItem(QStringLiteral("Auto (resolve from checkpoint)"), QStringLiteral("auto"));
        videoFamilyCombo_->addItem(QStringLiteral("LTX"), QStringLiteral("ltx"));
        videoFamilyCombo_->addItem(QStringLiteral("WAN"), QStringLiteral("wan"));
        configureComboBox(videoFamilyCombo_);
        familyLayout->addWidget(videoFamilyCombo_);

        videoFamilyCard_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Maximum);
        videoFamilyCard_->setVisible(isVideoMode());
        leftLayout->addWidget(videoFamilyCard_);

        connect(videoFamilyCombo_, qOverload<int>(&QComboBox::currentIndexChanged), this, [this]() {
            updateVideoFamilyUi();
            // The stack-mode UI consults resolvedVideoFamily() to decide
            // whether to show WAN advanced rows, so refresh it too.
            updateVideoStackModeUi();
            scheduleUiRefresh(0);
        });
    }

    auto *promptCard = createCard(QStringLiteral("PromptCard"));'''

if needle1 not in text:
    raise SystemExit("Could not find leftContainer/promptCard creation point")
text = text.replace(needle1, replacement1, 1)

# --- Insertion 2: tighten ltxLaunchOptionsPanel_ visibility ---
#
# Today: ltxLaunchOptionsPanel_->setVisible(isVideoMode())
# After: only visible when family resolves to LTX.

needle2 = '''    ltxLaunchOptionsPanel_->setVisible(isVideoMode());
    quickControlsLayout->addWidget(ltxLaunchOptionsPanel_);'''

replacement2 = '''    // Sprint V Pass 2: LTX panel visible only when the resolved family is LTX.
    // updateVideoFamilyUi() will re-apply this on every family change.
    ltxLaunchOptionsPanel_->setVisible(isVideoMode() && resolvedVideoFamilyToken() == QStringLiteral("ltx"));
    quickControlsLayout->addWidget(ltxLaunchOptionsPanel_);'''

if needle2 not in text:
    raise SystemExit("Could not find ltxLaunchOptionsPanel_ visibility line")
text = text.replace(needle2, replacement2, 1)

# --- Insertion 3: resolution helpers + updateVideoFamilyUi at end of file ---
#
# Anchor before the closing of usesWanDualNoiseMode (end of that function),
# inserting the new helpers after it. We pick a unique multi-line anchor.

needle3 = '''bool ImageGenerationPage::usesWanDualNoiseMode() const
{
    return isVideoMode() && effectiveVideoStackMode() == QStringLiteral("wan_dual_noise");
}'''

replacement3 = '''bool ImageGenerationPage::usesWanDualNoiseMode() const
{
    return isVideoMode() && effectiveVideoStackMode() == QStringLiteral("wan_dual_noise");
}

// Sprint V Pass 2: VideoFamily resolution helpers.
//
// videoFamilySelection() returns the literal combo choice (auto/ltx/wan).
// resolvedVideoFamily() resolves "auto" to a concrete family using the
// existing suggestedVideoStackMode() heuristic, which already inspects
// modelFamilyByValue_, path hints (looksLikeWanHighNoisePath, etc.), and
// stack_kind metadata. resolvedVideoFamilyToken() returns the lowercase
// string ("ltx" or "wan") for use in JSON payloads and qss/state checks.
ImageGenerationPage::VideoFamily ImageGenerationPage::videoFamilySelection() const
{
    if (!videoFamilyCombo_)
        return VideoFamily::Auto;
    const QString token = videoFamilyCombo_->currentData(Qt::UserRole).toString().trimmed().toLower();
    if (token == QStringLiteral("ltx"))
        return VideoFamily::Ltx;
    if (token == QStringLiteral("wan"))
        return VideoFamily::Wan;
    return VideoFamily::Auto;
}

ImageGenerationPage::VideoFamily ImageGenerationPage::resolvedVideoFamily() const
{
    const VideoFamily explicitChoice = videoFamilySelection();
    if (explicitChoice != VideoFamily::Auto)
        return explicitChoice;

    // Auto: lean on existing resolution. suggestedVideoStackMode() already
    // surfaces "wan_dual_noise" when a WAN checkpoint is selected. We also
    // sniff modelFamilyByValue_ directly because a single-model WAN
    // checkpoint won't trigger dual-noise detection but is still WAN.
    const QString family = modelFamilyByValue_.value(selectedModelPath_).trimmed().toLower();
    if (family == QStringLiteral("wan"))
        return VideoFamily::Wan;
    if (suggestedVideoStackMode() == QStringLiteral("wan_dual_noise"))
        return VideoFamily::Wan;

    // Fall back to LTX. Currently LTX is the other supported video family
    // in SpellVision; future families (CogVideoX, Hunyuan, Mochi) would
    // extend the enum and this resolution function.
    return VideoFamily::Ltx;
}

QString ImageGenerationPage::resolvedVideoFamilyToken() const
{
    switch (resolvedVideoFamily())
    {
    case VideoFamily::Ltx: return QStringLiteral("ltx");
    case VideoFamily::Wan: return QStringLiteral("wan");
    case VideoFamily::Auto: break;
    }
    return QStringLiteral("ltx");
}

void ImageGenerationPage::updateVideoFamilyUi()
{
    // Card visibility: only show in video modes.
    if (videoFamilyCard_)
        videoFamilyCard_->setVisible(isVideoMode());

    if (!isVideoMode())
    {
        // In image modes nothing video-specific should be visible regardless.
        if (ltxLaunchOptionsPanel_)
            ltxLaunchOptionsPanel_->setVisible(false);
        return;
    }

    const QString resolved = resolvedVideoFamilyToken();
    const bool isLtx = resolved == QStringLiteral("ltx");
    const bool isWan = resolved == QStringLiteral("wan");

    // LTX launch options panel: visible only for LTX family.
    if (ltxLaunchOptionsPanel_)
        ltxLaunchOptionsPanel_->setVisible(isLtx);

    // Tooltip on the family combo surfaces what Auto resolved to so users
    // can tell at a glance whether their selection is being treated as LTX
    // or WAN without having to look at the panels below.
    if (videoFamilyCombo_ && videoFamilySelection() == VideoFamily::Auto)
    {
        videoFamilyCombo_->setToolTip(QStringLiteral("Auto resolved to: %1")
            .arg(isWan ? QStringLiteral("WAN") : QStringLiteral("LTX")));
    }
    else if (videoFamilyCombo_)
    {
        videoFamilyCombo_->setToolTip(QStringLiteral("Manual family override active."));
    }
}'''

if needle3 not in text:
    raise SystemExit("Could not find usesWanDualNoiseMode definition")
text = text.replace(needle3, replacement3, 1)

path.write_text(text, encoding="utf-8")
print("Applied Sprint V Pass 2: VideoFamily card built; LTX panel gated by family.")
'@
Set-Content .\scripts\refactors\apply_sprint_v_pass2_video_family_card.py $patch -Encoding UTF8
.\.venv\Scripts\python.exe .\scripts\refactors\apply_sprint_v_pass2_video_family_card.py
