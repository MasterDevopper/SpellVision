#pragma once

#include <QJsonObject>
#include <QString>

#include <functional>

namespace spellvision::generation
{

class GenerationStatusController final
{
public:
    struct Bindings
    {
        std::function<void(bool busy, const QString &message)> setBusy;
        std::function<void(const QString &outputPath, const QString &caption)> routeOutput;
        std::function<void(const QString &message)> showProblem;
    };

    static void applyWorkerPayload(const QJsonObject &payload, const Bindings &bindings);

private:
    GenerationStatusController() = delete;
};

} // namespace spellvision::generation
