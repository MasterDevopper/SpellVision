#pragma once

// SpellVision — Chain Studio model headers (Pass 1).
//
// Pure data. Zero behavior, zero Qt-widget includes, no dependencies on
// any other spellvision component. This is the single source of truth
// for the chain data model defined in CHAIN_STUDIO_TRACK_A_DESIGN_REVISED.md §2.
//
// All later passes (store, watcher, engine, UI) consume these structs.
// If anything in the runtime contract feels wrong, change it HERE and
// the rest of the system follows; never silently extend behavior beside
// the model.
//
// Conventions:
//  - enum class everywhere; free toString/fromString pair per enum
//    (consumed by ChainStore in Pass 2).
//  - Default-constructible structs with sensible defaults so a "blank"
//    chain/stage/variation/config is meaningful.
//  - No copy/move tricks; let the compiler generate the obvious ones.
//  - No QObject. Engine holds these by value/reference and emits Qt
//    signals separately.

#include <QDateTime>
#include <QJsonObject>
#include <QString>
#include <QVector>

namespace spellvision::chain
{

    // ---------------------------------------------------------------------------
    // Enums
    // ---------------------------------------------------------------------------

    // Per design: I2_3D and Audio are DEFINED but execution-disabled until
    // their Python workers exist. The model carries them so neither the
    // engine nor the UI needs rework when those workers land.
    enum class StageKind
    {
        T2I,
        T2V,
        I2I,
        I2V,
        I2_3D,
        Audio,
    };

    inline QString toString(StageKind k)
    {
        switch (k)
        {
        case StageKind::T2I:
            return QStringLiteral("t2i");
        case StageKind::T2V:
            return QStringLiteral("t2v");
        case StageKind::I2I:
            return QStringLiteral("i2i");
        case StageKind::I2V:
            return QStringLiteral("i2v");
        case StageKind::I2_3D:
            return QStringLiteral("i2_3d");
        case StageKind::Audio:
            return QStringLiteral("audio");
        }
        return QStringLiteral("t2i");
    }

    inline bool fromString(const QString &s, StageKind &out)
    {
        const QString t = s.trimmed().toLower();
        if (t == QStringLiteral("t2i"))
        {
            out = StageKind::T2I;
            return true;
        }
        if (t == QStringLiteral("t2v"))
        {
            out = StageKind::T2V;
            return true;
        }
        if (t == QStringLiteral("i2i"))
        {
            out = StageKind::I2I;
            return true;
        }
        if (t == QStringLiteral("i2v"))
        {
            out = StageKind::I2V;
            return true;
        }
        if (t == QStringLiteral("i2_3d"))
        {
            out = StageKind::I2_3D;
            return true;
        }
        if (t == QStringLiteral("audio"))
        {
            out = StageKind::Audio;
            return true;
        }
        return false;
    }

    // Per design: I2_3D and Audio are not yet runnable. Engine consults this
    // before attempting to submit; UI uses it to dim/lock the stage option.
    // Centralised here so adding a Python worker later is one return-value
    // flip plus a reader test, not a manual scan of every call site.
    inline bool isExecutable(StageKind k)
    {
        switch (k)
        {
        case StageKind::T2I:
        case StageKind::T2V:
        case StageKind::I2I:
        case StageKind::I2V:
            return true;
        case StageKind::I2_3D: // Trellis 2 worker pending
        case StageKind::Audio: // audio worker pending
            return false;
        }
        return false;
    }

    // Per design: I2I, I2V, I2_3D consume an image as their entry input;
    // T2I, T2V are pure text-entry; Audio consumes a video. Used by the
    // engine (entry validation) and the UI (which kinds appear in the +
    // picker depending on whether an image is uploaded).
    inline bool consumesImageInput(StageKind k)
    {
        return k == StageKind::I2I || k == StageKind::I2V || k == StageKind::I2_3D;
    }

    inline bool consumesVideoInput(StageKind k)
    {
        return k == StageKind::Audio;
    }

