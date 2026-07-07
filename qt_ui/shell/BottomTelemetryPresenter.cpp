#include "BottomTelemetryPresenter.h"

#include "../ImageGenerationPage.h"
#include "../QueueManager.h"
#include "../ThemeManager.h"

#include <QFileInfo>
#include <QLabel>
#include <QProgressBar>
#include <QSizePolicy>
#include <QStatusBar>
#include <QStringList>

namespace
{
QString queueStateDisplay(QueueItemState state)
{
    switch (state)
    {
    case QueueItemState::Queued:
        return QStringLiteral("Queued");
    case QueueItemState::Preparing:
        return QStringLiteral("Preparing");
    case QueueItemState::Running:
        return QStringLiteral("Running");
    case QueueItemState::Completed:
        return QStringLiteral("Completed");
    case QueueItemState::Failed:
        return QStringLiteral("Failed");
    case QueueItemState::Cancelled:
        return QStringLiteral("Cancelled");
    case QueueItemState::Skipped:
        return QStringLiteral("Skipped");
    case QueueItemState::Unknown:
    default:
        return QStringLiteral("Unknown");
    }
}


QString normalizedCommand(const QString &value)
{
    return value.trimmed().toLower();
}

QStringList acceptedCommandsForMode(const QString &modeId)
{
    const QString mode = modeId.trimmed().toLower();

    if (mode == QStringLiteral("t2i"))
        return {QStringLiteral("t2i"), QStringLiteral("txt2img"), QStringLiteral("text_to_image")};

    if (mode == QStringLiteral("i2i"))
        return {QStringLiteral("i2i"), QStringLiteral("img2img"), QStringLiteral("image_to_image")};

    if (mode == QStringLiteral("t2v"))
        return {QStringLiteral("t2v"), QStringLiteral("text_to_video")};

    if (mode == QStringLiteral("i2v"))
        return {QStringLiteral("i2v"), QStringLiteral("image_to_video")};

    return {};
}

bool itemMatchesMode(const QueueItem &item, const QString &modeId)
{
    const QStringList accepted = acceptedCommandsForMode(modeId);
    if (accepted.isEmpty())
        return true;

    return accepted.contains(normalizedCommand(item.command));
}

bool itemIsActiveWork(const QueueItem &item)
{
    if (item.isTerminal())
        return false;

    return item.running ||
           item.state == QueueItemState::Queued ||
           item.state == QueueItemState::Preparing ||
           item.state == QueueItemState::Running;
}

bool modeIsImageWorkspace(const QString &modeId)
{
    const QString mode = modeId.trimmed().toLower();
    return mode == QStringLiteral("t2i") || mode == QStringLiteral("i2i");
}


QLabel *makeLabel(const QString &text, QWidget *owner)
{
    return new QLabel(text, owner);
}

void assignLabel(QLabel **slot, QLabel *label)
{
    if (!slot)
        return;

    *slot = label;
}

void assignProgress(QProgressBar **slot, QProgressBar *progressBar)
{
    if (!slot)
        return;

    *slot = progressBar;
}
}

