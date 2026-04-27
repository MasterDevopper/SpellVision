#pragma once

#include "PreviewFileSettler.h"

#include <QMediaPlayer>
#include <QObject>
#include <QString>
#include <QUrl>
#include <QtGlobal>

#include <functional>

class QAudioOutput;
class QCheckBox;
class QComboBox;
class QLabel;
class QPushButton;
class QSlider;
class QStackedWidget;
class QVideoWidget;
class QWidget;

namespace spellvision::preview
{

struct MediaPreviewBindings
{
    QStackedWidget *previewStack = nullptr;
    QWidget *imagePage = nullptr;
    QWidget *videoPage = nullptr;
    QVideoWidget *videoWidget = nullptr;
    QLabel *captionLabel = nullptr;
    QWidget *transportBar = nullptr;
    QPushButton *playPauseButton = nullptr;
    QPushButton *stopButton = nullptr;
    QPushButton *stepBackButton = nullptr;
    QPushButton *stepForwardButton = nullptr;
    QPushButton *restartButton = nullptr;
    QSlider *seekSlider = nullptr;
    QLabel *timeLabel = nullptr;
    QComboBox *speedCombo = nullptr;
    QCheckBox *loopCheck = nullptr;

    std::function<int()> framesPerSecondProvider;
};

class MediaPreviewController : public QObject
{
    Q_OBJECT

public:
    explicit MediaPreviewController(QObject *parent = nullptr);

    void bind(const MediaPreviewBindings &bindings);
    [[nodiscard]] const MediaPreviewBindings &bindings() const;

    [[nodiscard]] QMediaPlayer *player() const;
    [[nodiscard]] QAudioOutput *audioOutput() const;
    [[nodiscard]] QString currentVideoPath() const;
    [[nodiscard]] QString currentVideoCaption() const;
    [[nodiscard]] bool hasVideo() const;
    [[nodiscard]] bool isPlaying() const;
    [[nodiscard]] qint64 durationMs() const;
    [[nodiscard]] qint64 positionMs() const;

    void showImageSurface();
    void showVideoSurface(const QString &videoPath, const QString &caption = QString());
    void clearVideoPreview();

    void play();
    void pause();
    void stopPlayback();
    void restart();
    void stepFrames(int frameDelta);
    void seek(qint64 positionMs, bool preservePlaybackState);
    void setPlaybackRate(double rate);

    void updateTransportUi();
    void updateCaption();

    [[nodiscard]] static QString formatDurationLabel(qint64 milliseconds);
    [[nodiscard]] static QString formatFileSizeLabel(qint64 bytes);

signals:
    void stateChanged();
    void mediaError(const QString &message);
    void mediaLogMessage(const QString &message);

private:
    void connectPlayerSignals();
    void connectTransportSignals();
    void loadVideoSource(const QString &videoPath,
                         const QString &caption,
                         const FileSnapshot &snapshot);
    void deferLoad(const QString &videoPath, const QString &caption);
    void retryPendingLoad();
    [[nodiscard]] bool playerHasHealthyMedia() const;
    [[nodiscard]] bool sameSourceLoaded(const QUrl &sourceUrl) const;
    [[nodiscard]] int framesPerSecond() const;

    void handleMediaStatus(QMediaPlayer::MediaStatus status);
    void handlePlaybackStateChanged(QMediaPlayer::PlaybackState state);
    void handlePositionChanged(qint64 positionMs);
    void handleDurationChanged(qint64 durationMs);
    void handleMediaError(QMediaPlayer::Error error, const QString &errorString);

    MediaPreviewBindings bindings_;
    QMediaPlayer *player_ = nullptr;
    QAudioOutput *audioOutput_ = nullptr;

    QString currentVideoPath_;
    QString currentVideoCaption_;
    qint64 currentVideoFileSize_ = -1;
    qint64 currentVideoModifiedMs_ = -1;
    qint64 lastLoadedVideoFileSize_ = -1;
    qint64 lastLoadedVideoModifiedMs_ = -1;
    qint64 lastKnownDurationMs_ = 0;

    QString pendingLoadPath_;
    QString pendingLoadCaption_;
    bool seekInternalUpdate_ = false;
    bool seekDragging_ = false;
    bool userPaused_ = false;
    bool userStopped_ = false;
    bool transportSignalsConnected_ = false;
};

} // namespace spellvision::preview
