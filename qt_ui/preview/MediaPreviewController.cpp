#include "MediaPreviewController.h"

#include <QAudioOutput>
#include <QCheckBox>
#include <QComboBox>
#include <QFileInfo>
#include <QLabel>
#include <QPushButton>
#include <QSlider>
#include <QStackedWidget>
#include <QTimer>
#include <QVideoWidget>

#include <cmath>

namespace spellvision::preview
{

namespace
{
constexpr int kReloadRetryMs = 180;
constexpr int kDefaultFps = 24;
}

MediaPreviewController::MediaPreviewController(QObject *parent)
    : QObject(parent),
      player_(new QMediaPlayer(this)),
      audioOutput_(new QAudioOutput(this))
{
    player_->setAudioOutput(audioOutput_);
    audioOutput_->setVolume(1.0);
    connectPlayerSignals();
}

void MediaPreviewController::bind(const MediaPreviewBindings &bindings)
{
    bindings_ = bindings;

    if (bindings_.videoWidget)
    {
        bindings_.videoWidget->setAttribute(Qt::WA_NativeWindow, true);
        bindings_.videoWidget->winId();
        player_->setVideoOutput(bindings_.videoWidget);
    }

    connectTransportSignals();
    updateTransportUi();
    updateCaption();
}

const MediaPreviewBindings &MediaPreviewController::bindings() const
{
    return bindings_;
}

QMediaPlayer *MediaPreviewController::player() const
{
    return player_;
}

QAudioOutput *MediaPreviewController::audioOutput() const
{
    return audioOutput_;
}

QString MediaPreviewController::currentVideoPath() const
{
    return currentVideoPath_;
}

QString MediaPreviewController::currentVideoCaption() const
{
    return currentVideoCaption_;
}

bool MediaPreviewController::hasVideo() const
{
    return player_ && player_->source().isValid();
}

bool MediaPreviewController::isPlaying() const
{
    return player_ && player_->playbackState() == QMediaPlayer::PlayingState;
}

qint64 MediaPreviewController::durationMs() const
{
    return qMax<qint64>(lastKnownDurationMs_, player_ ? player_->duration() : 0);
}

qint64 MediaPreviewController::positionMs() const
{
    return player_ ? player_->position() : 0;
}

void MediaPreviewController::showImageSurface()
{
    if (bindings_.previewStack && bindings_.imagePage)
        bindings_.previewStack->setCurrentWidget(bindings_.imagePage);
}

void MediaPreviewController::showVideoSurface(const QString &videoPath, const QString &caption)
{
    if (!bindings_.previewStack || !bindings_.videoPage || !bindings_.videoWidget || !player_)
    {
        showImageSurface();
        return;
    }

    const QString normalizedPath = videoPath.trimmed();
    if (normalizedPath.isEmpty())
    {
        clearVideoPreview();
        showImageSurface();
        return;
    }

    currentVideoPath_ = normalizedPath;
    currentVideoCaption_ = caption.trimmed();
    bindings_.previewStack->setCurrentWidget(bindings_.videoPage);

    const FileSnapshot snapshot = PreviewFileSettler::snapshot(normalizedPath);
    currentVideoFileSize_ = snapshot.size;
    currentVideoModifiedMs_ = snapshot.modifiedMs;

    updateCaption();

    const QUrl sourceUrl = QUrl::fromLocalFile(normalizedPath);
    const bool sourceChanged = !sameSourceLoaded(sourceUrl);
    const bool fileChangedSinceLoad = PreviewFileSettler::hasChanged(
        snapshot,
        lastLoadedVideoFileSize_,
        lastLoadedVideoModifiedMs_);

    if (!sourceChanged && playerHasHealthyMedia())
    {
        updateTransportUi();
        return;
    }

    if (!sourceChanged && !fileChangedSinceLoad)
    {
        updateTransportUi();
        return;
    }

    if (PreviewFileSettler::shouldDeferLoad(snapshot))
    {
        deferLoad(normalizedPath, currentVideoCaption_);
        updateTransportUi();
        return;
    }

    loadVideoSource(normalizedPath, currentVideoCaption_, snapshot);
}

void MediaPreviewController::clearVideoPreview()
{
    currentVideoPath_.clear();
    currentVideoCaption_.clear();
    currentVideoFileSize_ = -1;
    currentVideoModifiedMs_ = -1;
    lastLoadedVideoFileSize_ = -1;
    lastLoadedVideoModifiedMs_ = -1;
    lastKnownDurationMs_ = 0;
    pendingLoadPath_.clear();
    pendingLoadCaption_.clear();
    seekDragging_ = false;
    userPaused_ = false;
    userStopped_ = true;

    if (player_)
    {
        player_->stop();
        player_->setSource(QUrl());
    }

    if (bindings_.seekSlider)
    {
        bindings_.seekSlider->setRange(0, 0);
        bindings_.seekSlider->setValue(0);
    }

    if (bindings_.timeLabel)
        bindings_.timeLabel->setText(QStringLiteral("00:00 / 00:00"));

    if (bindings_.transportBar)
        bindings_.transportBar->setVisible(false);

    if (bindings_.captionLabel)
    {
        bindings_.captionLabel->clear();
        bindings_.captionLabel->setToolTip(QString());
        bindings_.captionLabel->setVisible(false);
    }

    updateTransportUi();
    emit stateChanged();
}

void MediaPreviewController::play()
{
    if (!player_ || !player_->source().isValid())
        return;

    if (bindings_.videoWidget)
    {
        bindings_.videoWidget->setAttribute(Qt::WA_NativeWindow, true);
        bindings_.videoWidget->winId();
        player_->setVideoOutput(bindings_.videoWidget);
        bindings_.videoWidget->show();
    }

    if (bindings_.previewStack && bindings_.videoPage)
        bindings_.previewStack->setCurrentWidget(bindings_.videoPage);

    userPaused_ = false;
    userStopped_ = false;

    const qint64 duration = durationMs();
    if (duration > 0 && player_->position() >= duration - 25)
        player_->setPosition(0);

    if (bindings_.speedCombo)
        setPlaybackRate(bindings_.speedCombo->currentData().toDouble());

    player_->play();
    updateTransportUi();
}

void MediaPreviewController::pause()
{
    if (!player_)
        return;

    userPaused_ = true;
    userStopped_ = false;
    player_->pause();
    updateTransportUi();
}

void MediaPreviewController::stopPlayback()
{
    if (!player_)
        return;

    userStopped_ = true;
    userPaused_ = false;
    player_->pause();
    player_->setPosition(0);
    updateTransportUi();
}

void MediaPreviewController::restart()
{
    if (!player_ || !player_->source().isValid())
        return;

    userPaused_ = false;
    userStopped_ = false;
    player_->setPosition(0);
    player_->play();
    updateTransportUi();
}

void MediaPreviewController::stepFrames(int frameDelta)
{
    if (!player_ || !player_->source().isValid())
        return;

    const int fps = qMax(1, framesPerSecond());
    const qint64 frameMs = qMax<qint64>(1, qRound64(1000.0 / static_cast<double>(fps)));
    const qint64 duration = durationMs();
    const qint64 target = qBound<qint64>(0,
                                         player_->position() + (frameMs * frameDelta),
                                         qMax<qint64>(0, duration));

    userPaused_ = true;
    userStopped_ = false;
    player_->pause();
    player_->setPosition(target);
    updateTransportUi();
}

void MediaPreviewController::seek(qint64 positionMs, bool preservePlaybackState)
{
    if (!player_ || !player_->source().isValid())
        return;
    if (seekInternalUpdate_)
        return;

    const bool wasPlaying = player_->playbackState() == QMediaPlayer::PlayingState;
    const qint64 duration = durationMs();
    const qint64 target = qBound<qint64>(0, positionMs, qMax<qint64>(0, duration));

    player_->setPosition(target);

    if (!preservePlaybackState || !wasPlaying)
    {
        userPaused_ = true;
        userStopped_ = false;
        player_->pause();
        updateTransportUi();
        return;
    }

    userPaused_ = false;
    userStopped_ = false;
    player_->play();
    updateTransportUi();
}

void MediaPreviewController::setPlaybackRate(double rate)
{
    if (!player_)
        return;

    if (rate <= 0.0)
        rate = 1.0;
    player_->setPlaybackRate(rate);
}

void MediaPreviewController::updateTransportUi()
{
    const bool hasLoadedVideo = hasVideo();
    const qint64 duration = durationMs();
    const qint64 position = positionMs();
    const bool playing = isPlaying();
    const bool canSeek = hasLoadedVideo && duration > 0;

    if (bindings_.transportBar)
        bindings_.transportBar->setVisible(hasLoadedVideo);

    if (bindings_.playPauseButton)
    {
        bindings_.playPauseButton->setEnabled(hasLoadedVideo);
        bindings_.playPauseButton->setText(playing ? QStringLiteral("Pause") : QStringLiteral("Play"));
        bindings_.playPauseButton->setToolTip(playing ? QStringLiteral("Pause playback") : QStringLiteral("Play preview"));
    }

    if (bindings_.stopButton)
        bindings_.stopButton->setEnabled(hasLoadedVideo);
    if (bindings_.restartButton)
        bindings_.restartButton->setEnabled(hasLoadedVideo);
    if (bindings_.stepBackButton)
        bindings_.stepBackButton->setEnabled(canSeek);
    if (bindings_.stepForwardButton)
        bindings_.stepForwardButton->setEnabled(canSeek);
    if (bindings_.loopCheck)
        bindings_.loopCheck->setEnabled(hasLoadedVideo);
    if (bindings_.speedCombo)
        bindings_.speedCombo->setEnabled(hasLoadedVideo);

    if (bindings_.seekSlider && !seekInternalUpdate_ && !seekDragging_)
    {
        seekInternalUpdate_ = true;
        bindings_.seekSlider->setEnabled(canSeek);
        bindings_.seekSlider->setRange(0, static_cast<int>(qMax<qint64>(0, duration)));
        bindings_.seekSlider->setValue(static_cast<int>(qBound<qint64>(0, position, duration)));
        seekInternalUpdate_ = false;
    }
    else if (bindings_.seekSlider)
    {
        bindings_.seekSlider->setEnabled(canSeek);
    }

    if (bindings_.timeLabel)
        bindings_.timeLabel->setText(QStringLiteral("%1 / %2").arg(formatDurationLabel(position), formatDurationLabel(duration)));
}

void MediaPreviewController::updateCaption()
{
    if (!bindings_.captionLabel)
        return;

    const QString normalizedPath = currentVideoPath_.trimmed();
    if (normalizedPath.isEmpty())
    {
        bindings_.captionLabel->clear();
        bindings_.captionLabel->setToolTip(QString());
        bindings_.captionLabel->setVisible(false);
        return;
    }

    const QFileInfo info(normalizedPath);
    QStringList lines;
    if (!currentVideoCaption_.trimmed().isEmpty())
        lines << currentVideoCaption_.trimmed();
    lines << info.fileName();

    QStringList meta;
    if (info.exists())
        meta << formatFileSizeLabel(info.size());

    if (durationMs() > 0)
        meta << QStringLiteral("%1 @ %2").arg(formatDurationLabel(durationMs()), QStringLiteral("preview"));

    if (!meta.isEmpty())
        lines << meta.join(QStringLiteral(" • "));

    lines << normalizedPath;
    bindings_.captionLabel->setText(lines.join(QStringLiteral("\n")));
    bindings_.captionLabel->setToolTip(normalizedPath);
    bindings_.captionLabel->setVisible(true);
}

QString MediaPreviewController::formatDurationLabel(qint64 milliseconds)
{
    const qint64 totalSeconds = qMax<qint64>(0, milliseconds / 1000);
    const qint64 minutes = totalSeconds / 60;
    const qint64 seconds = totalSeconds % 60;
    return QStringLiteral("%1:%2")
        .arg(minutes, 2, 10, QLatin1Char('0'))
        .arg(seconds, 2, 10, QLatin1Char('0'));
}

QString MediaPreviewController::formatFileSizeLabel(qint64 bytes)
{
    const double size = static_cast<double>(qMax<qint64>(0, bytes));
    if (size >= 1024.0 * 1024.0 * 1024.0)
        return QStringLiteral("%1 GB").arg(QString::number(size / (1024.0 * 1024.0 * 1024.0), 'f', 2));
    if (size >= 1024.0 * 1024.0)
        return QStringLiteral("%1 MB").arg(QString::number(size / (1024.0 * 1024.0), 'f', 2));
    if (size >= 1024.0)
        return QStringLiteral("%1 KB").arg(QString::number(size / 1024.0, 'f', 1));
    return QStringLiteral("%1 B").arg(static_cast<qlonglong>(size));
}

void MediaPreviewController::connectPlayerSignals()
{
    connect(player_, &QMediaPlayer::mediaStatusChanged, this, &MediaPreviewController::handleMediaStatus);
    connect(player_, &QMediaPlayer::playbackStateChanged, this, &MediaPreviewController::handlePlaybackStateChanged);
    connect(player_, &QMediaPlayer::positionChanged, this, &MediaPreviewController::handlePositionChanged);
    connect(player_, &QMediaPlayer::durationChanged, this, &MediaPreviewController::handleDurationChanged);
    connect(player_, &QMediaPlayer::errorOccurred, this, &MediaPreviewController::handleMediaError);
}

void MediaPreviewController::connectTransportSignals()
{
    if (transportSignalsConnected_)
        return;

    if (bindings_.playPauseButton)
    {
        connect(bindings_.playPauseButton, &QPushButton::clicked, this, [this]() {
            if (isPlaying())
                pause();
            else
                play();
        });
    }

    if (bindings_.stopButton)
        connect(bindings_.stopButton, &QPushButton::clicked, this, &MediaPreviewController::stopPlayback);

    if (bindings_.restartButton)
        connect(bindings_.restartButton, &QPushButton::clicked, this, &MediaPreviewController::restart);

    if (bindings_.stepBackButton)
        connect(bindings_.stepBackButton, &QPushButton::clicked, this, [this]() { stepFrames(-1); });

    if (bindings_.stepForwardButton)
        connect(bindings_.stepForwardButton, &QPushButton::clicked, this, [this]() { stepFrames(1); });

    if (bindings_.seekSlider)
    {
        connect(bindings_.seekSlider, &QSlider::sliderPressed, this, [this]() { seekDragging_ = true; });
        connect(bindings_.seekSlider, &QSlider::sliderReleased, this, [this]() {
            seekDragging_ = false;
            seek(bindings_.seekSlider ? bindings_.seekSlider->value() : 0, true);
        });
        connect(bindings_.seekSlider, &QSlider::valueChanged, this, [this](int value) {
            if (seekDragging_)
                seek(value, false);
        });
    }

    if (bindings_.speedCombo)
    {
        connect(bindings_.speedCombo, &QComboBox::currentIndexChanged, this, [this]() {
            if (bindings_.speedCombo)
                setPlaybackRate(bindings_.speedCombo->currentData().toDouble());
        });
    }

    transportSignalsConnected_ = true;
}

void MediaPreviewController::loadVideoSource(const QString &videoPath,
                                             const QString &caption,
                                             const FileSnapshot &snapshot)
{
    if (!player_)
        return;

    currentVideoPath_ = videoPath.trimmed();
    currentVideoCaption_ = caption.trimmed();
    currentVideoFileSize_ = snapshot.size;
    currentVideoModifiedMs_ = snapshot.modifiedMs;
    lastLoadedVideoFileSize_ = snapshot.size;
    lastLoadedVideoModifiedMs_ = snapshot.modifiedMs;
    lastKnownDurationMs_ = 0;
    userPaused_ = true;
    userStopped_ = false;
    seekInternalUpdate_ = false;
    seekDragging_ = false;

    if (bindings_.videoWidget)
    {
        bindings_.videoWidget->setAttribute(Qt::WA_NativeWindow, true);
        bindings_.videoWidget->winId();
        player_->setVideoOutput(bindings_.videoWidget);
    }

    player_->stop();
    player_->setSource(QUrl::fromLocalFile(currentVideoPath_));
    updateCaption();
    updateTransportUi();

    emit mediaLogMessage(QStringLiteral("Loaded preview video source: %1").arg(currentVideoPath_));
    emit stateChanged();
}

void MediaPreviewController::deferLoad(const QString &videoPath, const QString &caption)
{
    pendingLoadPath_ = videoPath.trimmed();
    pendingLoadCaption_ = caption.trimmed();
    QTimer::singleShot(kReloadRetryMs, this, &MediaPreviewController::retryPendingLoad);
}

void MediaPreviewController::retryPendingLoad()
{
    if (pendingLoadPath_.trimmed().isEmpty())
        return;

    const QString path = pendingLoadPath_;
    const QString caption = pendingLoadCaption_;
    pendingLoadPath_.clear();
    pendingLoadCaption_.clear();
    showVideoSurface(path, caption);
}

bool MediaPreviewController::playerHasHealthyMedia() const
{
    if (!player_ || !player_->source().isValid())
        return false;

    if (durationMs() > 0)
        return true;

    const auto status = player_->mediaStatus();
    return status == QMediaPlayer::LoadedMedia ||
           status == QMediaPlayer::BufferedMedia ||
           status == QMediaPlayer::EndOfMedia;
}

bool MediaPreviewController::sameSourceLoaded(const QUrl &sourceUrl) const
{
    return player_ && player_->source() == sourceUrl;
}

int MediaPreviewController::framesPerSecond() const
{
    if (bindings_.framesPerSecondProvider)
        return qMax(1, bindings_.framesPerSecondProvider());
    return kDefaultFps;
}

void MediaPreviewController::handleMediaStatus(QMediaPlayer::MediaStatus status)
{
    if (!player_)
        return;

    if (status == QMediaPlayer::LoadedMedia)
    {
        lastKnownDurationMs_ = qMax<qint64>(0, player_->duration());
        if (bindings_.speedCombo)
            setPlaybackRate(bindings_.speedCombo->currentData().toDouble());
        updateTransportUi();
        updateCaption();
        emit stateChanged();
        return;
    }

    if (status == QMediaPlayer::EndOfMedia)
    {
        const bool loopEnabled = bindings_.loopCheck && bindings_.loopCheck->isChecked();
        if (!userPaused_ && !userStopped_ && loopEnabled)
        {
            player_->setPosition(0);
            player_->play();
        }
        else
        {
            const qint64 duration = durationMs();
            player_->pause();
            if (duration > 0)
                player_->setPosition(duration);
        }
        updateTransportUi();
        updateCaption();
        emit stateChanged();
        return;
    }

    updateTransportUi();
    updateCaption();
    emit stateChanged();
}

void MediaPreviewController::handlePlaybackStateChanged(QMediaPlayer::PlaybackState)
{
    updateTransportUi();
    emit stateChanged();
}

void MediaPreviewController::handlePositionChanged(qint64)
{
    updateTransportUi();
}

void MediaPreviewController::handleDurationChanged(qint64 durationMs)
{
    lastKnownDurationMs_ = qMax<qint64>(lastKnownDurationMs_, durationMs);
    updateTransportUi();
    updateCaption();
}

void MediaPreviewController::handleMediaError(QMediaPlayer::Error error, const QString &errorString)
{
    if (error == QMediaPlayer::NoError)
        return;

    const QString message = QStringLiteral("Video preview error [%1]: %2 | %3")
                                .arg(static_cast<int>(error))
                                .arg(errorString)
                                .arg(currentVideoPath_);
    emit mediaError(message);
    emit mediaLogMessage(message);
}

} // namespace spellvision::preview
