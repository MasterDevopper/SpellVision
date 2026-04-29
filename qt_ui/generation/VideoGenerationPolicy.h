#pragma once

#include "GenerationRequestBuilder.h"

#include <QString>
#include <QStringList>

namespace spellvision::generation
{

struct VideoGenerationPolicySnapshot
{
    QString requestKind;
    QString durationLabel;
    QString stackKind;
    QString stackMode;
    QString diagnosticSummary;

    bool isVideoMode = false;
    bool isI2V = false;
    bool requiresInputImage = false;
    bool hasInputImage = false;
    bool hasWorkflowBinding = false;
    bool hasNativeVideoStack = false;
    bool stackReady = false;
    bool dimensionsValid = false;
    bool frameCountValid = false;
    bool fpsValid = false;
    bool ready = false;

    QStringList warnings;
};

class VideoGenerationPolicy final
{
public:
    static VideoGenerationPolicySnapshot evaluate(const GenerationRequestDraft &draft);
    static QString formatDurationLabel(int frames, int fps);
    static bool requiresInputImageForMode(const QString &mode);

private:
    static bool hasWorkflowBinding(const GenerationRequestDraft &draft);
    static bool hasNativeVideoStack(const GenerationRequestDraft &draft);
    static bool isStackReady(const GenerationRequestDraft &draft);
};

} // namespace spellvision::generation
