#pragma once

#include <QJsonObject>
#include <QString>

#include <functional>

namespace spellvision::workflows
{

class WorkflowLaunchController final
{
public:
    using ModeAvailability = std::function<bool(const QString &modeId)>;

    // The answer to "what kind of generation is this workflow", plus why -- because the UI has to be
    // able to EXPLAIN a refusal. `modeId` is empty whenever `routable` is false, so a caller that
    // only wants the answer can use resolveModeId() and treat empty as "do not navigate".
    //
    // `confidence` is the classifier's confidence in its own verdict (workflow_scanner's
    // classification_confidence / capability_report.confidence), 0.0 when none was recorded. A user
    // override reports 1.0: it is not an inference, so the classifier's number does not describe it.
    struct ModeResolution
    {
        // Where it can be OPENED. Empty whenever `routable` is false -- a caller that only wants the
        // answer uses resolveModeId() and treats empty as "do not navigate".
        QString modeId;
        // What it IS, routable or not: the normalised classification, so Flows can still say "v2v"
        // about a workflow it cannot open, and still send that task_command to the worker. Empty only
        // when nothing classified it. These are two different questions that share a vocabulary, and
        // collapsing them is how "media_type says video" became "therefore t2v".
        QString verdict;
        QString reason;
        double confidence = 0.0;
        bool routable = false;
    };

    WorkflowLaunchController() = delete;

    static QString normalizeModeId(const QString &modeId);

    // THE resolver. Accepts an import reply, a profile.json object or a launch draft -- they spell
    // the verdict with different keys and this knows all of them, so no caller has to.
    //
    // It was three functions: resolveDraftModeId here, HomePage::inferModeFromWorkflowProfile and
    // WorkflowLibraryPage's own normalisation. The Home one fell back to matching "t2i"/"i2v"/... as
    // SUBSTRINGS OF THE FILE PATH and then to t2i regardless, so a workflow whose classification
    // failed was routed by its filename onto a page whose graph it does not belong to. There is no
    // filename fallback here and there must never be one: landing the user somewhere plausible with
    // the wrong graph is worse than refusing, because a refusal can carry a reason.
    static ModeResolution modeResolution(const QJsonObject &source,
                                         const ModeAvailability &isModeAvailable = ModeAvailability());
    static QString resolveModeId(const QJsonObject &source,
                                 const ModeAvailability &isModeAvailable = ModeAvailability());

    static QString resolveDraftModeId(const QJsonObject &draft, const ModeAvailability &isModeAvailable);

    static QString draftSourceName(const QJsonObject &draft);
    static QString draftOpenedLogLine(const QJsonObject &draft, const QString &modeId);
    static QString draftRequiresReviewLogLine(const QString &modeId);

    static QJsonObject buildWorkflowLaunchRequest(const QJsonObject &profile,
                                                  const QString &projectRoot,
                                                  const QString &pythonExecutable);
};

} // namespace spellvision::workflows
