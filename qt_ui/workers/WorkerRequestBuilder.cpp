#include "workers/WorkerRequestBuilder.h"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonValue>
#include <QLatin1Char>
#include <QLatin1String>
#include <QStringList>

#include "generation/OutputPathHelpers.h"
#include "shell/RuntimeProfile.h"
#include "workers/WorkerSubmissionPolicy.h"

namespace spellvision::workers
{

QString workerTaskCommandForMode(const QString &modeId)
{
    if (modeId == QStringLiteral("t2i"))
        return QStringLiteral("t2i");
    if (modeId == QStringLiteral("i2i"))
        return QStringLiteral("i2i");
    if (modeId == QStringLiteral("t2v"))
        return QStringLiteral("t2v");
    if (modeId == QStringLiteral("i2v"))
        return QStringLiteral("i2v");
    return QString();
}

QJsonObject buildWorkerGenerationRequest(const QString &modeId,
                                         const QJsonObject &payload,
                                         const QString &projectRoot)
{
    const QString taskCommand = workerTaskCommandForMode(modeId);

    QString outputFolder = payload.value(QStringLiteral("output_folder")).toString().trimmed();
    if (outputFolder.startsWith(QLatin1String("Not set"), Qt::CaseInsensitive))
        outputFolder.clear();
    if (outputFolder.isEmpty())
        outputFolder = spellvision::generation::userGenerationDestFolder();
    if (!outputFolder.isEmpty())
        QDir().mkpath(outputFolder);

    const QString basePrefix = payload.value(QStringLiteral("output_prefix")).toString().trimmed().isEmpty()
                                   ? QStringLiteral("spellvision_render")
                                   : payload.value(QStringLiteral("output_prefix")).toString().trimmed();
    const bool videoOutput = taskCommand == QStringLiteral("t2v") || taskCommand == QStringLiteral("i2v");
    QString outputPath;
    QString metadataPath;
    spellvision::generation::resolveGenerationOutputPaths(outputFolder, basePrefix, taskCommand, videoOutput, &outputPath, &metadataPath);
    const QString promptTxt = QDir(QFileInfo(outputPath).absolutePath()).filePath(QStringLiteral("prompt.txt"));
    if (QFileInfo(outputPath).fileName().startsWith(QStringLiteral("plate")))
    {
        QFile promptFile(promptTxt);
        if (promptFile.open(QIODevice::WriteOnly | QIODevice::Truncate))
            promptFile.write(payload.value(QStringLiteral("prompt")).toString().toUtf8());
    }

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("enqueue"));
    request.insert(QStringLiteral("task_command"), taskCommand);
    const QString studioCommand = payload.value(QStringLiteral("task_command")).toString().trimmed().isEmpty()
                                      ? payload.value(QStringLiteral("command")).toString().trimmed().toLower()
                                      : payload.value(QStringLiteral("task_command")).toString().trimmed().toLower();
    static const QStringList kStudioExecutionCommands = {
        QStringLiteral("clothes_only"),
        QStringLiteral("garment_shrinkwrap"),
        QStringLiteral("krea2_regional_inpaint"),
        QStringLiteral("look_complete"),
    };
    if (kStudioExecutionCommands.contains(studioCommand)) {
        request.insert(QStringLiteral("task_command"), studioCommand);
        request.insert(QStringLiteral("execution_command"), studioCommand);
        request.insert(QStringLiteral("worker_command"), studioCommand);
        request.insert(QStringLiteral("dispatch_command"), studioCommand);
        request.insert(QStringLiteral("task_type"), studioCommand);
    }
    spellvision::shell::RuntimeProfile::load(projectRoot).applyToWorkerRequest(request);
    if (!kStudioExecutionCommands.contains(studioCommand))
        request.insert(QStringLiteral("task_type"), taskCommand);
    request.insert(QStringLiteral("submit_origin"), payload.value(QStringLiteral("submit_origin")).toString());
    request.insert(QStringLiteral("client_readiness_block"), payload.value(QStringLiteral("client_readiness_block")).toString());
    request.insert(QStringLiteral("prompt"), payload.value(QStringLiteral("prompt")).toString());
    request.insert(QStringLiteral("negative_prompt"), payload.value(QStringLiteral("negative_prompt")).toString());
    const QString resolvedModelValue = WorkerSubmissionPolicy::resolvedModelValueFromPayload(payload);
    request.insert(QStringLiteral("model"), resolvedModelValue);
    request.insert(QStringLiteral("model_display"), payload.value(QStringLiteral("model_display")).toString());
    request.insert(QStringLiteral("model_family"), payload.value(QStringLiteral("model_family")).toString());
    request.insert(QStringLiteral("model_modality"), payload.value(QStringLiteral("model_modality")).toString());
    request.insert(QStringLiteral("model_role"), payload.value(QStringLiteral("model_role")).toString());
    if (payload.value(QStringLiteral("video_model_stack")).isObject())
        request.insert(QStringLiteral("video_model_stack"), payload.value(QStringLiteral("video_model_stack")).toObject());
    if (payload.value(QStringLiteral("model_stack")).isObject())
        request.insert(QStringLiteral("model_stack"), payload.value(QStringLiteral("model_stack")).toObject());
    if (!payload.value(QStringLiteral("native_video_stack_kind")).toString().trimmed().isEmpty())
        request.insert(QStringLiteral("native_video_stack_kind"), payload.value(QStringLiteral("native_video_stack_kind")).toString());
    request.insert(QStringLiteral("steps"), payload.value(QStringLiteral("steps")).toInt(28));
    request.insert(QStringLiteral("cfg"), payload.value(QStringLiteral("cfg")).toDouble(payload.value(QStringLiteral("cfg_scale")).toDouble(7.0)));
    request.insert(QStringLiteral("seed"), static_cast<qint64>(payload.value(QStringLiteral("seed")).toVariant().toLongLong()));
    request.insert(QStringLiteral("width"), payload.value(QStringLiteral("width")).toInt(1024));
    request.insert(QStringLiteral("height"), payload.value(QStringLiteral("height")).toInt(1024));
    request.insert(QStringLiteral("sampler"), payload.value(QStringLiteral("sampler")).toString());
    request.insert(QStringLiteral("scheduler"), payload.value(QStringLiteral("scheduler")).toString());
    const QString requestProfilePath = QDir::fromNativeSeparators(payload.value(QStringLiteral("workflow_profile_path")).toString());
    const QString requestWorkflowPath = QDir::fromNativeSeparators(payload.value(QStringLiteral("workflow_path")).toString());
    const QString requestCompiledPromptPath = QDir::fromNativeSeparators(payload.value(QStringLiteral("compiled_prompt_path")).toString());
    const bool hasWorkflowBinding = !requestProfilePath.trimmed().isEmpty() ||
                                    !requestWorkflowPath.trimmed().isEmpty() ||
                                    !requestCompiledPromptPath.trimmed().isEmpty();

