#include "BottomTelemetryPresenter.h"

#include "../ImageGenerationPage.h"
#include "../QueueManager.h"

#include <QFileInfo>
#include <QLabel>
#include <QProgressBar>
#include <QStatusBar>

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

    auto *readyLabel = makeLabel(QStringLiteral("Ready"), bindings.owner);
    readyLabel->setMinimumWidth(44);

    auto *pageLabel = makeLabel(QStringLiteral("Home"), bindings.owner);
    auto *runtimeLabel = makeLabel(QStringLiteral("Runtime: unknown"), bindings.owner);
    auto *queueLabel = makeLabel(QStringLiteral("Queue: 0"), bindings.owner);
    auto *vramLabel = makeLabel(QStringLiteral("VRAM: n/a"), bindings.owner);
    auto *modelLabel = makeLabel(QStringLiteral("Model: none"), bindings.owner);
    auto *loraLabel = makeLabel(QStringLiteral("LoRA: none"), bindings.owner);
    auto *stateLabel = makeLabel(QStringLiteral("Idle"), bindings.owner);

    auto *progressBar = new QProgressBar(bindings.owner);
    progressBar->setObjectName(QStringLiteral("BottomProgressBar"));
    progressBar->setRange(0, 100);
    progressBar->setValue(0);
    progressBar->setTextVisible(false);
    progressBar->setFixedHeight(8);
    progressBar->setMaximumWidth(120);

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
    const int queueCount = bindings.queueManager ? bindings.queueManager->count() : 0;
    const QString activeQueueId = bindings.queueManager ? bindings.queueManager->activeQueueItemId() : QString();
    const bool hasActiveQueueItem = bindings.queueManager && !activeQueueId.trimmed().isEmpty() && bindings.queueManager->contains(activeQueueId);

    QString stateText = QStringLiteral("Idle");
    int progressPercent = 0;

    if (hasActiveQueueItem)
    {
        const QueueItem item = bindings.queueManager->itemById(activeQueueId);
        stateText = queueStateDisplay(item.state);
        progressPercent = item.progressPercent();
    }

    if (bindings.readyLabel)
        bindings.readyLabel->setText(hasActiveQueueItem ? QStringLiteral("Busy") : QStringLiteral("Ready"));

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
    {
        bindings.queueLabel->setText(activeQueueId.isEmpty()
                                         ? QStringLiteral("Queue: %1").arg(queueCount)
                                         : QStringLiteral("Queue: %1 • active").arg(queueCount));
    }

    if (bindings.vramLabel && bindings.vramLabel->text().trimmed().isEmpty())
        bindings.vramLabel->setText(QStringLiteral("VRAM: n/a"));

    const QString modelValue = bindings.currentGenerationPage ? bindings.currentGenerationPage->selectedModelValue() : QString();
    const QString loraValue = bindings.currentGenerationPage ? bindings.currentGenerationPage->selectedLoraValue() : QString();

    if (bindings.modelLabel)
        bindings.modelLabel->setText(QStringLiteral("Model: %1").arg(shortAssetName(modelValue)));

    if (bindings.loraLabel)
        bindings.loraLabel->setText(QStringLiteral("LoRA: %1").arg(shortAssetName(loraValue)));

    if (bindings.stateLabel)
        bindings.stateLabel->setText(stateText);

    if (bindings.progressBar)
        bindings.progressBar->setValue(progressPercent);
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
