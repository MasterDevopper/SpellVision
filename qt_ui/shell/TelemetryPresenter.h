#pragma once

#include "QueueManager.h"

#include <QString>

namespace spellvision::shell
{

// What one chip of the bottom telemetry bar should say, and whether it should be there at all.
struct TelemetryChip
{
    bool visible = true;
    QString text;
    QString toolTip;
};

// Latch MainWindow keeps across polls. Named fields rather than QObject properties so a test can
// construct a submit → empty-snapshot → complete sequence without a MainWindow.
struct TelemetryLatch
{
    bool explicitBusy = false;
    QString busyMode;
    QString currentMode;
    QString busyState;
    int completedRowsAtSubmit = 0;
    bool sawActive = false;
    bool completionPulse = false;
    int phaseRank = 0;
    int progressTarget = 0;
};

// The queue's contribution to one telemetry tick. MainWindow reduces QueueManager + the tray
// model to this; the presenter never walks either.
struct TelemetryJob
{
    bool hasActiveItem = false;
    QueueItemState activeState = QueueItemState::Unknown;
    int activeProgress = 0;
    int activeSteps = 0;
};

// What the bottom bar must show, plus the latch writes the next tick needs.
struct TelemetryProgressView
{
    QString readyText;
    QString stateText;
    int progress = 0;
    int phaseRank = 0;
    int progressTarget = 0;
    bool busy = false;
    bool indeterminate = false;
    bool showsPercent = false;
    bool latchSawActive = false;
    bool startCompletionPulse = false;
    bool completedOutputObserved = false;
    bool videoCompletionObserved = false;
};

// The bottom bar's answers, in one place, as pure functions.
//
// Two defects made this a class rather than three more lines in MainWindow:
//
//   * "Model:" showed the LAST-RUN model rather than the current page's. Not two writers -- one
//     writer that was never CALLED on a page change. syncBottomTelemetry() hung off submits and
//     queue changes only, and the queue route is change-gated, so an idle app kept whatever the
//     bar held when the queue last moved. The third instance of that trap in MainWindow.cpp, whose
//     first two are documented in comments beside the fix (`queuePollSucceeded`, not
//     `afterQueueSnapshotApplied`).
//   * The page name had THREE writers -- `modeId.toUpper()` ("T2I"), `pageContextForMode()`
//     ("Text to Image"), and a `setBottomPageContext` setter -- so which one you saw depended on
//     whether the queue last moved before or after the mode switch.
//
// And a third state that was never expressed: every page with no model slot read "Model: none",
// the same string as "you are on T2I and have chosen nothing". A chip that cannot apply is hidden;
// a chip that applies and is empty says so in words.
//
// Wave 3 task 2 adds the busy/progress half. It lived as anonymous helpers plus a 150-line method
// on MainWindow, which is why the rank ratchet, the saw-active latch and the completed-rows
// denominator had no test: constructing MainWindow to tick them also runs the 35 s venv probe.
class TelemetryPresenter
{
public:
    // The 900 ms hold at "Completed" / 100 % before the bar returns to Idle. Anchored in the
    // tests as a product number, not compared to itself.
    static constexpr int kCompletionPulseMs = 900;

    // The one page-name answer. Same source as the title-bar breadcrumb.
    static QString pageLabelText(const QString &modeId);

    // Basename of a model/LoRA path, for a bar that is ~160px wide.
    static QString shortAssetName(const QString &value);

    // `hasSlot` is whether THIS page can carry such an asset at all -- not whether one is chosen.
    static TelemetryChip assetChip(const QString &caption, bool hasSlot, const QString &value);

    static bool modeIsImage(const QString &modeId);

    static int rankFromState(QueueItemState state);
    static int rankFromText(const QString &stateText);
    static QString stateFromRank(int rank, const QString &fallback = QString());
    static int minimumProgressForRank(int rank);

    // One tick of the busy/progress half of the bar. Pure: the same inputs always produce the
    // same labels, so a test can assert what is ON SCREEN without a window.
    static TelemetryProgressView progressView(bool imageWorkspace,
                                              int visibleQueueCount,
                                              const TelemetryJob &job,
                                              TelemetryLatch latch);
};

} // namespace spellvision::shell
