#include "ImageGenerationPage.h"
#include "ImageGenerationPage_units.h"
#include "generation/GenerationResultRouter.h"

#include <QAbstractItemView>
#include <QCheckBox>
#include <QColor>
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
#include <QPainterPath>
#include <QPixmap>
#include <QPolygonF>
#include <QPushButton>
#include <QSettings>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QStandardPaths>
#include <QStringList>

namespace {

QPixmap sessionLoadingTile(int size, bool video)
{
    QPixmap pm(size, size);
    pm.fill(Qt::transparent);
    QPainter p(&pm);
    p.setRenderHint(QPainter::Antialiasing, true);
    ThemeManager &tm = ThemeManager::instance();
    QPainterPath path;
    path.addRoundedRect(QRectF(0.5, 0.5, size - 1.0, size - 1.0), 8, 8);
    p.fillPath(path, tm.color(ThemeManager::Color::Surface2));
    p.setPen(QPen(tm.color(ThemeManager::Color::Border), 1.0));
    p.drawPath(path);
    if (video)
    {
        p.setBrush(tm.color(ThemeManager::Color::TextMid));
        p.setPen(Qt::NoPen);
        const double c = size / 2.0;
        const double r = size * 0.16;
        QPolygonF tri;
        tri << QPointF(c - r * 0.6, c - r) << QPointF(c - r * 0.6, c + r) << QPointF(c + r, c);
        p.drawPolygon(tri);
    }
    p.end();
    return pm;
}

void paintPlayBadge(QPixmap &pm)
{
    QPainter p(&pm);
    p.setRenderHint(QPainter::Antialiasing, true);
    const int s = qMin(pm.width(), pm.height());
    const double d = s * 0.34;
    const QRectF badge(6.0, pm.height() - d - 6.0, d, d);
    p.setPen(Qt::NoPen);
    p.setBrush(QColor(0, 0, 0, 150));
    p.drawEllipse(badge);
    p.setBrush(QColor(255, 255, 255, 235));
    const double cx = badge.center().x();
    const double cy = badge.center().y();
    const double r = d * 0.22;
    QPolygonF tri;
    tri << QPointF(cx - r * 0.6, cy - r) << QPointF(cx - r * 0.6, cy + r) << QPointF(cx + r, cy);
    p.drawPolygon(tri);
    p.end();
}

QString writeSessionPoster(const QString &videoPath, const QImage &frame)
{
    if (frame.isNull())
        return {};
    QString base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    if (base.trimmed().isEmpty())
        base = QDir::current().filePath(QStringLiteral("runtime/cache/ui"));
    QDir dir(base);
    dir.mkpath(QStringLiteral("session_posters"));
    const QString name = QString::fromLatin1(
                             QCryptographicHash::hash(videoPath.toUtf8(), QCryptographicHash::Md5).toHex())
                         + QStringLiteral(".png");
    const QString out = QDir(dir.filePath(QStringLiteral("session_posters"))).filePath(name);
    return frame.save(out, "PNG") ? out : QString();
}

} // namespace


void ImageGenerationPage::showImagePreviewSurface()
{
    if (mediaPreviewController_)
    {
        mediaPreviewController_->showImageSurface();
        return;
    }

    if (previewStack_ && previewImagePage_)
        previewStack_->setCurrentWidget(previewImagePage_);
}

void ImageGenerationPage::playPreviewVideo()
{
    if (mediaPreviewController_)
        mediaPreviewController_->play();
}

void ImageGenerationPage::pausePreviewVideo()
{
    if (mediaPreviewController_)
        mediaPreviewController_->pause();
}

void ImageGenerationPage::stopPreviewVideoPlayback()
{
    if (mediaPreviewController_)
        mediaPreviewController_->stopPlayback();
}

void ImageGenerationPage::restartPreviewVideo()
{
    if (mediaPreviewController_)
        mediaPreviewController_->restart();
}

void ImageGenerationPage::stepPreviewVideoFrames(int frameDelta)
{
    if (mediaPreviewController_)
        mediaPreviewController_->stepFrames(frameDelta);
}

void ImageGenerationPage::seekPreviewVideo(qint64 positionMs, bool preservePlaybackState)
{
    if (mediaPreviewController_)
        mediaPreviewController_->seek(positionMs, preservePlaybackState);
}

