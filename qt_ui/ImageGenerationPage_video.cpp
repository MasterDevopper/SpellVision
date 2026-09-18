#include "ImageGenerationPage.h"
#include "generation/ErrorPillLabel.h"
#include "ImageGenerationPage_units.h"
#include "shell/ModelsLibraryPaths.h"
#include "widgets/ElidingLabel.h"
#include "style/SvKit.h"

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
#include <QTimer>


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
    const QString rawFamily = modelFamilyByValue_.value(selectedModelPath_).trimmed().toLower();
    const bool isHunyuan = rawFamily.contains(QLatin1String("hunyuan"))
        || selectedModelPath_.contains(QStringLiteral("hunyuan"), Qt::CaseInsensitive);

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

    // Distilled LTX pins CFG 1 and ManualSigmas. FLUX.3 API ignores steps/cfg.
    if (stepsRow_)
        stepsRow_->setVisible(!isLtx && !isFlux3);
    if (cfgRow_)
        cfgRow_->setVisible(!isLtx && !isFlux3);

    // Hunyuan T2V is FluxGuidance + BasicGuider. Negative has nowhere to land.
    if (negativeRow_)
        negativeRow_->setVisible(!isHunyuan);
    if (negativeToggleButton_)
        negativeToggleButton_->setVisible(!isHunyuan);

    // Hosted BFL API: no CreateVideo sink to graft. Catalog also hides; this catches family hops.
    if (upscaleRow_)
        upscaleRow_->setVisible(!isFlux3);
}

// --- W2: the user's own edits -------------------------------------------------------------------

void ImageGenerationPage::watchForUserEdits()
{
    // `valueChanged` plus the ProgrammaticWrite depth, NOT `editingFinished`: editingFinished also
    // fires when focus merely leaves a box nobody typed in, which would mark a field the user never
    // touched and freeze it against every later model. `activated` (not currentIndexChanged) for
    // the combos, because applyFamilyChoices REBUILDS their items on each family change and
    // currentIndexChanged fires for that too -- activated is emitted only by a human choosing.
    auto watchSpin = [this](QSpinBox *spin, ResolvedField field) {
        if (spin)
            connect(spin, &QSpinBox::valueChanged, this, [this, field](int) { markUserEdited(field); });
    };
    auto watchDouble = [this](QDoubleSpinBox *spin, ResolvedField field) {
        if (spin)
            connect(spin, &QDoubleSpinBox::valueChanged, this, [this, field](double) { markUserEdited(field); });
    };
    auto watchCombo = [this](QComboBox *combo, ResolvedField field) {
        if (combo)
            connect(combo, &QComboBox::activated, this, [this, field](int) { markUserEdited(field); });
    };

    watchSpin(widthSpin_, ResolvedField::Width);
    watchSpin(heightSpin_, ResolvedField::Height);
    watchSpin(frameCountSpin_, ResolvedField::Frames);
    watchSpin(fpsSpin_, ResolvedField::Fps);
    watchDouble(highNoiseShiftSpin_, ResolvedField::Shift);
    watchDouble(lowNoiseShiftSpin_, ResolvedField::Shift);
    // The dual-noise trio. applyResolvedSettings writes all three from `steps / 2` and they were
    // watched by nothing, so a deliberate asymmetric split (20 high / 8 low, an MoE handoff the
    // user chose) was reset to 14 / 14 by the next Simple/Advanced toggle -- `steps` had never been
    // touched, so its guard was open. The sweep rule `resolved-fields-are-watched` now fails a
    // build in which applyResolvedSettings writes a spin box this function does not connect.
    watchSpin(highNoiseStepsSpin_, ResolvedField::SplitSteps);
    watchSpin(lowNoiseStepsSpin_, ResolvedField::SplitSteps);
    watchSpin(splitStepSpin_, ResolvedField::SplitSteps);
    if (sampling_)
    {
        watchSpin(sampling_->stepsSpin(), ResolvedField::Steps);
        watchDouble(sampling_->cfgSpin(), ResolvedField::Cfg);
        watchDouble(sampling_->guidanceSpin(), ResolvedField::Guidance);
        // Both halves of each pair: video mode drives the video combos and image mode the image
        // ones, and one page is only ever one of those -- but marking the logical FIELD rather than
        // the widget is what makes a sampler chosen in Advanced survive a Simple/Advanced round
        // trip, which writes through whichever pair the mode selects.
        watchCombo(sampling_->samplerCombo(), ResolvedField::Sampler);
        watchCombo(sampling_->videoSamplerCombo(), ResolvedField::Sampler);
        watchCombo(sampling_->schedulerCombo(), ResolvedField::Scheduler);
        watchCombo(sampling_->videoSchedulerCombo(), ResolvedField::Scheduler);
    }
}

bool ImageGenerationPage::userEdited(ResolvedField field) const
{
    // Two sets, one question. "The user typed this" is cleared by a deliberate model change; "this
    // came from the user's own content" is not, because picking a checkpoint is not a request to
    // resize the keyframe they staged. applyResolvedSettings asks only whether it may write.
    return userEditedFields_.contains(static_cast<int>(field))
        || contentDerivedFields_.contains(static_cast<int>(field));
}