namespace spellvision::shell
{


void BottomTelemetryPresenter::build(const BuildBindings &bindings)
{
    if (!bindings.statusBar)
        return;

    auto *bar = bindings.statusBar;
    bar->setSizeGripEnabled(false);
    bar->setFixedHeight(34);
    bar->setMinimumHeight(34);
    bar->setMaximumHeight(34);

    auto *readyLabel = makeLabel(QStringLiteral("Ready"), bindings.owner);
    auto *pageLabel = makeLabel(QStringLiteral("Home"), bindings.owner);
    auto *runtimeLabel = makeLabel(QStringLiteral("Runtime: local"), bindings.owner);
    auto *queueLabel = makeLabel(QStringLiteral("Queue: 0"), bindings.owner);
    auto *vramLabel = makeLabel(QStringLiteral("VRAM: idle"), bindings.owner);
    auto *modelLabel = makeLabel(QStringLiteral("Model: none"), bindings.owner);
    auto *loraLabel = makeLabel(QStringLiteral("LoRA: none"), bindings.owner);
    auto *stateLabel = makeLabel(QStringLiteral("Idle"), bindings.owner);

    auto stabilizeLabel = [](QLabel *label, int width) {
        if (!label)
            return;

        label->setFixedWidth(width);
        label->setMinimumHeight(22);
        label->setMaximumHeight(22);
        label->setWordWrap(false);
        label->setTextInteractionFlags(Qt::NoTextInteraction);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    };

    stabilizeLabel(readyLabel, 64);
    stabilizeLabel(pageLabel, 150);
    stabilizeLabel(runtimeLabel, 150);
    stabilizeLabel(queueLabel, 104);
    stabilizeLabel(vramLabel, 118);
    stabilizeLabel(modelLabel, 210);
    stabilizeLabel(loraLabel, 150);
    stabilizeLabel(stateLabel, 96);

    auto *progressBar = new QProgressBar(bindings.owner);
    progressBar->setObjectName(QStringLiteral("BottomProgressBar"));
    progressBar->setRange(0, 100);
    progressBar->setValue(0);
    progressBar->setTextVisible(true);
    progressBar->setFormat(QStringLiteral("%p%"));
    progressBar->setFixedSize(154, 16);
    progressBar->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    // Phase 8: build() is vestigial/dead (no call site; the live bottom progress bar is owned
    // by the shell stylesheet's migrated #BottomProgressBar rule). Tokenized anyway so the
    // bleed audit is zero and a resurrected build() would be theme-correct.
    progressBar->setStyleSheet(QStringLiteral(
        "QProgressBar#BottomProgressBar {"
        " border: 1px solid %1;"
        " border-radius: 7px;"
        " background: %2;"
        " color: %3;"
        " font-size: 9px;"
        " text-align: center;"
        "}"
        "QProgressBar#BottomProgressBar::chunk {"
        " border-radius: 6px;"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        " stop:0 %4,"
        " stop:1 %5);"
        "}")
        .arg(ThemeManager::instance().css(ThemeManager::Color::Border),
             ThemeManager::instance().css(ThemeManager::Color::Surface0),
             ThemeManager::instance().css(ThemeManager::Color::TextHi),
             ThemeManager::instance().css(ThemeManager::Color::Accent),
             ThemeManager::instance().css(ThemeManager::Color::AccentSecondary)));

    assignLabel(bindings.readyLabel, readyLabel);
    assignLabel(bindings.pageLabel, pageLabel);
    assignLabel(bindings.runtimeLabel, runtimeLabel);
    assignLabel(bindings.queueLabel, queueLabel);
    assignLabel(bindings.vramLabel, vramLabel);
    assignLabel(bindings.modelLabel, modelLabel);
    assignLabel(bindings.loraLabel, loraLabel);
    assignLabel(bindings.stateLabel, stateLabel);
    assignProgress(bindings.progressBar, progressBar);

    bar->addWidget(readyLabel);
    bar->addWidget(pageLabel);
    bar->addPermanentWidget(runtimeLabel);
    bar->addPermanentWidget(queueLabel);
    bar->addPermanentWidget(vramLabel);
    bar->addPermanentWidget(modelLabel);
    bar->addPermanentWidget(loraLabel);
    bar->addPermanentWidget(stateLabel);
    bar->addPermanentWidget(progressBar);
}



void BottomTelemetryPresenter::sync(const SyncBindings &bindings)
{
    const bool imageWorkspace = modeIsImageWorkspace(bindings.currentModeId);

    int visibleQueueCount = 0;
    const QueueItem *activeItem = nullptr;

    if (bindings.queueManager)
    {
        const QString activeQueueId = bindings.queueManager->activeQueueItemId();

        if (!activeQueueId.trimmed().isEmpty() && bindings.queueManager->contains(activeQueueId))
        {
            const QueueItem item = bindings.queueManager->itemById(activeQueueId);
            if (itemMatchesMode(item, bindings.currentModeId) && itemIsActiveWork(item))
            {
                const QVector<QueueItem> &items = bindings.queueManager->items();
                for (const QueueItem &candidate : items)
                {
                    if (candidate.id == item.id)
                    {
                        activeItem = &candidate;
                        break;
                    }
                }
            }
        }

        const QVector<QueueItem> &items = bindings.queueManager->items();
        for (const QueueItem &item : items)
        {
            if (!itemMatchesMode(item, bindings.currentModeId))
                continue;

            if (itemIsActiveWork(item))
            {
                activeItem = &item;
                continue;
            }

            if (imageWorkspace)
            {
                if (item.isTerminal())
                    ++visibleQueueCount;
            }
            else
            {
                ++visibleQueueCount;
            }
        }
    }

    const bool busy = activeItem != nullptr;
    const QString stateText = busy ? queueStateDisplay(activeItem->state) : QStringLiteral("Idle");

    int progressPercent = 0;
    if (busy)
    {
        progressPercent = activeItem->progressPercent();

        if (progressPercent <= 0 && activeItem->state == QueueItemState::Preparing)
            progressPercent = 5;

        if (progressPercent <= 0 && activeItem->state == QueueItemState::Running)
            progressPercent = 8;
    }

    if (bindings.readyLabel)
        bindings.readyLabel->setText(busy ? QStringLiteral("Busy") : QStringLiteral("Ready"));

    if (bindings.pageLabel)
    {
        const QString pageText = !bindings.pageContextText.trimmed().isEmpty()
                                     ? bindings.pageContextText.trimmed()
                                     : bindings.currentModeId.trimmed().toUpper();
        bindings.pageLabel->setText(pageText.isEmpty() ? QStringLiteral("Home") : pageText);
    }

    if (bindings.runtimeLabel)
        bindings.runtimeLabel->setText(QStringLiteral("Runtime: local"));

    if (bindings.queueLabel)
        bindings.queueLabel->setText(QStringLiteral("Queue: %1").arg(visibleQueueCount));

    // Pass 28P:
    // Until real GPU memory telemetry is wired from the worker, do not leave this
    // as the misleading permanent "n/a" placeholder. Show GPU activity state.
    if (bindings.vramLabel)
        bindings.vramLabel->setText(busy ? QStringLiteral("VRAM: active") : QStringLiteral("VRAM: idle"));

    const QString modelValue = bindings.currentGenerationPage ? bindings.currentGenerationPage->selectedModelValue() : QString();
    const QString loraValue = bindings.currentGenerationPage ? bindings.currentGenerationPage->selectedLoraValue() : QString();

    if (bindings.modelLabel)
        bindings.modelLabel->setText(QStringLiteral("Model: %1").arg(shortAssetName(modelValue)));

    if (bindings.loraLabel)
        bindings.loraLabel->setText(QStringLiteral("LoRA: %1").arg(shortAssetName(loraValue)));

    if (bindings.stateLabel)
        bindings.stateLabel->setText(busy ? stateText : QStringLiteral("Idle"));

    if (bindings.progressBar)
    {
        bindings.progressBar->setRange(0, 100);
        bindings.progressBar->setValue(progressPercent);
        bindings.progressBar->setTextVisible(true);
        bindings.progressBar->setFormat(busy ? QStringLiteral("%p%") : QStringLiteral(""));
    }
}


QString BottomTelemetryPresenter::shortAssetName(const QString &value)
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return QStringLiteral("none");

    const QFileInfo info(trimmed);
    const QString baseName = info.completeBaseName().trimmed();
    if (!baseName.isEmpty())
        return baseName;

    const QString fileName = info.fileName().trimmed();
    return fileName.isEmpty() ? trimmed : fileName;
}

} // namespace spellvision::shell