void ImageGenerationPage::setPreviewPlaybackRate(double rate)
{
    if (mediaPreviewController_)
        mediaPreviewController_->setPlaybackRate(rate);
}

void ImageGenerationPage::handlePreviewMediaStatus(int)
{
    updateVideoTransportUi();
}

void ImageGenerationPage::updateVideoTransportUi()
{
    if (mediaPreviewController_)
        mediaPreviewController_->updateTransportUi();
}

QString ImageGenerationPage::formatDurationLabel(qint64 milliseconds) const
{
    return spellvision::preview::MediaPreviewController::formatDurationLabel(milliseconds);
}

QString ImageGenerationPage::formatFileSizeLabel(qint64 bytes) const
{
    return spellvision::preview::MediaPreviewController::formatFileSizeLabel(bytes);
}

void ImageGenerationPage::updateVideoCaption(const QString &, const QString &)
{
    if (mediaPreviewController_)
        mediaPreviewController_->updateCaption();
}

void ImageGenerationPage::showVideoPreviewSurface(const QString &videoPath, const QString &caption)
{
    suppressStartupVideoPreviewRestore_ = false;

    if (!mediaPreviewController_)
    {
        showImagePreviewSurface();
        return;
    }

    mediaPreviewController_->showVideoSurface(videoPath, caption);

    // Whenever a session-strip video is on screen without a poster yet, (re)attempt the frame grab --
    // covers restore/click timings that fall outside the initial record-time capture window.
    for (const SessionOutput &o : sessionOutputs_)
        if (o.path == videoPath.trimmed() && o.posterPath.isEmpty())
        {
            captureVideoPosterIfNeeded(videoPath.trimmed());
            break;
        }
}

void ImageGenerationPage::stopVideoPreview()
{
    if (mediaPreviewController_)
        mediaPreviewController_->clearVideoPreview();
}

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

    // Show the arcane empty-state surface only when there is no image/input; a rendered image
    // flips to previewLabel_ (the single source of truth: visualEmptyState). This is the gate-#2
    // guarantee that the sigil never overlays a result.
    if (previewImageInnerStack_ && canvasEmptyState_)
        previewImageInnerStack_->setCurrentWidget(visualEmptyState
                                                      ? canvasEmptyState_
                                                      : static_cast<QWidget *>(previewLabel_));

    const AdaptiveLayoutMode mode = currentAdaptiveLayoutMode();
    const int desiredMinHeight = geometryNeedsEmptyCanvas
        ? (mode == AdaptiveLayoutMode::Compact ? 340 : 420)
        : 0;

    if (previewLabel_->minimumHeight() != desiredMinHeight)
    {
        previewLabel_->setMinimumHeight(desiredMinHeight);
        changed = true;
    }
    // The inner stack (not just the label) carries the empty-canvas floor, since the empty-state
    // page -- not previewLabel_ -- is current when there is no image.
    if (previewImageInnerStack_ && previewImageInnerStack_->minimumHeight() != desiredMinHeight)
        previewImageInnerStack_->setMinimumHeight(desiredMinHeight);

    if (previewLabel_->maximumHeight() != QWIDGETSIZE_MAX)
    {
        previewLabel_->setMaximumHeight(QWIDGETSIZE_MAX);
        changed = true;
    }

    if (changed)
        repolishWidget(previewLabel_);
}

