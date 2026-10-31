#pragma once

#include <QWidget>

class QLabel;
class QMediaPlayer;
class QVideoSink;

// The open. A short branded film, then the window. Missing file, a player
// error, or a self-test argument skips it. Launch must never wait on a film
// that cannot play.
class StartupFilm final : public QWidget
{
public:
    explicit StartupFilm(QWidget *parent = nullptr);
    ~StartupFilm() override;

    // True when a file was found and playback started.
    bool start();
    // Pump events until the film ends, errors, or maxMs. No-op if start() failed.
    void waitUntilDone(int maxMs = 4000);
    void finish();

    static QString locate();

private:
    QLabel *view_ = nullptr;
    QMediaPlayer *player_ = nullptr;
    QVideoSink *sink_ = nullptr;
    bool done_ = true;
};
