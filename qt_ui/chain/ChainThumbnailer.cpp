#include "chain/ChainThumbnailer.h"

#include <QDir>
#include <QFileInfo>
#include <QImage>
#include <QMediaPlayer>
#include <QMetaObject>
#include <QPointer>
#include <QString>
#include <QThreadPool>
#include <QTimer>
#include <QUrl>
#include <QVideoFrame>
#include <QVideoSink>
#include <QtConcurrent/QtConcurrentRun>

namespace spellvision::chain
{

namespace
{

// Build the thumbnail destination path — alongside the source file.
// The engine reads thumbnailPath verbatim, so we standardize on
// "<outId>.thumb.jpg" beside the source. If the source is missing or
// has no parent dir, we return "".
QString thumbPathFor(const QString &outputPath, const QString &outId)
{
    if (outputPath.trimmed().isEmpty() || outId.trimmed().isEmpty())
        return QString();
    const QFileInfo fi(outputPath);
    const QString parent = fi.absolutePath();
    if (parent.isEmpty())
        return QString();
    QDir dir(parent);
    return dir.filePath(outId + QStringLiteral(".thumb.jpg"));
}

// Aspect-preserving scale to fit inside kMaxDimension x kMaxDimension.
// Uses SmoothTransformation — for a single 192px-side image this is
// pennies on a worker thread.
QImage scaleForThumb(const QImage &src)
{
    if (src.isNull())
        return QImage();
    return src.scaled(
        ChainThumbnailer::kMaxDimension,
        ChainThumbnailer::kMaxDimension,
        Qt::KeepAspectRatio,
        Qt::SmoothTransformation);
}

// Image worker — pure function of paths; safe to run off the UI
// thread. Returns the thumb path on success, "" on any failure.
// Failures are silent here; the callback layer logs / surfaces if
// needed.
QString runImageThumbJob(const QString &outputPath, const QString &outId)
{
    const QString destPath = thumbPathFor(outputPath, outId);
    if (destPath.isEmpty())
        return QString();

    QImage src(outputPath);
    if (src.isNull())
        return QString();

    const QImage scaled = scaleForThumb(src);
    if (scaled.isNull())
        return QString();

    if (!scaled.save(destPath, "JPG", ChainThumbnailer::kJpegQuality))
        return QString();

    return destPath;
}

// Deliver a callback result on the context's thread via
// QueuedConnection. If the context has been destroyed by the time we
// post (QPointer::isNull), the callback is silently dropped — which
// is exactly the contract documented in the header.
void deliverCallback(QPointer<QObject> ctx,
                     ChainThumbnailer::Callback cb,
                     QString thumbPath)
{
    if (ctx.isNull() || !cb)
        return;
    QMetaObject::invokeMethod(
        ctx.data(),
        [cb = std::move(cb), thumbPath = std::move(thumbPath)]() { cb(thumbPath); },
        Qt::QueuedConnection);
}

} // anonymous namespace

// ---------------------------------------------------------------------------
// ChainThumbnailer — image path
// ---------------------------------------------------------------------------

void ChainThumbnailer::makeImageThumb(const QString &outputPath,
                                      const QString &outId,
                                      QObject *callbackContext,
                                      Callback cb)
{
    // Snapshot the context as a QPointer so the worker lambda can
    // detect destruction by the time it tries to deliver. cb is
    // captured by value into the worker (it's a std::function — copy
    // is the right semantic here).
    QPointer<QObject> ctx(callbackContext);

    // Fire-and-forget on the global pool. We don't keep the
    // QFuture — the only result we care about is the thumb path,
    // and that's delivered via the callback.
    (void)QtConcurrent::run(QThreadPool::globalInstance(),
        [outputPath, outId, ctx, cb = std::move(cb)]() mutable {
            const QString result = runImageThumbJob(outputPath, outId);
            deliverCallback(ctx, std::move(cb), result);
        });
}

// ---------------------------------------------------------------------------
// ChainThumbnailer — video path (delegates to VideoPosterGrabber)
// ---------------------------------------------------------------------------

void ChainThumbnailer::makeVideoPoster(const QString &outputPath,
                                       const QString &outId,
                                       QObject *callbackContext,
                                       Callback cb)
{
    auto *grabber = new VideoPosterGrabber(outputPath, outId,
                                           callbackContext, std::move(cb));
    grabber->start();
}

// ---------------------------------------------------------------------------
// VideoPosterGrabber — short-lived QObject driving QMediaPlayer
// ---------------------------------------------------------------------------

VideoPosterGrabber::VideoPosterGrabber(QString outputPath,
                                       QString outId,
                                       QObject *callbackContext,
                                       ChainThumbnailer::Callback cb)
    : QObject(callbackContext)
    , outputPath_(std::move(outputPath))
    , outId_(std::move(outId))
    , callbackContext_(callbackContext)
    , cb_(std::move(cb))
{
    // Parent to callbackContext: if the context dies before our work
    // completes, Qt cleans us up automatically (the player + sink +
    // timer are our children and follow). The fired_ guard prevents
    // the dtor path from invoking a stale callback.
}

VideoPosterGrabber::~VideoPosterGrabber() = default;

void VideoPosterGrabber::start()
{
    const QString destPath = thumbPathFor(outputPath_, outId_);
    if (destPath.isEmpty() || outputPath_.trimmed().isEmpty())
    {
        finish(QString());
        return;
    }

    // Build the player + offscreen sink. No video widget — the sink
    // is a pure frame source we attach to grab the first decoded
    // frame.
    player_ = new QMediaPlayer(this);
    sink_   = new QVideoSink(this);
    player_->setVideoSink(sink_);
    // We don't want audio playback during a poster grab — explicitly
    // detach by not assigning an audio output. (QMediaPlayer with no
    // audioOutput simply doesn't play audio.)

    connect(sink_, &QVideoSink::videoFrameChanged,
            this, &VideoPosterGrabber::onVideoFrameChanged);

    timeout_ = new QTimer(this);
    timeout_->setSingleShot(true);
    timeout_->setInterval(ChainThumbnailer::kVideoTimeoutMs);
    connect(timeout_, &QTimer::timeout, this, &VideoPosterGrabber::onTimeout);
    timeout_->start();

    player_->setSource(QUrl::fromLocalFile(outputPath_));
    // play() is required for QMediaPlayer to actually decode frames
    // through the sink. The first decoded frame fires
    // videoFrameChanged; we capture it and tear down immediately.
    player_->play();
}

void VideoPosterGrabber::onVideoFrameChanged()
{
    if (fired_)
        return;

    const QVideoFrame frame = sink_ ? sink_->videoFrame() : QVideoFrame();
    if (!frame.isValid())
        return;

    // toImage() handles the format conversion internally. May return
    // null if the underlying format isn't supported — in that case we
    // wait for the next frame (videoFrameChanged keeps firing during
    // playback) until the timeout catches us if nothing usable shows
    // up.
    const QImage image = frame.toImage();
    if (image.isNull())
        return;

    const QString destPath = thumbPathFor(outputPath_, outId_);
    if (destPath.isEmpty())
    {
        finish(QString());
        return;
    }

    const QImage scaled = scaleForThumb(image);
    if (scaled.isNull() || !scaled.save(destPath, "JPG",
                                        ChainThumbnailer::kJpegQuality))
    {
        finish(QString());
        return;
    }

    finish(destPath);
}

void VideoPosterGrabber::onTimeout()
{
    if (fired_)
        return;
    finish(QString());
}

void VideoPosterGrabber::finish(const QString &thumbPath)
{
    if (fired_)
        return;
    fired_ = true;

    // Stop everything cleanly before we deliver the callback. If the
    // callback synchronously schedules more thumbnail work, we don't
    // want our QMediaPlayer still emitting frames in the background.
    if (timeout_ != nullptr)
        timeout_->stop();
    if (player_ != nullptr)
    {
        player_->stop();
        // Drop the sink connection so a late frame after stop() can't
        // re-enter onVideoFrameChanged.
        if (sink_ != nullptr)
            disconnect(sink_, nullptr, this, nullptr);
    }

    // Deliver via QueuedConnection so the callback runs in a clean
    // stack frame on the context's thread — matches the image path's
    // behavior so the engine sees both paths identically.
    if (callbackContext_ != nullptr && cb_)
    {
        QPointer<QObject> ctx(callbackContext_);
        deliverCallback(ctx, std::move(cb_), thumbPath);
    }

    // Self-destruct. deleteLater() schedules removal after the
    // current event loop iteration so any pending frame signals
    // already in the queue can drain without re-entering a freed
    // object.
    deleteLater();
}

} // namespace spellvision::chain
