#include "chain/ChainStore.h"

#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSaveFile>
#include <QSettings>
#include <QStandardPaths>

namespace spellvision::chain
{

    namespace
    {

        // QSettings convention — matches ImageGenerationPage::saveSnapshot.
        constexpr auto kOrg = "DarkDuck";
        constexpr auto kApp = "SpellVision";
        constexpr auto kSettingsGroup = "ChainStudio";
        constexpr auto kKeyLastActiveChainId = "lastActiveChainId";

        // JSON keys. Kept in one place so toJson/fromJson can't drift.
        namespace K
        {
            // chain
            constexpr auto id = "id";
            constexpr auto createdAt = "created_at";
            constexpr auto updatedAt = "updated_at";
            constexpr auto entryKind = "entry_kind";
            constexpr auto sourceImagePath = "source_image_path";
            constexpr auto stages = "stages";
            constexpr auto selectedStageId = "selected_stage_id";

            // stage
            constexpr auto index = "index";
            constexpr auto kind = "kind";
            constexpr auto config = "config";
            constexpr auto variations = "variations";
            constexpr auto selectedVarIdx = "selected_var_idx";
            constexpr auto lockedVarIdx = "locked_var_idx";
            constexpr auto status = "status";
            constexpr auto inputRef = "input_ref";

            // inputRef
            constexpr auto refKind = "kind";
            constexpr auto priorStageId = "prior_stage_id";

            // variation
            constexpr auto outputPath = "output_path";
            constexpr auto metadataPath = "metadata_path";
            constexpr auto thumbnailPath = "thumbnail_path";
            constexpr auto configSnapshot = "config_snapshot";
            constexpr auto queueItemId = "queue_item_id";
            constexpr auto chainRef = "chain_ref";
            constexpr auto mediaType = "media_type";

            // StageConfig — flat namespace; field names mirror GenerationRequestDraft
            // snake-cased for JSON. The toJson/fromJson pair below is the single
            // place where the field shape is enumerated.
            constexpr auto prompt = "prompt";
            constexpr auto negativePrompt = "negative_prompt";
            constexpr auto preset = "preset";
            constexpr auto model = "model";
            constexpr auto modelDisplay = "model_display";
            constexpr auto modelFamily = "model_family";
            constexpr auto modelModality = "model_modality";
            constexpr auto modelRole = "model_role";
            constexpr auto selectedVideoStack = "selected_video_stack";
            constexpr auto workflowProfile = "workflow_profile";
            constexpr auto workflowDraftSource = "workflow_draft_source";
            constexpr auto workflowProfilePath = "workflow_profile_path";
            constexpr auto workflowPath = "workflow_path";
            constexpr auto compiledPromptPath = "compiled_prompt_path";
            constexpr auto workflowBackend = "workflow_backend";
            constexpr auto workflowMediaType = "workflow_media_type";
            constexpr auto promptApiExportPath = "prompt_api_export_path";
            constexpr auto ltxPrimaryModelName = "ltx_primary_model_name";
            constexpr auto ltxTextEncoderName = "ltx_text_encoder_name";
            constexpr auto ltxTextProjectionName = "ltx_text_projection_name";
            constexpr auto ltxAudioVaeName = "ltx_audio_vae_name";
            constexpr auto ltxVideoVaeName = "ltx_video_vae_name";
            constexpr auto ltxVisionEncoderName = "ltx_vision_encoder_name";
            constexpr auto ltxOutputVariant = "ltx_output_variant";
            constexpr auto loras = "loras";
            constexpr auto loraStackSummary = "lora_stack_summary";
            constexpr auto imageSampler = "image_sampler";
            constexpr auto imageScheduler = "image_scheduler";
            constexpr auto videoSampler = "video_sampler";
            constexpr auto videoScheduler = "video_scheduler";
            constexpr auto steps = "steps";
            constexpr auto cfg = "cfg";
            constexpr auto seed = "seed";
            constexpr auto width = "width";
            constexpr auto height = "height";
            constexpr auto isVideoMode = "is_video_mode";
            constexpr auto frames = "frames";
            constexpr auto fps = "fps";
            constexpr auto videoStackMode = "video_stack_mode";
            constexpr auto wanSplit = "wan_split";
            constexpr auto highSteps = "high_steps";
            constexpr auto lowSteps = "low_steps";
            constexpr auto splitStep = "split_step";
            constexpr auto highNoiseShift = "high_noise_shift";
            constexpr auto lowNoiseShift = "low_noise_shift";
            constexpr auto enableVaeTiling = "enable_vae_tiling";
            constexpr auto batchCount = "batch_count";
            constexpr auto outputPrefix = "output_prefix";
            constexpr auto outputFolder = "output_folder";
            constexpr auto modelsRoot = "models_root";
            constexpr auto isImageInputMode = "is_image_input_mode";
            constexpr auto inputImage = "input_image";
            constexpr auto denoiseStrength = "denoise_strength";

