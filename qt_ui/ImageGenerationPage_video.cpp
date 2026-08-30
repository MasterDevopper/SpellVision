#include "ImageGenerationPage.h"
#include "ImageGenerationPage_units.h"

#include <QAbstractItemView>
#include <QButtonGroup>
#include <QAbstractButton>
#include <QCheckBox>
#include <QComboBox>
#include <QCryptographicHash>
#include <QDir>
#include <QDoubleSpinBox>
#include <QFileDialog>
#include <QFileInfo>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QPainter>
#include <QPixmap>
#include <QPointer>
#include <QPushButton>
#include <QSettings>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QStandardPaths>
#include <QStringList>


QString ImageGenerationPage::videoComponentValue(const QComboBox *combo) const
{
    return comboStoredValue(combo).trimmed();
}

QString ImageGenerationPage::videoStackModeSelection() const
{
    return normalizedVideoStackModeToken(comboStoredValue(videoStackModeCombo_));
}

QString ImageGenerationPage::suggestedVideoStackMode() const
{
    if (!isVideoMode())
        return QStringLiteral("single_model");

    const QJsonObject stack = modelStackByValue_.value(selectedModelPath_);
    const QString stackKind = normalizedVideoStackModeToken(stack.value(QStringLiteral("stack_kind")).toString());
    if (stackKind == QStringLiteral("wan_dual_noise"))
        return stackKind;

    if (!stack.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty() ||
        !stack.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty() ||
        !stack.value(QStringLiteral("high_noise_model_path")).toString().trimmed().isEmpty() ||
        !stack.value(QStringLiteral("low_noise_model_path")).toString().trimmed().isEmpty())
    {
        return QStringLiteral("wan_dual_noise");
    }

    const QString family = modelFamilyByValue_.value(selectedModelPath_).trimmed().toLower();
    const QString note = modelNoteByValue_.value(selectedModelPath_).trimmed().toLower();
    const QString haystack = QDir::fromNativeSeparators(selectedModelPath_ + QStringLiteral(" ") + selectedModelDisplay_ + QStringLiteral(" ") + note).toLower();

    if (family == QStringLiteral("wan") && (looksLikeWanHighNoisePath(selectedModelPath_) || looksLikeWanLowNoisePath(selectedModelPath_) || haystack.contains(QStringLiteral("dual-noise"))))
        return QStringLiteral("wan_dual_noise");

    return QStringLiteral("single_model");
}

QString ImageGenerationPage::effectiveVideoStackMode() const
{
    const QString explicitMode = videoStackModeSelection();
    if (explicitMode != QStringLiteral("auto"))
        return explicitMode;
    return suggestedVideoStackMode();
}

bool ImageGenerationPage::usesWanDualNoiseMode() const
{
    return isVideoMode() && effectiveVideoStackMode() == QStringLiteral("wan_dual_noise");
}

// Sprint V Pass 2: VideoFamily resolution helpers.
//
// videoFamilySelection() returns the literal combo choice (auto/ltx/wan/flux3).
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
    if (token == QStringLiteral("flux3"))
        return VideoFamily::Flux3;
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
    if (family == QStringLiteral("ltx"))
        return VideoFamily::Ltx;
    if (family == QStringLiteral("flux3") || family == QStringLiteral("flux"))
        return VideoFamily::Flux3;
    if (suggestedVideoStackMode() == QStringLiteral("wan_dual_noise"))
        return VideoFamily::Wan;
    return VideoFamily::Auto;
}

QString ImageGenerationPage::resolvedVideoFamilyToken() const
{
    switch (resolvedVideoFamily())
    {
    case VideoFamily::Ltx: return QStringLiteral("ltx");
    case VideoFamily::Wan: return QStringLiteral("wan");
    case VideoFamily::Flux3: return QStringLiteral("flux3");
    case VideoFamily::Auto: break;
    }
    return QStringLiteral("auto");
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
    const bool isFlux3 = resolved == QStringLiteral("flux3");

    // LTX launch options panel: legacy Prompt-API surface — hide from primary path (native LTX).
    // Still reachable only if Advanced is on (updateDisclosure owns final visibility).
    if (ltxLaunchOptionsPanel_)
        ltxLaunchOptionsPanel_->setVisible(false);

    // Tooltip on the family combo surfaces what Auto resolved to so users
    // can tell at a glance whether their selection is being treated as LTX
    // or WAN without having to look at the panels below.
    if (videoFamilyCombo_ && videoFamilySelection() == VideoFamily::Auto)
    {
        const QString resolvedName = isWan ? QStringLiteral("WAN")
                                     : (isFlux3 ? QStringLiteral("FLUX.3 API")
                                     : (isLtx ? QStringLiteral("LTX") : QStringLiteral("pick a video stack")));
        videoFamilyCombo_->setToolTip(QStringLiteral("Auto resolved to: %1").arg(resolvedName));
    }
    else if (videoFamilyCombo_)
    {
        videoFamilyCombo_->setToolTip(QStringLiteral("Manual family override active."));
    }

    // Sync the segmented bar to the backing combo's selection, and show what Auto resolves to
    // (mockup "resolves -> X"). setChecked emits toggled, not clicked, so it never re-drives
    // the combo -- no loop.
    const VideoFamily selection = videoFamilySelection();
    QPushButton *targetButton = selection == VideoFamily::Wan ? videoFamilyWanButton_
                              : selection == VideoFamily::Ltx ? videoFamilyLtxButton_
                              : selection == VideoFamily::Flux3 ? videoFamilyFlux3Button_
                                                              : videoFamilyAutoButton_;
    if (targetButton && !targetButton->isChecked())
        targetButton->setChecked(true);
    if (videoFamilyResolvesLabel_)
    {
        if (resolved == QStringLiteral("auto") || resolved.isEmpty())
            videoFamilyResolvesLabel_->setText(QStringLiteral("resolves → pick a stack"));
        else
            videoFamilyResolvesLabel_->setText(QStringLiteral("resolves → %1").arg(resolved.toUpper()));
    }
}

