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
    QString resolvedFamily;
    QString backendRoute;
    QString validationStatus;

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
    bool usesPromptApiBackend = false;
    bool validatedPromptApiFamily = false;
    bool validatedVideoBackend = false;

    QStringList warnings;
};

class VideoGenerationPolicy final
{
public:
    static VideoGenerationPolicySnapshot evaluate(const GenerationRequestDraft &draft);
    static QString formatDurationLabel(int frames, int fps);
    static bool requiresInputImageForMode(const QString &mode);
    static bool isValidatedNativeFamily(const QString &family);
    static bool isValidatedPromptApiFamily(const QString &family);
    // Public so request construction can scope family-specific payload fields
    // (e.g. LTX defaults) to the resolved video family.
    static QString resolvedVideoFamily(const GenerationRequestDraft &draft);

private:
    static bool hasWorkflowBinding(const GenerationRequestDraft &draft);
    static bool hasNativeVideoStack(const GenerationRequestDraft &draft);
    static bool isStackReady(const GenerationRequestDraft &draft);
};

} // namespace spellvision::generation