void ImageGenerationPage::updateCanvasEmptyState(const QString &message)
{
    // Split the "Title\n\nSub" empty-state message into the mockup's title + subtitle.
    if (canvasEmptyTitle_)
    {
        const int sep = message.indexOf(QStringLiteral("\n\n"));
        if (sep >= 0)
        {
            canvasEmptyTitle_->setText(message.left(sep).trimmed());
            if (canvasEmptySub_)
                canvasEmptySub_->setText(message.mid(sep + 2).trimmed());
        }
        else
        {
            canvasEmptyTitle_->setText(message.trimmed());
            if (canvasEmptySub_)
                canvasEmptySub_->clear();
        }
    }

    // Metric chips reflect the LIVE control values (seed 0 == random, the app convention).
    if (canvasEmptyChipDim_)
        canvasEmptyChipDim_->setText(QStringLiteral("%1 × %2")
                                         .arg(widthSpin_ ? widthSpin_->value() : 1024)
                                         .arg(heightSpin_ ? heightSpin_->value() : 1024));
    if (canvasEmptyChipSteps_)
        canvasEmptyChipSteps_->setText(QStringLiteral("%1 steps").arg(sampling_->stepsSpin() ? sampling_->stepsSpin()->value() : 28));
    if (canvasEmptyChipCfg_)
        canvasEmptyChipCfg_->setText(QStringLiteral("cfg %1")
                                         .arg(QString::number(sampling_->cfgSpin() ? sampling_->cfgSpin()->value() : 7.0, 'f', 1)));
    if (canvasEmptyChipSeed_)
    {
        const int seed = sampling_->seedSpin() ? sampling_->seedSpin()->value() : 0;
        canvasEmptyChipSeed_->setText(seed == 0 ? QStringLiteral("seed · random")
                                                : QStringLiteral("seed · %1").arg(seed));
    }
}

void ImageGenerationPage::refreshPreview()
{
    if (isVideoMode() && suppressStartupVideoPreviewRestore_)
    {
        if (mediaPreviewController_)
            mediaPreviewController_->clearVideoPreview();

        if (previewStack_ && previewImagePage_)
            previewStack_->setCurrentWidget(previewImagePage_);

        if (previewLabel_)
        {
            previewLabel_->setProperty("emptyState", true);
            previewLabel_->setText(QStringLiteral("No video preview loaded yet. Generate a video or choose one from History."));
        }
        // Specific startup message -> show the text surface, not the arcane empty-state.
        if (previewImageInnerStack_)
            previewImageInnerStack_->setCurrentWidget(previewLabel_);

        return;
    }


    if (!previewLabel_)
        return;

    if (!imagePreviewController_)
    {
        previewLabel_->setPixmap(QPixmap());
        previewLabel_->setText(QStringLiteral("Preview controller unavailable."));
        return;
    }

    if (!generatedPreviewPath_.trimmed().isEmpty() && QFileInfo::exists(generatedPreviewPath_))
    {
        if (isVideoAssetPath(generatedPreviewPath_) && !isImageAssetPath(generatedPreviewPath_))
        {
            imagePreviewController_->clearLabelPixmap();
            imagePreviewController_->clearCache(false);
            imagePreviewController_->markVideoRendered(generatedPreviewPath_, generatedPreviewCaption_);
            imagePreviewController_->setEmptyState(false);

            const QString summary = generatedPreviewCaption_.trimmed().isEmpty()
                                        ? QStringLiteral("Video output ready.")
                                        : generatedPreviewCaption_.trimmed();
            showVideoPreviewSurface(generatedPreviewPath_, summary);
            return;
        }

        if (!imagePreviewController_->loadPixmapIntoCache(generatedPreviewPath_))
        {
            stopVideoPreview();
            showImagePreviewSurface();
            imagePreviewController_->showText(QStringLiteral("Loading latest output preview…"));
            schedulePreviewRefresh(120);
            return;
        }

        const QPixmap &pixmap = imagePreviewController_->cachedPixmap();
        if (!pixmap.isNull())
        {
            const QString summary = !generatedPreviewCaption_.trimmed().isEmpty()
                                        ? generatedPreviewCaption_.trimmed()
                                        : QStringLiteral("Latest result: %1\n%2 × %3")
                                              .arg(QFileInfo(generatedPreviewPath_).fileName())
                                              .arg(pixmap.width())
                                              .arg(pixmap.height());

            imagePreviewController_->showPixmap(generatedPreviewPath_, pixmap, summary);
            return;
        }
    }

    if (isImageInputMode())
    {
        const QString path = inputImageEdit_ ? inputImageEdit_->text().trimmed() : QString();
        if (!path.isEmpty() && QFileInfo::exists(path) && imagePreviewController_->loadPixmapIntoCache(path))
        {
            const QPixmap &pixmap = imagePreviewController_->cachedPixmap();
            if (!pixmap.isNull())
            {
                imagePreviewController_->showPixmap(path,
                                                    pixmap,
                                                    QStringLiteral("%1: %2\nStrength: %3    Sampler: %4    Steps: %5")
                                                        .arg(isVideoMode() ? QStringLiteral("Keyframe") : QStringLiteral("Source image"))
                                                        .arg(QFileInfo(path).fileName())
                                                        .arg(denoiseSpin_ ? QString::number(denoiseSpin_->value(), 'f', 2) : QStringLiteral("n/a"))
                                                        .arg(comboDisplayValue(sampling_->samplerCombo()))
                                                        .arg(sampling_->stepsSpin() ? sampling_->stepsSpin()->value() : 0));
                return;
            }
        }
    }

    stopVideoPreview();
    showImagePreviewSurface();
    imagePreviewController_->clearLabelPixmap();
    imagePreviewController_->resetTargetSize();
    imagePreviewController_->clearRenderedFingerprint();

    if (generatedPreviewPath_.trimmed().isEmpty())
        imagePreviewController_->clearCache();

    updatePreviewEmptyStateSizing();

    if (previewLabel_->property("emptyState").toBool())
    {
        const QString reason = readinessBlockReason();
        const QString message =
            isImageInputMode()
                ? (isVideoMode()
                       ? QStringLiteral("No keyframe loaded yet.\n\nDrop or browse a source keyframe from the prompt strip.")
                       : QStringLiteral("No source image loaded yet.\n\nDrop or browse an input image from the prompt strip."))
                : (reason.isEmpty()
                       ? (isVideoMode()
                              ? QStringLiteral("Ready when you are.\n\nWrite a motion prompt, choose a video family, then Generate.")
                              : QStringLiteral("Ready when you are.\n\nWrite a prompt, lock a model, then Generate — results land here."))
                       : QStringLiteral("Almost ready.\n\n%1").arg(reason));
        imagePreviewController_->showText(message);
        updateCanvasEmptyState(message); // arcane empty-state title/sub + live metric chips
        return;
    }

    imagePreviewController_->showText(
        busy_ ? (busyMessage_.isEmpty() ? QStringLiteral("Generation in progress…") : busyMessage_)
              : (isImageInputMode()
                     ? (isVideoMode()
                            ? QStringLiteral("No keyframe loaded yet.\n\nDrop a keyframe into the Input Image card or browse for one to begin image-to-video.")
                            : QStringLiteral("No source image loaded yet.\n\nDrop an image into the Input Image card or browse for one to begin."))
                     : (isVideoMode()
                            ? QStringLiteral("Text to Video ready.\n\nBuild the prompt and motion stack on the left, then press Generate or Queue.")
                            : QStringLiteral("Your generated image will appear here.\n\nBuild the prompt and stack on the left, then generate."))));
}