void ImageGenerationPage::applyOptimalVideoSamplingDefaults()
{
    if (!isVideoMode())
        return;

    const QString family = resolvedVideoFamilyToken().trimmed().toLower();
    // Community-validated operating points; user can still edit Advanced knobs afterward.
    if (family.startsWith(QStringLiteral("wan"))) {
        if (wanSplitCombo_)
            selectComboValue(wanSplitCombo_, QStringLiteral("auto"));
        if (highNoiseStepsSpin_)
            highNoiseStepsSpin_->setValue(14);
        if (lowNoiseStepsSpin_)
            lowNoiseStepsSpin_->setValue(14);
        if (splitStepSpin_)
            splitStepSpin_->setValue(14);
        if (highNoiseShiftSpin_)
            highNoiseShiftSpin_->setValue(5.0);
        if (lowNoiseShiftSpin_)
            lowNoiseShiftSpin_->setValue(5.0);
        if (sampling_->stepsSpin())
            sampling_->stepsSpin()->setValue(28); // high+low when split
        if (sampling_->cfgSpin())
            sampling_->cfgSpin()->setValue(5.0);
        if (sampling_->videoSamplerCombo()) {
            if (!selectComboValue(sampling_->videoSamplerCombo(), QStringLiteral("uni_pc")))
                selectComboValue(sampling_->videoSamplerCombo(), QStringLiteral("euler"));
        }
        if (sampling_->videoSchedulerCombo())
            selectComboValue(sampling_->videoSchedulerCombo(), QStringLiteral("simple"));
        if (readinessHintLabel_)
            readinessHintLabel_->setText(
                QStringLiteral("WAN defaults applied: split auto · 14/14 · shift 5.0 (editable in Advanced)."));
    } else if (family.startsWith(QStringLiteral("ltx"))) {
        // Full ltx-2.3-22b wants 25–40 steps, CFG 3–5 (native AV path).
        if (sampling_->stepsSpin())
            sampling_->stepsSpin()->setValue(30);
        if (sampling_->cfgSpin())
            sampling_->cfgSpin()->setValue(3.5);
        if (sampling_->videoSamplerCombo())
            selectComboValue(sampling_->videoSamplerCombo(), QStringLiteral("euler"));
        if (frameCountSpin_) {
            // Snap toward (N×8)+1 without fighting user too hard on first pick.
            const int f = frameCountSpin_->value();
            if (f < 49)
                frameCountSpin_->setValue(49);
        }
        if (readinessHintLabel_)
            readinessHintLabel_->setText(
                QStringLiteral("LTX defaults applied: 30 steps · CFG 3.5 · native AV (editable in Advanced)."));
    } else if (family == QStringLiteral("flux3")) {
        if (fpsSpin_)
            fpsSpin_->setValue(24);
        if (frameCountSpin_ && frameCountSpin_->value() < 120)
            frameCountSpin_->setValue(120);
        if (readinessHintLabel_)
            readinessHintLabel_->setText(
                QStringLiteral("FLUX.3 BFL API preview: hosted, paid, audio enabled · BFL_API_KEY required."));
    }
    updateVideoStackModeUi();
}

void ImageGenerationPage::setVideoComponentComboValue(QComboBox *combo, const QString &value)
{
    if (!combo)
        return;

    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
    {
        combo->setCurrentIndex(combo->count() > 0 ? 0 : -1);
        return;
    }

    for (int index = 0; index < combo->count(); ++index)
    {
        if (combo->itemData(index, Qt::UserRole).toString().compare(trimmed, Qt::CaseInsensitive) == 0 ||
            combo->itemText(index).compare(trimmed, Qt::CaseInsensitive) == 0)
        {
            combo->setCurrentIndex(index);
            return;
        }
    }

    combo->addItem(QStringLiteral("Manual • %1").arg(shortDisplayFromValue(trimmed)), trimmed);
    combo->setCurrentIndex(combo->count() - 1);
}

void ImageGenerationPage::populateVideoComponentControls()
{
    if (!isVideoMode())
        return;
    if (!videoStackModeCombo_ || !videoPrimaryModelCombo_ || !videoHighNoiseModelCombo_ || !videoLowNoiseModelCombo_ || !videoTextEncoderCombo_ || !videoVaeCombo_ || !videoClipVisionCombo_)
        return;

    auto looksVideoPrimary = [](const CatalogEntry &entry) {
        const QString haystack = normalizedPathText(entry.value + QStringLiteral(" ") + entry.display);
        return haystack.contains(QStringLiteral("wan")) ||
               haystack.contains(QStringLiteral("ltx")) ||
               haystack.contains(QStringLiteral("hunyuan")) ||
               haystack.contains(QStringLiteral("hyvideo")) ||
               haystack.contains(QStringLiteral("cogvideo")) ||
               haystack.contains(QStringLiteral("mochi")) ||
               haystack.contains(QStringLiteral("animatediff")) ||
               haystack.contains(QStringLiteral("svd")) ||
               haystack.contains(QStringLiteral("video"));
    };

    auto appendUnique = [](QVector<CatalogEntry> &target, QVector<CatalogEntry> source, const QString &family, const QString &role) {
        QSet<QString> seen;
        for (const CatalogEntry &entry : target)
            seen.insert(entry.value.toLower());
        for (CatalogEntry entry : source)
        {
            const QString key = entry.value.toLower();
            if (seen.contains(key))
                continue;
            seen.insert(key);
            entry.family = family.isEmpty() ? inferVideoFamilyFromText(entry.value + QStringLiteral(" ") + entry.display) : family;
            entry.modality = QStringLiteral("video");
            entry.role = role;
            target.push_back(entry);
        }
    };

    QVector<CatalogEntry> primaryEntries;
    for (const QString &dir : {QStringLiteral("diffusion_models"), QStringLiteral("unet"), QStringLiteral("video"), QStringLiteral("wan"), QStringLiteral("ltx"), QStringLiteral("hunyuan_video"), QStringLiteral("checkpoints")})
    {
        QVector<CatalogEntry> filtered;
        for (CatalogEntry entry : scanCatalog(modelsRootDir_, dir))
        {
            if (!looksVideoPrimary(entry))
                continue;
            entry.note = QStringLiteral("Primary video diffusion model");
            filtered.push_back(entry);
        }
        appendUnique(primaryEntries, filtered, QString(), QStringLiteral("primary"));
    }

    QVector<CatalogEntry> textEntries;
    appendUnique(textEntries, scanCatalog(modelsRootDir_, QStringLiteral("text_encoders")), QString(), QStringLiteral("text_encoder"));
    appendUnique(textEntries, scanCatalog(modelsRootDir_, QStringLiteral("clip")), QString(), QStringLiteral("text_encoder"));

    QVector<CatalogEntry> vaeEntries;
    appendUnique(vaeEntries, scanCatalog(modelsRootDir_, QStringLiteral("vae")), QString(), QStringLiteral("vae"));

    QVector<CatalogEntry> visionEntries;
    appendUnique(visionEntries, scanCatalog(modelsRootDir_, QStringLiteral("clip_vision")), QString(), QStringLiteral("clip_vision"));
    appendUnique(visionEntries, scanCatalog(modelsRootDir_, QStringLiteral("image_encoders")), QString(), QStringLiteral("clip_vision"));

    auto fillCombo = [](QComboBox *combo, const QString &autoLabel, const QVector<CatalogEntry> &entries) {
        if (!combo)
            return;
        const QString prior = comboStoredValue(combo);
        const QSignalBlocker blocker(combo);
        combo->clear();
        combo->addItem(autoLabel, QString());
        for (const CatalogEntry &entry : entries)
            combo->addItem(entry.display, entry.value);
        if (!prior.trimmed().isEmpty())
        {
            for (int index = 0; index < combo->count(); ++index)
            {
                if (combo->itemData(index, Qt::UserRole).toString().compare(prior, Qt::CaseInsensitive) == 0)
                {
                    combo->setCurrentIndex(index);
                    return;
                }
            }
            combo->addItem(QStringLiteral("Manual • %1").arg(shortDisplayFromValue(prior)), prior);
            combo->setCurrentIndex(combo->count() - 1);
            return;
        }
        combo->setCurrentIndex(0);
    };

    fillCombo(videoPrimaryModelCombo_, QStringLiteral("Auto primary from selected stack"), primaryEntries);
    fillCombo(videoHighNoiseModelCombo_, QStringLiteral("Auto high-noise model"), primaryEntries);
    fillCombo(videoLowNoiseModelCombo_, QStringLiteral("Auto low-noise model"), primaryEntries);
    fillCombo(videoTextEncoderCombo_, QStringLiteral("Auto text encoder"), textEntries);
    fillCombo(videoVaeCombo_, QStringLiteral("Auto VAE"), vaeEntries);
    fillCombo(videoClipVisionCombo_, QStringLiteral("Auto vision encoder"), visionEntries);
    if (videoStackModeCombo_ && videoStackModeCombo_->count() > 0 && videoStackModeCombo_->currentIndex() < 0)
        videoStackModeCombo_->setCurrentIndex(0);
    updateVideoFamilyUi();
    updateVideoStackModeUi();
}

