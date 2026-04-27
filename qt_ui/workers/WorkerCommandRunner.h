#pragma once

#include <QJsonObject>
#include <QString>

#include <functional>

namespace spellvision::workers
{

class WorkerCommandRunner final
{
public:
    enum class SubmitKind
    {
        Generate,
        Queue
    };

    struct Bindings
    {
        std::function<QJsonObject()> buildPayload;
        std::function<QString()> readinessBlockReason;
        std::function<void(const QString &)> showReadinessHint;
        std::function<bool()> isVideoMode;
        std::function<QString()> selectedModelValue;
        std::function<bool()> hasVideoWorkflowBinding;
        std::function<void(const QJsonObject &)> emitGenerate;
        std::function<void(const QJsonObject &)> emitQueue;
    };

    static QString submitOrigin(SubmitKind kind);
    static void submit(SubmitKind kind, const Bindings &bindings);
};

} // namespace spellvision::workers