            constexpr auto stageKind = "stage_kind";
            constexpr auto ultraShape = "ultra_shape";

            // LoraEntry / UltraShapeConfig
            constexpr auto display = "display";
            constexpr auto value = "value";
            constexpr auto weight = "weight";
            constexpr auto enabled = "enabled";
            constexpr auto path = "path";
        } // namespace K

        QJsonObject loraToJson(const LoraEntry &l)
        {
            return QJsonObject{
                {K::display, l.display},
                {K::value, l.value},
                {K::weight, l.weight},
                {K::enabled, l.enabled},
            };
        }

        LoraEntry loraFromJson(const QJsonObject &o)
        {
            LoraEntry l;
            l.display = o.value(K::display).toString();
            l.value = o.value(K::value).toString();
            l.weight = o.value(K::weight).toDouble(1.0);
            l.enabled = o.value(K::enabled).toBool(true);
            return l;
        }

        QJsonObject ultraShapeToJson(const UltraShapeConfig &u)
        {
            return QJsonObject{
                {K::path, u.path},
                {K::weight, u.weight},
                {K::enabled, u.enabled},
            };
        }

        UltraShapeConfig ultraShapeFromJson(const QJsonObject &o)
        {
            UltraShapeConfig u;
            u.path = o.value(K::path).toString();
            u.weight = o.value(K::weight).toDouble(1.0);
            u.enabled = o.value(K::enabled).toBool(false);
            return u;
        }

        QJsonObject configToJson(const StageConfig &c)
        {
            QJsonArray loraArr;
            for (const LoraEntry &l : c.loras)
                loraArr.append(loraToJson(l));

            QJsonObject obj;
            obj[K::prompt] = c.prompt;
            obj[K::negativePrompt] = c.negativePrompt;
            obj[K::preset] = c.preset;
            obj[K::model] = c.model;
            obj[K::modelDisplay] = c.modelDisplay;
            obj[K::modelFamily] = c.modelFamily;
            obj[K::modelModality] = c.modelModality;
            obj[K::modelRole] = c.modelRole;
            obj[K::selectedVideoStack] = c.selectedVideoStack;
            obj[K::workflowProfile] = c.workflowProfile;
            obj[K::workflowDraftSource] = c.workflowDraftSource;
            obj[K::workflowProfilePath] = c.workflowProfilePath;
            obj[K::workflowPath] = c.workflowPath;
            obj[K::compiledPromptPath] = c.compiledPromptPath;
            obj[K::workflowBackend] = c.workflowBackend;
            obj[K::workflowMediaType] = c.workflowMediaType;
            obj[K::promptApiExportPath] = c.promptApiExportPath;
            obj[K::ltxPrimaryModelName] = c.ltxPrimaryModelName;
            obj[K::ltxTextEncoderName] = c.ltxTextEncoderName;
            obj[K::ltxTextProjectionName] = c.ltxTextProjectionName;
            obj[K::ltxAudioVaeName] = c.ltxAudioVaeName;
            obj[K::ltxVideoVaeName] = c.ltxVideoVaeName;
            obj[K::ltxVisionEncoderName] = c.ltxVisionEncoderName;
            obj[K::ltxOutputVariant] = c.ltxOutputVariant;
            obj[K::loras] = loraArr;
            obj[K::loraStackSummary] = c.loraStackSummary;
            obj[K::imageSampler] = c.imageSampler;
            obj[K::imageScheduler] = c.imageScheduler;
            obj[K::videoSampler] = c.videoSampler;
            obj[K::videoScheduler] = c.videoScheduler;
            obj[K::steps] = c.steps;
            obj[K::cfg] = c.cfg;
            obj[K::seed] = c.seed;
            obj[K::width] = c.width;
            obj[K::height] = c.height;
            obj[K::isVideoMode] = c.isVideoMode;
            obj[K::frames] = c.frames;
            obj[K::fps] = c.fps;
            obj[K::videoStackMode] = c.videoStackMode;
            obj[K::wanSplit] = c.wanSplit;
            obj[K::highSteps] = c.highSteps;
            obj[K::lowSteps] = c.lowSteps;
            obj[K::splitStep] = c.splitStep;
            obj[K::highNoiseShift] = c.highNoiseShift;
            obj[K::lowNoiseShift] = c.lowNoiseShift;
            obj[K::enableVaeTiling] = c.enableVaeTiling;
            obj[K::batchCount] = c.batchCount;
            obj[K::outputPrefix] = c.outputPrefix;
            obj[K::outputFolder] = c.outputFolder;
            obj[K::modelsRoot] = c.modelsRoot;
            obj[K::isImageInputMode] = c.isImageInputMode;
            obj[K::inputImage] = c.inputImage;
            obj[K::denoiseStrength] = c.denoiseStrength;

            obj[K::stageKind] = toString(c.stageKind);
            obj[K::ultraShape] = ultraShapeToJson(c.ultraShape);
            return obj;
        }