QJsonObject ImageGenerationPage::selectedVideoStackForPayload() const
{
    if (!isVideoMode())
        return QJsonObject();

    QJsonObject stack = modelStackByValue_.value(selectedModelPath_);
    QString primary = videoComponentValue(videoPrimaryModelCombo_).trimmed();
    if (primary.isEmpty())
        primary = stack.value(QStringLiteral("primary_path")).toString().trimmed();
    if (primary.isEmpty())
        primary = selectedModelPath_.trimmed();
    if (stack.isEmpty() && primary.isEmpty())
        return QJsonObject();

    const QString family = !modelFamilyByValue_.value(selectedModelPath_).trimmed().isEmpty()
                               ? modelFamilyByValue_.value(selectedModelPath_).trimmed()
                               : inferVideoFamilyFromText(primary);

    const QString stackMode = effectiveVideoStackMode();
    stack.insert(QStringLiteral("family"), family);
    stack.insert(QStringLiteral("modality"), QStringLiteral("video"));
    stack.insert(QStringLiteral("stack_mode"), stackMode);

    const QString textEncoder = videoComponentValue(videoTextEncoderCombo_);
    const QString vae = videoComponentValue(videoVaeCombo_);
    const QString clipVision = videoComponentValue(videoClipVisionCombo_);

    if (stackMode == QStringLiteral("wan_dual_noise"))
    {
        QString highNoise = videoComponentValue(videoHighNoiseModelCombo_);
        QString lowNoise = videoComponentValue(videoLowNoiseModelCombo_);

        if (highNoise.isEmpty())
        {
            highNoise = stack.value(QStringLiteral("high_noise_path")).toString().trimmed();
            if (highNoise.isEmpty())
                highNoise = stack.value(QStringLiteral("high_noise_model_path")).toString().trimmed();
            if (highNoise.isEmpty() && looksLikeWanHighNoisePath(primary))
                highNoise = primary;
        }
        if (lowNoise.isEmpty())
        {
            lowNoise = stack.value(QStringLiteral("low_noise_path")).toString().trimmed();
            if (lowNoise.isEmpty())
                lowNoise = stack.value(QStringLiteral("low_noise_model_path")).toString().trimmed();
            if (lowNoise.isEmpty() && looksLikeWanLowNoisePath(primary))
                lowNoise = primary;
        }

        const QString resolvedPrimary = !primary.isEmpty() ? primary : (!lowNoise.isEmpty() ? lowNoise : highNoise);
        const QString resolvedRuntimeModel = !lowNoise.isEmpty() ? lowNoise : resolvedPrimary;
        stack.insert(QStringLiteral("role"), QStringLiteral("split_stack"));
        stack.insert(QStringLiteral("stack_kind"), QStringLiteral("wan_dual_noise"));
        stack.insert(QStringLiteral("primary_path"), resolvedPrimary);
        stack.insert(QStringLiteral("transformer_path"), resolvedRuntimeModel);
        stack.insert(QStringLiteral("unet_path"), resolvedRuntimeModel);
        stack.insert(QStringLiteral("model_path"), resolvedRuntimeModel);
        stack.insert(QStringLiteral("high_noise_path"), highNoise);
        stack.insert(QStringLiteral("high_noise_model_path"), highNoise);
        stack.insert(QStringLiteral("wan_high_noise_path"), highNoise);
        stack.insert(QStringLiteral("low_noise_path"), lowNoise);
        stack.insert(QStringLiteral("low_noise_model_path"), lowNoise);
        stack.insert(QStringLiteral("wan_low_noise_path"), lowNoise);
        if (!textEncoder.isEmpty())
            stack.insert(QStringLiteral("text_encoder_path"), textEncoder);
        if (!vae.isEmpty())
            stack.insert(QStringLiteral("vae_path"), vae);
        if (!clipVision.isEmpty())
            stack.insert(QStringLiteral("clip_vision_path"), clipVision);

        QJsonArray missing;
        if (stack.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty())
            missing.append(QStringLiteral("high noise"));
        if (stack.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty())
            missing.append(QStringLiteral("low noise"));
        if (stack.value(QStringLiteral("text_encoder_path")).toString().trimmed().isEmpty())
            missing.append(QStringLiteral("text encoder"));
        if (stack.value(QStringLiteral("vae_path")).toString().trimmed().isEmpty())
            missing.append(QStringLiteral("vae"));
        stack.insert(QStringLiteral("missing_parts"), missing);
        stack.insert(QStringLiteral("stack_ready"), missing.isEmpty());
        stack.insert(QStringLiteral("manual_component_selection"),
                     videoStackModeSelection() != QStringLiteral("auto") ||
                     !textEncoder.isEmpty() || !vae.isEmpty() || !clipVision.isEmpty() ||
                     !videoComponentValue(videoHighNoiseModelCombo_).isEmpty() ||
                     !videoComponentValue(videoLowNoiseModelCombo_).isEmpty());

        QJsonObject controls;
        controls.insert(QStringLiteral("stack_mode"), stackMode);
        controls.insert(QStringLiteral("primary_path"), resolvedPrimary);
        controls.insert(QStringLiteral("high_noise_path"), videoComponentValue(videoHighNoiseModelCombo_));
        controls.insert(QStringLiteral("low_noise_path"), videoComponentValue(videoLowNoiseModelCombo_));
        controls.insert(QStringLiteral("text_encoder_path"), textEncoder);
        controls.insert(QStringLiteral("vae_path"), vae);
        controls.insert(QStringLiteral("clip_vision_path"), clipVision);
        stack.insert(QStringLiteral("component_controls"), controls);
        return stack;
    }

    stack.insert(QStringLiteral("role"), stack.value(QStringLiteral("role")).toString().trimmed().isEmpty() ? QStringLiteral("model_stack") : stack.value(QStringLiteral("role")).toString());
    const QString currentKind = stack.value(QStringLiteral("stack_kind")).toString().trimmed();
    stack.insert(QStringLiteral("stack_kind"), currentKind.isEmpty() ? QStringLiteral("single_model") : currentKind);

    if (!primary.isEmpty())
    {
        stack.insert(QStringLiteral("primary_path"), primary);
        stack.insert(QStringLiteral("transformer_path"), primary);
        stack.insert(QStringLiteral("unet_path"), primary);
        stack.insert(QStringLiteral("model_path"), primary);
    }

    if (!textEncoder.isEmpty())
        stack.insert(QStringLiteral("text_encoder_path"), textEncoder);
    if (!vae.isEmpty())
        stack.insert(QStringLiteral("vae_path"), vae);
    if (!clipVision.isEmpty())
        stack.insert(QStringLiteral("clip_vision_path"), clipVision);

    QJsonArray missing;
    const QString kind = stack.value(QStringLiteral("stack_kind")).toString().trimmed();
    const bool requiresComponents = kind == QStringLiteral("split_stack");
    if (requiresComponents && stack.value(QStringLiteral("text_encoder_path")).toString().trimmed().isEmpty())
        missing.append(QStringLiteral("text encoder"));
    if (requiresComponents && stack.value(QStringLiteral("vae_path")).toString().trimmed().isEmpty())
        missing.append(QStringLiteral("vae"));
    stack.insert(QStringLiteral("missing_parts"), missing);
    stack.insert(QStringLiteral("stack_ready"), missing.isEmpty() || !requiresComponents);
    stack.insert(QStringLiteral("manual_component_selection"), videoStackModeSelection() != QStringLiteral("auto") || !textEncoder.isEmpty() || !vae.isEmpty() || !clipVision.isEmpty() || (!primary.isEmpty() && primary.compare(selectedModelPath_, Qt::CaseInsensitive) != 0));

    QJsonObject controls;
    controls.insert(QStringLiteral("stack_mode"), stackMode);
    controls.insert(QStringLiteral("primary_path"), primary);
    controls.insert(QStringLiteral("text_encoder_path"), textEncoder);
    controls.insert(QStringLiteral("vae_path"), vae);
    controls.insert(QStringLiteral("clip_vision_path"), clipVision);
    stack.insert(QStringLiteral("component_controls"), controls);

    return stack;
}