    // Per design: StageStatus drives the state machine in §3 of the design.
    // Transitions are owned by ChainEngine (Pass 4); the model just holds
    // the current value.
    enum class StageStatus
    {
        Draft,      // configured, never generated
        Queued,     // submitted, not yet running on the worker
        Generating, // worker actively producing the current variation
        Completed,  // at least one variation exists, none locked
        Failed,     // last attempt failed; prior variations retained
        Locked,     // a variation is frozen; this stage feeds the next
    };

    inline QString toString(StageStatus s)
    {
        switch (s)
        {
        case StageStatus::Draft:
            return QStringLiteral("draft");
        case StageStatus::Queued:
            return QStringLiteral("queued");
        case StageStatus::Generating:
            return QStringLiteral("generating");
        case StageStatus::Completed:
            return QStringLiteral("completed");
        case StageStatus::Failed:
            return QStringLiteral("failed");
        case StageStatus::Locked:
            return QStringLiteral("locked");
        }
        return QStringLiteral("draft");
    }

    inline bool fromString(const QString &s, StageStatus &out)
    {
        const QString t = s.trimmed().toLower();
        if (t == QStringLiteral("draft"))
        {
            out = StageStatus::Draft;
            return true;
        }
        if (t == QStringLiteral("queued"))
        {
            out = StageStatus::Queued;
            return true;
        }
        if (t == QStringLiteral("generating"))
        {
            out = StageStatus::Generating;
            return true;
        }
        if (t == QStringLiteral("completed"))
        {
            out = StageStatus::Completed;
            return true;
        }
        if (t == QStringLiteral("failed"))
        {
            out = StageStatus::Failed;
            return true;
        }
        if (t == QStringLiteral("locked"))
        {
            out = StageStatus::Locked;
            return true;
        }
        return false;
    }

    // How a chain's first stage gets its input.
    //   DescribedText  -> entry stage takes no image (T2I, T2V).
    //   UploadedImage  -> entry stage consumes Chain::sourceImagePath
    //                     (I2I, I2V, I2_3D).
    enum class EntryKind
    {
        DescribedText,
        UploadedImage,
    };

    inline QString toString(EntryKind e)
    {
        return e == EntryKind::UploadedImage
                   ? QStringLiteral("uploaded_image")
                   : QStringLiteral("described_text");
    }

    inline bool fromString(const QString &s, EntryKind &out)
    {
        const QString t = s.trimmed().toLower();
        if (t == QStringLiteral("described_text"))
        {
            out = EntryKind::DescribedText;
            return true;
        }
        if (t == QStringLiteral("uploaded_image"))
        {
            out = EntryKind::UploadedImage;
            return true;
        }
        return false;
    }

    // Variation media classification. Filled by the engine on finalize from
    // GenerationResultRouter's isImageAssetPath / isVideoAssetPath helpers.
    enum class MediaType
    {
        Image,
        Video,
        Mesh,
    };

    inline QString toString(MediaType m)
    {
        switch (m)
        {
        case MediaType::Image:
            return QStringLiteral("image");
        case MediaType::Video:
            return QStringLiteral("video");
        case MediaType::Mesh:
            return QStringLiteral("mesh");
        }
        return QStringLiteral("image");
    }

    inline bool fromString(const QString &s, MediaType &out)
    {
        const QString t = s.trimmed().toLower();
        if (t == QStringLiteral("image"))
        {
            out = MediaType::Image;
            return true;
        }
        if (t == QStringLiteral("video"))
        {
            out = MediaType::Video;
            return true;
        }
        if (t == QStringLiteral("mesh"))
        {
            out = MediaType::Mesh;
            return true;
        }
        return false;
    }