void ImageGenerationPage::recordSessionOutput(const QString &path, const QString &caption)
{
    const QString norm = path.trimmed();
    if (norm.isEmpty() || !QFileInfo::exists(norm))
        return;

    // Already seen this session -> move it to the front (newest) instead of duplicating.
    for (int i = 0; i < sessionOutputs_.size(); ++i)
    {
        if (sessionOutputs_.at(i).path == norm)
        {
            SessionOutput existing = sessionOutputs_.takeAt(i);
            if (!caption.trimmed().isEmpty())
                existing.caption = caption;
            sessionOutputs_.prepend(existing);
            selectedSessionPath_ = norm;
            rebuildSessionStrip();
            return;
        }
    }

    SessionOutput out;
    out.path = norm;
    out.isVideo = isVideoAssetPath(norm) && !isImageAssetPath(norm);
    out.posterPath = out.isVideo ? QString() : norm; // video poster is captured lazily below
    out.caption = caption;
    out.model = resolveSelectedModelDisplay(selectedModelValue());
    if (out.model.trimmed().isEmpty())
        out.model = selectedModelValue();
    out.seed = sampling_->seedSpin() ? sampling_->seedSpin()->value() : 0;
    out.steps = sampling_->stepsSpin() ? sampling_->stepsSpin()->value() : 0;

    sessionOutputs_.prepend(out);
    selectedSessionPath_ = norm;
    rebuildSessionStrip();

    if (out.isVideo)
        captureVideoPosterIfNeeded(norm);
}