void ImageGenerationPage::syncVideoComponentControlsFromSelectedStack()
{
    if (!isVideoMode())
        return;
    if (!videoStackModeCombo_ || !videoPrimaryModelCombo_ || !videoHighNoiseModelCombo_ || !videoLowNoiseModelCombo_ || !videoTextEncoderCombo_ || !videoVaeCombo_ || !videoClipVisionCombo_)
        return;

    syncingVideoComponentControls_ = true;
    const QJsonObject stack = modelStackByValue_.value(selectedModelPath_);
    if (videoStackModeCombo_->currentIndex() < 0)
        videoStackModeCombo_->setCurrentIndex(0);
    setVideoComponentComboValue(videoPrimaryModelCombo_,
                                stack.value(QStringLiteral("primary_path")).toString().trimmed().isEmpty()
                                    ? selectedModelPath_
                                    : stack.value(QStringLiteral("primary_path")).toString().trimmed());
    setVideoComponentComboValue(videoHighNoiseModelCombo_,
                                stack.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty()
                                    ? stack.value(QStringLiteral("high_noise_model_path")).toString()
                                    : stack.value(QStringLiteral("high_noise_path")).toString());
    setVideoComponentComboValue(videoLowNoiseModelCombo_,
                                stack.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty()
                                    ? stack.value(QStringLiteral("low_noise_model_path")).toString()
                                    : stack.value(QStringLiteral("low_noise_path")).toString());
    if (videoComponentValue(videoHighNoiseModelCombo_).isEmpty() && looksLikeWanHighNoisePath(selectedModelPath_))
        setVideoComponentComboValue(videoHighNoiseModelCombo_, selectedModelPath_);
    if (videoComponentValue(videoLowNoiseModelCombo_).isEmpty() && looksLikeWanLowNoisePath(selectedModelPath_))
        setVideoComponentComboValue(videoLowNoiseModelCombo_, selectedModelPath_);
    setVideoComponentComboValue(videoTextEncoderCombo_, stack.value(QStringLiteral("text_encoder_path")).toString());
    setVideoComponentComboValue(videoVaeCombo_, stack.value(QStringLiteral("vae_path")).toString());
    setVideoComponentComboValue(videoClipVisionCombo_, stack.value(QStringLiteral("clip_vision_path")).toString());
    applyVideoAutoPopulateToCombos();     // A2: auto-fill (override-aware) + constrain menus to valid set
    syncingVideoComponentControls_ = false;
}