void ImageGenerationPage::markUserEdited(ResolvedField field)
{
    if (programmaticWriteDepth_ > 0)
        return;
    userEditedFields_.insert(static_cast<int>(field));
}

void ImageGenerationPage::markContentDerived(ResolvedField field)
{
    // Deliberately NOT gated on programmaticWriteDepth_. The write that produced this value was the
    // app's (ensureCanvasSizeDefault, inside its own guard); what makes it the user's is the image
    // they chose, not the keystroke they did not make.
    contentDerivedFields_.insert(static_cast<int>(field));
}

void ImageGenerationPage::clearContentDerivedFields()
{
    contentDerivedFields_.clear();
}

void ImageGenerationPage::clearUserEditedFields()
{
    userEditedFields_.clear();
}

void ImageGenerationPage::applyResolvedSettings(const QJsonObject &values)
{
    if (values.isEmpty() || !sampling_)
        return;

    const ProgrammaticWrite guard(this);

    // Each field is written only if the answer CARRIES it and the user has not typed one. A field
    // the answer omits keeps whatever is already there -- that is what lets this model's own
    // settings overlay the family's rather than replacing them wholesale.
    auto field = [&values](const char *name) { return values.value(QLatin1String(name)); };

    const QJsonValue steps = field("steps");
    if (steps.isDouble() && !userEdited(ResolvedField::Steps) && sampling_->stepsSpin())
        sampling_->stepsSpin()->setValue(steps.toInt());
    const QJsonValue cfg = field("cfg");
    if (cfg.isDouble() && !userEdited(ResolvedField::Cfg) && sampling_->cfgSpin())
        sampling_->cfgSpin()->setValue(cfg.toDouble());
    // Distilled guidance. Written by exactly the same rules as every other field -- carried by the
    // answer, not typed by the user -- so a Flux model's published 3.5 now lands in a control the
    // request builder actually reads. Before 2026-09-18 there was no control, and the builder
    // derived this from the cfg box (Doc 62 3e).
    const QJsonValue guidance = field("guidance");
    if (guidance.isDouble() && !userEdited(ResolvedField::Guidance) && sampling_->guidanceSpin())
        sampling_->guidanceSpin()->setValue(guidance.toDouble());

    // Video routes sampler/scheduler through the VIDEO combos (the ones actually shown and sent for
    // video); image mode uses the image combos.
    QComboBox *samplerTarget = (isVideoMode() && sampling_->videoSamplerCombo())
                                   ? sampling_->videoSamplerCombo()
                                   : sampling_->samplerCombo();
    QComboBox *schedulerTarget = (isVideoMode() && sampling_->videoSchedulerCombo())
                                     ? sampling_->videoSchedulerCombo()
                                     : sampling_->schedulerCombo();
    const QString sampler = field("sampler").toString().trimmed();
    if (!sampler.isEmpty() && !userEdited(ResolvedField::Sampler) && samplerTarget
        && !selectComboValue(samplerTarget, sampler))
        selectComboByContains(samplerTarget, {sampler});
    const QString scheduler = field("scheduler").toString().trimmed();
    if (!scheduler.isEmpty() && !userEdited(ResolvedField::Scheduler) && schedulerTarget
        && !selectComboValue(schedulerTarget, scheduler))
        selectComboByContains(schedulerTarget, {scheduler});

    const QJsonValue shift = field("shift");
    if (shift.isDouble() && !userEdited(ResolvedField::Shift))
    {
        if (highNoiseShiftSpin_)
            highNoiseShiftSpin_->setValue(shift.toDouble());
        if (lowNoiseShiftSpin_)
            lowNoiseShiftSpin_->setValue(shift.toDouble());
    }

    // W2 Task 6: the canvas and the duration come from the same answer as the sampling values. The
    // legality rules -- LTX width/height divisible by 32, frame length (N*8)+1, mochi's and
    // hunyuan_video's own strides -- are NOT re-derived here. resolve.py snaps them, transcribed
    // from the one place each is actually enforced, and this writes what it is handed. A second
    // C++ copy of those rules is precisely the duplicate resolver this wave exists to remove.
    const QJsonValue width = field("width");
    if (width.toInt() >= 64 && !userEdited(ResolvedField::Width) && widthSpin_)
        widthSpin_->setValue(width.toInt());
    const QJsonValue height = field("height");
    if (height.toInt() >= 64 && !userEdited(ResolvedField::Height) && heightSpin_)
        heightSpin_->setValue(height.toInt());
    if (isVideoMode())
    {
        const QJsonValue frames = field("frames");
        if (frames.toInt() > 0 && !userEdited(ResolvedField::Frames) && frameCountSpin_)
            frameCountSpin_->setValue(frames.toInt());
        const QJsonValue fps = field("fps");
        if (fps.toInt() > 0 && !userEdited(ResolvedField::Fps) && fpsSpin_)
            fpsSpin_->setValue(fps.toInt());
    }

    // The dual-noise split boxes are the resolved step count expressed across two experts -- the
    // builder runs the high expert 0->N/2 and the low one N/2->N. They are not a second sampling
    // decision, so they follow the number above instead of carrying one of their own.
    if (steps.isDouble() && !userEdited(ResolvedField::Steps) && !userEdited(ResolvedField::SplitSteps)
        && usesWanDualNoiseMode() && resolvedVideoFamilyToken() == QStringLiteral("wan"))
    {
        const int half = qMax(1, steps.toInt() / 2);
        if (highNoiseStepsSpin_)
            highNoiseStepsSpin_->setValue(half);
        if (lowNoiseStepsSpin_)
            lowNoiseStepsSpin_->setValue(half);
        if (splitStepSpin_)
            splitStepSpin_->setValue(half);
    }

    // Last, and inside the same guard: whatever pair the resolver produced, the user's stated
    // orientation decides which way round it is shown. Applying it here rather than making it a
    // user-edit means a later model's own canvas still arrives -- it simply arrives the right way
    // up. A Portrait choice that FROZE the canvas would be the Aspect preset's behaviour, and the
    // reason Aspect cannot serve as the orientation control.
    applyOrientationPreference();
}

