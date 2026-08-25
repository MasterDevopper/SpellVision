#pragma once

#include <QJsonObject>
#include <QString>
#include <QStringList>
#include <QVector>

namespace spellvision::generation
{

struct LoraRequestEntry
{
    QString display;
    QString value;
    double weight = 1.0;
    bool enabled = true;
};

struct GenerationRequestDraft
{
    QString mode;
    QString prompt;
    QString negativePrompt;
    QString preset;

    QString model;
    QString modelDisplay;
    QString modelFamily;
    QString modelModality;
    QString modelRole;
    QJsonObject selectedVideoStack;

    QString workflowProfile;
    QString workflowDraftSource;
    QString workflowProfilePath;
    QString workflowPath;
    QString compiledPromptPath;
    QString workflowBackend;
    QString workflowMediaType;
    QString promptApiExportPath;

    QString ltxPrimaryModelName;
    QString ltxTextEncoderName;
    QString ltxTextProjectionName;
    QString ltxAudioVaeName;
    QString ltxVideoVaeName;
    QString ltxVisionEncoderName;
    QString ltxOutputVariant;

    QVector<LoraRequestEntry> loras;
    QString loraStackSummary;

    QString imageSampler;
    QString imageScheduler;
    QString videoSampler;
    QString videoScheduler;

    int steps = 0;
    double cfg = 0.0;
    int seed = 0;
    int width = 0;
    int height = 0;

    bool isVideoMode = false;
    int frames = 81;
    int fps = 16;
    QString videoStackMode;
    // Explicit video-family pick from the UI combo (wan/ltx/...). Empty or "auto" = derive the
    // family from the model (VideoGenerationPolicy::resolvedVideoFamily); a concrete value overrides it.
    QString videoFamilyOverride;
    QString wanSplit = QStringLiteral("auto");
        int highSteps = 14;
        int lowSteps = 14;
        int splitStep = 14;
        double highNoiseShift = 5.0;
        double lowNoiseShift = 5.0;
        bool enableVaeTiling = false;

        // Textual inversion / embeddings (positive + negative token names)
        QStringList positiveEmbeddings;
        QStringList negativeEmbeddings;

        // Post-gen upscale (algorithmic and/or model)
        bool upscaleEnabled = false;
        QString upscaleMethod = QStringLiteral("none"); // none|lanczos|nearest|bilinear|model
        double upscaleScale = 1.0;
        QString upscaleModel;

        int batchCount = 1;
    QString outputPrefix;
    QString outputFolder;
    QString modelsRoot;

    bool isImageInputMode = false;
    QString inputImage;
    double denoiseStrength = 0.0;
};

class GenerationRequestBuilder final
{
public:
    static QJsonObject build(const GenerationRequestDraft &draft);

private:
    static QString normalizeAutoValue(const QString &value);
};

} // namespace spellvision::generation