        StageConfig configFromJson(const QJsonObject &o)
        {
            StageConfig c;
            c.prompt = o.value(K::prompt).toString();
            c.negativePrompt = o.value(K::negativePrompt).toString();
            c.preset = o.value(K::preset).toString();
            c.model = o.value(K::model).toString();
            c.modelDisplay = o.value(K::modelDisplay).toString();
            c.modelFamily = o.value(K::modelFamily).toString();
            c.modelModality = o.value(K::modelModality).toString();
            c.modelRole = o.value(K::modelRole).toString();
            c.selectedVideoStack = o.value(K::selectedVideoStack).toObject();
            c.workflowProfile = o.value(K::workflowProfile).toString();
            c.workflowDraftSource = o.value(K::workflowDraftSource).toString();
            c.workflowProfilePath = o.value(K::workflowProfilePath).toString();
            c.workflowPath = o.value(K::workflowPath).toString();
            c.compiledPromptPath = o.value(K::compiledPromptPath).toString();
            c.workflowBackend = o.value(K::workflowBackend).toString();
            c.workflowMediaType = o.value(K::workflowMediaType).toString();
            c.promptApiExportPath = o.value(K::promptApiExportPath).toString();
            c.ltxPrimaryModelName = o.value(K::ltxPrimaryModelName).toString();
            c.ltxTextEncoderName = o.value(K::ltxTextEncoderName).toString();
            c.ltxTextProjectionName = o.value(K::ltxTextProjectionName).toString();
            c.ltxAudioVaeName = o.value(K::ltxAudioVaeName).toString();
            c.ltxVideoVaeName = o.value(K::ltxVideoVaeName).toString();
            c.ltxVisionEncoderName = o.value(K::ltxVisionEncoderName).toString();
            c.ltxOutputVariant = o.value(K::ltxOutputVariant).toString();

            const QJsonArray loraArr = o.value(K::loras).toArray();
            c.loras.reserve(loraArr.size());
            for (const QJsonValue &v : loraArr)
                c.loras.append(loraFromJson(v.toObject()));
            c.loraStackSummary = o.value(K::loraStackSummary).toString();

            c.imageSampler = o.value(K::imageSampler).toString();
            c.imageScheduler = o.value(K::imageScheduler).toString();
            c.videoSampler = o.value(K::videoSampler).toString();
            c.videoScheduler = o.value(K::videoScheduler).toString();

            // toInt/toDouble fall back to 0/0.0 silently — keep StageConfig
            // defaults as the secondary fallback for fields where 0 isn't
            // semantically valid.
            c.steps = o.value(K::steps).toInt(0);
            c.cfg = o.value(K::cfg).toDouble(0.0);
            c.seed = o.value(K::seed).toInt(0);
            c.width = o.value(K::width).toInt(0);
            c.height = o.value(K::height).toInt(0);

            c.isVideoMode = o.value(K::isVideoMode).toBool(false);
            c.frames = o.value(K::frames).toInt(81);
            c.fps = o.value(K::fps).toInt(16);
            c.videoStackMode = o.value(K::videoStackMode).toString();
            c.wanSplit = o.value(K::wanSplit).toString(QStringLiteral("auto"));
            c.highSteps = o.value(K::highSteps).toInt(14);
            c.lowSteps = o.value(K::lowSteps).toInt(14);
            c.splitStep = o.value(K::splitStep).toInt(14);
            c.highNoiseShift = o.value(K::highNoiseShift).toDouble(5.0);
            c.lowNoiseShift = o.value(K::lowNoiseShift).toDouble(5.0);
            c.enableVaeTiling = o.value(K::enableVaeTiling).toBool(false);

            c.batchCount = o.value(K::batchCount).toInt(1);
            c.outputPrefix = o.value(K::outputPrefix).toString();
            c.outputFolder = o.value(K::outputFolder).toString();
            c.modelsRoot = o.value(K::modelsRoot).toString();
            c.isImageInputMode = o.value(K::isImageInputMode).toBool(false);
            c.inputImage = o.value(K::inputImage).toString();
            c.denoiseStrength = o.value(K::denoiseStrength).toDouble(0.0);

            // stageKind / ultraShape — unknown stage_kind strings fall back to
            // T2I rather than failing the load; the engine surfaces "unknown
            // kind" as a separate problem if it matters.
            StageKind sk = StageKind::T2I;
            fromString(o.value(K::stageKind).toString(), sk);
            c.stageKind = sk;
            c.ultraShape = ultraShapeFromJson(o.value(K::ultraShape).toObject());
            return c;
        }