void ImageGenerationPage::rebuildSessionStrip()
{
    if (!sessionStrip_ || !sessionStripLayout_ || !sessionThumbs_)
        return;

    // Tear down existing item widgets (the trailing stretch comes off here too, re-added below).
    while (QLayoutItem *item = sessionStripLayout_->takeAt(0))
    {
        if (QWidget *w = item->widget())
            w->deleteLater();
        delete item;
    }

    if (sessionOutputs_.isEmpty())
    {
        sessionStrip_->setVisible(false);
        return;
    }

    constexpr int kThumb = 84;
    const ThemeManager &tm = ThemeManager::instance();
    const QString sheet = QStringLiteral(
        "QToolButton#SessionThumb { border: 1px solid %1; border-radius: 9px; background: %2; padding: 2px; }"
        "QToolButton#SessionThumb:hover { border-color: %3; }"
        "QToolButton#SessionThumb:checked { border: 2px solid %4; }")
        .arg(tm.css(ThemeManager::Color::Border),
             tm.css(ThemeManager::Color::Surface1),
             tm.css(ThemeManager::Color::BorderStrong),
             tm.css(ThemeManager::Color::Accent));

    for (const SessionOutput &out : sessionOutputs_)
    {
        auto *btn = new QToolButton(sessionStrip_);
        btn->setObjectName(QStringLiteral("SessionThumb"));
        btn->setFixedSize(kThumb + 8, kThumb + 8);
        btn->setIconSize(QSize(kThumb, kThumb));
        btn->setCheckable(true);
        btn->setChecked(out.path == selectedSessionPath_);
        btn->setCursor(Qt::PointingHandCursor);
        btn->setAutoRaise(true);
        btn->setStyleSheet(sheet);

        QPixmap thumb;
        if (!out.posterPath.isEmpty())
            thumb = sessionThumbs_->thumbnail(out.posterPath, out.path, kThumb);
        if (thumb.isNull())
            thumb = sessionLoadingTile(kThumb, out.isVideo); // loading (or video-without-poster) tile
        else if (out.isVideo)
            paintPlayBadge(thumb);
        btn->setIcon(QIcon(thumb));

        QStringList tip;
        tip << QFileInfo(out.path).fileName();
        if (!out.model.trimmed().isEmpty())
            tip << QStringLiteral("Model: %1").arg(out.model);
        tip << QStringLiteral("Seed: %1").arg(out.seed == 0 ? QStringLiteral("random") : QString::number(out.seed));
        if (out.steps > 0)
            tip << QStringLiteral("Steps: %1").arg(out.steps);
        btn->setToolTip(tip.join(QChar('\n')));

        const QString itemPath = out.path;
        connect(btn, &QToolButton::clicked, this, [this, itemPath]() { selectSessionOutput(itemPath); });

        sessionStripLayout_->addWidget(btn);
    }
    sessionStripLayout_->addStretch(1);
    sessionStrip_->setVisible(true);
}

void ImageGenerationPage::selectSessionOutput(const QString &path)
{
    const QString norm = path.trimmed();
    if (norm.isEmpty() || !QFileInfo::exists(norm))
        return;

    selectedSessionPath_ = norm;
    QString caption;
    for (const SessionOutput &o : sessionOutputs_)
        if (o.path == norm)
        {
            caption = o.caption;
            break;
        }
    // Reuse the normal show path (image vs video routing + player). This is a re-show, so it must NOT
    // re-record / reorder the strip -- only the highlight moves.
    suppressSessionRecord_ = true;
    setPreviewImage(norm, caption);
    suppressSessionRecord_ = false;
    rebuildSessionStrip();
}

void ImageGenerationPage::captureVideoPosterIfNeeded(const QString &videoPath)
{
    const QString norm = videoPath.trimmed();
    if (norm.isEmpty())
        return;

    // The first frame only lands after the player loads + decodes, so poll a few times.
    for (int delay : {700, 1600, 3200})
    {
        QPointer<ImageGenerationPage> self(this);
        QTimer::singleShot(delay, this, [self, norm]() {
            if (!self || !self->mediaPreviewController_)
                return;
            bool needs = false;
            for (const SessionOutput &o : self->sessionOutputs_)
                if (o.path == norm && o.posterPath.isEmpty())
                {
                    needs = true;
                    break;
                }
            if (!needs)
                return;
            const QImage frame = self->mediaPreviewController_->currentFrameImage();
            if (frame.isNull())
                return;
            const QString poster = writeSessionPoster(norm, frame);
            if (poster.isEmpty())
                return;
            for (SessionOutput &o : self->sessionOutputs_)
                if (o.path == norm)
                    o.posterPath = poster;
            self->rebuildSessionStrip();
        });
    }
}

