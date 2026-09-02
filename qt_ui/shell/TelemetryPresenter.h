#pragma once

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
class TelemetryPresenter
{
public:
    // The one page-name answer. Same source as the title-bar breadcrumb.
    static QString pageLabelText(const QString &modeId);

    // Basename of a model/LoRA path, for a bar that is ~160px wide.
    static QString shortAssetName(const QString &value);

    // `hasSlot` is whether THIS page can carry such an asset at all -- not whether one is chosen.
    static TelemetryChip assetChip(const QString &caption, bool hasSlot, const QString &value);
};

} // namespace spellvision::shell