    request.insert(QStringLiteral("workflow_profile"), payload.value(QStringLiteral("workflow_profile")).toString());
    request.insert(QStringLiteral("workflow_profile_name"), payload.value(QStringLiteral("workflow_draft_source")).toString());
    request.insert(QStringLiteral("profile_path"), requestProfilePath);
    request.insert(QStringLiteral("workflow_path"), requestWorkflowPath);
    request.insert(QStringLiteral("compiled_prompt_path"), requestCompiledPromptPath);
    request.insert(QStringLiteral("workflow_backend"), payload.value(QStringLiteral("workflow_backend")).toString());
    request.insert(QStringLiteral("workflow_media_type"), payload.value(QStringLiteral("workflow_media_type")).toString());
    if (videoOutput && !hasWorkflowBinding)
    {
        request.insert(QStringLiteral("backend_kind"), QStringLiteral("native_video"));
        request.insert(QStringLiteral("runtime"), QStringLiteral("diffusers_video"));
    }
    request.insert(QStringLiteral("output"), QDir::fromNativeSeparators(outputPath));
    request.insert(QStringLiteral("metadata_output"), QDir::fromNativeSeparators(metadataPath));
    request.insert(QStringLiteral("original_output"), QDir::fromNativeSeparators(outputPath));
    request.insert(QStringLiteral("original_metadata_output"), QDir::fromNativeSeparators(metadataPath));

    const QString loraValue = payload.value(QStringLiteral("lora_summary")).toString().trimmed();
    if (!loraValue.isEmpty() && loraValue.compare(QStringLiteral("none"), Qt::CaseInsensitive) != 0)
        request.insert(QStringLiteral("lora"), loraValue);

    // C3: studios send loras[{path,name,weight}]; never drop them.
    if (payload.contains(QStringLiteral("loras")) && payload.value(QStringLiteral("loras")).isArray()) {
        const QJsonArray loras = payload.value(QStringLiteral("loras")).toArray();
        request.insert(QStringLiteral("loras"), loras);
        if (!request.contains(QStringLiteral("lora"))) {
            for (const QJsonValue &item : loras) {
                const QJsonObject obj = item.toObject();
                if (obj.value(QStringLiteral("enabled")).toBool(true) == false)
                    continue;
                const QString path = obj.value(QStringLiteral("path")).toString().trimmed();
                if (path.isEmpty())
                    continue;
                request.insert(QStringLiteral("lora"), path);
                if (obj.contains(QStringLiteral("weight")))
                    request.insert(QStringLiteral("lora_scale"), obj.value(QStringLiteral("weight")).toDouble(1.0));
                break;
            }
        }
    }