void ImageGenerationPage::persistLatestGeneratedOutput(const QString &path)
{
    spellvision::generation::persistLatestGeneratedOutput(path);
}

QString ImageGenerationPage::latestGeneratedOutputPath() const
{
    return spellvision::generation::latestGeneratedImageOutputPath();
}

void ImageGenerationPage::prepLatestForI2I()
{
    QString latest = generatedPreviewPath_.trimmed();
    if (latest.isEmpty())
        latest = latestGeneratedOutputPath();

    if (latest.isEmpty() || !QFileInfo::exists(latest))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Prep for I2I"),
                                 QStringLiteral("No generated image is available yet. Generate or queue a T2I image first."));
        return;
    }

    spellvision::generation::persistStagedI2IInputPath(latest);

    if (prepLatestForI2IButton_)
    {
        prepLatestForI2IButton_->setText(QStringLiteral("Prepped"));
        QTimer::singleShot(1300, this, [this]() {
            if (prepLatestForI2IButton_)
                prepLatestForI2IButton_->setText(QStringLiteral("Prep for I2I"));
        });
    }

    emit prepForI2IRequested(latest);
}

void ImageGenerationPage::useLatestForI2I()
{
    QString staged = spellvision::generation::stagedI2IInputPath();

    if (staged.isEmpty())
        staged = latestGeneratedOutputPath();

    if (staged.isEmpty() || !QFileInfo::exists(staged))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Use Last Image"),
                                 QStringLiteral("No staged or generated image is available yet."));
        return;
    }

    useImageAsInput(staged);
}

void ImageGenerationPage::useImageAsInput(const QString &path)
{
    const QString normalizedPath = path.trimmed();
    if (normalizedPath.isEmpty() || !QFileInfo::exists(normalizedPath))
        return;

    setInputImagePath(normalizedPath);
    updatePrimaryActionAvailability();
    scheduleUiRefresh(0);
    schedulePreviewRefresh(0);
}


void ImageGenerationPage::schedulePreviewRefresh(int delayMs)
{
    if (!previewResizeTimer_)
    {
        refreshPreview();
        return;
    }

    previewResizeTimer_->start(qBound(0, delayMs, 250));
}

void ImageGenerationPage::openInputImageBrowse()
{
    // Same picker the (now-hidden) Input-card Browse button used; funnels into setInputImagePath.
    const QString filePath = QFileDialog::getOpenFileName(this,
        QStringLiteral("Choose input image"),
        QString(),
        QStringLiteral("Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"));
    if (!filePath.isEmpty())
        setInputImagePath(filePath);
}

void ImageGenerationPage::setInputImagePath(const QString &path)
{
    if (!inputImageEdit_ || !inputDropLabel_)
        return;

    generatedPreviewPath_.clear();
    generatedPreviewCaption_.clear();
    stopVideoPreview();
    showImagePreviewSurface();
    if (imagePreviewController_)
        imagePreviewController_->clearCache();

    inputImageEdit_->setText(path);
    if (path.isEmpty())
    {
        inputDropLabel_->setText(isVideoMode()
                                     ? QStringLiteral("Drop a keyframe here or click Browse to select one.")
                                     : QStringLiteral("Drop an image here or click Browse to select a source image."));
    }
    else
    {
        const QString labelTemplate = isVideoMode()
                                          ? QStringLiteral("Current keyframe:\n%1")
                                          : QStringLiteral("Current source image:\n%1");
        inputDropLabel_->setText(labelTemplate.arg(path));
    }

    // Reflect into the prompt-row input chip-dropzone (i2i/i2v): thumbnail + clear when loaded,
    // dashed hint when empty. Pure presentation -- the path already lives in inputImageEdit_ above.
    if (inputChipDropzone_)
    {
        const bool loaded = !path.isEmpty();
        if (loaded && inputChipThumb_)
        {
            const QPixmap source(path);
            inputChipThumb_->setPixmap(source.isNull()
                                           ? QPixmap()
                                           : source.scaled(82, 82, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation));
        }
        inputChipDropzone_->setStyleSheet(loaded
            ? QStringLiteral("#PromptInputDropzone{border:1px solid %1;border-radius:9px;background:%2;}")
                  .arg(rgbaToken(ThemeManager::Color::Success, 0.35),
                       rgbaToken(ThemeManager::Color::Surface0, 0.50))
            : QStringLiteral("#PromptInputDropzone{border:1px dashed %1;border-radius:9px;background:%2;}")
                  .arg(rgbaToken(ThemeManager::Color::Border, 0.30),
                       rgbaToken(ThemeManager::Color::Surface0, 0.30)));
        if (inputChipThumb_)
            inputChipThumb_->setVisible(loaded);
        if (inputChipHint_)
            inputChipHint_->setVisible(!loaded);
        if (inputChipClear_)
        {
            inputChipClear_->setVisible(loaded);
            inputChipClear_->raise();
        }
    }

    updatePrimaryActionAvailability();
    updatePreviewEmptyStateSizing();
    schedulePreviewRefresh(0);
}