void ImageGenerationPage::applyOrientationPreference()
{
    if (!orientationCombo_ || !widthSpin_ || !heightSpin_)
        return;
    const QString wanted = orientationCombo_->currentData().toString();
    if (wanted.isEmpty())
        return;  // "As published" -- the resolver's pair, untouched.
    const int width = widthSpin_->value();
    const int height = heightSpin_->value();
    if (width < 64 || height < 64 || width == height)
        return;
    const bool isPortrait = height > width;
    if ((wanted == QStringLiteral("portrait")) == isPortrait)
        return;
    // A SWAP, not a new size: the long and short edges the model published are both kept, so the
    // pixel count, the divisibility the resolver snapped to and the family's own aspect all survive.
    const ProgrammaticWrite guard(this);
    widthSpin_->setValue(height);
    heightSpin_->setValue(width);
}

void ImageGenerationPage::applyOptimalVideoSamplingDefaults()
{
    if (!isVideoMode())
        return;

    // No numbers here any more. wan's 28 / 5.0 / uni_pc, ltx's 30 / 3.5 / 49 and flux3's 24 / 120
    // lived in this function as C++ literals that DUPLICATED and OVERRODE the table the worker
    // actually resolves from -- and had already drifted from it: the table says wan is CFG 4.0 on
    // euler, so the cockpit was showing a pair the render was never going to use. The family's
    // numbers now arrive through the same provider the Speed chips read, and this applies whatever
    // it is handed.
    //
    // Two deletions worth their own line. The wanSplitCombo_ "auto" write went with the numbers: it
    // re-forced auto over a manual split on every Simple/Advanced toggle, which is the overwrite
    // the user-edit flags exist to stop, and "auto" is already the combo's construction value and
    // what Reset restores. And flux3's 24 fps / 120 frames needed no data home, because they never
    // reached the API: build_flux3_payload sends `duration`, and _duration_seconds is
    // `max(5, min(20, round(frames/fps)))` -- 120/24 and the spin boxes' own 81/16 are both 5.
    //
    // resolvedVideoFamilyForSelector rather than resolvedVideoFamilyToken: the token answers "auto"
    // for the Auto family and no table is keyed that way, so the selector's resolver (which falls
    // through to the checkpoint) is the one that can actually name a family here.
    const QString family = resolvedVideoFamilyForSelector().trimmed().toLower();
    QJsonObject params;
    if (operatingPointsProvider_ && !family.isEmpty())
    {
        const QJsonObject table = operatingPointsProvider_(family);
        const QJsonArray points = table.value(QStringLiteral("operating_points")).toArray();
        const QString wanted = table.value(QStringLiteral("default_operating_point")).toString().trimmed();
        for (const QJsonValue &v : points)
        {
            const QJsonObject point = v.toObject();
            const bool isWanted = point.value(QStringLiteral("name")).toString() == wanted;
            if (params.isEmpty() || isWanted)
                params = point.value(QStringLiteral("params")).toObject();
            if (isWanted)
                break;
        }
    }
    applyResolvedSettings(params);

    // The hint reports what is SHOWING, read back off the controls, rather than what was sent to
    // them: a value the user typed is deliberately not overwritten above, and a caption naming the
    // family's number anyway would be describing a render nobody is going to get.
    if (readinessHintLabel_ && !params.isEmpty() && sampling_->stepsSpin() && sampling_->cfgSpin())
    {
        readinessHintLabel_->setHint(QStringLiteral("%1 sampling: %2 steps · CFG %3 (editable in Advanced).")
                                         .arg(family.toUpper())
                                         .arg(sampling_->stepsSpin()->value())
                                         .arg(sampling_->cfgSpin()->value(), 0, 'g', 3));
    }
    updateVideoStackModeUi();
}