    if (taskCommand == QStringLiteral("i2i") || taskCommand == QStringLiteral("i2v"))
    {
        request.insert(QStringLiteral("input_image"), payload.value(QStringLiteral("input_image")).toString());
        request.insert(QStringLiteral("strength"), payload.value(QStringLiteral("strength")).toDouble(0.45));
    }

    if (videoOutput)
    {
        request.insert(QStringLiteral("frames"), payload.value(QStringLiteral("frames")).toInt(payload.value(QStringLiteral("num_frames")).toInt(81)));
        request.insert(QStringLiteral("num_frames"), payload.value(QStringLiteral("num_frames")).toInt(payload.value(QStringLiteral("frames")).toInt(81)));
        request.insert(QStringLiteral("fps"), payload.value(QStringLiteral("fps")).toInt(16));
        request.insert(QStringLiteral("duration_seconds"), payload.value(QStringLiteral("duration_seconds")).toDouble(0.0));
        request.insert(QStringLiteral("media_type"), QStringLiteral("video"));

        const QStringList videoRoutingKeys = {
            QStringLiteral("video_family"),
            QStringLiteral("resolved_native_video_family"),
            QStringLiteral("video_backend_route"),
            QStringLiteral("video_validation_status"),
            QStringLiteral("video_validated_backend"),
            QStringLiteral("video_uses_remote_api_backend"),
            QStringLiteral("video_validated_remote_api_family"),
        };
        for (const QString &key : videoRoutingKeys)
        {
            if (payload.contains(key))
                request.insert(key, payload.value(key));
        }

        if (payload.value(QStringLiteral("video_backend_route")).toString() == QStringLiteral("bfl_api"))
        {
            request.insert(QStringLiteral("backend_kind"), QStringLiteral("bfl_api"));
            request.insert(QStringLiteral("runtime"), QStringLiteral("remote_api"));
        }
    }

    // --- CHAIN STUDIO PASS 8C.1: queue_item_id forward ---
    // When the chain engine submits, it stamps its engine-generated
    // UUID into payload["queue_item_id"]. We mirror that into THREE
    // request fields because the Python worker may echo it back
    // under any of them, and ChainCompletionWatcher matches against
    // item.id OR item.workerJobId OR item.sourceJobId (first hit
    // wins). Belt-and-braces: stamping all three guarantees the
    // watcher can correlate completions back regardless of which
    // field the worker chooses to echo.
    const QString chainQueueItemId = payload.value(QStringLiteral("queue_item_id")).toString().trimmed();
    if (!chainQueueItemId.isEmpty())
    {
        request.insert(QStringLiteral("queue_item_id"), chainQueueItemId);
        request.insert(QStringLiteral("worker_job_id"), chainQueueItemId);
        request.insert(QStringLiteral("source_job_id"), chainQueueItemId);
    }

    const QStringList clothesKeys = {
        QStringLiteral("garment"),
        QStringLiteral("garment_text"),
        QStringLiteral("views"),
        QStringLiteral("dummy"),
        QStringLiteral("wrap_dummy"),
        QStringLiteral("queue"),
        QStringLiteral("character_id"),
        QStringLiteral("dest"),
        QStringLiteral("plates_dir"),
        QStringLiteral("body"),
        QStringLiteral("body_path"),
        QStringLiteral("dry_run"),
        QStringLiteral("input_image"),
        QStringLiteral("method"),
        QStringLiteral("present_regions"),
        QStringLiteral("target"),
        QStringLiteral("run_blender"),
    };
    for (const QString &key : clothesKeys) {
        if (payload.contains(key))
            request.insert(key, payload.value(key));
    }

    return request;
}