void ImageGenerationPage::setPreviewImage(const QString &imagePath, const QString &caption)
{
    // Pass 28G result output unlocks busy canvas geometry before binding a new preview.
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

    using spellvision::generation::GenerationResultRouter;

    const GenerationResultRouter::Route route = GenerationResultRouter::routePreviewResult({
        imagePath,
        caption,
        generatedPreviewPath_,
    });

    if (route.kind == GenerationResultRouter::RouteKind::Clear)
    {
        generatedPreviewPath_.clear();
        generatedPreviewCaption_.clear();
        if (route.shouldStopVideo)
            stopVideoPreview();
        if (route.shouldShowImageSurface)
            showImagePreviewSurface();
        if (imagePreviewController_ && route.shouldClearImageCache)
            imagePreviewController_->clearCache();
        busy_ = false;
        busyMessage_.clear();
        schedulePreviewRefresh(route.previewRefreshDelayMs);
        return;
    }

    generatedPreviewPath_ = route.normalizedPath;
    generatedPreviewCaption_ = route.normalizedCaption;
    busy_ = false;
    busyMessage_.clear();

    if (route.shouldPersistOutput)
        persistLatestGeneratedOutput(route.normalizedPath);

    // Session strip: a genuinely-new persisted output (image or video) joins this mode's in-memory,
    // since-launch list. A strip click re-shows through here too, so the suppress flag keeps it from
    // re-recording / reordering.
    if (route.shouldPersistOutput && !suppressSessionRecord_)
        recordSessionOutput(route.normalizedPath, route.normalizedCaption);

    if (route.kind == GenerationResultRouter::RouteKind::VideoPreview)
    {
        // A routed video result is an explicit output to show NOW (a generation completion or a
        // History pick) -- not the startup auto-restore that suppressStartupVideoPreviewRestore_
        // guards against. Clear that guard here, otherwise refreshPreview()'s startup early-return
        // (isVideoMode() && suppress) shows the "No video preview loaded yet" placeholder and never
        // reaches the video-render branch -> a freshly generated video can never appear on canvas.
        suppressStartupVideoPreviewRestore_ = false;
        // Video result/status messages may repeat the same output path many times.
        // Do not clear the player or force image mode for the same MP4; refreshPreview()
        // will decide whether the file is stable enough to load or can be left alone.
        if (imagePreviewController_ && route.shouldClearImageCache)
        {
            imagePreviewController_->clearCache(!route.shouldClearImageCachePreserveVideoMarker);
            if (route.shouldMarkVideoRendered)
                imagePreviewController_->markVideoRendered(generatedPreviewPath_, generatedPreviewCaption_);
        }
        schedulePreviewRefresh(route.previewRefreshDelayMs);
        return;
    }

    if (route.shouldStopVideo)
        stopVideoPreview();
    if (route.shouldShowImageSurface)
        showImagePreviewSurface();
    if (imagePreviewController_ && route.shouldClearImageCache)
        imagePreviewController_->clearCache();
    schedulePreviewRefresh(route.previewRefreshDelayMs);
}



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





