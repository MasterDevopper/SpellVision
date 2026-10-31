#include "StartupFilm.h"

#include <QCoreApplication>
#include <QDir>
#include <QEventLoop>
#include <QFileInfo>
#include <QLabel>
#include <QScreen>
#include <QMediaPlayer>
#include <QTimer>
#include <QUrl>
#include <QVideoFrame>
#include <QVideoSink>
#include <QVBoxLayout>

StartupFilm::StartupFilm(QWidget *parent)
    : QWidget(parent)
{
    setWindowFlags(Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint | Qt::Tool);
    setAttribute(Qt::WA_TranslucentBackground, false);
    setStyleSheet(QStringLiteral("background:#0B0A10;"));
    setFixedSize(960, 540);

    view_ = new QLabel(this);
    view_->setAlignment(Qt::AlignCenter);
    view_->setScaledContents(true);
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->addWidget(view_);
}

StartupFilm::~StartupFilm() = default;

QString StartupFilm::locate()
{
    const QString name = QStringLiteral("spellvision_open.mp4");
    const QString beside = QCoreApplication::applicationDirPath() + QStringLiteral("/brand/") + name;
    if (QFileInfo::exists(beside))
        return beside;
    const QString tree = QCoreApplication::applicationDirPath()
                         + QStringLiteral("/../../qt_ui/brand/") + name;
    if (QFileInfo::exists(tree))
        return QDir::cleanPath(tree);
    return {};
}

bool StartupFilm::start()
{
    const QString path = locate();
    if (path.isEmpty())
        return false;

    player_ = new QMediaPlayer(this);
    sink_ = new QVideoSink(this);
    player_->setVideoSink(sink_);
    player_->setAudioOutput(nullptr);
    connect(sink_, &QVideoSink::videoFrameChanged, this, [this](const QVideoFrame &frame) {
        if (!frame.isValid() || !view_)
            return;
        const QImage image = frame.toImage();
        if (!image.isNull())
            view_->setPixmap(QPixmap::fromImage(image));
    });
    connect(player_, &QMediaPlayer::mediaStatusChanged, this, [this](QMediaPlayer::MediaStatus status) {
        if (status == QMediaPlayer::EndOfMedia || status == QMediaPlayer::InvalidMedia)
            done_ = true;
    });
    connect(player_, &QMediaPlayer::errorOccurred, this, [this](QMediaPlayer::Error, const QString &) {
        done_ = true;
    });

    done_ = false;
    const QRect desk = this->screen() ? this->screen()->availableGeometry() : QRect(0, 0, 960, 540);
    move(desk.center() - rect().center());
    show();
    player_->setSource(QUrl::fromLocalFile(path));
    player_->play();
    return true;
}

void StartupFilm::waitUntilDone(int maxMs)
{
    if (!player_ || done_)
        return;
    QEventLoop loop;
    QTimer cap;
    cap.setSingleShot(true);
    connect(&cap, &QTimer::timeout, &loop, &QEventLoop::quit);
    QTimer pump;
    connect(&pump, &QTimer::timeout, this, [this, &loop]() {
        if (done_)
            loop.quit();
    });
    pump.start(40);
    cap.start(maxMs);
    loop.exec();
}

void StartupFilm::finish()
{
    if (player_)
        player_->stop();
    hide();
    done_ = true;
}