QJsonObject buildWorkflowLaunchRequest(const QJsonObject &profile,
                                       const QString &modelOverride,
                                       const QString &loraOverride,
                                       const QString &loraScaleOverride,
                                       const QString &projectRoot,
                                       const QString &managedComfyRoot)
{
    auto firstNonEmpty = [](const QString &a, const QString &b, const QString &fallback = QString())
    {
        const QString aTrimmed = a.trimmed();
        if (!aTrimmed.isEmpty())
            return aTrimmed;
        const QString bTrimmed = b.trimmed();
        if (!bTrimmed.isEmpty())
            return bTrimmed;
        return fallback.trimmed();
    };

    auto slugify = [](QString value)
    {
        value = value.trimmed().toLower();
        QString out;
        bool dashPending = false;

        for (const QChar ch : value)
        {
            if (ch.isLetterOrNumber())
            {
                out.append(ch);
                dashPending = false;
            }
            else if (!out.isEmpty() && !dashPending)
            {
                out.append(QLatin1Char('-'));
                dashPending = true;
            }
        }

        while (out.endsWith(QLatin1Char('-')))
            out.chop(1);

        if (out.isEmpty())
            out = QStringLiteral("workflow");

        return out.left(72);
    };

    const QString profileName = firstNonEmpty(profile.value(QStringLiteral("profile_name")).toString(),
                                              profile.value(QStringLiteral("name")).toString(),
                                              QStringLiteral("Imported Workflow"));
    const QString importSlug = slugify(firstNonEmpty(profile.value(QStringLiteral("import_slug")).toString(), profileName));
    const QString workflowTaskCommand = firstNonEmpty(profile.value(QStringLiteral("task_command")).toString(),
                                                      QStringLiteral("unknown"));
    const QString workflowMediaType = profile.value(QStringLiteral("media_type")).toString().trimmed();
    const QString backendKind = firstNonEmpty(profile.value(QStringLiteral("backend_kind")).toString(),
                                              QStringLiteral("comfy_workflow"));

    const QString profilePath = profile.value(QStringLiteral("profile_path")).toString().trimmed();
    const QString workflowPath = firstNonEmpty(profile.value(QStringLiteral("workflow_path")).toString(),
                                               profile.value(QStringLiteral("workflow_source")).toString());

    const QString comfyRoot = managedComfyRoot;

    const QString outputRoot = QDir(projectRoot).filePath(QStringLiteral("output/workflows/%1").arg(workflowTaskCommand));
    QDir().mkpath(outputRoot);

    const QString stamp = QDateTime::currentDateTimeUtc().toString(QStringLiteral("yyyyMMdd_HHmmss_zzz"));
    const QString baseName = QStringLiteral("%1_%2").arg(importSlug, stamp);
    const bool workflowVideoOutput = workflowMediaType == QStringLiteral("video") ||
                                     workflowTaskCommand == QStringLiteral("t2v") ||
                                     workflowTaskCommand == QStringLiteral("i2v");
    const QString outputPath = QDir(outputRoot).filePath(baseName + (workflowVideoOutput ? QStringLiteral(".mp4") : QStringLiteral(".png")));
    const QString metadataPath = QDir(outputRoot).filePath(baseName + QStringLiteral(".json"));

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("enqueue"));
    request.insert(QStringLiteral("task_command"), QStringLiteral("comfy_workflow"));
    request.insert(QStringLiteral("task_type"), workflowTaskCommand);
    request.insert(QStringLiteral("backend_kind"), backendKind);
    request.insert(QStringLiteral("workflow_profile_name"), profileName);
    request.insert(QStringLiteral("workflow_task_command"), workflowTaskCommand);
    if (!workflowMediaType.isEmpty())
        request.insert(QStringLiteral("workflow_media_type"), workflowMediaType);
    if (!profilePath.isEmpty())
        request.insert(QStringLiteral("profile_path"), QDir::fromNativeSeparators(profilePath));
    if (!workflowPath.isEmpty())
        request.insert(QStringLiteral("workflow_path"), QDir::fromNativeSeparators(workflowPath));
    if (!comfyRoot.isEmpty())
        request.insert(QStringLiteral("comfy_root"), QDir::fromNativeSeparators(comfyRoot));

    request.insert(QStringLiteral("output"), QDir::fromNativeSeparators(outputPath));
    request.insert(QStringLiteral("metadata_output"), QDir::fromNativeSeparators(metadataPath));
    request.insert(QStringLiteral("original_output"), QDir::fromNativeSeparators(outputPath));
    request.insert(QStringLiteral("original_metadata_output"), QDir::fromNativeSeparators(metadataPath));

    // Stage 1 (workflow<->model binding): when a model override is supplied, carry it in the launch
    // request so the worker's _apply_workflow_slot_bindings substitutes it into the workflow's bound
    // checkpoint/model (and lora) loader nodes -- otherwise the graph's baked-in filenames win. This
    // only takes effect when the profile's scan actually produced a checkpoint/model slot binding.
    const QString modelTrimmed = modelOverride.trimmed();
    if (!modelTrimmed.isEmpty())
        request.insert(QStringLiteral("model"), modelTrimmed);
    const QString loraTrimmed = loraOverride.trimmed();
    if (!loraTrimmed.isEmpty())
        request.insert(QStringLiteral("lora"), loraTrimmed);
    const QString loraScaleTrimmed = loraScaleOverride.trimmed();
    if (!loraScaleTrimmed.isEmpty())
        request.insert(QStringLiteral("lora_scale"), loraScaleTrimmed);

    return request;
}

}  // namespace spellvision::workers