void ImageGenerationPage::setComponentStackResolver(
    std::function<void(
        const QString &,
        const QString &,
        const QString &,
        const QJsonObject &,
        std::function<void(const QJsonArray &)>)> resolver)
{
    componentStackResolver_ = std::move(resolver);
}

void ImageGenerationPage::setOperatingPointsProvider(std::function<QJsonObject(const QString &)> provider)
{
    operatingPointsProvider_ = std::move(provider);
    updateOperatingPointSelector();
}

void ImageGenerationPage::refreshOperatingPointSelector()
{
    updateOperatingPointSelector();
}

QString ImageGenerationPage::resolvedVideoFamilyForSelector() const
{
    if (!isVideoMode())
        return QString();
    switch (videoFamilySelection())
    {
    case VideoFamily::Wan:
        return QStringLiteral("wan");
    case VideoFamily::Ltx:
        return QStringLiteral("ltx");
    case VideoFamily::Auto:
    default:
        break;
    }
    // Auto -> resolve from the selected checkpoint (same logic maybeAutoPopulateVideoComponents uses).
    const QString model = selectedModelPath_.trimmed();
    QString family = modelFamilyByValue_.value(model).trimmed();
    if (family.isEmpty())
        family = inferVideoFamilyFromText(model);
    return family.trimmed().toLower();
}

void ImageGenerationPage::applyFamilySamplingChoices(const QString &family)
{
    if (!sampling_ || !operatingPointsProvider_ || family.trimmed().isEmpty())
        return;
    sampling_->applyFamilyChoices(operatingPointsProvider_(family), isVideoMode());
}

QJsonObject ImageGenerationPage::buildVideoComponentChoicesForResolver() const
{
    // The cockpit's own combo file basenames -> the engine resolves against exactly what the UI
    // can display, so value/valid_options come back aligned to selectable entries.
    auto names = [](const QComboBox *combo) {
        QJsonArray arr;
        if (!combo)
            return arr;
        QSet<QString> seen;
        for (int i = 1; i < combo->count(); ++i)  // skip index 0 (Auto placeholder, empty value)
        {
            const QString value = combo->itemData(i, Qt::UserRole).toString().trimmed();
            const QString base = QFileInfo(value.isEmpty() ? combo->itemText(i) : value).fileName().trimmed();
            if (!base.isEmpty() && !seen.contains(base.toLower()))
            {
                seen.insert(base.toLower());
                arr.append(base);
            }
        }
        return arr;
    };
    QJsonObject vaeChoices;
    vaeChoices.insert(QStringLiteral("vae_name"), names(videoVaeCombo_));
    QJsonObject textChoices;
    textChoices.insert(QStringLiteral("clip_name"), names(videoTextEncoderCombo_));
    QJsonObject visionChoices;
    visionChoices.insert(QStringLiteral("clip_name"), names(videoClipVisionCombo_));

    QJsonObject choices;
    choices.insert(QStringLiteral("VAELoader"), vaeChoices);
    choices.insert(QStringLiteral("CLIPLoader"), textChoices);
    choices.insert(QStringLiteral("CLIPVisionLoader"), visionChoices);
    return choices;
}

void ImageGenerationPage::maybeAutoPopulateVideoComponents()
{
    if (!isVideoMode() || !componentStackResolver_)
        return;
    const QString model = selectedModelPath_.trimmed();
    if (model.isEmpty())
    {
        ++componentResolveGeneration_;
        lastAutoPopulatedModel_.clear();
        return;
    }
    // Run once per model CHANGE -- re-running would clobber a manual override the user made
    // after selection (the whole "auto-fill on change, respect overrides after" contract).
    if (model.compare(lastAutoPopulatedModel_, Qt::CaseInsensitive) == 0)
        return;
    lastAutoPopulatedModel_ = model;
    videoComponentValidOptions_.clear();
    videoAutoFilledValues_.clear();
    videoMissingRequiredComponents_.clear();

    QString family = modelFamilyByValue_.value(model).trimmed();
    if (family.isEmpty())
        family = inferVideoFamilyFromText(model);
    const QString task = (mode_ == Mode::ImageToVideo) ? QStringLiteral("i2v") : QStringLiteral("t2v");

    const quint64 generation = ++componentResolveGeneration_;
    const QPointer<ImageGenerationPage> pageGuard(this);
    componentStackResolver_(
        model,
        family,
        task,
        buildVideoComponentChoicesForResolver(),
        [pageGuard, model, generation](const QJsonArray &resolvedSlots) {
            if (!pageGuard || generation != pageGuard->componentResolveGeneration_)
                return;
            if (pageGuard->selectedModelPath_.trimmed().compare(model, Qt::CaseInsensitive) != 0)
                return;
            pageGuard->applyResolvedVideoComponents(model, resolvedSlots);
        });
}

void ImageGenerationPage::applyResolvedVideoComponents(
    const QString &model,
    const QJsonArray &resolvedSlots)
{
    if (resolvedSlots.isEmpty())
        return;  // worker down / error -> combos stay on Auto (worker backstop resolves at gen time)

    auto keyFor = [](const QString &c) -> QString {
        if (c == QStringLiteral("vae")) return QStringLiteral("vae_path");
        if (c == QStringLiteral("text_encoder")) return QStringLiteral("text_encoder_path");
        if (c == QStringLiteral("clip_vision")) return QStringLiteral("clip_vision_path");
        return QString();
    };
    // On a model CHANGE the engine's resolution WINS over any stale/sidecar stored stack value
    // (a Wan model's companion metadata often carries a generic clip_l/name-matched VAE). We write
    // the resolved value into the stack here; a manual override the user makes AFTER this is then
    // captured by applyVideoComponentOverridesToSelectedStack and wins on subsequent re-syncs
    // (maybeAutoPopulate does not re-run for the same model -> lastAutoPopulatedModel_ gate).
    QJsonObject stack = modelStackByValue_.value(model);
    for (const QJsonValue &v : resolvedSlots)
    {
        const QJsonObject s = v.toObject();
        const QString comp = s.value(QStringLiteral("component")).toString();
        const QString key = keyFor(comp);
        if (key.isEmpty())
            continue;  // model slots (primary/high/low) are user-provided, not auto-filled here
        QStringList valid;
        for (const QJsonValue &o : s.value(QStringLiteral("valid_options")).toArray())
            valid << o.toString();
        videoComponentValidOptions_.insert(comp, valid);
        const QString value = s.value(QStringLiteral("value")).toString().trimmed();
        if (!value.isEmpty())
        {
            videoAutoFilledValues_.insert(comp, value);
            stack.insert(key, value);
        }
        if (s.value(QStringLiteral("required")).toBool() && s.value(QStringLiteral("tier")).toString() == QStringLiteral("T3"))
            videoMissingRequiredComponents_ << comp;
    }
    if (!stack.isEmpty())
        modelStackByValue_.insert(model, stack);
    syncVideoComponentControlsFromSelectedStack();
    updateAssetIntelligenceUi();
    updateOperatingPointSelector();
}