    // Routing spine — how a stage gets its input.
    // Per design §2.4: a non-entry stage can only run when its predecessor
    // is StageStatus::Locked, in which case its input is exactly that
    // predecessor's lockedVarIdx variation's outputPath. ChainEngine (Pass
    // 4) enforces this; the model just records the dependency.
    enum class InputRefKind
    {
        None,             // entry stage, no image input (T2I, T2V)
        ChainSource,      // entry stage consuming Chain::sourceImagePath
        PriorStageLocked, // input = stages[index-1] locked variation output
    };

    inline QString toString(InputRefKind k)
    {
        switch (k)
        {
        case InputRefKind::None:
            return QStringLiteral("none");
        case InputRefKind::ChainSource:
            return QStringLiteral("chain_source");
        case InputRefKind::PriorStageLocked:
            return QStringLiteral("prior_stage_locked");
        }
        return QStringLiteral("none");
    }

    inline bool fromString(const QString &s, InputRefKind &out)
    {
        const QString t = s.trimmed().toLower();
        if (t == QStringLiteral("none"))
        {
            out = InputRefKind::None;
            return true;
        }
        if (t == QStringLiteral("chain_source"))
        {
            out = InputRefKind::ChainSource;
            return true;
        }
        if (t == QStringLiteral("prior_stage_locked"))
        {
            out = InputRefKind::PriorStageLocked;
            return true;
        }
        return false;
    }

    // ---------------------------------------------------------------------------
    // Modifier types
    // ---------------------------------------------------------------------------

    // LoRA is the general per-stage modifier. Mirrors
    // spellvision::generation::LoraRequestEntry field-for-field so a 1:1
    // copy into a GenerationRequestDraft is trivial in Pass 4. We do NOT
    // include the generation header here to keep this model standalone;
    // the field set is the small stable shape that has been in use across
    // the project for a long time.
    struct LoraEntry
    {
        QString display;
        QString value;
        double weight = 1.0;
        bool enabled = true;
    };

    // 3D-stage-only configuration. Per Young's clarification, UltraShape is
    // NOT a general modifier parallel to LoRA — it only meaningfully
    // applies when stageKind == I2_3D. Carrying it as a separate struct
    // (rather than another entry in modifiers) makes that scope explicit
    // in the type system: every read site has to acknowledge it's the 3D
    // case. Engine and UI gate on stageKind before touching it.
    struct UltraShapeConfig
    {
        QString path;
        double weight = 1.0;
        bool enabled = false;
    };

    // ---------------------------------------------------------------------------
    // StageConfig
    // ---------------------------------------------------------------------------
    //
    // Per design §2.5, StageConfig is a superset of
    // spellvision::generation::GenerationRequestDraft. We mirror the same
    // field names and shapes so the engine can fill a draft from a config
    // with a flat 1:1 copy and call the existing
    // GenerationRequestBuilder::build() verbatim — no parallel request
    // path, no translation bugs.
    //
    // We intentionally do NOT include GenerationRequestBuilder.h here. The
    // model header stays standalone; the copy lives in Pass 4 where both
    // headers are already needed.
    struct StageConfig
    {
        // --- prompt + preset ---
        QString prompt;
        QString negativePrompt;
        QString preset;

        // --- model selection ---
        QString model;
        QString modelDisplay;
        QString modelFamily;
        QString modelModality;
        QString modelRole;
        QJsonObject selectedVideoStack;

        // --- workflow / draft binding (carried verbatim through engine) ---
        QString workflowProfile;
        QString workflowDraftSource;
        QString workflowProfilePath;
        QString workflowPath;
        QString compiledPromptPath;
        QString workflowBackend;
        QString workflowMediaType;
        QString promptApiExportPath;

        // --- LTX launch options (carried verbatim) ---
        QString ltxPrimaryModelName;
        QString ltxTextEncoderName;
        QString ltxTextProjectionName;
        QString ltxAudioVaeName;
        QString ltxVideoVaeName;
        QString ltxVisionEncoderName;
        QString ltxOutputVariant;

        // --- modifiers ---
        QVector<LoraEntry> loras; // general per-stage modifiers
        QString loraStackSummary;