        QJsonObject inputRefToJson(const InputRef &r)
        {
            return QJsonObject{
                {K::refKind, toString(r.kind)},
                {K::priorStageId, r.priorStageId},
            };
        }

        InputRef inputRefFromJson(const QJsonObject &o)
        {
            InputRef r;
            InputRefKind k = InputRefKind::None;
            fromString(o.value(K::refKind).toString(), k);
            r.kind = k;
            r.priorStageId = o.value(K::priorStageId).toString();
            return r;
        }

        QJsonObject variationToJson(const Variation &v)
        {
            return QJsonObject{
                {K::id, v.id},
                {K::createdAt, v.createdAt.toString(Qt::ISODateWithMs)},
                {K::outputPath, v.outputPath},
                {K::metadataPath, v.metadataPath},
                {K::thumbnailPath, v.thumbnailPath},
                {K::configSnapshot, configToJson(v.configSnapshot)},
                {K::queueItemId, v.queueItemId},
                {K::chainRef, v.chainRef},
                {K::mediaType, toString(v.mediaType)},
            };
        }

        Variation variationFromJson(const QJsonObject &o)
        {
            Variation v;
            v.id = o.value(K::id).toString();
            v.createdAt = QDateTime::fromString(o.value(K::createdAt).toString(), Qt::ISODateWithMs);
            v.outputPath = o.value(K::outputPath).toString();
            v.metadataPath = o.value(K::metadataPath).toString();
            v.thumbnailPath = o.value(K::thumbnailPath).toString();
            v.configSnapshot = configFromJson(o.value(K::configSnapshot).toObject());
            v.queueItemId = o.value(K::queueItemId).toString();
            v.chainRef = o.value(K::chainRef).toString();
            MediaType mt = MediaType::Image;
            fromString(o.value(K::mediaType).toString(), mt);
            v.mediaType = mt;
            return v;
        }

        QJsonObject stageToJson(const Stage &s)
        {
            QJsonArray varsArr;
            for (const Variation &v : s.variations)
                varsArr.append(variationToJson(v));

            return QJsonObject{
                {K::id, s.id},
                {K::index, s.index},
                {K::kind, toString(s.kind)},
                {K::config, configToJson(s.config)},
                {K::variations, varsArr},
                {K::selectedVarIdx, s.selectedVarIdx},
                {K::lockedVarIdx, s.lockedVarIdx},
                {K::status, toString(s.status)},
                {K::inputRef, inputRefToJson(s.inputRef)},
            };
        }

        Stage stageFromJson(const QJsonObject &o)
        {
            Stage s;
            s.id = o.value(K::id).toString();
            s.index = o.value(K::index).toInt(0);

            StageKind sk = StageKind::T2I;
            fromString(o.value(K::kind).toString(), sk);
            s.kind = sk;

            s.config = configFromJson(o.value(K::config).toObject());

            const QJsonArray varsArr = o.value(K::variations).toArray();
            s.variations.reserve(varsArr.size());
            for (const QJsonValue &v : varsArr)
                s.variations.append(variationFromJson(v.toObject()));

            s.selectedVarIdx = o.value(K::selectedVarIdx).toInt(-1);
            s.lockedVarIdx = o.value(K::lockedVarIdx).toInt(-1);

            StageStatus ss = StageStatus::Draft;
            fromString(o.value(K::status).toString(), ss);
            s.status = ss;

            s.inputRef = inputRefFromJson(o.value(K::inputRef).toObject());
            return s;
        }

    } // anonymous namespace

