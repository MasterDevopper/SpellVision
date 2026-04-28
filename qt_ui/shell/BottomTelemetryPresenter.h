#pragma once

#include <QString>

class ImageGenerationPage;
class QLabel;
class QProgressBar;
class QStatusBar;
class QWidget;
class QueueManager;

namespace spellvision::shell
{

class BottomTelemetryPresenter final
{
public:
    struct BuildBindings
    {
        QWidget *owner = nullptr;
        QStatusBar *statusBar = nullptr;

        QLabel **readyLabel = nullptr;
        QLabel **pageLabel = nullptr;
        QLabel **runtimeLabel = nullptr;
        QLabel **queueLabel = nullptr;
        QLabel **vramLabel = nullptr;
        QLabel **modelLabel = nullptr;
        QLabel **loraLabel = nullptr;
        QLabel **stateLabel = nullptr;
        QProgressBar **progressBar = nullptr;
    };

    struct SyncBindings
    {
        QueueManager *queueManager = nullptr;
        ImageGenerationPage *currentGenerationPage = nullptr;
        QString currentModeId;
        QString pageContextText;

        QLabel *readyLabel = nullptr;
        QLabel *pageLabel = nullptr;
        QLabel *runtimeLabel = nullptr;
        QLabel *queueLabel = nullptr;
        QLabel *vramLabel = nullptr;
        QLabel *modelLabel = nullptr;
        QLabel *loraLabel = nullptr;
        QLabel *stateLabel = nullptr;
        QProgressBar *progressBar = nullptr;
    };

    static void build(const BuildBindings &bindings);
    static void sync(const SyncBindings &bindings);
    static QString shortAssetName(const QString &value);

private:
    BottomTelemetryPresenter() = delete;
};

} // namespace spellvision::shell
