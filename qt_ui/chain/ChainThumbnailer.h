#pragma once

// SpellVision — Chain Studio thumbnailer (Pass 5).
//
// Generates small preview thumbnails for chain Variations. Both paths
// are async so the UI thread never blocks:
//
//   makeImageThumb  -> QtConcurrent::run for decode + scale; result
//                       arrives on the main thread via QMetaObject::
//                       invokeMethod.
//   makeVideoPoster -> QMediaPlayer + QVideoSink + first-frame grab;
//                       all decoding happens on QtMultimedia worker
//                       threads. The helper QObject self-deletes
//                       after callback fires (or timeout).
//
// Both methods take an OutputId (used to build the destination
// filename: "<outId>.thumb.jpg") and a completion callback. The
// callback receives the thumb path on success or "" on failure. The
// engine treats "" as "use the kind glyph" — bad thumbs never block
// the pipeline.
//
// Failure modes (return "" via callback, no exceptions):
//   - source file missing / unreadable
//   - decode failure
//   - video first-frame timeout (default 8s)
//   - write failure
//
// Thumbnail size: 192x192 max-dimension, aspect-preserving. JPG q=80.
// Single intermediate size — UI downscales further for smaller chips
// at render time.

#include <QObject>
#include <QString>

#include <functional>

class QMediaPlayer;
class QVideoSink;
class QTimer;

namespace spellvision::chain
{

class ChainThumbnailer
{
public:
    using Callback = std::function<void(const QString &thumbPath)>;

    // The constants below are tunable in one place; UI sizing code
    // should defer to them so a future bump propagates cleanly.
    static constexpr int kMaxDimension = 192;
    static constexpr int kJpegQuality  = 80;
    static constexpr int kVideoTimeoutMs = 8000;

    // Async — kicks off image decode/scale on the global thread pool.
    // The callback is invoked on the QObject context's thread (the
    // engine's thread, i.e. main) via QMetaObject::invokeMethod with
    // QueuedConnection. callbackContext must outlive the operation;
    // if it gets destroyed first, the callback is silently dropped.
    static void makeImageThumb(const QString &outputPath,
                               const QString &outId,
                               QObject *callbackContext,
                               Callback cb);

    // Async — sets up a short-lived QMediaPlayer to grab the first
    // decoded frame, scale, write JPG, fire callback. The helper
    // QObject manages its own lifetime and self-destroys on
    // completion or timeout. callbackContext is the receiver for
    // the callback's QueuedConnection delivery (typically the
    // engine).
    static void makeVideoPoster(const QString &outputPath,
                                const QString &outId,
                                QObject *callbackContext,
                                Callback cb);
};

// ---------------------------------------------------------------------------
// Internal helper for the video path (declared in the header so MOC
// can find Q_OBJECT). Not part of the public API — engine calls
// ChainThumbnailer::makeVideoPoster which constructs one of these
// internally.
// ---------------------------------------------------------------------------

class VideoPosterGrabber final : public QObject
{
    Q_OBJECT

public:
    VideoPosterGrabber(QString outputPath,
                       QString outId,
                       QObject *callbackContext,
                       ChainThumbnailer::Callback cb);
    ~VideoPosterGrabber() override;

    // Kick off the grab. Returns immediately. The grabber will
    // self-delete via deleteLater() after the callback fires.
    void start();

private slots:
    void onVideoFrameChanged();
    void onTimeout();

private:
    void finish(const QString &thumbPath);

    QString outputPath_;
    QString outId_;
    QObject *callbackContext_ = nullptr;
    ChainThumbnailer::Callback cb_;
    QMediaPlayer *player_ = nullptr;
    QVideoSink *sink_ = nullptr;
    QTimer *timeout_ = nullptr;
    bool fired_ = false;
};

} // namespace spellvision::chain