    // ---------------------------------------------------------------------------
    // public API
    // ---------------------------------------------------------------------------

    ChainStore::ChainStore(QString projectRoot)
        : projectRoot_(std::move(projectRoot))
    {
    }

    QJsonObject ChainStore::toJson(const Chain &c)
    {
        QJsonArray stagesArr;
        for (const Stage &s : c.stages)
            stagesArr.append(stageToJson(s));

        return QJsonObject{
            {K::id, c.id},
            {K::createdAt, c.createdAt.toString(Qt::ISODateWithMs)},
            {K::updatedAt, c.updatedAt.toString(Qt::ISODateWithMs)},
            {K::entryKind, toString(c.entryKind)},
            {K::sourceImagePath, c.sourceImagePath},
            {K::stages, stagesArr},
            {K::selectedStageId, c.selectedStageId},
        };
    }

    std::optional<Chain> ChainStore::fromJson(const QJsonObject &o)
    {
        // Minimum sanity: a chain has an id. Anything else missing falls
        // back to defaults; engine treats those as "needs setup".
        const QString id = o.value(K::id).toString();
        if (id.trimmed().isEmpty())
            return std::nullopt;

        Chain c;
        c.id = id;
        c.createdAt = QDateTime::fromString(o.value(K::createdAt).toString(), Qt::ISODateWithMs);
        c.updatedAt = QDateTime::fromString(o.value(K::updatedAt).toString(), Qt::ISODateWithMs);

        EntryKind ek = EntryKind::DescribedText;
        fromString(o.value(K::entryKind).toString(), ek);
        c.entryKind = ek;

        c.sourceImagePath = o.value(K::sourceImagePath).toString();

        const QJsonArray stagesArr = o.value(K::stages).toArray();
        c.stages.reserve(stagesArr.size());
        for (const QJsonValue &v : stagesArr)
            c.stages.append(stageFromJson(v.toObject()));

        c.selectedStageId = o.value(K::selectedStageId).toString();
        return c;
    }

    bool ChainStore::save(const Chain &chain) const
    {
        if (chain.id.trimmed().isEmpty())
            return false;

        const QString path = chainFilePath(chain.id);
        QDir().mkpath(QFileInfo(path).absolutePath());

        QSaveFile f(path);
        if (!f.open(QIODevice::WriteOnly | QIODevice::Truncate))
            return false;

        const QByteArray bytes = QJsonDocument(toJson(chain)).toJson(QJsonDocument::Indented);
        if (f.write(bytes) != bytes.size())
        {
            f.cancelWriting();
            return false;
        }
        return f.commit();
    }

    std::optional<Chain> ChainStore::load(const QString &chainId) const
    {
        const QString path = chainFilePath(chainId);
        QFile f(path);
        if (!f.exists() || !f.open(QIODevice::ReadOnly))
            return std::nullopt;

        QJsonParseError err{};
        const QJsonDocument doc = QJsonDocument::fromJson(f.readAll(), &err);
        if (err.error != QJsonParseError::NoError || !doc.isObject())
            return std::nullopt;

        return fromJson(doc.object());
    }

    void ChainStore::setLastActiveChainId(const QString &chainId)
    {
        QSettings s{QLatin1String(kOrg), QLatin1String(kApp)};  // brace-init avoids most-vexing-parse on MSVC
        s.beginGroup(QLatin1String(kSettingsGroup));
        s.setValue(QLatin1String(kKeyLastActiveChainId), chainId);
        s.endGroup();
    }

    QString ChainStore::lastActiveChainId() const
    {
        QSettings s{QLatin1String(kOrg), QLatin1String(kApp)};  // brace-init avoids most-vexing-parse on MSVC
        s.beginGroup(QLatin1String(kSettingsGroup));
        const QString v = s.value(QLatin1String(kKeyLastActiveChainId)).toString();
        s.endGroup();
        return v;
    }

    QString ChainStore::chainsDir() const
    {
        QString base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
        if (base.trimmed().isEmpty())
        {
            if (!projectRoot_.trimmed().isEmpty())
                base = QDir(projectRoot_).filePath(QStringLiteral("runtime/cache/ui"));
            else
                base = QDir::current().filePath(QStringLiteral("runtime/cache/ui"));
        }
        return QDir(base).filePath(QStringLiteral("chains"));
    }

    QString ChainStore::chainFilePath(const QString &chainId) const
    {
        return QDir(chainsDir()).filePath(chainId + QStringLiteral(".json"));
    }

} // namespace spellvision::chain