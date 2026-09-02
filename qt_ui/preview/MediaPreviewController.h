#pragma once

#include "PreviewFileSettler.h"

#include <QElapsedTimer>
#include <QImage>
#include <QMediaPlayer>
#include <QObject>
#include <QString>
#include <QUrl>
#include <QtGlobal>

#include <functional>

class QAudioOutput;
class QCheckBox;
class QComboBox;
class QEvent;
class QLabel;
class QPushButton;
class QSlider;
class QStackedWidget;
class QVideoFrame;
class QVideoSink;
class QWidget;

namespace spellvision::preview
{

struct MediaPreviewBindings
{
    QStackedWidget *previewStack = nullptr;
    // The space a clip may take (the preview area). The cap shrinks the stack, never this, so the
    // frame is fitted against it -- see preview/AspectCap.h fitBudget(). Optional.
    QWidget *sizeBudgetWidget = nullptr;
    QWidget *imagePage = nullptr;
    QWidget *videoPage = nullptr;
    // Video is presented by painting decoded frames (QVideoSink -> QImage) onto this
    // QLabel, NOT via QVideoWidget: the native-window surface fails to composite on some
    // GPU/driver stacks (frames decode but nothing shows). A QLabel + toImage() blit is
    // portable across every machine — required for an open-source release.
    QLabel *videoSurface = nullptr;
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
    // The last decoded frame (for session-strip video posters). Null until a frame has rendered.
    [[nodiscard]] QImage currentFrameImage() const { return lastFrameImage_; }

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

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;

private:
    void connectPlayerSignals();
    void connectTransportSignals();
    void renderVideoFrame(const QVideoFrame &frame);
    void repaintVideoSurface();
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
    QVideoSink *videoSink_ = nullptr;
    QImage lastFrameImage_;

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

    // Playback-perf diagnostics (env-gated by SPELLVISION_VIDEO_PERF). Measures true playback
    // speed (player-position advance vs wall-clock) + per-frame render cost, so slow-motion can be
    // proven from real numbers instead of guessed at (project rule: gate video on measurement).
    bool videoPerfLogging_ = false;
    QElapsedTimer perfWallTimer_;
    int perfFrameCount_ = 0;
    qint64 perfWindowStartPositionMs_ = -1;
    double perfRenderMsAccum_ = 0.0;
};

} // namespace spellvision::preview