void ImageGenerationPage::applyVideoAutoPopulateToCombos()
{
    if (videoComponentValidOptions_.isEmpty())
        return;  // nothing resolved for this model -> leave the existing combos untouched
    const QJsonObject stack = modelStackByValue_.value(selectedModelPath_);
    QComboBox *const combos[3] = {videoVaeCombo_, videoTextEncoderCombo_, videoClipVisionCombo_};
    const char *const comps[3] = {"vae", "text_encoder", "clip_vision"};
    const char *const keys[3] = {"vae_path", "text_encoder_path", "clip_vision_path"};
    for (int i = 0; i < 3; ++i)
    {
        QComboBox *combo = combos[i];
        const QString comp = QString::fromLatin1(comps[i]);
        if (!combo || !videoComponentValidOptions_.contains(comp))
            continue;
        // A manual override captured into the stack wins over the auto-fill (expert flexibility).
        const QString overrideValue = stack.value(QString::fromLatin1(keys[i])).toString().trimmed();
        const QString value = overrideValue.isEmpty() ? videoAutoFilledValues_.value(comp) : overrideValue;
        if (!value.isEmpty())
            setVideoComboToBasename(combo, value);
        constrainVideoComboToValid(combo, videoComponentValidOptions_.value(comp), value);
    }
}

void ImageGenerationPage::setVideoComboToBasename(QComboBox *combo, const QString &value)
{
    if (!combo || value.trimmed().isEmpty())
        return;
    const QString base = QFileInfo(value.trimmed()).fileName().toLower();
    for (int i = 0; i < combo->count(); ++i)
    {
        const QString itemVal = combo->itemData(i, Qt::UserRole).toString().trimmed();
        const QString itemBase = QFileInfo(itemVal.isEmpty() ? combo->itemText(i) : itemVal).fileName().toLower();
        if (!itemBase.isEmpty() && itemBase == base)
        {
            combo->setCurrentIndex(i);
            return;
        }
    }
    setVideoComponentComboValue(combo, value);  // not a catalog entry -> exact-value setter (Manual entry)
}

void ImageGenerationPage::constrainVideoComboToValid(QComboBox *combo, const QStringList &validBasenames, const QString &keepValue)
{
    if (!combo || validBasenames.isEmpty())
        return;  // no constraint -> full menu (unresolved slot / unknown family)
    QSet<QString> validSet;
    for (const QString &v : validBasenames)
        validSet.insert(QFileInfo(v).fileName().toLower());
    const QString keepBase = QFileInfo(keepValue.trimmed()).fileName().toLower();
    const QSignalBlocker blocker(combo);
    for (int i = combo->count() - 1; i >= 1; --i)  // keep index 0 (the Auto placeholder)
    {
        const QString itemVal = combo->itemData(i, Qt::UserRole).toString().trimmed();
        const QString itemBase = QFileInfo(itemVal.isEmpty() ? combo->itemText(i) : itemVal).fileName().toLower();
        const bool isKept = !keepBase.isEmpty() && itemBase == keepBase;
        if (!validSet.contains(itemBase) && !isKept)
            combo->removeItem(i);
    }
}

void ImageGenerationPage::applyVideoComponentOverridesToSelectedStack()
{
    if (!isVideoMode() || syncingVideoComponentControls_ || selectedModelPath_.trimmed().isEmpty())
        return;

    const QJsonObject stack = selectedVideoStackForPayload();
    if (!stack.isEmpty())
    {
        modelStackByValue_.insert(selectedModelPath_, stack);
        const QString family = stack.value(QStringLiteral("family")).toString().trimmed();
        if (!family.isEmpty())
            modelFamilyByValue_.insert(selectedModelPath_, family);
        modelModalityByValue_.insert(selectedModelPath_, QStringLiteral("video"));
        modelRoleByValue_.insert(selectedModelPath_, stack.value(QStringLiteral("role")).toString().trimmed().isEmpty() ? QStringLiteral("model_stack") : stack.value(QStringLiteral("role")).toString().trimmed());

        QStringList pieces;
        const QString stackMode = stack.value(QStringLiteral("stack_mode")).toString().trimmed();
        if (stackMode == QStringLiteral("wan_dual_noise"))
        {
            if (!stack.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty())
                pieces << QStringLiteral("high noise");
            if (!stack.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty())
                pieces << QStringLiteral("low noise");
        }
        else if (!stack.value(QStringLiteral("primary_path")).toString().trimmed().isEmpty())
        {
            pieces << QStringLiteral("model");
        }
        if (!stack.value(QStringLiteral("text_encoder_path")).toString().trimmed().isEmpty())
            pieces << QStringLiteral("text");
        if (!stack.value(QStringLiteral("vae_path")).toString().trimmed().isEmpty())
            pieces << QStringLiteral("vae");
        if (!stack.value(QStringLiteral("clip_vision_path")).toString().trimmed().isEmpty())
            pieces << QStringLiteral("vision");

        QJsonArray missing = stack.value(QStringLiteral("missing_parts")).toArray();
        QStringList missingParts;
        for (const QJsonValue &item : missing)
            missingParts << item.toString();

        if (!missingParts.isEmpty())
            modelNoteByValue_.insert(selectedModelPath_, QStringLiteral("Manual %1 stack: missing %2").arg(stackMode == QStringLiteral("wan_dual_noise") ? QStringLiteral("WAN dual-noise") : QStringLiteral("video"), missingParts.join(QStringLiteral(", "))));
        else
            modelNoteByValue_.insert(selectedModelPath_, QStringLiteral("Manual %1 stack: %2").arg(stackMode == QStringLiteral("wan_dual_noise") ? QStringLiteral("WAN dual-noise") : QStringLiteral("video"), pieces.join(QStringLiteral(" + "))));
    }

    updateVideoFamilyUi();
    updateVideoStackModeUi();
    updateAssetIntelligenceUi();
    updatePrimaryActionAvailability();
}