void ImageGenerationPage::applySimpleOperatingPointDefaults()
{
    // Simple starts on the family table. Advanced keeps last-chose knobs.
    updateOperatingPointSelector();
    applyOptimalVideoSamplingDefaults();
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

QString ImageGenerationPage::remapWanTaskVariantPath(const QString &path) const
{
    // Live 2026-09-09: I2V Generate kept wan2.2_t2v_* experts. WanImageToVideo was wired
    // but T2V weights ignored the goblin keyframe (frame-0 MAE 79.13 vs proven i2v ~5.19).
    // If the matching i2v/t2v sibling exists on disk, swap. If not, leave the path so
    // the worker fail-closes instead of silently rendering the wrong task.
    const QString trimmed = path.trimmed();
    if (trimmed.isEmpty() || !isVideoMode())
        return trimmed;

    const bool wantI2v = (mode_ == Mode::ImageToVideo);
    QString remapped = trimmed;
    if (wantI2v)
    {
        remapped.replace(QStringLiteral("_t2v_"), QStringLiteral("_i2v_"), Qt::CaseInsensitive);
        remapped.replace(QStringLiteral("-t2v-"), QStringLiteral("-i2v-"), Qt::CaseInsensitive);
    }
    else
    {
        remapped.replace(QStringLiteral("_i2v_"), QStringLiteral("_t2v_"), Qt::CaseInsensitive);
        remapped.replace(QStringLiteral("-i2v-"), QStringLiteral("-t2v-"), Qt::CaseInsensitive);
    }
    if (remapped.compare(trimmed, Qt::CaseInsensitive) == 0)
        return trimmed;
    if (QFileInfo::exists(remapped))
        return remapped;
    return trimmed;
}

QString ImageGenerationPage::modelsLibraryRootFromSelected() const
{
    // Live I2V T3: umt5 + wan VAE sit on D:/AI_ASSETS/models next to the i2v experts,
    // while modelsRootDir_ / extraModelsRoots are F:/. Scan the selected checkpoint's
    // own models library so Auto can fill companions the worker already knows how to pick.
    const QString normalized = QDir::fromNativeSeparators(selectedModelPath_.trimmed()).toLower();
    const int idx = normalized.lastIndexOf(QLatin1String("/models/"));
    if (idx < 0)
        return QString();
    return QDir::fromNativeSeparators(selectedModelPath_.trimmed()).left(idx + 7);
}

void ImageGenerationPage::applyVideoFamilyCheckpointIfNeeded()
{
    // Live 2026-09-10: LTX tab said "resolves → LTX" / Ready while primary stayed
    // wan2.2_t2v_*. Same class of hole as I2V keeping T2V experts. If the user
    // picks a family, swap onto a matching checkpoint when one is in the combo.
    if (!isVideoMode() || !videoPrimaryModelCombo_)
        return;
    const QString family = resolvedVideoFamilyToken();
    auto matchesFamily = [&](const QString &path) -> bool {
        const QString h = path.toLower();
        if (family == QStringLiteral("ltx"))
            return h.contains(QStringLiteral("ltx")) && !h.contains(QStringLiteral("wan"));
        if (family == QStringLiteral("wan"))
            return h.contains(QStringLiteral("wan")) && !h.contains(QStringLiteral("ltx"));
        return true;
    };
    if (matchesFamily(selectedModelPath_))
        return;
    for (int i = 0; i < videoPrimaryModelCombo_->count(); ++i)
    {
        const QString value = videoPrimaryModelCombo_->itemData(i, Qt::UserRole).toString().trimmed();
        if (value.isEmpty() || !matchesFamily(value))
            continue;
        setSelectedModel(value, videoPrimaryModelCombo_->itemText(i));
        return;
    }
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

    QStringList roots = spellvision::shell::scannableModelsRoots(
        modelsRootDir_, spellvision::shell::extraModelsRootsFromSettings());
    const QString selectedLibrary = modelsLibraryRootFromSelected();
    if (!selectedLibrary.isEmpty())
    {
        bool have = false;
        for (const QString &root : roots)
        {
            if (QDir::fromNativeSeparators(root).compare(selectedLibrary, Qt::CaseInsensitive) == 0)
            {
                have = true;
                break;
            }
        }
        if (!have)
            roots.prepend(selectedLibrary);
    }

    QVector<CatalogEntry> primaryEntries;
    for (const QString &root : roots)
    {
        for (const QString &dir : {QStringLiteral("diffusion_models"), QStringLiteral("unet"), QStringLiteral("video"), QStringLiteral("wan"), QStringLiteral("ltx"), QStringLiteral("hunyuan_video"), QStringLiteral("checkpoints")})
        {
            QVector<CatalogEntry> filtered;
            for (CatalogEntry entry : scanCatalog(root, dir))
            {
                if (!looksVideoPrimary(entry))
                    continue;
                entry.note = QStringLiteral("Primary video diffusion model");
                filtered.push_back(entry);
            }
            appendUnique(primaryEntries, filtered, QString(), QStringLiteral("primary"));
        }
    }

    QVector<CatalogEntry> textEntries;
    QVector<CatalogEntry> vaeEntries;
    QVector<CatalogEntry> visionEntries;
    for (const QString &root : roots)
    {
        appendUnique(textEntries, scanCatalog(root, QStringLiteral("text_encoders")), QString(), QStringLiteral("text_encoder"));
        appendUnique(textEntries, scanCatalog(root, QStringLiteral("clip")), QString(), QStringLiteral("text_encoder"));
        appendUnique(vaeEntries, scanCatalog(root, QStringLiteral("vae")), QString(), QStringLiteral("vae"));
        appendUnique(visionEntries, scanCatalog(root, QStringLiteral("clip_vision")), QString(), QStringLiteral("clip_vision"));
        appendUnique(visionEntries, scanCatalog(root, QStringLiteral("image_encoders")), QString(), QStringLiteral("clip_vision"));
    }

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
                                remapWanTaskVariantPath(
                                    stack.value(QStringLiteral("primary_path")).toString().trimmed().isEmpty()
                                        ? selectedModelPath_
                                        : stack.value(QStringLiteral("primary_path")).toString().trimmed()));
    setVideoComponentComboValue(videoHighNoiseModelCombo_,
                                remapWanTaskVariantPath(
                                    stack.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty()
                                        ? stack.value(QStringLiteral("high_noise_model_path")).toString()
                                        : stack.value(QStringLiteral("high_noise_path")).toString()));
    setVideoComponentComboValue(videoLowNoiseModelCombo_,
                                remapWanTaskVariantPath(
                                    stack.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty()
                                        ? stack.value(QStringLiteral("low_noise_model_path")).toString()
                                        : stack.value(QStringLiteral("low_noise_path")).toString()));
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

void ImageGenerationPage::setModelDefaultsProvider(
    std::function<QJsonObject(const QString &, const QString &, const QString &)> provider)
{
    // Store only. Unlike setOperatingPointsProvider, this does NOT refresh the selector: the family
    // table is app-wide and worth re-rendering the moment it arrives, while this answers a question
    // about the selected model -- and at the moment MainWindow wires it, no model is selected.
    modelDefaultsProvider_ = std::move(provider);
}

void ImageGenerationPage::setModelDefaultsFetcher(
    std::function<void(const QString &, const QString &, const QString &, std::function<void()>)> fetcher)
{
    modelDefaultsFetcher_ = std::move(fetcher);
}

void ImageGenerationPage::refreshModelDefaults()
{
    applyModelDefaults();
}

void ImageGenerationPage::requestModelDefaults(const QString &family)
{
    // Recorded BEFORE the early-outs. applyModelDefaults reads the cache with this family, and the
    // cache is keyed on it -- so a page that asked for one family and then looked up another would
    // simply miss its own answer. It is also the fix for the coalescing hazard below: the LAST ask
    // in an event-loop turn owns the widgets, so it owns the family the lookup uses.
    modelDefaultsFamily_ = family.trimmed().toLower();
    if (selectedModelPath_.trimmed().isEmpty())
    {
        // No model, nothing to overlay -- but the caption must stop describing the last one.
        applyModelDefaults();
        return;
    }
    if (modelDefaultsRequestScheduled_)
        return; // a burst of selector refreshes inside one event-loop turn is one ask

    modelDefaultsRequestScheduled_ = true;
    const QString path = selectedModelPath_;
    const QString mode = modeKey();
    // Deferred for exactly the reason setSelectedModel already defers its component resolve, and
    // the comment there is the record of what happens otherwise: a worker round-trip runs a nested
    // event loop, and starting one from inside a combo-change handler re-enters the UI with the
    // popup possibly still open, and crashes. singleShot(0) runs it on a clean stack.
    QTimer::singleShot(0, this, [this, path, mode]() {
        modelDefaultsRequestScheduled_ = false;
        // The family is read HERE, not captured at schedule time. applyVideoFamilyCheckpointIfNeeded
        // and the family combo's own handler both fire inside one turn, and capturing the first
        // ask's family cached whichever ran first -- so the answer the page then applied was an
        // answer about a family the bar is no longer showing.
        const QString familyKey = modelDefaultsFamily_;
        if (path.compare(selectedModelPath_, Qt::CaseInsensitive) != 0)
            return; // the user moved on while this was queued; the newer ask owns the widgets
        if (!modelDefaultsFetcher_)
        {
            // No worker wired (a test, or a page built without one). The provider may still answer,
            // and if it does not, applyModelDefaults leaves the family operating point alone.
            applyModelDefaults();
            return;
        }
        const QPointer<ImageGenerationPage> guard(this);
        modelDefaultsFetcher_(path, familyKey, mode, [guard, path]() {
            if (!guard)
                return;
            if (path.compare(guard->selectedModelPath_, Qt::CaseInsensitive) != 0)
                return;
            guard->applyModelDefaults();
        });
    });
}

namespace
{
// Every entry in the reply's `settings` is {value, provenance, confidence, n, total}. This reaches
// past that envelope for the number the widget wants, and returns an undefined QJsonValue for a
// field the model did not mention -- which is what keeps an unmentioned field on the family's
// value instead of clearing it.
QJsonValue modelDefaultValue(const QJsonObject &settings, const QString &field)
{
    const QJsonValue entry = settings.value(field);
    if (!entry.isObject())
        return {};
    return entry.toObject().value(QStringLiteral("value"));
}
} // namespace

void ImageGenerationPage::applyModelDefaults()
{
    QJsonObject reply;
    if (modelDefaultsProvider_ && !selectedModelPath_.trimmed().isEmpty())
        reply = modelDefaultsProvider_(selectedModelPath_, modelDefaultsFamily_, modeKey());

    const QJsonObject settings = reply.value(QStringLiteral("settings")).toObject();

    // Spec ruling R2.1: this applies in BOTH modes, and there is deliberately no `advanced_` test
    // anywhere in this function. Simple applies it because the user will not change it; Advanced
    // applies it because a pre-filled correct value is the entire point, and the house rule is that
    // Advanced REVEALS IN PLACE rather than starting from nothing -- the user edits the number
    // afterwards, in the control it was already sitting in. Treating the pre-fill as a Simple-mode
    // convenience is the tempting shortcut and it is the wrong one.
    //
    // This is an OVERLAY, not a replacement. The caller has already applied the family operating
    // point, so a field the model does not mention keeps the family's value; only fields the
    // resolver actually answered are written here. It writes the same widgets applyOperatingPoint
    // writes, by the same rules, because since W2 Task 6 it writes them through the SAME function.
    //
    // Peel the envelope off every field the resolver answered and hand the flat map to that one
    // applier. Task 6 added width/height/frames/fps to what the resolver answers, and this loop is
    // why that needed no change here: a field the model does not mention is simply not in the map.
    QJsonObject values;
    for (auto it = settings.constBegin(); it != settings.constEnd(); ++it)
    {
        const QJsonValue value = modelDefaultValue(settings, it.key());
        if (!value.isUndefined() && !value.isNull())
            values.insert(it.key(), value);
    }

    // Doc 62 3f: a preset and a model's defaults both write steps and CFG, and neither knew the
    // other existed, so the last one to fire won and the user could not tell which they were
    // looking at. The ruling: **a preset is a deliberate user choice and wins until the model
    // changes.** So exactly the fields the current preset owns are dropped from this overlay --
    // not all of them, because the overlay's whole value is that a field the preset does NOT set
    // still gets the model's answer. `setSelectedModel` clears the record on a model change, which
    // is the other half of the sentence.
    //
    // A preset's writes reach the widgets outside a ProgrammaticWrite scope, so they already trip
    // markUserEdited -- for a spin box whose value actually MOVED. That near-miss is why the
    // record is explicit: `setValue(30)` on a box already showing 30 emits nothing, and the
    // combos are watched on `activated`, which a programmatic selectComboValue never emits, so a
    // preset's sampler and scheduler were never protected at all.
    for (const QString &field : presetOwnedFields_)
        values.remove(field);

    // The DATA answer to "does this family steer with distilled guidance": it published one. See
    // ImageGenerationPage.h. Read before the preset filter would matter -- a preset never sets
    // guidance, so the two cannot interact -- and applied through updateDisclosure so the row's
    // visibility keeps its single owner.
    guidanceOffered_ = settings.contains(QStringLiteral("guidance"));
    if (guidanceRow_)
        guidanceRow_->setVisible(advanced_ && guidanceOffered_);

    applyResolvedSettings(values);

    refreshModelDefaultsCaption(reply);
}

namespace
{
// Where a number came from, at the coarseness a caption can honestly report. This is NOT a second
// copy of the precedence order -- that lives in model_intelligence/resolve.py and restating it here
// is exactly the duplicate resolver this wave exists to remove. It groups the provenance strings
// into the four places a user would recognise, so the caption names WHERE rather than which rule won.
enum class DefaultsSource
{
    None = 0,
    Table = 1,   // table:family-operating-point / table:family-default
    Card = 2,    // card:frontmatter / card:snippet-regex / card:prose-regex
    Site = 3,    // site:image-meta-mode / site:trainedWords / site:image-meta-weak
    User = 4,    // a value the user pinned on the Models page
};

DefaultsSource sourceOfProvenance(const QString &provenance)
{
    if (provenance.startsWith(QStringLiteral("user")))
        return DefaultsSource::User;
    if (provenance.startsWith(QStringLiteral("site:")))
        return DefaultsSource::Site;
    if (provenance.startsWith(QStringLiteral("card:")))
        return DefaultsSource::Card;
    if (provenance.startsWith(QStringLiteral("table:")))
        return DefaultsSource::Table;
    return DefaultsSource::None;
}
} // namespace

void ImageGenerationPage::refreshModelDefaultsCaption(const QJsonObject &reply)
{
    if (!modelDefaultsCaptionLabel_)
        return;

    const QJsonObject settings = reply.value(QStringLiteral("settings")).toObject();
    // Nothing to report: no model, or no answer yet / the worker could not be reached. Saying
    // "family defaults" here would be a claim we have not earned -- we do not know what this model
    // wants, which is different from knowing it publishes nothing.
    if (selectedModelPath_.trimmed().isEmpty() || settings.isEmpty())
    {
        modelDefaultsCaptionLabel_->setVisible(false);
        return;
    }

    DefaultsSource best = DefaultsSource::None;
    int agreeCount = 0;
    int agreeTotal = 0;
    bool capped = false;
    for (auto it = settings.constBegin(); it != settings.constEnd(); ++it)
    {
        const QJsonObject entry = it.value().toObject();
        QString provenance = entry.value(QStringLiteral("provenance")).toString().trimmed();
        // A capped field keeps its provenance with ":capped" appended, so the caption can say the
        // number shown is not the number the model asked for.
        if (provenance.endsWith(QStringLiteral(":capped")))
        {
            capped = true;
            provenance.chop(QStringLiteral(":capped").size());
        }
        const DefaultsSource source = sourceOfProvenance(provenance);
        if (source <= best)
            continue;
        best = source;
        agreeCount = entry.value(QStringLiteral("n")).toInt();
        agreeTotal = entry.value(QStringLiteral("total")).toInt();
    }

    bool noSidecar = false;
    const QJsonArray warnings = reply.value(QStringLiteral("warnings")).toArray();
    for (const QJsonValue &w : warnings)
    {
        if (w.toString().contains(QStringLiteral("no sidecar"), Qt::CaseInsensitive))
            noSidecar = true;
    }

    QString caption;
    switch (best)
    {
    case DefaultsSource::User:
        caption = QStringLiteral("Defaults you saved for this model");
        break;
    case DefaultsSource::Site:
        caption = QStringLiteral("Defaults from this model's CivitAI examples");
        if (agreeCount > 0 && agreeTotal > 0)
            caption += QStringLiteral(" · %1 of %2 agree").arg(agreeCount).arg(agreeTotal);
        break;
    case DefaultsSource::Card:
        caption = QStringLiteral("Defaults from the model card");
        break;
    case DefaultsSource::Table:
    case DefaultsSource::None:
        // Two different situations, and conflating them is what sends a user looking for a setting
        // that was never published. The difference is worth a sentence, and the first one may now
        // name an action again: W5 Task 4 built "Refresh metadata" on the Models page -- a real
        // control, beside "Refresh Models", that starts a model_intel_refresh and writes the
        // sidecar this branch is missing. W2 had to delete this sentence because the button did
        // not exist; restoring it is the other half of that ruling, and it is restored here rather
        // than paraphrased so the words on screen match the words on the button.
        caption = noSidecar
            ? QStringLiteral("Family defaults · run Refresh metadata on the Models page to use "
                             "this model's own")
            : QStringLiteral("Family defaults (this model has no published settings)");
        break;
    }
    // NOT "reduced to fit VRAM". That states as fact something the code does not know: the cap is a
    // rough pixels-per-gigabyte heuristic that has never been measured against any family, and the
    // sentence saying so lives in a `warnings` array this function throws away. The visible string
    // now claims exactly what was done and on what basis.
    if (capped)
        caption += QStringLiteral(" · canvas reduced by a rough VRAM estimate");

    // setFullText, not setText: the label elides to whatever width the inspector gives it and keeps
    // the full sentence in the tooltip, so no width cuts this mid-word. Shown in BOTH modes.
    modelDefaultsCaptionLabel_->setFullText(caption);
    modelDefaultsCaptionLabel_->setVisible(true);
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
    QJsonObject ltxTextChoices;
    ltxTextChoices.insert(QStringLiteral("text_encoder"), names(videoTextEncoderCombo_));
    QJsonObject visionChoices;
    visionChoices.insert(QStringLiteral("clip_name"), names(videoClipVisionCombo_));

    QJsonObject choices;
    choices.insert(QStringLiteral("VAELoader"), vaeChoices);
    choices.insert(QStringLiteral("CLIPLoader"), textChoices);
    choices.insert(QStringLiteral("LTXAVTextEncoderLoader"), ltxTextChoices);
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
        // A sidecar/stack companion wins ONLY if it is in the worker's valid set.
        // Live 2026-09-09: I2V remapped t2v->i2v experts but catalog stack still had
        // clip_l + an onTHEFLY VAE; those overrides beat umt5 and blocked Generate.
        const QString overrideValue = stack.value(QString::fromLatin1(keys[i])).toString().trimmed();
        const QStringList valid = videoComponentValidOptions_.value(comp);
        auto companionInValidSet = [&](const QString &candidate) -> bool {
            if (candidate.isEmpty() || valid.isEmpty())
                return false;
            const QString base = QFileInfo(candidate).fileName().toLower();
            for (const QString &opt : valid)
            {
                if (QFileInfo(opt).fileName().toLower() == base)
                    return true;
            }
            return false;
        };
        const bool overrideValid = companionInValidSet(overrideValue);
        const QString autoValue = videoAutoFilledValues_.value(comp);
        const QString value = overrideValid ? overrideValue
                                            : (companionInValidSet(autoValue) ? autoValue : QString());
        if (!value.isEmpty())
            setVideoComboToBasename(combo, value);
        else if (!overrideValue.isEmpty() && !overrideValid)
            setVideoComponentComboValue(combo, QString());
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

    // Manual combo pick must drop the T3 block Auto-resolve left behind.
    // Live 2026-09-10: Gemma was on Text, VAE was video, Generate still no-op'd.
    auto dropMissingIfPicked = [this](QComboBox *combo, const QString &comp) {
        if (combo && combo->currentIndex() > 0)
            videoMissingRequiredComponents_.removeAll(comp);
    };
    dropMissingIfPicked(videoTextEncoderCombo_, QStringLiteral("text_encoder"));
    dropMissingIfPicked(videoVaeCombo_, QStringLiteral("vae"));
    dropMissingIfPicked(videoClipVisionCombo_, QStringLiteral("clip_vision"));

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

    // Dual-noise, core Wan, LTX, Hunyuan, Mochi all decode through vae_decode_node.
    // Hiding this on dual-noise was leftover from when that builder hardcoded VAEDecode.
    if (enableVaeTilingRow_)
        enableVaeTilingRow_->setVisible(true);

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
    // W2: ask what THIS model wants. Above both of this function's exits on purpose -- a family
    // with one operating point (or none) returns early below, and that is precisely the case where
    // the model's own published settings are the only thing there is to show. The ask is deferred,
    // so it lands after the family point has been applied and overlays it rather than racing it.
    requestModelDefaults(family);
    QJsonArray points;
    QString defaultPoint;
    if (operatingPointsProvider_ && !family.isEmpty())
    {
        const QJsonObject table = operatingPointsProvider_(family);
        points = table.value(QStringLiteral("operating_points")).toArray();
        defaultPoint = table.value(QStringLiteral("default_operating_point")).toString();
    }
    // W2 Task 7: krea2 used to be special-cased twice right here -- once to pick `raw` vs `turbo`
    // by testing the FILENAME for "turbo" (krea2OperatingPointForPath, now deleted), and once to
    // write that choice's 52/3.5 or 8/1.0 as literals. The filename test is wrong for the owner's
    // own loxsUtopicWorldKrea2_v20Quants, whose author publishes 10 steps and whose name says
    // neither word; resolve.py reads the variant off the sidecar's identity and falls back to the
    // same substring only when there is nothing better, so the answer is now right for that model
    // and arrives through requestModelDefaults above like every other model's.

    // >1 point -> show a selector; <=1 -> hide it entirely (nothing to choose).
    if (points.size() <= 1)
    {
        operatingPointCard_->setVisible(false);
        currentOperatingPoints_ = {};
        currentOperatingPoint_.clear();
        operatingPointFamily_.clear();
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
            // Said at the creation site: an operating point is a chip, and this row is rebuilt on
            // every family change, so the role has to be set here rather than once at construction.
            spellvision::kit::setRole(btn, spellvision::style::Role::Chip);
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
    else if (!defaultPoint.isEmpty())
    {
        applyOperatingPoint(defaultPoint);
    }

    operatingPointCard_->setVisible(advanced_);
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

    // Write the bundle into the VISIBLE controls -- the user sees exactly what will run, no hidden
    // state. Through applyResolvedSettings, which is also what this model's own settings go
    // through: one applier, so the family point and the model overlay cannot disagree about which
    // widget a field lands in, and W2's canvas/duration fields (the point now carries width,
    // height, frames and fps beside steps and cfg) arrive here without a second copy of the logic.
    applyResolvedSettings(point.value(QStringLiteral("params")).toObject());

    // LoRA: Fast populates the VISIBLE stack with the declared accel LoRAs (so the user sees what they
    // got -- unlike the API path's silent inject); Quality removes the accel LoRAs the selector added
    // and leaves user-added content LoRAs alone.
    removeOperatingPointLoras();
    const QJsonObject lora = point.value(QStringLiteral("lora")).toObject();
    if (lora.value(QStringLiteral("accel")).toBool(false))
    {
        // The pair is per TASK VARIANT. The dual-noise builder serves t2v and i2v from one graph and
        // already refuses a mixed expert pair as off-model; the accel LoRAs are the same model choice
        // one layer down, and this page used to add the t2v pair on an i2v job. There is deliberately
        // no flat high/low fallback: a point that declares no pair for this command adds nothing here
        // and the worker refuses the render, rather than either side quietly borrowing the other
        // variant's weights.
        const QString task = (mode_ == Mode::ImageToVideo) ? QStringLiteral("i2v") : QStringLiteral("t2v");
        const QJsonObject pair = lora.value(task).toObject();
        const int before = loraStack_.size();
        for (const QString &key : {QStringLiteral("high"), QStringLiteral("low")})
        {
            const QString fn = pair.value(key).toString().trimmed();
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