        // --- sampler / scheduler ---
        QString imageSampler;
        QString imageScheduler;
        QString videoSampler;
        QString videoScheduler;

        // --- common numeric ---
        int steps = 0;
        double cfg = 0.0;
        int seed = 0;
        int width = 0;
        int height = 0;

        // --- video ---
        bool isVideoMode = false;
        int frames = 81;
        int fps = 16;
        QString videoStackMode;
        QString wanSplit = QStringLiteral("auto");
        int highSteps = 14;
        int lowSteps = 14;
        int splitStep = 14;
        double highNoiseShift = 5.0;
        double lowNoiseShift = 5.0;
        bool enableVaeTiling = false;

        // --- output routing ---
        int batchCount = 1;
        QString outputPrefix;
        QString outputFolder;
        QString modelsRoot;

        // --- image-input mode (I2I / I2V / I2_3D entry path) ---
        bool isImageInputMode = false;
        QString inputImage;
        double denoiseStrength = 0.0;

        // --- chain-only additions (not in GenerationRequestDraft) ---
        StageKind stageKind = StageKind::T2I;
        UltraShapeConfig ultraShape; // ignored unless stageKind == I2_3D
    };

    // ---------------------------------------------------------------------------
    // Variation, Stage, Chain
    // ---------------------------------------------------------------------------

    // Hard rule from design §2.3: Regenerate APPENDS a Variation; the list
    // only grows. selectedVarIdx moves. configSnapshot is the exact config
    // that produced this output so the UI can restore "settings of var N".
    struct Variation
    {
        QString id; // uuid
        QDateTime createdAt;
        QString outputPath; // full-res image / video from worker
        QString metadataPath;
        QString thumbnailPath; // engine-generated (Pass 5)
        StageConfig configSnapshot;
        QString queueItemId; // QueueManager::QueueItem.id at submit
        QString chainRef;    // "chainId/stageId/variationId"
        MediaType mediaType = MediaType::Image;
    };

    struct InputRef
    {
        InputRefKind kind = InputRefKind::None;
        QString priorStageId; // valid iff kind == PriorStageLocked
    };

    struct Stage
    {
        QString id;    // uuid
        int index = 0; // position in chain (0-based)
        StageKind kind = StageKind::T2I;
        StageConfig config;
        QVector<Variation> variations;
        int selectedVarIdx = -1; // -1 == none yet
        int lockedVarIdx = -1;   // -1 == unlocked
        StageStatus status = StageStatus::Draft;
        InputRef inputRef;

        // Convenience predicates. Keep these as inline helpers on the data
        // struct (not engine methods) because they are pure functions of
        // the stage's own fields — no engine state involved. Used by the
        // UI for enabling controls and by the engine for sanity checks.
        bool isLocked() const { return status == StageStatus::Locked && lockedVarIdx >= 0; }
        bool hasVariations() const { return !variations.isEmpty(); }
        bool isEntry() const { return index == 0; }
    };

    struct Chain
    {
        QString id; // uuid
        QDateTime createdAt;
        QDateTime updatedAt;
        EntryKind entryKind = EntryKind::DescribedText;
        QString sourceImagePath; // iff entryKind == UploadedImage
        QVector<Stage> stages;
        QString selectedStageId; // UI focus
    };

    // ---------------------------------------------------------------------------
    // chainRef helper — the single point of truth for the correlation string
    // ---------------------------------------------------------------------------
    //
    // Read-first finding from the build plan: QueueItem is rebuilt from
    // every worker snapshot, so the engine carries correlation in its own
    // in-memory map rather than stamping a field on QueueItem. The string
    // shape is still useful in signals and logs; keep its formatting in
    // one place so the engine, the watcher, and any future debug surface
    // can't disagree.
    inline QString makeChainRef(const QString &chainId,
                                const QString &stageId,
                                const QString &variationId)
    {
        return chainId + QStringLiteral("/") + stageId + QStringLiteral("/") + variationId;
    }

} // namespace spellvision::chain