void ImageGenerationPage::updateVideoStackModeUi()
{
    if (!isVideoMode())
        return;

    // Sprint V Pass 3:
    // Family resolution gates WAN UI. Even if the stack mode combo would
    // technically allow dual-noise, an LTX family selection hides WAN
    // rows entirely so the user sees a coherent LTX-only surface.
    const bool familyIsWan = resolvedVideoFamilyToken() == QStringLiteral("wan");
    const bool wanDualNoise = usesWanDualNoiseMode() && familyIsWan;

    if (videoHighNoiseRow_)
        videoHighNoiseRow_->setVisible(wanDualNoise);
    if (videoHighNoiseModelCombo_)
        videoHighNoiseModelCombo_->setVisible(wanDualNoise);
    if (videoLowNoiseRow_)
        videoLowNoiseRow_->setVisible(wanDualNoise);
    if (videoLowNoiseModelCombo_)
        videoLowNoiseModelCombo_->setVisible(wanDualNoise);

    for (QWidget *row : {wanSplitRow_, highNoiseStepsRow_, lowNoiseStepsRow_, splitStepRow_, highNoiseShiftRow_, lowNoiseShiftRow_})
    {
        if (row)
            row->setVisible(wanDualNoise);
    }

    // VAE Tiling was shown EXACTLY where it is ignored. It rode in the list above, so it appeared
    // only for WAN dual-noise -- and the dual-noise builder never reads enable_vae_tiling. The one
    // builder that does is the WAN wrapper route (_build_native_wan_split_video_prompt), which is
    // reached when the family is WAN and dual-noise is off, and there the checkbox was hidden.
    //
    // The UI cannot tell wan_wrapper from wan_core with certainty -- that depends on which classes
    // the live ComfyUI offers -- so this is the closest honest approximation: offer the control on
    // the WAN routes that can honour it, rather than on the one that cannot.
    if (enableVaeTilingRow_)
        enableVaeTilingRow_->setVisible(familyIsWan && !wanDualNoise);

    // The stack-mode row itself is only meaningful for WAN. Hide it when
    // family resolved to LTX so the right-rail Components panel doesn't
    // show a "Stack Mode: WAN dual-noise" choice that does nothing.
    if (videoStackModeRow_)
        videoStackModeRow_->setVisible(familyIsWan);
    if (videoStackModeCombo_)
        videoStackModeCombo_->setVisible(familyIsWan);

    if (videoStackModeCombo_)
    {
        const QString suggested = suggestedVideoStackMode();
        const QString explicitMode = videoStackModeSelection();
        const QString effective = effectiveVideoStackMode();
        const QString suffix = explicitMode == QStringLiteral("auto")
                                   ? QStringLiteral("Auto detect (%1)").arg(suggested == QStringLiteral("wan_dual_noise") ? QStringLiteral("WAN dual-noise") : QStringLiteral("single model"))
                                   : (effective == QStringLiteral("wan_dual_noise") ? QStringLiteral("Manual WAN dual-noise override") : QStringLiteral("Manual single-model override"));
        videoStackModeCombo_->setToolTip(suffix);
    }

    if (wanSplitCombo_)
        wanSplitCombo_->setToolTip(wanDualNoise ? QStringLiteral("Controls how WAN dual-noise sampling is split between the high-noise and low-noise models.") : QStringLiteral("Available when WAN dual-noise mode is active."));
}

void ImageGenerationPage::pinVideoFamily(const QString &family)
{
    if (!videoFamilyCombo_)
        return; // image page: no video family bar
    const QString f = family.trimmed().toLower();
    // The bar only offers Auto / Wan / LTX. Other video families (hunyuan/cog/mochi) stay on Auto,
    // which resolves from the primary model once one is selected.
    if (f == QStringLiteral("wan"))
        selectComboValue(videoFamilyCombo_, QStringLiteral("wan"));
    else if (f == QStringLiteral("ltx"))
        selectComboValue(videoFamilyCombo_, QStringLiteral("ltx"));
}


