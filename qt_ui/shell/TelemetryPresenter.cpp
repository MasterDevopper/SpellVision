#include "TelemetryPresenter.h"

#include "ShellNavigationController.h"

#include <QFileInfo>
#include <QtGlobal>

namespace spellvision::shell
{

QString TelemetryPresenter::pageLabelText(const QString &modeId)
{
    return ShellNavigationController::pageContextForMode(modeId);
}

QString TelemetryPresenter::shortAssetName(const QString &value)
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return QString();
    const QFileInfo info(trimmed);
    const QString baseName = info.completeBaseName().trimmed();
    if (!baseName.isEmpty())
        return baseName;
    const QString fileName = info.fileName().trimmed();
    return fileName.isEmpty() ? trimmed : fileName;
}

TelemetryChip TelemetryPresenter::assetChip(const QString &caption, bool hasSlot, const QString &value)
{
    TelemetryChip chip;
    if (!hasSlot)
    {
        // Flows, History, Models, Runtime, Settings... "Model: none" on a page that has no model to
        // choose is a false statement about the user's choices, and it is indistinguishable from a
        // generation page where they have chosen nothing. The bar already hides ETA and LoRA when
        // the window is narrow, so a hidden chip is existing behaviour, not a new shape.
        chip.visible = false;
        return chip;
    }

    const QString shortName = shortAssetName(value);
    if (shortName.isEmpty())
    {
        chip.text = QStringLiteral("%1: not selected").arg(caption);
        chip.toolTip = QStringLiteral("No %1 chosen on this page yet.").arg(caption.toLower());
        return chip;
    }

    chip.text = QStringLiteral("%1: %2").arg(caption, shortName);
    chip.toolTip = value.trimmed();
    return chip;
}

bool TelemetryPresenter::modeIsImage(const QString &modeId)
{
    const QString mode = modeId.trimmed().toLower();
    return mode == QStringLiteral("t2i") || mode == QStringLiteral("i2i");
}

int TelemetryPresenter::rankFromState(QueueItemState state)
{
    switch (state)
    {
    case QueueItemState::Queued:
        return 1;
    case QueueItemState::Preparing:
        return 2;
    case QueueItemState::Running:
        return 3;
    case QueueItemState::Completed:
    case QueueItemState::Failed:
    case QueueItemState::Cancelled:
    case QueueItemState::Skipped:
    case QueueItemState::Unknown:
    default:
        return 0;
    }
}

int TelemetryPresenter::rankFromText(const QString &stateText)
{
    const QString state = stateText.trimmed().toLower();

    if (state == QStringLiteral("running"))
        return 3;

    if (state == QStringLiteral("preparing"))
        return 2;

    if (state == QStringLiteral("queued") ||
        state == QStringLiteral("queueing") ||
        state == QStringLiteral("submitting"))
        return 1;

    return 0;
}

QString TelemetryPresenter::stateFromRank(int rank, const QString &fallback)
{
    if (rank >= 3)
        return QStringLiteral("Running");

    if (rank == 2)
        return QStringLiteral("Preparing");

    if (rank == 1)
    {
        const QString normalized = fallback.trimmed();
        return normalized.isEmpty() ? QStringLiteral("Submitting") : normalized;
    }

    return QStringLiteral("Idle");
}

int TelemetryPresenter::minimumProgressForRank(int rank)
{
    if (rank >= 3)
        return 12;

    if (rank == 2)
        return 7;

    if (rank == 1)
        return 3;

    return 0;
}

TelemetryProgressView TelemetryPresenter::progressView(bool imageWorkspace,
                                                       int visibleQueueCount,
                                                       const TelemetryJob &job,
                                                       TelemetryLatch latch)
{
    TelemetryProgressView out;

    if (job.hasActiveItem)
        latch.sawActive = true;
    out.latchSawActive = job.hasActiveItem;

    const bool explicitBusy =
        latch.explicitBusy && latch.busyMode == latch.currentMode;

    out.videoCompletionObserved =
        explicitBusy &&
        !imageWorkspace &&
        !job.hasActiveItem &&
        latch.sawActive;

    out.completedOutputObserved =
        (explicitBusy &&
         imageWorkspace &&
         !job.hasActiveItem &&
         latch.completedRowsAtSubmit >= 0 &&
         visibleQueueCount > latch.completedRowsAtSubmit) ||
        out.videoCompletionObserved;

    const bool completionPulse = latch.completionPulse;
    const bool activeForBusy = job.hasActiveItem && !out.completedOutputObserved;
    out.busy = activeForBusy || explicitBusy || completionPulse;
    out.startCompletionPulse = out.completedOutputObserved && !completionPulse;

    const int observedRank = activeForBusy
        ? rankFromState(job.activeState)
        : (out.busy ? rankFromText(latch.busyState) : 0);

    int displayedRank = latch.phaseRank;
    if (out.busy && !out.completedOutputObserved && !completionPulse)
        displayedRank = qMax(displayedRank, observedRank);
    else if (!out.busy)
        displayedRank = 0;

    out.phaseRank = displayedRank;

    if (out.completedOutputObserved || completionPulse)
        out.stateText = QStringLiteral("Completed");
    else if (out.busy)
        out.stateText = stateFromRank(displayedRank, latch.busyState);
    else
        out.stateText = QStringLiteral("Idle");

    int targetProgress = job.hasActiveItem && !out.completedOutputObserved ? job.activeProgress : 0;
    if (out.completedOutputObserved || completionPulse)
    {
        targetProgress = 100;
    }
    else if (out.busy)
    {
        targetProgress = qMax(targetProgress, minimumProgressForRank(displayedRank));
        targetProgress = qMax(targetProgress, latch.progressTarget);
        targetProgress = qBound(0, targetProgress, 99);
    }
    else
    {
        targetProgress = 0;
    }

    out.progressTarget = targetProgress;
    out.progress = targetProgress;
    out.readyText = (out.busy || completionPulse || out.completedOutputObserved)
        ? QStringLiteral("Busy")
        : QStringLiteral("Ready");
    out.showsPercent = out.busy || completionPulse || out.completedOutputObserved;
    out.indeterminate = out.busy && activeForBusy && job.activeSteps <= 0
                        && !completionPulse && !out.completedOutputObserved;
    return out;
}

} // namespace spellvision::shell