void ImageGenerationPage::updateOperatingPointSelector()
{
    if (!operatingPointCard_ || !operatingPointButtonRow_ || !operatingPointGroup_)
        return;

    const QString family = isVideoMode()
        ? resolvedVideoFamilyForSelector()
        : modelFamilyByValue_.value(selectedModelPath_).trimmed().toLower();
    applyFamilySamplingChoices(family);
    QJsonArray points;
    QString defaultPoint;
    if (operatingPointsProvider_ && !family.isEmpty())
    {
        const QJsonObject table = operatingPointsProvider_(family);
        points = table.value(QStringLiteral("operating_points")).toArray();
        defaultPoint = table.value(QStringLiteral("default_operating_point")).toString();
    }
    if (family == QStringLiteral("krea2"))
        defaultPoint = krea2OperatingPointForPath(selectedModelPath_);

    // >1 point -> show a selector; <=1 -> hide it entirely (nothing to choose).
    if (points.size() <= 1)
    {
        operatingPointCard_->setVisible(false);
        currentOperatingPoints_ = {};
        currentOperatingPoint_.clear();
        operatingPointFamily_.clear();
        if (family == QStringLiteral("krea2"))
        {
            const bool raw = defaultPoint == QStringLiteral("raw");
            if (sampling_->stepsSpin())
                sampling_->stepsSpin()->setValue(raw ? 52 : 8);
            if (sampling_->cfgSpin())
                sampling_->cfgSpin()->setValue(raw ? 3.5 : 1.0);
            if (sampling_->samplerCombo() && !selectComboValue(sampling_->samplerCombo(), QStringLiteral("euler")))
                selectComboByContains(sampling_->samplerCombo(), {QStringLiteral("euler")});
            if (sampling_->schedulerCombo() && !selectComboValue(sampling_->schedulerCombo(), QStringLiteral("simple")))
                selectComboByContains(sampling_->schedulerCombo(), {QStringLiteral("simple")});
        }
        return;
    }

    // Rebuild the buttons only when the family (hence the point set) changed.
    if (family != operatingPointFamily_ || operatingPointGroup_->buttons().size() != points.size())
    {
        for (QAbstractButton *b : operatingPointGroup_->buttons())
        {
            operatingPointGroup_->removeButton(b);
            b->deleteLater();
        }
        while (QLayoutItem *item = operatingPointButtonRow_->takeAt(0))
        {
            if (item->widget())
                item->widget()->deleteLater();
            delete item;
        }
        for (const QJsonValue &v : points)
        {
            const QJsonObject point = v.toObject();
            auto *btn = new QPushButton(operatingPointLabel(point), operatingPointCard_);
            btn->setObjectName(QStringLiteral("OperatingPointButton"));
            btn->setCheckable(true);
            btn->setCursor(Qt::PointingHandCursor);
            const QString name = point.value(QStringLiteral("name")).toString();
            btn->setProperty("opName", name);
            operatingPointGroup_->addButton(btn);
            operatingPointButtonRow_->addWidget(btn);
        }
        operatingPointButtonRow_->addStretch(1);
        operatingPointFamily_ = family;
        currentOperatingPoints_ = points;
        // Apply the default point so the visible controls immediately MATCH what will run (no hidden
        // state -- the whole point). The user picks Fast/Quality to switch; a manual control edit after
        // is their override, and re-picking a point resets it. Applies once per family change.
        const QString toSelect = defaultPoint.isEmpty()
                                     ? points.first().toObject().value(QStringLiteral("name")).toString()
                                     : defaultPoint;
        applyOperatingPoint(toSelect);
    }
    else if (family == QStringLiteral("krea2") && !defaultPoint.isEmpty()
             && defaultPoint != currentOperatingPoint_)
    {
        applyOperatingPoint(defaultPoint);
    }

    operatingPointCard_->setVisible(true);
}

void ImageGenerationPage::removeOperatingPointLoras()
{
    if (operatingPointLoras_.isEmpty())
        return;
    QSet<QString> targets;
    for (const QString &v : operatingPointLoras_)
        targets.insert(spellvision::assets::ModelStackState::normalizedPath(v));
    loraStack_.erase(std::remove_if(loraStack_.begin(), loraStack_.end(),
                                    [&](const spellvision::assets::LoraStackEntry &e) { return targets.contains(e.value); }),
                     loraStack_.end());
    operatingPointLoras_.clear();
    if (loraStackController_)
        loraStackController_->rebuild();
    scheduleUiRefresh(0);
}

void ImageGenerationPage::applyOperatingPoint(const QString &name)
{
    QJsonObject point;
    for (const QJsonValue &v : currentOperatingPoints_)
    {
        if (v.toObject().value(QStringLiteral("name")).toString() == name)
        {
            point = v.toObject();
            break;
        }
    }
    if (point.isEmpty())
        return;

    currentOperatingPoint_ = name;
    const QJsonObject params = point.value(QStringLiteral("params")).toObject();

    // Write the bundle into the VISIBLE controls -- the user sees exactly what will run, no hidden state.
    if (params.contains(QStringLiteral("steps")) && sampling_->stepsSpin())
        sampling_->stepsSpin()->setValue(params.value(QStringLiteral("steps")).toInt());
    if (params.contains(QStringLiteral("cfg")) && sampling_->cfgSpin())
        sampling_->cfgSpin()->setValue(params.value(QStringLiteral("cfg")).toDouble());
    // Video routes the sampler/scheduler through the VIDEO combos (the ones actually shown + sent for
    // video); image mode uses the image combos. Operating points are video-only today, but guard both.
    QComboBox *samplerTarget = (isVideoMode() && sampling_->videoSamplerCombo()) ? sampling_->videoSamplerCombo() : sampling_->samplerCombo();
    QComboBox *schedulerTarget = (isVideoMode() && sampling_->videoSchedulerCombo()) ? sampling_->videoSchedulerCombo() : sampling_->schedulerCombo();
    if (params.contains(QStringLiteral("sampler")) && samplerTarget)
    {
        const QString s = params.value(QStringLiteral("sampler")).toString();
        if (!s.isEmpty() && !selectComboValue(samplerTarget, s))
            selectComboByContains(samplerTarget, {s});
    }
    if (params.contains(QStringLiteral("scheduler")) && schedulerTarget)
    {
        const QString s = params.value(QStringLiteral("scheduler")).toString();
        if (!s.isEmpty() && !selectComboValue(schedulerTarget, s))
            selectComboByContains(schedulerTarget, {s});
    }
    if (params.contains(QStringLiteral("shift")))
    {
        const double shift = params.value(QStringLiteral("shift")).toDouble();
        if (highNoiseShiftSpin_)
            highNoiseShiftSpin_->setValue(shift);
        if (lowNoiseShiftSpin_)
            lowNoiseShiftSpin_->setValue(shift);
    }

    // LoRA: Fast populates the VISIBLE stack with the declared accel LoRAs (so the user sees what they
    // got -- unlike the API path's silent inject); Quality removes the accel LoRAs the selector added
    // and leaves user-added content LoRAs alone.
    removeOperatingPointLoras();
    const QJsonObject lora = point.value(QStringLiteral("lora")).toObject();
    if (lora.value(QStringLiteral("accel")).toBool(false))
    {
        const int before = loraStack_.size();
        for (const QString &key : {QStringLiteral("high"), QStringLiteral("low")})
        {
            const QString fn = lora.value(key).toString().trimmed();
            if (fn.isEmpty())
                continue;
            if (!tryAddLoraByCandidate({fn, QFileInfo(fn).completeBaseName()}, 1.0, true))
                addLoraToStack(fn, fn); // fallback: add by filename even if the catalog match missed
        }
        for (int i = before; i < loraStack_.size(); ++i)
            operatingPointLoras_.push_back(loraStack_.at(i).value);
    }

    // Reflect the selection on the buttons + recompute readiness/preview chips.
    if (operatingPointGroup_)
        for (QAbstractButton *b : operatingPointGroup_->buttons())
            b->setChecked(b->property("opName").toString() == name);
    scheduleUiRefresh(0);
}
