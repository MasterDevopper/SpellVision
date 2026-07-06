#include "MainWindow.h"

#include "CommandPaletteDialog.h"
#include "CustomTitleBar.h"
#include "HomePage.h"
// --- CHAIN STUDIO PASS 7C-PRELUDE RAIL ENTRY ---
#include "chain/ChainStudioPage.h"
#include "ImageGenerationPage.h"
#include "ModePage.h"
#include "QueueFilterProxyModel.h"
#include "QueueManager.h"
#include "QueueTableModel.h"
#include "SettingsPage.h"
#include "T2VHistoryPage.h"
#include "ThemeManager.h"
#include "WorkflowImportDialog.h"
#include "WorkflowLibraryPage.h"
#include "workflows/WorkflowLaunchController.h"
#include "shell/MainWindowTrayController.h"
#include "shell/QueueUiPresenter.h"
#include "shell/ShellNavigationController.h"
#include "shell/BottomTelemetryPresenter.h"
#include "workers/WorkerProcessController.h"
#include "workers/WorkerQueueController.h"
#include "workers/WorkerSubmissionPolicy.h"

#include <QAbstractButton>
#include <QAbstractItemView>
#include <QAbstractItemModel>
#include <QAction>
#include <QCoreApplication>
#include <QDesktopServices>
#include <QColor>
#include <QDir>
#include <QEvent>
#include <QEventLoop>
#include <QPalette>
#include <QSettings>
#include <QFileInfo>
#include <QFile>
#include <QItemSelectionModel>
#include <QIODevice>
#include <QUuid>
#include <QUrl>
#include <QTimer>
#include <QProcessEnvironment>
#include <QProcess>
#include <QPropertyAnimation>
#include <QRegularExpression>
#include <QSignalBlocker>
#include <QJsonParseError>
#include <QJsonObject>
#include <QJsonDocument>
#include <QJsonArray>
#include <QColorDialog>
#include <QComboBox>
#include <QDateTime>
#include <QEasingCurve>
#include <QDockWidget>
#include <QFrame>
#include <QGridLayout>
#include <QIcon>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QKeySequence>
#include <QLabel>
#include <QLineEdit>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QMenu>
#include <QMessageBox>

#include <initializer_list>
#include <QProgressBar>
#include <QScrollArea>
#include <QSizePolicy>
#include <QPushButton>
#include <QStatusBar>
#include <QTabWidget>
#include <QTableView>
#include <QTextEdit>
#include <QTime>
#include <QFont>

#include <QToolButton>
#include <QSplitter>
#include <QVBoxLayout>
#include <QWidget>
#include <algorithm>
#include <limits>

#ifdef Q_OS_WIN
#include <windows.h>
#include <windowsx.h>
#include <dwmapi.h>
#endif

namespace
{


int pass28sTelemetryRankFromState(QueueItemState state)
{
    switch (state)
    {
    case QueueItemState::Queued:
        return 1;
    case QueueItemState::Preparing:
        return 2;
    case QueueItemState::Running:
        return 3;
    case QueueItemState::Completed:
    case QueueItemState::Failed:
    case QueueItemState::Cancelled:
    case QueueItemState::Skipped:
    case QueueItemState::Unknown:
    default:
        return 0;
    }
}

int pass28sTelemetryRankFromText(const QString &stateText)
{
    const QString state = stateText.trimmed().toLower();

    if (state == QStringLiteral("running"))
        return 3;

    if (state == QStringLiteral("preparing"))
        return 2;

    if (state == QStringLiteral("queued") ||
        state == QStringLiteral("queueing") ||
        state == QStringLiteral("submitting"))
        return 1;

    return 0;
}

QString pass28sTelemetryStateFromRank(int rank, const QString &fallback = QString())
{
    if (rank >= 3)
        return QStringLiteral("Running");

    if (rank == 2)
        return QStringLiteral("Preparing");

    if (rank == 1)
    {
        const QString normalized = fallback.trimmed();
        return normalized.isEmpty() ? QStringLiteral("Submitting") : normalized;
    }

    return QStringLiteral("Idle");
}

int pass28sMinimumProgressForRank(int rank)
{
    if (rank >= 3)
        return 12;

    if (rank == 2)
        return 7;

    if (rank == 1)
        return 3;

    return 0;
}


QString pass28qQueueStateText(QueueItemState state)
{
    switch (state)
    {
    case QueueItemState::Queued:
        return QStringLiteral("Queued");
    case QueueItemState::Preparing:
        return QStringLiteral("Preparing");
    case QueueItemState::Running:
        return QStringLiteral("Running");
    case QueueItemState::Completed:
        return QStringLiteral("Completed");
    case QueueItemState::Failed:
        return QStringLiteral("Failed");
    case QueueItemState::Cancelled:
        return QStringLiteral("Cancelled");
    case QueueItemState::Skipped:
        return QStringLiteral("Skipped");
    case QueueItemState::Unknown:
    default:
        return QStringLiteral("Unknown");
    }
}

QStringList pass28qAcceptedCommandsForMode(const QString &modeId)
{
    const QString mode = modeId.trimmed().toLower();

    if (mode == QStringLiteral("t2i"))
        return {QStringLiteral("t2i"), QStringLiteral("txt2img"), QStringLiteral("text_to_image")};

    if (mode == QStringLiteral("i2i"))
        return {QStringLiteral("i2i"), QStringLiteral("img2img"), QStringLiteral("image_to_image")};

    if (mode == QStringLiteral("t2v"))
        return {QStringLiteral("t2v"), QStringLiteral("text_to_video")};

    if (mode == QStringLiteral("i2v"))
        return {QStringLiteral("i2v"), QStringLiteral("image_to_video")};

    return {};
}

bool pass28qItemMatchesMode(const QueueItem &item, const QString &modeId)
{
    const QStringList accepted = pass28qAcceptedCommandsForMode(modeId);
    if (accepted.isEmpty())
        return true;

    return accepted.contains(item.command.trimmed().toLower());
}

bool pass28qItemIsActive(const QueueItem &item)
{
    if (item.isTerminal())
        return false;

    return item.running ||
           item.state == QueueItemState::Queued ||
           item.state == QueueItemState::Preparing ||
           item.state == QueueItemState::Running;
}

bool pass28qModeIsImage(const QString &modeId)
{
    const QString mode = modeId.trimmed().toLower();
    return mode == QStringLiteral("t2i") || mode == QStringLiteral("i2i");
}

QString pass28qFormatVramText(double usedMb, double totalMb)
{
    if (usedMb < 0.0 || totalMb <= 0.0)
        return QStringLiteral("VRAM: unavailable");

    const double usedGb = usedMb / 1024.0;
    const double totalGb = totalMb / 1024.0;

    return QStringLiteral("VRAM: %1/%2 GB")
        .arg(usedGb, 0, 'f', 1)
        .arg(totalGb, 0, 'f', 0);
}


    bool queueModeIsVideoWorkspace(const QString &modeId)
    {
        return modeId == QStringLiteral("t2v") || modeId == QStringLiteral("i2v");
    }

    bool queueModeIsImageWorkspace(const QString &modeId)
    {
        return modeId == QStringLiteral("t2i") || modeId == QStringLiteral("i2i");
    }


    QString generationModeIdForQueueItem(const QueueItem &item)
    {
        const QString command = item.command.trimmed().toLower();
        const QString mediaType = item.mediaType.trimmed().toLower();

        if (command == QStringLiteral("t2i") || command == QStringLiteral("txt2img") || command == QStringLiteral("text_to_image"))
            return QStringLiteral("t2i");
        if (command == QStringLiteral("i2i") || command == QStringLiteral("img2img") || command == QStringLiteral("image_to_image"))
            return QStringLiteral("i2i");
        if (command == QStringLiteral("t2v") || command == QStringLiteral("text_to_video"))
            return QStringLiteral("t2v");
        if (command == QStringLiteral("i2v") || command == QStringLiteral("image_to_video"))
            return QStringLiteral("i2v");
        if (mediaType == QStringLiteral("video"))
            return QStringLiteral("t2v");
        if (mediaType == QStringLiteral("image"))
            return QStringLiteral("t2i");

        return {};
    }

    QString normalizedPreviewPathKey(const QString &path)
    {
        const QString trimmed = path.trimmed();
        if (trimmed.isEmpty())
            return {};

        return QDir::fromNativeSeparators(QFileInfo(trimmed).absoluteFilePath()).toLower();
    }

    bool queueItemIsActiveForGeneration(const QueueItem &item)
    {
        return item.state == QueueItemState::Queued ||
               item.state == QueueItemState::Preparing ||
               item.state == QueueItemState::Running ||
               item.running;
    }

    qint64 queueItemPreviewSortKey(const QueueItem &item)
    {
        if (item.finishedAt.isValid())
            return item.finishedAt.toMSecsSinceEpoch();

        if (item.updatedAt.isValid())
            return item.updatedAt.toMSecsSinceEpoch();

        if (item.startedAt.isValid())
            return item.startedAt.toMSecsSinceEpoch();

        if (item.createdAt.isValid())
            return item.createdAt.toMSecsSinceEpoch();

        return static_cast<qint64>(item.orderIndex);
    }

    QString previewFileRevisionKey(const QString &path)
    {
        const QFileInfo info(path.trimmed());
        if (!info.exists())
            return QStringLiteral("missing");

        return QStringLiteral("%1:%2")
            .arg(info.lastModified().toUTC().toMSecsSinceEpoch())
            .arg(info.size());
    }



    QFrame *createPanelFrame(const QString &objectName, QWidget *parent = nullptr)
    {
        auto *frame = new QFrame(parent);
        frame->setObjectName(objectName);
        frame->setFrameShape(QFrame::NoFrame);
        return frame;
    }

    QToolButton *createRailButton(const QString &text, const QString &toolTip, QWidget *parent = nullptr)
    {
        auto *button = new QToolButton(parent);
        button->setObjectName(QStringLiteral("SideRailButton"));
        button->setText(text);
        button->setToolTip(toolTip);
        button->setCheckable(true);
        button->setAutoRaise(true);
        button->setFixedSize(58, 48); // fits the 74px re-sectioned rail (was 72x52)
        button->setToolButtonStyle(Qt::ToolButtonTextOnly);
        button->setCursor(Qt::PointingHandCursor);

        // Pre-empt the Qt-internal "QFont::setPointSize: Point size <= 0"
        // warning that fires on rail-button :hover recompute. The shell
        // stylesheet sets font-size: 12px (a PIXEL size) on
        // QToolButton#SideRailButton; giving the button's QFont an explicit
        // pixelSize here means Qt's hover restyle reads a valid size instead
        // of the -1 "unset point size" sentinel. 12px matches the stylesheet,
        // so this is visually a no-op.
        QFont railButtonFont = button->font();
        railButtonFont.setPixelSize(11); // matches the SideRailButton stylesheet (avoids the -1 point-size sentinel)
        button->setFont(railButtonFont);

        return button;
    }

    QFrame *createDockHeaderFrame(const QString &objectName, QWidget *parent = nullptr)
    {
        auto *frame = createPanelFrame(objectName, parent);
        frame->setFixedHeight(34);
        return frame;
    }

    QString defaultManagedComfyRoot(const QString &projectRoot)
    {
        const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_COMFY")).trimmed();
        if (!envPath.isEmpty())
            return QDir::fromNativeSeparators(QDir(envPath).absolutePath());

        const QString preferred = QStringLiteral("D:/AI_ASSETS/comfy_runtime/ComfyUI");
        if (QDir(preferred).exists())
            return preferred;

        return QDir::fromNativeSeparators(QDir(projectRoot).filePath(QStringLiteral("runtime/comfy/ComfyUI")));
    }

    QString defaultImportedWorkflowsRoot(const QString &projectRoot)
    {
        return QDir(projectRoot).filePath(QStringLiteral("runtime/imported_workflows"));
    }


    QString queueStateDisplay(QueueItemState state)
    {
        switch (state)
        {
        case QueueItemState::Queued:
            return QStringLiteral("Queued");
        case QueueItemState::Preparing:
            return QStringLiteral("Preparing");
        case QueueItemState::Running:
            return QStringLiteral("Running");
        case QueueItemState::Completed:
            return QStringLiteral("Completed");
        case QueueItemState::Failed:
            return QStringLiteral("Failed");
        case QueueItemState::Cancelled:
            return QStringLiteral("Cancelled");
        case QueueItemState::Skipped:
            return QStringLiteral("Skipped");
        case QueueItemState::Unknown:
        default:
            return QStringLiteral("Unknown");
        }
    }

    QStringList brandIconCandidates()
    {
        QStringList starts = {QCoreApplication::applicationDirPath(), QDir::currentPath()};
        QStringList names = {
            QStringLiteral("icons/SpellVision.jpg"),
            QStringLiteral("icons/SpellVision.jpeg"),
            QStringLiteral("icons/SpellVision.png"),
            QStringLiteral("qt_ui/icons/SpellVision.jpg"),
            QStringLiteral("qt_ui/icons/SpellVision.jpeg"),
            QStringLiteral("qt_ui/icons/SpellVision.png"),
            QStringLiteral("SpellVision.jpg"),
            QStringLiteral("SpellVision.jpeg"),
            QStringLiteral("SpellVision.png")};

        QStringList out;
        for (const QString &start : starts)
        {
            QDir dir(start);
            for (int depth = 0; depth < 7; ++depth)
            {
                for (const QString &name : names)
                    out << dir.filePath(name);
                if (!dir.cdUp())
                    break;
            }
        }
        out.removeDuplicates();
        return out;
    }

    QPixmap loadBrandPixmap()
    {
        for (const QString &path : brandIconCandidates())
        {
            if (!QFileInfo::exists(path))
                continue;
            QPixmap pm(path);
            if (!pm.isNull())
                return pm;
        }
        return {};
    }

    QPixmap roundedBrandPixmap(const QSize &size, int radius)
    {
        const QPixmap source = loadBrandPixmap();
        if (source.isNull())
            return {};

        QPixmap scaled = source.scaled(size, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation);
        QPixmap out(size);
        out.fill(Qt::transparent);

        QPainter painter(&out);
        painter.setRenderHint(QPainter::Antialiasing, true);
        QPainterPath clipPath;
        clipPath.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius);
        painter.setClipPath(clipPath);
        painter.drawPixmap(0, 0, scaled);

        painter.setClipping(false);
        QPen border(QColor(QStringLiteral("#7f93dc")));
        border.setWidthF(1.0);
        painter.setPen(border);
        painter.drawRoundedRect(QRectF(0.5, 0.5, size.width() - 1.0, size.height() - 1.0), radius, radius);
        return out;
    }

    QString summarizePrompt(const QString &prompt)
    {
        const QString compact = prompt.simplified();
        if (compact.isEmpty())
            return QStringLiteral("No prompt summary available.");

        return compact.left(220);
    }


    bool isVideoQueueItem(const QueueItem &item)
    {
        return item.command.compare(QStringLiteral("t2v"), Qt::CaseInsensitive) == 0 ||
               item.command.compare(QStringLiteral("i2v"), Qt::CaseInsensitive) == 0 ||
               item.mediaType.compare(QStringLiteral("video"), Qt::CaseInsensitive) == 0;
    }

    QString queueOutputFileStatus(const QString &path)
    {
        const QString trimmed = path.trimmed();
        if (trimmed.isEmpty())
            return QStringLiteral("Output: not available yet");

        const QFileInfo info(trimmed);
        return info.exists()
                   ? QStringLiteral("Output: %1").arg(QDir::toNativeSeparators(info.absoluteFilePath()))
                   : QStringLiteral("Output: missing or not settled yet — %1").arg(QDir::toNativeSeparators(trimmed));
    }

    QString queueMetadataFileStatus(const QString &path)
    {
        const QString trimmed = path.trimmed();
        if (trimmed.isEmpty())
            return QStringLiteral("Metadata: not available yet");

        const QFileInfo info(trimmed);
        return info.exists()
                   ? QStringLiteral("Metadata: %1").arg(QDir::toNativeSeparators(info.absoluteFilePath()))
                   : QStringLiteral("Metadata: missing or not settled yet — %1").arg(QDir::toNativeSeparators(trimmed));
    }

    QString videoQueueSummary(const QueueItem &item)
    {
        QStringList facts;
        if (!item.videoFamily.trimmed().isEmpty())
            facts << QStringLiteral("Family: %1").arg(item.videoFamily.trimmed());
        if (!item.videoBackendType.trimmed().isEmpty())
            facts << QStringLiteral("Backend: %1").arg(item.videoBackendType.trimmed());
        if (!item.videoBackendName.trimmed().isEmpty())
            facts << QStringLiteral("Adapter: %1").arg(item.videoBackendName.trimmed());
        if (!item.videoResolution.trimmed().isEmpty())
            facts << QStringLiteral("Resolution: %1").arg(item.videoResolution.trimmed());
        else if (item.videoWidth > 0 && item.videoHeight > 0)
            facts << QStringLiteral("Resolution: %1x%2").arg(item.videoWidth).arg(item.videoHeight);
        if (!item.videoDurationLabel.trimmed().isEmpty())
            facts << QStringLiteral("Duration: %1").arg(item.videoDurationLabel.trimmed());
        else if (item.videoFrames > 0 && item.videoFps > 0)
            facts << QStringLiteral("Frames/FPS: %1 @ %2fps").arg(item.videoFrames).arg(item.videoFps);
        if (!item.videoLowModelName.trimmed().isEmpty() || !item.videoHighModelName.trimmed().isEmpty())
            facts << QStringLiteral("Stack: low=%1 • high=%2")
                         .arg(item.videoLowModelName.trimmed().isEmpty() ? QStringLiteral("unknown") : item.videoLowModelName.trimmed(),
                              item.videoHighModelName.trimmed().isEmpty() ? QStringLiteral("unknown") : item.videoHighModelName.trimmed());
        else if (!item.videoStackSummary.trimmed().isEmpty())
            facts << QStringLiteral("Stack: %1").arg(item.videoStackSummary.trimmed());
        if (item.videoValidatedBackend)
            facts << QStringLiteral("Validation: production-ready video backend");

        return facts.join(QStringLiteral("\n"));
    }

    QString compactRuntimeSignature(const QString &signature)
    {
        const QString compact = signature.simplified();
        if (compact.size() <= 180)
            return compact;
        return compact.left(177) + QStringLiteral("...");
    }

    QString runtimeMemoryModeLabel(const QueueItem &item)
    {
        if (item.videoRuntimeReused)
            return QStringLiteral("Video Warm Reuse");
        if (item.imageCacheUnloadedBeforeVideo)
            return QStringLiteral("Image → Video Cleanup");
        if (item.runtimeTarget.compare(QStringLiteral("image"), Qt::CaseInsensitive) == 0 &&
            item.runtimePrevious.compare(QStringLiteral("video"), Qt::CaseInsensitive) == 0)
            return QStringLiteral("Video → Image CUDA Cleanup");
        if (item.runtimePrevious.compare(QStringLiteral("cold"), Qt::CaseInsensitive) == 0)
            return QStringLiteral("Cold Start");
        if (!item.runtimeTransition.trimmed().isEmpty())
            return item.runtimeTransition.trimmed();
        return QString();
    }

    QString runtimeDiagnosticsSummary(const QueueItem &item)
    {
        QStringList facts;
        const QString mode = runtimeMemoryModeLabel(item);
        if (!mode.isEmpty())
            facts << QStringLiteral("Memory mode: %1").arg(mode);
        if (!item.runtimeTransition.trimmed().isEmpty())
            facts << QStringLiteral("Runtime transition: %1").arg(item.runtimeTransition.trimmed());
        if (!item.runtimePrevious.trimmed().isEmpty() || !item.runtimeTarget.trimmed().isEmpty())
            facts << QStringLiteral("Runtime route: %1 → %2")
                         .arg(item.runtimePrevious.trimmed().isEmpty() ? QStringLiteral("unknown") : item.runtimePrevious.trimmed(),
                              item.runtimeTarget.trimmed().isEmpty() ? QStringLiteral("unknown") : item.runtimeTarget.trimmed());
        if (item.imageCacheActiveBeforeRuntime)
            facts << QStringLiteral("Image cache before job: active");
        if (item.imageCacheUnloadedBeforeVideo)
            facts << QStringLiteral("Image VRAM cleanup: unloaded before video generation");
        if (!item.imageCacheKeyBeforeRuntime.trimmed().isEmpty())
            facts << QStringLiteral("Previous image cache: %1").arg(QFileInfo(item.imageCacheKeyBeforeRuntime.trimmed()).fileName());
        if (item.videoRuntimeReused)
            facts << QStringLiteral("Video runtime: reused warm Wan stack");
        else if (item.videoWarmReuseCandidate)
            facts << QStringLiteral("Video runtime: warm reuse candidate");
        if (!item.videoWarmReuseSource.trimmed().isEmpty())
            facts << QStringLiteral("Video warm source: %1").arg(item.videoWarmReuseSource.trimmed());
        if (item.videoRuntimeCacheUpdated)
            facts << QStringLiteral("Video runtime cache: updated after completion");
        if (!item.videoRuntimeSignatureBefore.trimmed().isEmpty())
            facts << QStringLiteral("Previous video affinity: %1").arg(compactRuntimeSignature(item.videoRuntimeSignatureBefore));
        if (!item.videoRuntimeAffinitySignature.trimmed().isEmpty())
            facts << QStringLiteral("Current video affinity: %1").arg(compactRuntimeSignature(item.videoRuntimeAffinitySignature));
        if (!item.runtimeNotesSummary.trimmed().isEmpty())
            facts << QStringLiteral("Runtime notes: %1").arg(item.runtimeNotesSummary.trimmed());
        return facts.join(QStringLiteral("\n"));
    }


    QString videoHistoryIndexPathForProjectRoot(const QString &projectRoot)
    {
        return QDir(projectRoot).filePath(QStringLiteral("runtime/history/video_history_index.json"));
    }

    QString firstJsonText(const QJsonObject &obj, std::initializer_list<const char *> keys)
    {
        for (const char *rawKey : keys)
        {
            const QString key = QString::fromLatin1(rawKey);
            const QString value = obj.value(key).toString().trimmed();
            if (!value.isEmpty())
                return value;
        }
        return QString();
    }

    int firstJsonInt(const QJsonObject &obj, std::initializer_list<const char *> keys, int fallback = 0)
    {
        for (const char *rawKey : keys)
        {
            const QString key = QString::fromLatin1(rawKey);
            const QJsonValue value = obj.value(key);
            if (value.isDouble())
                return value.toInt(fallback);
        }
        return fallback;
    }

    QJsonObject latestPersistedVideoHistoryObject(const QString &projectRoot)
    {
        QFile file(videoHistoryIndexPathForProjectRoot(projectRoot));
        if (!file.exists() || !file.open(QIODevice::ReadOnly))
            return {};

        QJsonParseError parseError;
        const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parseError);
        if (parseError.error != QJsonParseError::NoError || !doc.isObject())
            return {};

        const QJsonArray items = doc.object().value(QStringLiteral("items")).toArray();
        for (int i = items.size() - 1; i >= 0; --i)
        {
            const QJsonObject item = items.at(i).toObject();
            if (!firstJsonText(item, {"output_video", "video_path", "output"}).isEmpty())
                return item;
        }
        return {};
    }

    QueueItem queueItemFromVideoHistoryObject(const QJsonObject &obj)
    {
        QueueItem item;
        if (obj.isEmpty())
            return item;

        item.id = firstJsonText(obj, {"history_id", "queue_item_id", "job_id"});
        item.workerJobId = obj.value(QStringLiteral("job_id")).toString().trimmed();
        item.command = firstJsonText(obj, {"command", "video_request_kind", "task_type"});
        if (item.command.isEmpty())
            item.command = QStringLiteral("t2v");
        item.mediaType = QStringLiteral("video");
        item.prompt = obj.value(QStringLiteral("prompt_preview")).toString().trimmed();
        if (item.prompt.isEmpty())
            item.prompt = obj.value(QStringLiteral("prompt")).toString().trimmed().left(160);
        item.outputPath = firstJsonText(obj, {"output_video", "video_path", "output"});
        item.metadataPath = firstJsonText(obj, {"metadata_output", "video_metadata_output"});
        item.videoFamily = obj.value(QStringLiteral("video_family")).toString().trimmed();
        item.videoBackendType = obj.value(QStringLiteral("video_backend_type")).toString().trimmed();
        item.videoBackendName = obj.value(QStringLiteral("video_backend_name")).toString().trimmed();
        item.videoDurationLabel = obj.value(QStringLiteral("video_duration_label")).toString().trimmed();
        item.videoResolution = obj.value(QStringLiteral("video_resolution")).toString().trimmed();
        item.videoStackSummary = obj.value(QStringLiteral("video_model_stack_summary")).toString().trimmed();
        item.videoLowModelName = obj.value(QStringLiteral("video_low_model_name")).toString().trimmed();
        item.videoHighModelName = obj.value(QStringLiteral("video_high_model_name")).toString().trimmed();
        item.videoPrimaryModelName = obj.value(QStringLiteral("video_primary_model_name")).toString().trimmed();
        item.videoFrames = firstJsonInt(obj, {"video_frame_count", "video_frames"});
        item.videoFps = firstJsonInt(obj, {"video_fps"});
        item.videoWidth = firstJsonInt(obj, {"video_width"});
        item.videoHeight = firstJsonInt(obj, {"video_height"});
        item.videoValidatedBackend = obj.value(QStringLiteral("video_validated_backend")).toBool(false);
        item.runtimeTransition = obj.value(QStringLiteral("runtime_transition")).toString().trimmed();
        item.runtimeTarget = obj.value(QStringLiteral("runtime_target")).toString().trimmed();
        item.runtimePrevious = obj.value(QStringLiteral("runtime_previous")).toString().trimmed();
        item.imageCacheActiveBeforeRuntime = obj.value(QStringLiteral("image_cache_active_before_runtime")).toBool(false);
        item.imageCacheUnloadedBeforeVideo = obj.value(QStringLiteral("image_cache_unloaded_before_video")).toBool(false);
        item.imageCacheKeyBeforeRuntime = obj.value(QStringLiteral("image_cache_key_before_runtime")).toString().trimmed();
        item.videoRuntimeSignatureBefore = obj.value(QStringLiteral("video_runtime_signature_before")).toString().trimmed();
        item.videoRuntimeReused = obj.value(QStringLiteral("video_runtime_reused")).toBool(false);
        item.videoWarmReuseCandidate = obj.value(QStringLiteral("video_warm_reuse_candidate")).toBool(false);
        item.videoWarmReuseSource = obj.value(QStringLiteral("video_warm_reuse_source")).toString().trimmed();
        item.videoRuntimeAffinitySignature = obj.value(QStringLiteral("video_runtime_affinity_signature")).toString().trimmed();
        item.videoRuntimeCacheUpdated = obj.value(QStringLiteral("video_runtime_cache_updated")).toBool(false);
        item.statusText = QStringLiteral("Loaded from persistent video history index");
        item.completed = true;
        item.state = QueueItemState::Completed;
        return item;
    }

    QueueItem latestPersistedVideoQueueItem(const QString &projectRoot)
    {
        return queueItemFromVideoHistoryObject(latestPersistedVideoHistoryObject(projectRoot));
    }
    QJsonObject parseLastJsonObjectFromStdout(const QString &allStdout, QString *errorText = nullptr)
    {
        QString lastJsonLine;
        const QStringList lines = allStdout.split('\n', Qt::SkipEmptyParts);
        for (auto it = lines.crbegin(); it != lines.crend(); ++it)
        {
            const QString candidate = it->trimmed();
            if (candidate.startsWith('{') && candidate.endsWith('}'))
            {
                lastJsonLine = candidate;
                break;
            }
        }

        if (lastJsonLine.isEmpty())
        {
            if (errorText)
                *errorText = QStringLiteral("Worker returned no JSON payload.");
            return {};
        }

        QJsonParseError parseError{};
        const QJsonDocument doc = QJsonDocument::fromJson(lastJsonLine.toUtf8(), &parseError);
        if (parseError.error != QJsonParseError::NoError || !doc.isObject())
        {
            if (errorText)
                *errorText = QStringLiteral("Worker returned invalid JSON: %1").arg(lastJsonLine);
            return {};
        }

        return doc.object();
    }
}

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    setObjectName(QStringLiteral("MainWindow"));
    setWindowTitle(QStringLiteral("SpellVision"));
    const QPixmap brandWindowIcon = loadBrandPixmap();
    if (!brandWindowIcon.isNull())
        setWindowIcon(QIcon(brandWindowIcon));
    setWindowFlags(Qt::Window | Qt::FramelessWindowHint | Qt::CustomizeWindowHint | Qt::WindowSystemMenuHint | Qt::WindowMinimizeButtonHint | Qt::WindowMaximizeButtonHint | Qt::WindowCloseButtonHint);
    setDockNestingEnabled(true);

#ifdef Q_OS_WIN
    // The WM_NCCALCSIZE handler (nativeEvent) collapses the non-client area to kill the
    // duplicate native caption; a zero-non-client window loses its DWM drop shadow, so
    // extend the frame 1px into the client to make DWM render the shadow again. winId()
    // forces native window creation here -- safe, because the NCCALCSIZE handler keys off
    // msg->hwnd, not winId(), so there's no creation re-entrancy.
    {
        const MARGINS shadowMargins{1, 1, 1, 1};
        DwmExtendFrameIntoClientArea(reinterpret_cast<HWND>(winId()), &shadowMargins);
    }
#endif

    // ComfyUI is launched detached (Popen CREATE_NEW_PROCESS_GROUP) and no window-close path
    // tears it down, so it orphans holding :8188 + GPU. aboutToQuit fires on EVERY quit path
    // (close button, Alt+F4, menu Quit, QApplication::quit), so one hook covers them all.
    connect(qApp, &QCoreApplication::aboutToQuit, this, &MainWindow::tearDownComfyOnExit);

    queueManager_ = new QueueManager(this);
    connect(queueManager_, &QueueManager::queueChanged, this, &MainWindow::onQueueChanged);

    workerQueueController_ = new spellvision::workers::WorkerQueueController(this);
    spellvision::workers::WorkerQueueController::Bindings queueBindings;
    queueBindings.queueManager = queueManager_;
    queueBindings.sendRequest = [this](const QJsonObject &request, QString *stderrText, bool *startedOk) {
        return sendWorkerRequest(request, stderrText, startedOk);
    };
    queueBindings.appendLogLine = [this](const QString &text) {
        appendLogLine(text);
    };
    queueBindings.afterQueueSnapshotApplied = [this]() {
        syncGenerationPreviewsFromQueue();
        syncBottomTelemetry();

        // Pass 28N:
        // BottomTelemetryPresenter reports global queue state. Re-apply the
        // mode-scoped queue presentation after telemetry sync so T2I/I2I keep
        // the visible-row count and stable ledger presentation.
        applyQueuePresentationForCurrentMode();
    };
    workerQueueController_->bind(queueBindings);
    workerQueueController_->startPolling(1800);

    buildShell();
    buildPages();
    buildPersistentDocks();
    buildBottomTelemetryBar();
    // Phase 6: restore the persisted Simple/Advanced disclosure mode and reflect it on the toggle.
    {
        QSettings disclosureSettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        setDisclosureMode(disclosureSettings.value(QStringLiteral("ui/advancedMode"), false).toBool());
    }
    switchToMode(QStringLiteral("home"));
    // Belt-and-suspenders floor so the window can shrink toward a 1366x768-class
    // laptop. NOTE: Qt still enforces max(this, layout minimumSizeHint) -- this only
    // bites once child minimums (side-panel widths above) allow it; it does not by
    // itself override a larger emergent layout minimum.
    setMinimumSize(1180, 760);
    resize(1760, 1020);
}

void MainWindow::buildShell()
{
    titleBar_ = new CustomTitleBar(this);
    titleBar_->setObjectName(QStringLiteral("CustomTitleBar"));
    titleBar_->setWindowTitleText(QString());
    titleBar_->setContextText(QStringLiteral("Home"));

    connect(titleBar_, &CustomTitleBar::menuRequested, this, &MainWindow::showTitleBarMenu);
    connect(titleBar_, &CustomTitleBar::layoutMenuRequested, this, &MainWindow::showLayoutMenu);
    connect(titleBar_, &CustomTitleBar::commandPaletteRequested, this, &MainWindow::showCommandPalette);
    connect(titleBar_, &CustomTitleBar::disclosureModeChangeRequested, this, &MainWindow::setDisclosureMode);
    connect(titleBar_, &CustomTitleBar::primarySidebarToggleRequested, this, &MainWindow::togglePrimarySidebar);
    connect(titleBar_, &CustomTitleBar::bottomPanelToggleRequested, this, &MainWindow::toggleBottomPanels);
    connect(titleBar_, &CustomTitleBar::secondarySidebarToggleRequested, this, &MainWindow::toggleDetailsPanel);
    connect(titleBar_, &CustomTitleBar::minimizeRequested, this, &QWidget::showMinimized);
    connect(titleBar_, &CustomTitleBar::maximizeRestoreRequested, this, [this]()
            {
        isMaximized() ? showNormal() : showMaximized();
        if (titleBar_)
            titleBar_->setMaximized(isMaximized()); });
    connect(titleBar_, &CustomTitleBar::closeRequested, this, &QWidget::close);
    connect(titleBar_, &CustomTitleBar::systemMenuRequested, this, &MainWindow::showSystemMenu);

    // The title bar is the QMainWindow menu widget; to soften the bar->body edge we install a
    // vertical container [bar, transition strip] as the menu widget. The strip is a styled QFrame
    // (#TitleBarTransitionStrip) that ramps the bar's tone down to the page void -- no hard seam.
    auto *menuContainer = new QWidget(this);
    auto *menuContainerLayout = new QVBoxLayout(menuContainer);
    menuContainerLayout->setContentsMargins(0, 0, 0, 0);
    menuContainerLayout->setSpacing(0);
    auto *titleBarTransitionStrip = new QFrame(menuContainer);
    titleBarTransitionStrip->setObjectName(QStringLiteral("TitleBarTransitionStrip"));
    titleBarTransitionStrip->setFixedHeight(12);
    menuContainerLayout->addWidget(titleBar_);
    menuContainerLayout->addWidget(titleBarTransitionStrip);
    setMenuWidget(menuContainer);

    auto *commandPaletteAction = new QAction(this);
    commandPaletteAction->setShortcut(QKeySequence(QStringLiteral("Ctrl+Shift+P")));
    addAction(commandPaletteAction);
    connect(commandPaletteAction, &QAction::triggered, this, &MainWindow::showCommandPalette);

    centralShell_ = new QWidget(this);
    auto *shellLayout = new QHBoxLayout(centralShell_);
    shellLayout->setContentsMargins(0, 0, 0, 0);
    shellLayout->setSpacing(0);

    sideRail_ = createSideRail();
    pageStack_ = new QStackedWidget(centralShell_);
    pageStack_->setObjectName(QStringLiteral("MainPageStack"));

    shellLayout->addWidget(sideRail_, 0);
    shellLayout->addWidget(pageStack_, 1);

    setCentralWidget(centralShell_);

    auto applyTheme = [this]()
    {
        setStyleSheet(ThemeManager::instance().shellStyleSheet());
    };
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, applyTheme);
}

QWidget *MainWindow::createSideRail()
{
    auto *rail = new QWidget(this);
    rail->setObjectName(QStringLiteral("SideRail"));
    rail->setFixedWidth(74); // studio-layout rail width (was 96)

    auto *layout = new QVBoxLayout(rail);
    layout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
    layout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    auto *badge = new QLabel(QStringLiteral("SV"), rail);
    badge->setObjectName(QStringLiteral("SideRailBadge"));
    badge->setAlignment(Qt::AlignCenter);
    badge->setFixedSize(48, 48);
    const QPixmap railBadge = roundedBrandPixmap(QSize(40, 40), 12);
    if (!railBadge.isNull())
        badge->setPixmap(railBadge);
    layout->addWidget(badge, 0, Qt::AlignHCenter);
    const auto specs = spellvision::shell::ShellNavigationController::railButtonSpecs();

    // Re-sectioned rail (Create / Manage / System): emit a group header whenever the
    // spec's section changes. Entries already sit in target order, so a linear walk groups them.
    QString currentSection;
    for (const auto &spec : specs)
    {
        if (spec.section != currentSection)
        {
            currentSection = spec.section;
            auto *header = new QLabel(currentSection.toUpper(), rail);
            header->setObjectName(QStringLiteral("RailSectionHeader"));
            header->setAlignment(Qt::AlignHCenter);
            layout->addWidget(header, 0, Qt::AlignHCenter);
        }
        auto *button = createRailButton(spec.text, spec.toolTip, rail);
        connect(button, &QToolButton::clicked, this, [this, spec]()
                { switchToMode(spec.modeId); });
        layout->addWidget(button);
        modeButtons_.insert(spec.modeId, button);
    }

    layout->addStretch(1);
    return rail;
}

void MainWindow::buildPages()
{
    homePage_ = new HomePage(this);
    // --- CHAIN STUDIO PASS 7C-PRELUDE RAIL ENTRY ---
    chainStudioPage_ = new spellvision::chain::ChainStudioPage(this);
    workflowsPage_ = new WorkflowLibraryPage(this);
    workflowsPage_->setProjectRoot(resolveProjectRoot());
    workflowsPage_->setPythonExecutable(resolvePythonExecutable());
    workflowsPage_->setProfilesRoot(defaultImportedWorkflowsRoot(resolveProjectRoot()));
    workflowsPage_->setComfyWorkflowsRoot(
        QDir(defaultManagedComfyRoot(resolveProjectRoot())).filePath(QStringLiteral("user/default/workflows")));
    connect(workflowsPage_, &WorkflowLibraryPage::importWorkflowRequested, this, &MainWindow::openWorkflowImportDialog);
    historyPage_ = new T2VHistoryPage(this);
    historyPage_->setProjectRoot(resolveProjectRoot());
    inspirationPage_ = new ModePage(
        QStringLiteral("Inspiration"),
        QStringLiteral("A moodboard plus prompt recipe system that sends favorites and starters back into Home."),
        {QStringLiteral("Use a top filter bar for fast navigation across local, curated, and future online content."),
         QStringLiteral("Make the prompt immediately editable when an item is selected."),
         QStringLiteral("Support Send to Home Hero, Send to T2I, and Save as Workflow actions.")},
        this);
    modelsPage_ = new ModePage(
        QStringLiteral("Models"),
        QStringLiteral("Keep model management adjacent to downloads and managers without cluttering creation pages."),
        {QStringLiteral("Surface checkpoints, LoRAs, VAEs, and upscalers with compatibility cues."),
         QStringLiteral("Show dependency health and install state in the library rather than scattering it across pages."),
         QStringLiteral("Reserve space for downloads, manager tools, and future multimodal assets.")},
        this);
    settingsPage_ = new SettingsPage(this);
    // Phase 7 capstone: the Settings "Workspace Mode" dropdown is a SECOND entry point to the same
    // persisted advancedMode_ that the title-bar toggle drives. A user pick routes through
    // setDisclosureMode (the single writer); disclosureModeChanged reflects it back so the two stay
    // in sync (last write wins). buildPages() runs before the constructor's restore, so the restore's
    // emit lands here too -- the explicit seed below just covers the pre-restore default.
    connect(settingsPage_, &SettingsPage::disclosureModeChangeRequested, this, &MainWindow::setDisclosureMode);
    connect(this, &MainWindow::disclosureModeChanged, settingsPage_, &SettingsPage::setDisclosureMode);
    settingsPage_->setDisclosureMode(isAdvancedMode());

    // The four ImageGenerationPages (t2i/i2i/t2v/i2v) are NOT built here -- they are
    // the ~6s of intrinsic widget-tree construction that used to block the window from
    // painting until ~9.8s. They are deferred to ensureGenerationPageBuilt(), reached
    // on first navigation (on-demand) or via the idle pre-warm started below. Only the
    // eager (cheap) pages are constructed + registered here.

    for (QWidget *page : {static_cast<QWidget *>(homePage_),
                          static_cast<QWidget *>(chainStudioPage_),  // CHAIN STUDIO PASS 7C-PRELUDE RAIL ENTRY
                          static_cast<QWidget *>(workflowsPage_),
                          static_cast<QWidget *>(historyPage_),
                          static_cast<QWidget *>(inspirationPage_),
                          static_cast<QWidget *>(modelsPage_),
                          static_cast<QWidget *>(settingsPage_)})
    {
        pageStack_->addWidget(page);
    }

    modePages_.insert(QStringLiteral("home"), homePage_);
    // --- CHAIN STUDIO PASS 7C-PRELUDE RAIL ENTRY ---
    modePages_.insert(QStringLiteral("chain"), chainStudioPage_);
    // t2i/i2i/t2v/i2v are inserted into modePages_ by ensureGenerationPageBuilt when built.
    modePages_.insert(QStringLiteral("workflows"), workflowsPage_);
    modePages_.insert(QStringLiteral("history"), historyPage_);
    modePages_.insert(QStringLiteral("inspiration"), inspirationPage_);
    modePages_.insert(QStringLiteral("models"), modelsPage_);
    modePages_.insert(QStringLiteral("settings"), settingsPage_);

    connect(homePage_, &HomePage::modeRequested, this, &MainWindow::switchToMode);
    connect(homePage_, &HomePage::managerRequested, this, &MainWindow::openManager);
    connect(homePage_, &HomePage::launchRequested, this, [this](const QString &modeId,
                                                                const QString &title,
                                                                const QString &subtitle,
                                                                const QString &sourceLabel) {
        handleHomeLaunchRequest(modeId, title, subtitle, sourceLabel);
    });

    // The four generation pages are wired inside ensureGenerationPageBuilt (via
    // connectGenerationPage) at build time, not here -- they no longer exist yet.

    workflowsPage_->refreshProfiles();

    connect(workflowsPage_, &WorkflowLibraryPage::importWorkflowRequested, this, &MainWindow::openWorkflowImportDialog);
    connect(workflowsPage_, &WorkflowLibraryPage::launchWorkflowRequested, this, &MainWindow::launchWorkflowProfile);
    connect(workflowsPage_, &WorkflowLibraryPage::workflowDraftRequested,
            this, &MainWindow::openWorkflowDraft);

    // Idle pre-warm is kicked off from showEvent() (first show), NOT here: scheduling
    // it from the constructor anchors the delay to ctor time, which elapses before the
    // event loop even starts, so the first build would race the window's first paint.
    // showEvent runs after show(), so the first-build delay is relative to the window
    // actually appearing.
}

void MainWindow::buildPersistentDocks()
{
    // Phase 5: the bottom QDockWidget is retired in favour of a frameless slide-up overlay drawer
    // (queueOverlay_) that floats over the canvas. queueDock_ stays nullptr; every queueDock_-guarded
    // path self-skips, and the chrome choke (updateDockChrome -> applyQueueDockChrome) is repointed
    // at the overlay below.
    buildQueueOverlay();
}







void MainWindow::buildBottomTelemetryBar()
{
    // Pass 28R:
    // QStatusBar shifts normal widgets and permanent widgets independently.
    // Use one fixed telemetry container so label updates cannot make the bar
    // jump left/right while generation and VRAM polling are active.
    QStatusBar *bar = statusBar();
    if (!bar)
        return;

    bar->clearMessage();
    bar->setSizeGripEnabled(false);
    bar->setFixedHeight(38);
    bar->setMinimumHeight(38);
    bar->setMaximumHeight(38);

    auto *container = new QFrame(bar);
    container->setObjectName(QStringLiteral("BottomTelemetryContainer"));
    container->setFrameShape(QFrame::NoFrame);
    container->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    container->setMinimumHeight(30);
    container->setMaximumHeight(30);

    auto *layout = new QHBoxLayout(container);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);

    auto makeTelemetryLabel = [container](const QString &objectName,
                                          const QString &text,
                                          int width,
                                          Qt::Alignment alignment = Qt::AlignCenter) {
        auto *label = new QLabel(text, container);
        label->setObjectName(objectName);
        label->setFixedWidth(width);
        label->setMinimumHeight(24);
        label->setMaximumHeight(24);
        label->setAlignment(alignment);
        label->setWordWrap(false);
        label->setTextInteractionFlags(Qt::NoTextInteraction);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
        return label;
    };

    auto addSeparator = [container, layout]() {
        auto *separator = new QFrame(container);
        separator->setObjectName(QStringLiteral("BottomTelemetrySeparator"));
        separator->setFrameShape(QFrame::VLine);
        separator->setFixedWidth(1);
        separator->setMinimumHeight(22);
        separator->setMaximumHeight(22);
        separator->setStyleSheet(QStringLiteral(
            "QFrame#BottomTelemetrySeparator {"
            " background: rgba(135,165,220,115);"
            " border: none;"
            "}"
        ));
        layout->addWidget(separator);
    };

    // Phase 8 wave 1 (clipping fix): the fixed telemetry widths summed to ~1258px + separators, which
    // overflowed the ~1184px-usable status bar at common window widths -> the rightmost widget (the
    // progress bar) clipped on the right. Trim the over-generous widths (each still exceeds its text)
    // so the bar fits; Model stays generous for checkpoint names. Fixed widths preserve the Pass-28R
    // no-jump behaviour; this just fits the budget.
    bottomReadyLabel_ = makeTelemetryLabel(QStringLiteral("BottomReadyLabel"), QStringLiteral("Ready"), 56);
    bottomPageLabel_ = makeTelemetryLabel(QStringLiteral("BottomPageLabel"), QStringLiteral("Home"), 128, Qt::AlignLeft | Qt::AlignVCenter);
    bottomRuntimeLabel_ = makeTelemetryLabel(QStringLiteral("BottomRuntimeLabel"), QStringLiteral("Runtime: local"), 124);
    bottomQueueLabel_ = makeTelemetryLabel(QStringLiteral("BottomQueueLabel"), QStringLiteral("Queue: 0"), 86);
    // Phase 5: this telemetry item is the primary trigger for the activity drawer (eventFilter).
    bottomQueueLabel_->setCursor(Qt::PointingHandCursor);
    bottomQueueLabel_->setToolTip(QStringLiteral("Open the activity drawer (queue · details · logs)"));
    bottomQueueLabel_->installEventFilter(this);
    bottomVramLabel_ = makeTelemetryLabel(QStringLiteral("BottomVramLabel"), QStringLiteral("VRAM: checking"), 150);
    bottomModelLabel_ = makeTelemetryLabel(QStringLiteral("BottomModelLabel"), QStringLiteral("Model: none"), 210);
    bottomLoraLabel_ = makeTelemetryLabel(QStringLiteral("BottomLoraLabel"), QStringLiteral("LoRA: none"), 126);
    bottomStateLabel_ = makeTelemetryLabel(QStringLiteral("BottomStateLabel"), QStringLiteral("Idle"), 96);

    bottomProgressBar_ = new QProgressBar(container);
    bottomProgressBar_->setObjectName(QStringLiteral("BottomProgressBar"));
    bottomProgressBar_->setRange(0, 100);
    bottomProgressBar_->setValue(0);
    bottomProgressBar_->setTextVisible(true);
    bottomProgressBar_->setFormat(QStringLiteral(""));
    bottomProgressBar_->setFixedSize(164, 18);
    bottomProgressBar_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    bottomProgressBar_->setStyleSheet(QStringLiteral(
        "QProgressBar#BottomProgressBar {"
        " border: 1px solid rgba(90,150,220,120);"
        " border-radius: 8px;"
        " background: rgba(6,12,24,190);"
        " color: rgba(220,235,255,235);"
        " font-size: 9px;"
        " text-align: center;"
        "}"
        "QProgressBar#BottomProgressBar::chunk {"
        " border-radius: 7px;"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        " stop:0 rgba(67,137,220,230),"
        " stop:1 rgba(142,92,210,230));"
        "}"
    ));

    layout->addWidget(bottomReadyLabel_);
    addSeparator();
    layout->addWidget(bottomPageLabel_);
    layout->addStretch(1);
    layout->addWidget(bottomRuntimeLabel_);
    addSeparator();
    layout->addWidget(bottomQueueLabel_);
    addSeparator();
    layout->addWidget(bottomVramLabel_);
    addSeparator();
    layout->addWidget(bottomModelLabel_);
    addSeparator();
    layout->addWidget(bottomLoraLabel_);
    addSeparator();
    layout->addWidget(bottomStateLabel_);
    addSeparator();
    layout->addWidget(bottomProgressBar_);

    bar->addWidget(container, 1);

    startVramTelemetryPolling();
    syncBottomTelemetry();
}







ImageGenerationPage *MainWindow::generationPageForMode(const QString &modeId) const
{
    if (modeId == QStringLiteral("t2i"))
        return t2iPage_;
    if (modeId == QStringLiteral("i2i"))
        return i2iPage_;
    if (modeId == QStringLiteral("t2v"))
        return t2vPage_;
    if (modeId == QStringLiteral("i2v"))
        return i2vPage_;
    return nullptr;
}

// Pure predicate: is this a mode that a lazily-built ImageGenerationPage hosts?
// Independent of whether that page has been constructed yet -- use this (not
// generationPageForMode() != nullptr) wherever a caller needs to know a mode is a
// valid generation target WITHOUT forcing its construction (e.g. a draft-routing
// existence check). See the header note on lazy page construction.
bool MainWindow::isGenerationMode(const QString &modeId) const
{
    return modeId == QStringLiteral("t2i") || modeId == QStringLiteral("i2i")
        || modeId == QStringLiteral("t2v") || modeId == QStringLiteral("i2v");
}

// The SINGLE construction path for the four deferred ImageGenerationPages. Both the
// on-demand route (switchToMode / the cross-page sites) and the idle pre-warm route
// call this, so a page built either way is identical by construction. Idempotent:
// if the target slot is already populated it is a no-op, so a user navigating to a
// page the pre-warm has not yet reached builds it once, and the pre-warm then skips
// it. Replicates exactly the eager wiring buildPages() used to do inline: construct
// -> add to the page stack -> register in modePages_ -> connectGenerationPage (which
// wires the page's signals and seeds updateDisclosure() from the current mode).
void MainWindow::ensureGenerationPageBuilt(const QString &modeId)
{
    ImageGenerationPage **slot = nullptr;
    ImageGenerationPage::Mode mode = ImageGenerationPage::Mode::TextToImage;
    if (modeId == QStringLiteral("t2i")) { slot = &t2iPage_; mode = ImageGenerationPage::Mode::TextToImage; }
    else if (modeId == QStringLiteral("i2i")) { slot = &i2iPage_; mode = ImageGenerationPage::Mode::ImageToImage; }
    else if (modeId == QStringLiteral("t2v")) { slot = &t2vPage_; mode = ImageGenerationPage::Mode::TextToVideo; }
    else if (modeId == QStringLiteral("i2v")) { slot = &i2vPage_; mode = ImageGenerationPage::Mode::ImageToVideo; }
    else return; // not a deferred generation page -- nothing to build

    if (*slot)
        return; // already built (idempotent -- single construction path, no drift)

    *slot = new ImageGenerationPage(mode, this);
    pageStack_->addWidget(*slot);
    modePages_.insert(modeId, *slot);
    connectGenerationPage(*slot, modeId);
}

// Idle pre-warm: after the window is up, construct the deferred generation pages
// one per event-loop turn so each ~1.5s build sits off the critical startup path
// and the UI stays responsive between builds. QWidget construction is GUI-thread
// only (it cannot be moved to a worker thread), so this is main-thread staggering,
// not background work. Kicked off from showEvent() (see prewarmStarted_), so the
// first build lands only after show() and the first paint.
void MainWindow::startIdlePagePrewarm()
{
    prewarmQueue_ = QStringList{QStringLiteral("t2i"), QStringLiteral("i2i"),
                                QStringLiteral("t2v"), QStringLiteral("i2v")};
    // Delay the FIRST build so the window paints and becomes interactive before any
    // heavy construction runs -- otherwise the first build fires on the very first
    // event-loop turn and briefly freezes the just-shown window. Subsequent builds
    // are one-per-turn (singleShot 0), off the critical path.
    scheduleNextPagePrewarm(250);
}

void MainWindow::scheduleNextPagePrewarm(int delayMs)
{
    if (prewarmQueue_.isEmpty())
        return;
    // Each tick yields to the event loop between builds (paint/input are serviced),
    // so warmup never blocks the window for more than one page at a time.
    QTimer::singleShot(delayMs, this, [this]() {
        if (prewarmQueue_.isEmpty())
            return;
        const QString modeId = prewarmQueue_.takeFirst();
        ensureGenerationPageBuilt(modeId); // no-op if the user already navigated there
        scheduleNextPagePrewarm(0);
    });
}

void MainWindow::showEvent(QShowEvent *event)
{
    QMainWindow::showEvent(event);
    // Kick off idle pre-warm exactly once, after the window is first shown. Anchoring
    // here (not in buildPages) means the first-build delay is relative to the window
    // appearing, so the freshly-painted window is interactive before any heavy build.
    if (!prewarmStarted_)
    {
        prewarmStarted_ = true;
        startIdlePagePrewarm();
    }
}

void MainWindow::handleHomeLaunchRequest(const QString &modeId,
                                         const QString &title,
                                         const QString &subtitle,
                                         const QString &sourceLabel)
{
    QString resolvedModeId = modeId;
    // Build the target generation page on demand so applyHomeStarter lands on a live
    // page (it runs BEFORE switchToMode). isGenerationMode keeps this correct for a
    // not-yet-built page, where modePages_.contains() would otherwise be false.
    if (isGenerationMode(resolvedModeId))
        ensureGenerationPageBuilt(resolvedModeId);
    if (!modePages_.contains(resolvedModeId))
        resolvedModeId = QStringLiteral("home");

    if (ImageGenerationPage *page = generationPageForMode(resolvedModeId))
        page->applyHomeStarter(title, subtitle, sourceLabel);

    switchToMode(resolvedModeId);
}

void MainWindow::openWorkflowDraft(const QJsonObject &draft)
{
    // Route by a PURE predicate (isGenerationMode), not generationPageForMode()!=nullptr:
    // with lazy construction an unbuilt-but-valid target reads as null and would be
    // wrongly rejected. Build the resolved page on demand before accessing it.
    const QString modeId = spellvision::workflows::WorkflowLaunchController::resolveDraftModeId(
        draft,
        [this](const QString &candidate) { return isGenerationMode(candidate); });

    ensureGenerationPageBuilt(modeId);
    ImageGenerationPage *page = generationPageForMode(modeId);
    if (!page)
    {
        QMessageBox::warning(this,
                             QStringLiteral("Workflow Draft"),
                             QStringLiteral("This workflow cannot be opened as an editable draft in the current build."));
        return;
    }

    page->applyWorkflowDraft(draft);
    switchToMode(modeId);

    appendLogLine(spellvision::workflows::WorkflowLaunchController::draftOpenedLogLine(draft, modeId));

    if (!page->workflowDraftCanSubmit())
        appendLogLine(spellvision::workflows::WorkflowLaunchController::draftRequiresReviewLogLine(modeId));
}

void MainWindow::connectGenerationPage(ImageGenerationPage *page, const QString &modeId)
{
    if (!page)
        return;

    connect(page, &ImageGenerationPage::openModelsRequested, this, [this]()
            { switchToMode(QStringLiteral("models")); });
    connect(page, &ImageGenerationPage::openWorkflowsRequested, this, [this]()
            { switchToMode(QStringLiteral("workflows")); });
    connect(page, &ImageGenerationPage::prepForI2IRequested, this, [this](const QString &imagePath) {
        // Send-to-I2I from another page: the I2I page may not be built yet under lazy
        // construction. Build it on demand so the image lands instead of silently
        // dropping (the old `if (!i2iPage_) return;` guard would have swallowed it).
        ensureGenerationPageBuilt(QStringLiteral("i2i"));
        if (!i2iPage_)
            return;

        i2iPage_->useImageAsInput(imagePath);
        switchToMode(QStringLiteral("i2i"));
        appendLogLine(QStringLiteral("Prepared latest image for I2I: %1").arg(imagePath));
    });

    connect(page, &ImageGenerationPage::queueRequested, this, [this, page, modeId](const QJsonObject &payload)
            { submitGenerationRequest(page, modeId, payload, true); });

    connect(page, &ImageGenerationPage::generateRequested, this, [this, page, modeId](const QJsonObject &payload)
            { submitGenerationRequest(page, modeId, payload, false); });

    // Phase 7 step 1 (plumbing): feed the app-global Simple/Advanced disclosure mode to the page,
    // and push the current state immediately. Pages are built eagerly here, BEFORE the Phase 6
    // restore (setDisclosureMode) runs -- so this push seeds the default and the restore's
    // disclosureModeChanged emit then delivers the persisted mode. Either way every page (visited
    // or not) holds the correct mode from startup.
    connect(this, &MainWindow::disclosureModeChanged, page, &ImageGenerationPage::updateDisclosure);
    page->updateDisclosure(isAdvancedMode());
}

// --- CHAIN STUDIO PASS 8C.1: chain submission variant ---
// Mirrors submitGenerationRequest below, MINUS the page-specific
// bits: no page parameter, no page->setBusy calls, no enqueueOnly
// flag (chain stages always submit as "Submitting" rather than
// "Queued"-only). The chain page's UX is driven by engine signals,
// not setBusy, so the page does not need to be told to spin.
//
// Returns true if the worker accepted (response.ok == true and a
// queue_item_id is present); false on any validation rejection or
// transport error. ChainEngine interprets false as a submission
// rejection and rolls back the pending variation.
bool MainWindow::submitChainGenerationRequest(const QString &modeId,
                                              const QJsonObject &payload,
                                              const QString &queueItemId)
{
    const QString taskCommand = workerTaskCommandForMode(modeId);
    if (taskCommand.isEmpty())
    {
        appendLogLine(QStringLiteral("Chain submission rejected: unknown mode %1.").arg(modeId));
        return false;
    }

    const bool videoMode = taskCommand == QStringLiteral("t2v") || taskCommand == QStringLiteral("i2v");
    const bool hasWorkflowBinding = spellvision::workers::WorkerSubmissionPolicy::hasWorkflowBinding(payload);
    const bool hasNativeVideoStack = videoMode && spellvision::workers::WorkerSubmissionPolicy::hasNativeVideoStackPayload(payload);
    const QString modelValue = spellvision::workers::WorkerSubmissionPolicy::resolvedModelValueFromPayload(payload);

    if (modelValue.isEmpty() && !(videoMode && (hasWorkflowBinding || hasNativeVideoStack)))
    {
        const QString message = spellvision::workers::WorkerSubmissionPolicy::missingModelMessage(modeId, videoMode);
        appendLogLine(QStringLiteral("Chain submission rejected: %1").arg(message));
        return false;
    }

    if ((taskCommand == QStringLiteral("i2i") || taskCommand == QStringLiteral("i2v")) &&
        payload.value(QStringLiteral("input_image")).toString().trimmed().isEmpty())
    {
        appendLogLine(QStringLiteral("Chain %1 submission rejected: missing input image.").arg(modeId.toUpper()));
        return false;
    }

    // Stamp the engine-provided queue_item_id into the payload so
    // buildWorkerGenerationRequest's forward picks it up. The
    // payload is const here; we work with a mutable copy.
    QJsonObject payloadWithId = payload;
    if (!queueItemId.trimmed().isEmpty())
        payloadWithId.insert(QStringLiteral("queue_item_id"), queueItemId);

    appendLogLine(spellvision::workers::WorkerSubmissionPolicy::acceptedRequestLogLine(
        modeId,
        videoMode,
        hasWorkflowBinding,
        modelValue));

    // Same telemetry property latches submitGenerationRequest uses
    // (Pass 28R/28S/28T). Without these the bottom telemetry bar
    // would not switch to Busy until the next queue poll.
    setProperty("svTelemetryBusy", true);
    setProperty("svTelemetryBusyMode", modeId);
    setProperty("svTelemetryBusyState", QStringLiteral("Submitting"));
    setProperty("svTelemetryPhaseRank", 1);
    setProperty("svTelemetryProgressTarget", 3);
    setProperty("svTelemetryJobActive", true);
    setProperty("svTelemetryCompletionPulse", false);

    const int completedRowsAtSubmit =
        (queueTableView_ && queueTableView_->model()) ? queueTableView_->model()->rowCount() : 0;
    setProperty("svTelemetryCompletedRowsAtSubmit", completedRowsAtSubmit);

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setValue(0);
        bottomProgressBar_->setFormat(QStringLiteral("%p%"));
    }

    syncBottomTelemetry();

    QString stderrText;
    bool startedOk = false;

    const QJsonObject request = buildWorkerGenerationRequest(modeId, payloadWithId);
    const QJsonObject response = sendWorkerRequest(request, &stderrText, &startedOk);

    if (!stderrText.trimmed().isEmpty())
        appendLogLine(stderrText.trimmed());

    if (!startedOk)
    {
        appendLogLine(QStringLiteral("Chain submission failed: could not start worker_client.py for %1.").arg(modeId.toUpper()));
        return false;
    }

    if (response.isEmpty())
    {
        appendLogLine(QStringLiteral("Chain submission failed: worker returned no JSON payload for %1.").arg(modeId.toUpper()));
        return false;
    }

    const bool ok = response.value(QStringLiteral("ok")).toBool(false);
    const QString errorText = response.value(QStringLiteral("error")).toString().trimmed();
    if (!ok)
    {
        if (!errorText.isEmpty())
            appendLogLine(QStringLiteral("Chain %1 request failed: %2").arg(modeId.toUpper(), errorText));
        else
            appendLogLine(QStringLiteral("Chain %1 request failed (no error text).").arg(modeId.toUpper()));
        return false;
    }

    applyWorkerQueueResponse(response);
    syncBottomTelemetry();

    const QString respQueueId = response.value(QStringLiteral("queue_item_id")).toString().trimmed();
    const QString respJobId = response.value(QStringLiteral("job_id")).toString().trimmed();
    appendLogLine(QStringLiteral("Chain %1 sent to worker queue%2%3.")
                      .arg(modeId.toUpper(),
                           respQueueId.isEmpty() ? QString() : QStringLiteral(" \u2022 queue=%1").arg(respQueueId),
                           respJobId.isEmpty() ? QString() : QStringLiteral(" \u2022 job=%1").arg(respJobId)));

    if (queueDock_ && !queueDock_->isVisible())
    {
        queueDock_->show();
        updateDockChrome();
    }

    return true;
}

void MainWindow::submitGenerationRequest(ImageGenerationPage *page, const QString &modeId, const QJsonObject &payload, bool enqueueOnly)
{
    if (!page)
        return;

    const QString taskCommand = workerTaskCommandForMode(modeId);
    if (taskCommand.isEmpty())
    {
        const QString message = QStringLiteral("%1 backend is not wired to the Python worker yet. Start with T2I or I2I first.")
                                    .arg(pageContextForMode(modeId));
        appendLogLine(message);
        page->setBusy(false, message);
        return;
    }

    const bool videoMode = taskCommand == QStringLiteral("t2v") || taskCommand == QStringLiteral("i2v");
    const QString clientBlockReason = payload.value(QStringLiteral("client_readiness_block")).toString().trimmed();
    const QString submitOrigin = payload.value(QStringLiteral("submit_origin")).toString().trimmed();
    if (!clientBlockReason.isEmpty())
    {
        appendLogLine(QStringLiteral("%1 submit reached MainWindow%2 with page readiness note: %3")
                          .arg(modeId.toUpper(),
                               submitOrigin.isEmpty() ? QString() : QStringLiteral(" from %1").arg(submitOrigin),
                               clientBlockReason));
    }

    const bool hasWorkflowBinding = spellvision::workers::WorkerSubmissionPolicy::hasWorkflowBinding(payload);
    const bool hasNativeVideoStack = videoMode && spellvision::workers::WorkerSubmissionPolicy::hasNativeVideoStackPayload(payload);
    const QString modelValue = spellvision::workers::WorkerSubmissionPolicy::resolvedModelValueFromPayload(payload);

    if (videoMode)
    {
        appendLogLine(spellvision::workers::WorkerSubmissionPolicy::videoSubmitLogLine(
            modeId,
            payload,
            modelValue,
            hasNativeVideoStack,
            hasWorkflowBinding));
    }

    if (modelValue.isEmpty() && !(videoMode && (hasWorkflowBinding || hasNativeVideoStack)))
    {
        const QString message = spellvision::workers::WorkerSubmissionPolicy::missingModelMessage(modeId, videoMode);
        appendLogLine(message);
        page->setBusy(false, message);
        return;
    }

    if ((taskCommand == QStringLiteral("i2i") || taskCommand == QStringLiteral("i2v")) &&
        payload.value(QStringLiteral("input_image")).toString().trimmed().isEmpty())
    {
        appendLogLine(QStringLiteral("%1 request blocked: choose an input image first.").arg(modeId.toUpper()));
        return;
    }

    appendLogLine(spellvision::workers::WorkerSubmissionPolicy::acceptedRequestLogLine(
        modeId,
        videoMode,
        hasWorkflowBinding,
        modelValue));

    // Pass 28R explicit busy latch:
    // Telemetry should say Busy immediately after user submission, even before
    // queue polling publishes an active row.
    setProperty("svTelemetryBusy", true);
    setProperty("svTelemetryBusyMode", modeId);
    setProperty("svTelemetryBusyState", enqueueOnly ? QStringLiteral("Queued") : QStringLiteral("Submitting"));

    // Pass 28S:
    // Start every new job from a clean telemetry state. From here, state can
    // advance Submitting -> Preparing -> Running, but it must not regress if a
    // queue snapshot temporarily omits the active row.
    setProperty("svTelemetryPhaseRank", 1);
    setProperty("svTelemetryProgressTarget", 3);
    setProperty("svTelemetryJobActive", true);
    setProperty("svTelemetryCompletionPulse", false);

    // Pass 28T:
    // The image queue tray is a completed-jobs ledger. Capture the visible
    // completed-row count at submission so telemetry can detect the new output
    // even if the worker's active queue row disappears or goes stale.
    const int completedRowsAtSubmit =
        (queueTableView_ && queueTableView_->model()) ? queueTableView_->model()->rowCount() : 0;
    setProperty("svTelemetryCompletedRowsAtSubmit", completedRowsAtSubmit);

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setValue(0);
        bottomProgressBar_->setFormat(QStringLiteral("%p%"));
    }

    syncBottomTelemetry();

    page->setBusy(true, enqueueOnly ? QStringLiteral("Queueing request…") : QStringLiteral("Submitting generation…"));

    QString stderrText;
    bool startedOk = false;

    const QJsonObject request = buildWorkerGenerationRequest(modeId, payload);
    const QJsonObject response = sendWorkerRequest(request, &stderrText, &startedOk);

    if (!stderrText.trimmed().isEmpty())
        appendLogLine(stderrText.trimmed());

    page->setBusy(false, QString());

    if (!startedOk)
    {
        appendLogLine(QStringLiteral("Failed to start worker_client.py for %1.").arg(modeId.toUpper()));
        return;
    }

    if (response.isEmpty())
    {
        appendLogLine(QStringLiteral("Worker returned no JSON payload for %1.").arg(modeId.toUpper()));
        return;
    }

    const bool ok = response.value(QStringLiteral("ok")).toBool(false);
    const QString errorText = response.value(QStringLiteral("error")).toString().trimmed();
    if (!ok && !errorText.isEmpty())
    {
        appendLogLine(QStringLiteral("%1 request failed: %2").arg(modeId.toUpper(), errorText));
        return;
    }

    applyWorkerQueueResponse(response);
    syncBottomTelemetry();

    const QString queueId = response.value(QStringLiteral("queue_item_id")).toString().trimmed();
    const QString jobId = response.value(QStringLiteral("job_id")).toString().trimmed();
    appendLogLine(QStringLiteral("%1 sent to worker queue%2%3.")
                      .arg(modeId.toUpper(),
                           queueId.isEmpty() ? QString() : QStringLiteral(" • queue=%1").arg(queueId),
                           jobId.isEmpty() ? QString() : QStringLiteral(" • job=%1").arg(jobId)));

    // Pass 28H:
    // Do not auto-expand the bottom tray after enqueue. The compact header can
    // still show Live/Idle state, and users can expand Queue/Details manually.
    if (queueDock_ && !queueDock_->isVisible())
    {
        queueDock_->show();
        updateDockChrome();
    }
}

QJsonObject MainWindow::sendWorkerRequest(const QJsonObject &request, QString *stderrText, bool *startedOk, int timeoutMs) const
{
    if (stderrText)
        stderrText->clear();
    if (startedOk)
        *startedOk = false;

    const QString projectRoot = resolveProjectRoot();
    const QString pythonExecutable = resolvePythonExecutable();
    const QString workerClient = QDir(projectRoot).filePath(QStringLiteral("python/worker_client.py"));

    spellvision::workers::WorkerProcessController controller;
    spellvision::workers::WorkerProcessController::CommandRequest command;
    command.program = pythonExecutable;
    command.arguments = {workerClient};
    command.workingDirectory = projectRoot;
    command.environment = QProcessEnvironment::systemEnvironment();
    command.payload = request;
    command.closeWriteChannelAfterPayload = true;

    QJsonObject lastJsonMessage;
    QStringList stderrLines;
    QStringList processErrors;
    bool finished = false;
    bool timedOut = false;
    int exitCode = -1;
    QProcess::ExitStatus exitStatus = QProcess::NormalExit;

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    connect(&controller, &spellvision::workers::WorkerProcessController::stderrLineReceived,
            &loop, [&stderrLines](const QString &line) {
                if (!line.trimmed().isEmpty())
                    stderrLines << line.trimmed();
            });

    connect(&controller, &spellvision::workers::WorkerProcessController::jsonMessageReceived,
            &loop, [&lastJsonMessage](const QJsonObject &message) {
                if (!message.isEmpty())
                    lastJsonMessage = message;
            });

    connect(&controller, &spellvision::workers::WorkerProcessController::processError,
            &loop, [&processErrors](const QString &message) {
                if (!message.trimmed().isEmpty())
                    processErrors << message.trimmed();
            });

    connect(&controller,
            &spellvision::workers::WorkerProcessController::processFinished,
            &loop,
            [&loop, &finished, &exitCode, &exitStatus](int code, QProcess::ExitStatus status) {
                finished = true;
                exitCode = code;
                exitStatus = status;
                loop.quit();
            });

    connect(&timeoutTimer, &QTimer::timeout, &loop, [&controller, &loop, &timedOut, &processErrors]() {
        timedOut = true;
        processErrors << QStringLiteral("Worker process timed out while waiting for a response.");
        controller.kill();
        loop.quit();
    });

    const bool started = controller.start(command);
    if (startedOk)
        *startedOk = started;

    if (!started)
    {
        if (stderrText)
            *stderrText = processErrors.join(QChar('\n'));
        return {};
    }

    if (controller.isRunning())
    {
        timeoutTimer.start(timeoutMs > 0 ? timeoutMs : 120000);
        loop.exec();
        timeoutTimer.stop();
    }

    if (stderrText)
    {
        QStringList diagnostics = stderrLines;
        diagnostics.append(processErrors);
        diagnostics.removeAll(QString());
        *stderrText = diagnostics.join(QChar('\n'));
    }

    if (timedOut)
        return lastJsonMessage;

    if (finished && exitStatus != QProcess::NormalExit)
        return lastJsonMessage;

    if (finished && exitCode != 0 && lastJsonMessage.isEmpty())
        return {};

    return lastJsonMessage;
}

namespace
{
#ifdef Q_OS_WIN
bool processIsAlive(qint64 pid)
{
    if (pid <= 0)
        return false;
    HANDLE h = OpenProcess(SYNCHRONIZE, FALSE, static_cast<DWORD>(pid));
    if (!h)
        return false;
    const DWORD wait = WaitForSingleObject(h, 0);
    CloseHandle(h);
    return wait == WAIT_TIMEOUT;  // still running (not signalled)
}
#endif
} // namespace

void MainWindow::tearDownComfyOnExit()
{
#ifdef Q_OS_WIN
    // Read the dev session file start_comfy.ps1 writes: it carries adopted_existing and the
    // ComfyUI PID. (App-managed runtimes are tracked separately by comfy_runtime_manager;
    // the stop_comfy_runtime command below reaches those.)
    bool adopted = false;
    qint64 comfyPid = 0;
    const QString sessionPath = QDir(resolveProjectRoot()).filePath(QStringLiteral("build/.comfy_runtime.session.json"));
    QFile sessionFile(sessionPath);
    if (sessionFile.exists() && sessionFile.open(QIODevice::ReadOnly))
    {
        QByteArray data = sessionFile.readAll();
        sessionFile.close();
        // PowerShell writes this file with a UTF-8 BOM; QJsonDocument::fromJson does not strip
        // it and would fail to parse -- losing both adopted_existing (we'd wrongly kill an
        // adopted runtime) and the PID (we'd fall to the slow worker path). Strip the BOM.
        if (data.startsWith("\xEF\xBB\xBF"))
            data.remove(0, 3);
        const QJsonObject obj = QJsonDocument::fromJson(data).object();
        adopted = obj.value(QStringLiteral("adopted_existing")).toBool(false);
        comfyPid = static_cast<qint64>(obj.value(QStringLiteral("pid")).toDouble(0));
    }

    // Least-surprise: if ComfyUI was already running before we launched (the user started it),
    // leave it alone.
    if (adopted)
        return;

    // Primary: if the tracked ComfyUI PID is live, force-kill it now (near-instant). This covers
    // the common cases -- dev/script-started, external-to-the-manager, app-restarted, or a
    // PID-mismatch -- and is what actually frees :8188 + GPU. taskkill /T kills the process tree;
    // the app is exiting, so a forceful kill is appropriate.
    bool killedTracked = false;
    if (comfyPid > 0 && processIsAlive(comfyPid))
    {
        QProcess::execute(QStringLiteral("taskkill"),
                          {QStringLiteral("/PID"), QString::number(comfyPid),
                           QStringLiteral("/T"), QStringLiteral("/F")});
        killedTracked = true;
    }

    // Fallback: only when taskkill couldn't resolve it -- the session PID wasn't live (e.g. an
    // app-managed runtime that comfy_runtime_manager tracks separately and started itself). Ask
    // the worker to stop its managed runtime gracefully. Bounded (4s) so a hung worker can't
    // freeze the app's exit. Skipped on the common dev/external close, keeping exit near-instant.
    if (!killedTracked)
    {
        QJsonObject stopRequest;
        stopRequest.insert(QStringLiteral("command"), QStringLiteral("stop_comfy_runtime"));
        stopRequest.insert(QStringLiteral("graceful_timeout_sec"), 2.0);
        sendWorkerRequest(stopRequest, nullptr, nullptr, 4000);
    }
#endif
}


QString MainWindow::workerTaskCommandForMode(const QString &modeId) const
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

QString MainWindow::resolveProjectRoot() const
{
    const QStringList starts = {QCoreApplication::applicationDirPath(), QDir::currentPath()};
    for (const QString &start : starts)
    {
        QDir dir(start);
        for (int depth = 0; depth < 7; ++depth)
        {
            if (QFileInfo::exists(dir.filePath(QStringLiteral("python/worker_client.py"))))
                return dir.absolutePath();
            if (!dir.cdUp())
                break;
        }
    }
    return QDir::currentPath();
}

QString MainWindow::resolvePythonExecutable() const
{
    const QString virtualEnv = QString::fromLocal8Bit(qgetenv("VIRTUAL_ENV")).trimmed();
    if (!virtualEnv.isEmpty())
    {
        const QString fromEnv = QDir(virtualEnv).filePath(QStringLiteral("Scripts/python.exe"));
        if (QFileInfo::exists(fromEnv))
            return fromEnv;
    }

    const QString projectVenv = QDir(resolveProjectRoot()).filePath(QStringLiteral(".venv/Scripts/python.exe"));
    if (QFileInfo::exists(projectVenv))
        return projectVenv;

    return QStringLiteral("python");
}

QJsonObject MainWindow::buildWorkerGenerationRequest(const QString &modeId, const QJsonObject &payload) const
{
    const QString taskCommand = workerTaskCommandForMode(modeId);

    QString outputFolder = payload.value(QStringLiteral("output_folder")).toString().trimmed();
    if (outputFolder.isEmpty())
        outputFolder = QDir(resolveProjectRoot()).filePath(QStringLiteral("output"));

    QDir().mkpath(outputFolder);

    const QString basePrefix = payload.value(QStringLiteral("output_prefix")).toString().trimmed().isEmpty()
                                   ? QStringLiteral("spellvision_render")
                                   : payload.value(QStringLiteral("output_prefix")).toString().trimmed();
    const QString stamp = QDateTime::currentDateTimeUtc().toString(QStringLiteral("yyyyMMdd_HHmmss_zzz"));
    const QString baseName = QStringLiteral("%1_%2_%3").arg(basePrefix, taskCommand, stamp);
    const bool videoOutput = taskCommand == QStringLiteral("t2v") || taskCommand == QStringLiteral("i2v");
    const QString outputPath = QDir(outputFolder).filePath(baseName + (videoOutput ? QStringLiteral(".mp4") : QStringLiteral(".png")));
    const QString metadataPath = QDir(outputFolder).filePath(baseName + QStringLiteral(".json"));

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("enqueue"));
    request.insert(QStringLiteral("task_command"), taskCommand);
    request.insert(QStringLiteral("task_type"), taskCommand);
    request.insert(QStringLiteral("submit_origin"), payload.value(QStringLiteral("submit_origin")).toString());
    request.insert(QStringLiteral("client_readiness_block"), payload.value(QStringLiteral("client_readiness_block")).toString());
    request.insert(QStringLiteral("prompt"), payload.value(QStringLiteral("prompt")).toString());
    request.insert(QStringLiteral("negative_prompt"), payload.value(QStringLiteral("negative_prompt")).toString());
    const QString resolvedModelValue = spellvision::workers::WorkerSubmissionPolicy::resolvedModelValueFromPayload(payload);
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

    return request;
}

QJsonObject MainWindow::buildWorkflowLaunchRequest(const QJsonObject &profile) const
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

    const QString projectRoot = resolveProjectRoot();
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

    QString comfyRoot = QString::fromLocal8Bit(qgetenv("SPELLVISION_COMFY")).trimmed();
    if (comfyRoot.isEmpty())
    {
        const QString preferred = QStringLiteral("D:/AI_ASSETS/comfy_runtime/ComfyUI");
        comfyRoot = QDir(preferred).exists()
                        ? preferred
                        : QDir(projectRoot).filePath(QStringLiteral("runtime/comfy/ComfyUI"));
    }

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

    return request;
}

void MainWindow::launchWorkflowProfile(const QJsonObject &profile)
{
    const QString profileName = profile.value(QStringLiteral("profile_name")).toString().trimmed().isEmpty()
                                    ? profile.value(QStringLiteral("name")).toString().trimmed()
                                    : profile.value(QStringLiteral("profile_name")).toString().trimmed();

    const QString profilePath = profile.value(QStringLiteral("profile_path")).toString().trimmed();
    const QString workflowPath = profile.value(QStringLiteral("workflow_path")).toString().trimmed().isEmpty()
                                     ? profile.value(QStringLiteral("workflow_source")).toString().trimmed()
                                     : profile.value(QStringLiteral("workflow_path")).toString().trimmed();

    if (profilePath.isEmpty() && workflowPath.isEmpty())
    {
        QMessageBox::warning(
            this,
            QStringLiteral("Workflow Launch"),
            QStringLiteral("The selected workflow does not have a usable profile path or workflow path."));
        return;
    }

    const int missingCustomNodeCount = profile.value(QStringLiteral("metadata")).toObject().value(QStringLiteral("missing_custom_nodes")).toArray().size();

    QString stderrText;
    bool startedOk = false;
    const QJsonObject request = buildWorkflowLaunchRequest(profile);
    const QJsonObject response = sendWorkerRequest(request, &stderrText, &startedOk);

    if (!stderrText.trimmed().isEmpty())
        appendLogLine(stderrText.trimmed());

    if (!startedOk)
    {
        QMessageBox::warning(
            this,
            QStringLiteral("Workflow Launch"),
            QStringLiteral("Failed to start worker_client.py for workflow launch."));
        return;
    }

    if (response.isEmpty())
    {
        QMessageBox::warning(
            this,
            QStringLiteral("Workflow Launch"),
            QStringLiteral("Worker returned no JSON payload for workflow launch."));
        return;
    }

    const bool ok = response.value(QStringLiteral("ok")).toBool(false);
    const QString errorText = response.value(QStringLiteral("error")).toString().trimmed();
    if (!ok && !errorText.isEmpty())
    {
        QMessageBox::warning(
            this,
            QStringLiteral("Workflow Launch"),
            QStringLiteral("Workflow launch failed: %1").arg(errorText));
        return;
    }

    applyWorkerQueueResponse(response);
    pollWorkerQueueStatus();

    const QString queueId = response.value(QStringLiteral("queue_item_id")).toString().trimmed();
    const QString jobId = response.value(QStringLiteral("job_id")).toString().trimmed();

    appendLogLine(QStringLiteral("Workflow queued: %1%2%3%4")
                      .arg(profileName.isEmpty() ? QStringLiteral("Imported Workflow") : profileName,
                           queueId.isEmpty() ? QString() : QStringLiteral(" • queue=%1").arg(queueId),
                           jobId.isEmpty() ? QString() : QStringLiteral(" • job=%1").arg(jobId),
                           missingCustomNodeCount > 0 ? QStringLiteral(" • review dependency warnings") : QString()));

    if (queueDock_)
    {
        queueDock_->show();
        queueDock_->raise();
    }
}

void MainWindow::applyWorkerQueueResponse(const QJsonObject &response)
{
    if (workerQueueController_)
        workerQueueController_->applyWorkerQueueResponse(response);
}


void MainWindow::pollWorkerQueueStatus()
{
    if (workerQueueController_)
        workerQueueController_->pollOnce();
}






void MainWindow::syncGenerationPreviewsFromQueue()
{
    if (!queueManager_)
        return;

    if (!isGenerationWorkspaceMode())
        return;

    ImageGenerationPage *page = generationPageForMode(currentModeId_);
    if (!page)
        return;

    const QVector<QueueItem> &items = queueManager_->items();

    // Pass 28D:
    // Queue polling is a discovery/fallback path only. It must not continuously
    // mutate the visible generation page, because repeated setBusy()/preview
    // writes can cause splitter/layout breathing while the user is working.
    //
    // Direct worker messages own active progress and normal terminal busy
    // recovery. Queue sync only binds a newly discovered completed output once.
    const QueueItem *newestCompleted = nullptr;
    qint64 newestSortKey = (std::numeric_limits<qint64>::min)();

    for (const QueueItem &item : items)
    {
        const QString itemModeId = generationModeIdForQueueItem(item);
        if (itemModeId != currentModeId_)
            continue;

        if (queueItemIsActiveForGeneration(item))
            continue;

        if (!item.completed || item.outputPath.trimmed().isEmpty())
            continue;

        const QString normalizedPath = normalizedPreviewPathKey(item.outputPath);
        if (normalizedPath.isEmpty())
            continue;

        const QFileInfo outputInfo(item.outputPath.trimmed());
        if (!outputInfo.exists())
            continue;

        const qint64 sortKey = queueItemPreviewSortKey(item);
        if (!newestCompleted || sortKey > newestSortKey ||
            (sortKey == newestSortKey && item.orderIndex > newestCompleted->orderIndex))
        {
            newestCompleted = &item;
            newestSortKey = sortKey;
        }
    }

    if (!newestCompleted)
        return;

    const QString normalizedPath = normalizedPreviewPathKey(newestCompleted->outputPath);
    const QString jobKey = newestCompleted->workerJobId.trimmed().isEmpty()
        ? newestCompleted->id.trimmed()
        : newestCompleted->workerJobId.trimmed();

    const QString stableKey = QStringLiteral("%1|%2|%3|%4")
        .arg(currentModeId_,
             normalizedPath,
             jobKey,
             previewFileRevisionKey(newestCompleted->outputPath));

    if (lastSyncedGenerationPreviewByMode_.value(currentModeId_) == stableKey)
        return;

    lastSyncedGenerationPreviewByMode_.insert(currentModeId_, stableKey);

    const QString caption = newestCompleted->statusText.trimmed().isEmpty()
        ? QStringLiteral("Completed output")
        : newestCompleted->statusText.trimmed();

    page->setPreviewImage(newestCompleted->outputPath, caption);

    // One terminal recovery write is acceptable when a genuinely new completed
    // output appears. Repeated queue polls now return above without touching UI.
    page->setBusy(false, QStringLiteral("Ready"));
}





void MainWindow::appendLogLine(const QString &text)
{
    if (!logsView_)
        return;

    const QString timestamp = QTime::currentTime().toString(QStringLiteral("HH:mm:ss"));
    logsView_->append(QStringLiteral("[%1] %2").arg(timestamp, text));
}

void MainWindow::buildQueueOverlay()
{
    const int tight = ThemeManager::instance().spacing(ThemeManager::Spacing::Tight);
    const int hairline = ThemeManager::instance().spacing(ThemeManager::Spacing::Hairline);

    // Frameless slide-up drawer. A free child of centralShell_ (NOT in its layout), geometry set
    // manually in positionQueueOverlay() so it FLOATS over the page area -- the canvas geometry is
    // untouched whether the drawer is open or closed. Hidden by default -> canvas runs full height.
    queueOverlay_ = new QWidget(centralShell_);
    queueOverlay_->setObjectName(QStringLiteral("QueueOverlay"));
    // A plain QWidget over the canvas was transparent (dark-on-dark, content bled through). Fill it
    // with a GUARANTEED opaque surface via autoFillBackground + palette -- more robust than relying
    // on WA_StyledBackground + a stylesheet background (which Qt silently disables/mishandles here).
    // The header QFrame + inner cards keep their own (stylesheet) surfaces on top of this solid base.
    {
        QColor overlayFill = ThemeManager::instance().surface1Color();
        overlayFill.setAlpha(255); // fully opaque -- a solid drawer, not a translucent film
        QPalette overlayPalette = queueOverlay_->palette();
        overlayPalette.setColor(QPalette::Window, overlayFill);
        queueOverlay_->setPalette(overlayPalette);
        queueOverlay_->setAutoFillBackground(true);
    }
    queueOverlay_->hide();
    auto *overlayLayout = new QVBoxLayout(queueOverlay_);
    overlayLayout->setContentsMargins(0, 0, 0, 0);
    overlayLayout->setSpacing(0);

    // Overlay header: title + live/idle state + close. (Replaces the old always-on dock header row.)
    auto *overlayHeader = createDockHeaderFrame(QStringLiteral("QueueOverlayHeader"), queueOverlay_);
    auto *headerLayout = new QHBoxLayout(overlayHeader);
    headerLayout->setContentsMargins(tight, hairline, tight, hairline);
    headerLayout->setSpacing(tight);

    auto *overlayTitle = new QLabel(QStringLiteral("Activity"), overlayHeader);
    overlayTitle->setObjectName(QStringLiteral("QueueOverlayTitle"));
    headerLayout->addWidget(overlayTitle);
    headerLayout->addStretch(1);

    queueDockStateLabel_ = new QLabel(QStringLiteral("Idle"), overlayHeader);
    queueDockStateLabel_->setObjectName(QStringLiteral("DetailsMetaValue"));
    queueDockStateLabel_->setMinimumWidth(34);
    queueDockStateLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    headerLayout->addWidget(queueDockStateLabel_);

    queueOverlayCloseButton_ = new QToolButton(overlayHeader);
    queueOverlayCloseButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    queueOverlayCloseButton_->setText(QStringLiteral("✕"));
    queueOverlayCloseButton_->setCursor(Qt::PointingHandCursor);
    queueOverlayCloseButton_->setToolButtonStyle(Qt::ToolButtonTextOnly);
    queueOverlayCloseButton_->setMinimumHeight(26);
    queueOverlayCloseButton_->setToolTip(QStringLiteral("Close (Esc)"));
    connect(queueOverlayCloseButton_, &QToolButton::clicked, this, [this]()
    {
        queueDockUserExpanded_ = false;
        bottomUtilityUserExpanded_ = false;
        detailsDockPinnedOpen_ = false;
        updateDockChrome();
    });
    headerLayout->addWidget(queueOverlayCloseButton_);
    overlayLayout->addWidget(overlayHeader);

    // Content: queue pane + Details/Logs tabs. Built ONCE here and bound to the existing queue
    // model/controller (queueManager_/queueTableModel_/...), so the drawer shows the real live
    // queue by construction -- no rebuild, no re-wiring.
    queueExpandedContent_ = new QWidget(queueOverlay_);
    auto *expandedLayout = new QHBoxLayout(queueExpandedContent_);
    expandedLayout->setContentsMargins(tight, hairline, tight, tight);
    expandedLayout->setSpacing(tight);

    bottomUtilitySplitter_ = new QSplitter(Qt::Horizontal, queueExpandedContent_);
    bottomUtilitySplitter_->setObjectName(QStringLiteral("BottomUtilitySplitter"));

    auto *queuePane = createQueueWidget();
    queuePane->setParent(bottomUtilitySplitter_);
    bottomUtilitySplitter_->addWidget(queuePane);

    bottomUtilityTabs_ = new QTabWidget(bottomUtilitySplitter_);
    bottomUtilityTabs_->setObjectName(QStringLiteral("BottomUtilityTabs"));
    bottomUtilityTabs_->addTab(createDetailsWidget(), QStringLiteral("Details"));
    bottomUtilityTabs_->addTab(createLogsWidget(), QStringLiteral("Logs"));
    bottomUtilitySplitter_->addWidget(bottomUtilityTabs_);
    bottomUtilitySplitter_->setStretchFactor(0, 4);
    bottomUtilitySplitter_->setStretchFactor(1, 2);

    expandedLayout->addWidget(bottomUtilitySplitter_, 1);
    overlayLayout->addWidget(queueExpandedContent_, 1);

    // Keep the floating drawer positioned when the shell resizes, and let the status-bar Queue
    // item open it (installed on bottomQueueLabel_ in buildBottomTelemetryBar).
    if (centralShell_)
        centralShell_->installEventFilter(this);

    applyQueueDockChrome();
}

void MainWindow::hideNativeDockTitleBar(QDockWidget *dock)
{
    if (!dock)
        return;

    auto *emptyTitleBar = new QWidget(dock);
    emptyTitleBar->setFixedHeight(0);
    dock->setTitleBarWidget(emptyTitleBar);
}

bool MainWindow::hasActiveQueueWork() const
{
    if (!queueManager_)
        return false;

    const QVector<QueueItem> &items = queueManager_->items();
    for (const QueueItem &item : items)
    {
        if (item.state == QueueItemState::Running ||
            item.state == QueueItemState::Queued ||
            item.state == QueueItemState::Preparing)
        {
            return true;
        }
    }

    return false;
}

bool MainWindow::isCompactShellWidth() const
{
    return width() < 1580 || (!isMaximized() && width() < 1720);
}

bool MainWindow::isGenerationWorkspaceMode() const
{
    return currentModeId_ == QStringLiteral("t2i") ||
           currentModeId_ == QStringLiteral("i2i") ||
           currentModeId_ == QStringLiteral("t2v") ||
           currentModeId_ == QStringLiteral("i2v");
}

int MainWindow::preferredBottomUtilityExpandedHeight(bool compact) const
{
    const int windowHeight = qMax(height(), 720);
    int target = isGenerationWorkspaceMode() ? static_cast<int>(windowHeight * 0.40)
                                             : static_cast<int>(windowHeight * 0.30);

    if (bottomUtilityTabs_ && bottomUtilityTabs_->currentIndex() == 0)
        target += 28;

    const int minHeight = compact ? 322 : 316;
    const int maxHeight = compact ? 468 : 520;
    return qBound(minHeight, target, maxHeight);
}

void MainWindow::applyQueueDockChrome()
{
    // Phase 5 choke: every queue/details/logs entry point flows through here (via updateDockChrome).
    // It now drives the floating overlay instead of a bottom dock -- show/position/raise when any
    // expand flag is set, hide otherwise. The canvas never moves; the drawer floats over it.
    if (!queueOverlay_)
        return;

    const bool active = hasActiveQueueWork();
    const bool showExpanded = queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;

    if (queueDockStateLabel_)
        queueDockStateLabel_->setText(active ? QStringLiteral("Live") : QStringLiteral("Idle"));

    if (detailsDockPinnedOpen_ && bottomUtilityTabs_)
        bottomUtilityTabs_->setCurrentIndex(0);

    if (showExpanded)
    {
        if (queueExpandedContent_)
            queueExpandedContent_->setVisible(true);
        positionQueueOverlay();
        queueOverlay_->show();
        queueOverlay_->raise();
    }
    else
    {
        detailsDockPinnedOpen_ = false;
        queueOverlay_->hide();
    }
}

void MainWindow::applyBottomUtilityTrayChrome()
{
    // Phase 5: overlay height/placement is owned by positionQueueOverlay(); this now only keeps the
    // queue|details splitter proportions sensible when the drawer is open.
    if (!queueOverlay_)
        return;

    const bool expanded = queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;
    const bool compact = isCompactShellWidth();

    if (expanded && bottomUtilitySplitter_)
    {
        const int totalWidth = qMax(bottomUtilitySplitter_->width(), width() - 120);
        const int currentTab = bottomUtilityTabs_ ? bottomUtilityTabs_->currentIndex() : 0;
        const QString splitterKey = QStringLiteral("%1|%2|%3|%4")
            .arg(totalWidth)
            .arg(compact ? 1 : 0)
            .arg(currentTab)
            .arg(currentModeId_);

        // Pass 28J: do not reset splitter sizes on every queue progress tick.
        if (bottomUtilitySplitter_->property("svLastQueueSplitterKey").toString() != splitterKey)
        {
            int detailsWidth = compact ? 560 : 680;
            if (currentTab == 0)
                detailsWidth = compact ? 640 : 780;
            if (currentTab == 1)
                detailsWidth = compact ? 520 : 580;
            detailsWidth = qBound(460, detailsWidth, qMax(520, totalWidth / 2));
            const int queueWidth = qMax(500, totalWidth - detailsWidth);
            bottomUtilitySplitter_->setSizes({queueWidth, detailsWidth});
            bottomUtilitySplitter_->setProperty("svLastQueueSplitterKey", splitterKey);
        }
    }
}

void MainWindow::positionQueueOverlay()
{
    // Float the drawer over the bottom of the page area (right of the rail). Geometry only -- the
    // canvas underneath is never resized, so it stays full-height whether the drawer is open or not.
    if (!queueOverlay_ || !centralShell_)
        return;

    const int railWidth = (sideRail_ && sideRail_->isVisible()) ? sideRail_->width() : 0;
    const int shellWidth = centralShell_->width();
    const int shellHeight = centralShell_->height();

    int h = preferredBottomUtilityExpandedHeight(isCompactShellWidth());
    h = qBound(160, h, qMax(160, shellHeight - 32));
    const int w = qMax(0, shellWidth - railWidth);

    queueOverlay_->setGeometry(railWidth, shellHeight - h, w, h);
}

bool MainWindow::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == centralShell_ && event->type() == QEvent::Resize)
    {
        if (queueOverlay_ && queueOverlay_->isVisible())
            positionQueueOverlay();
    }
    else if (watched == bottomQueueLabel_ && event->type() == QEvent::MouseButtonRelease)
    {
        // Status-bar "Queue: N" item is the primary drawer trigger -- click to toggle (open on the
        // Queue tab / close). Flows through the same flag path + updateDockChrome choke.
        const bool isOpen = queueOverlay_ && queueOverlay_->isVisible();
        if (isOpen)
        {
            queueDockUserExpanded_ = false;
            bottomUtilityUserExpanded_ = false;
            detailsDockPinnedOpen_ = false;
        }
        else
        {
            queueDockUserExpanded_ = true;
            bottomUtilityUserExpanded_ = true;
            if (bottomUtilityTabs_)
                bottomUtilityTabs_->setCurrentIndex(0);
        }
        updateDockChrome();
        return true;
    }
    return QMainWindow::eventFilter(watched, event);
}





void MainWindow::applyQueuePresentationForCurrentMode()
{
    const bool videoMode = queueModeIsVideoWorkspace(currentModeId_);
    const bool imageMode = queueModeIsImageWorkspace(currentModeId_);

    QStringList acceptedCommands;

    if (currentModeId_ == QStringLiteral("t2i"))
        acceptedCommands = {QStringLiteral("t2i"), QStringLiteral("txt2img"), QStringLiteral("text_to_image")};
    else if (currentModeId_ == QStringLiteral("i2i"))
        acceptedCommands = {QStringLiteral("i2i"), QStringLiteral("img2img"), QStringLiteral("image_to_image")};
    else if (currentModeId_ == QStringLiteral("t2v"))
        acceptedCommands = {QStringLiteral("t2v"), QStringLiteral("text_to_video")};
    else if (currentModeId_ == QStringLiteral("i2v"))
        acceptedCommands = {QStringLiteral("i2v"), QStringLiteral("image_to_video")};

    // Pass 28N:
    // T2I/I2I queue tray is a stable recent-image-jobs ledger.
    // T2V/I2V can still show live video rows where long-running progress matters.
    if (queueFilterProxyModel_)
    {
        queueFilterProxyModel_->setCommandFilter(acceptedCommands);
        queueFilterProxyModel_->setTerminalOnlyFilter(imageMode);
    }

    int visibleRows = 0;

    if (queueTableView_)
    {
        QAbstractItemModel *model = queueTableView_->model();
        visibleRows = model ? model->rowCount() : 0;

        queueTableView_->setUpdatesEnabled(false);

        const int columnCount = model ? model->columnCount() : QueueTableModel::ColumnCount;

        auto setColumnHiddenIfPresent = [&](int column, bool hidden) {
            if (column < 0 || column >= columnCount)
                return;

            queueTableView_->setColumnHidden(column, hidden);
        };

        auto setColumnWidthIfPresent = [&](int column, int width) {
            if (column < 0 || column >= columnCount)
                return;

            queueTableView_->setColumnWidth(column, width);
        };

        const QString geometryKey = QStringLiteral("%1|%2|%3")
            .arg(currentModeId_)
            .arg(columnCount)
            .arg(videoMode ? 1 : 0);

        const bool geometryChanged =
            queueTableView_->property("svQueueModeGeometryKey").toString() != geometryKey;

        if (geometryChanged)
        {
            queueTableView_->setProperty("svQueueModeGeometryKey", geometryKey);

            setColumnHiddenIfPresent(QueueTableModel::VideoColumn, !videoMode);

            queueTableView_->horizontalHeader()->setStretchLastSection(false);
            queueTableView_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
            queueTableView_->verticalHeader()->setDefaultSectionSize(28);
            queueTableView_->verticalHeader()->setMinimumSectionSize(28);
            queueTableView_->setWordWrap(false);
            queueTableView_->setTextElideMode(Qt::ElideRight);

            setColumnWidthIfPresent(QueueTableModel::StateColumn, 104);
            setColumnWidthIfPresent(QueueTableModel::CommandColumn, 76);
            setColumnWidthIfPresent(QueueTableModel::ProgressColumn, 96);
            setColumnWidthIfPresent(QueueTableModel::StatusColumn, imageMode ? 210 : 190);
            setColumnWidthIfPresent(QueueTableModel::QueueIdColumn, 150);
            setColumnWidthIfPresent(QueueTableModel::UpdatedAtColumn, 142);

            if (videoMode)
                setColumnWidthIfPresent(QueueTableModel::VideoColumn, 116);
        }

        queueTableView_->setUpdatesEnabled(true);
    }

    setProperty("svVisibleQueueRowsForMode", visibleRows);


    // Pass 28O:
    // Expanded queue internals should never resize the bottom dock. The tray
    // height is controlled by collapse/expand state, not row count or text width.
    if (queueTableView_)
    {
        queueTableView_->setSizeAdjustPolicy(QAbstractScrollArea::AdjustIgnored);
        queueTableView_->setWordWrap(false);
        queueTableView_->setTextElideMode(Qt::ElideRight);
        queueTableView_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
        queueTableView_->verticalHeader()->setDefaultSectionSize(28);
        queueTableView_->verticalHeader()->setMinimumSectionSize(28);
    }

    if (queueSearchEdit_)
    {
        queueSearchEdit_->setFixedHeight(30);
        queueSearchEdit_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    }

    if (queueStateFilter_)
    {
        queueStateFilter_->setFixedHeight(30);
        queueStateFilter_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    }

    if (queueSearchEdit_)
    {
        queueSearchEdit_->setPlaceholderText(videoMode
            ? QStringLiteral("Search video queue by prompt, model, or state")
            : QStringLiteral("Search recent image jobs by prompt, model, or state"));
    }

    if (bottomQueueLabel_)
    {
        const QString queueText = QStringLiteral("Queue: %1").arg(visibleRows);
        if (bottomQueueLabel_->text() != queueText)
            bottomQueueLabel_->setText(queueText);

        bottomQueueLabel_->setFixedWidth(104);
        bottomQueueLabel_->setWordWrap(false);
        bottomQueueLabel_->setAlignment(Qt::AlignCenter);
        bottomQueueLabel_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
    }

    QWidget *activeStrip = findChild<QWidget *>(QStringLiteral("QueueActiveStrip"));
    if (!activeStrip)
        return;

    activeStrip->setFixedHeight(78);
    activeStrip->setMinimumHeight(78);
    activeStrip->setMaximumHeight(78);
    activeStrip->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    const QString title = QStringLiteral("%1 Queue").arg(currentModeId_.toUpper());
    const QString summary = videoMode
        ? QStringLiteral("%1 video job(s) visible for this workspace.").arg(visibleRows)
        : QStringLiteral("%1 completed image job(s) visible for this workspace.").arg(visibleRows);

    const QList<QLabel *> labels = activeStrip->findChildren<QLabel *>();
    for (QLabel *label : labels)
    {
        if (!label)
            continue;

        label->setWordWrap(false);
        label->setTextInteractionFlags(Qt::NoTextInteraction);
        label->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

        const QString objectName = label->objectName().toLower();
        const QString currentText = label->text();

        if (objectName.contains(QStringLiteral("body")) ||
            objectName.contains(QStringLiteral("summary")) ||
            currentText.contains(QStringLiteral("Recent ")) ||
            currentText.contains(QStringLiteral("visible for this workspace")))
        {
            label->setFixedHeight(22);
            if (label->text() != summary)
                label->setText(summary);
            continue;
        }

        if (objectName.contains(QStringLiteral("title")) ||
            objectName.contains(QStringLiteral("headline")) ||
            currentText.contains(QStringLiteral("•")) ||
            currentText.contains(QStringLiteral("Completed")) ||
            currentText.contains(QStringLiteral("Running")) ||
            currentText.contains(QStringLiteral("Pending")))
        {
            label->setFixedHeight(28);
            if (label->text() != title)
                label->setText(title);
        }
    }
}





void MainWindow::updateDockChrome()
{
    applyQueueDockChrome();
    applyBottomUtilityTrayChrome();
}

QWidget *MainWindow::createQueueWidget()
{
    auto *root = new QWidget(this);
    root->setObjectName(QStringLiteral("QueuePaneRoot"));
    auto *layout = new QVBoxLayout(root);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    auto *activeStrip = createPanelFrame(QStringLiteral("QueueActiveStrip"), root);
    activeStrip->setFixedHeight(78);
    auto *activeLayout = new QVBoxLayout(activeStrip);
    activeLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), ThemeManager::instance().spacing(ThemeManager::Spacing::Tight), ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    activeLayout->setSpacing(3);

    auto *eyebrow = new QLabel(QStringLiteral("ACTIVE QUEUE"), activeStrip);
    eyebrow->setObjectName(QStringLiteral("QueueActiveEyebrow"));
    activeQueueTitleLabel_ = new QLabel(QStringLiteral("No active work"), activeStrip);
    activeQueueTitleLabel_->setObjectName(QStringLiteral("QueueActiveTitle"));
    activeQueueSummaryLabel_ = new QLabel(QStringLiteral("Recent jobs will appear here when the queue is idle."), activeStrip);
    // Pass 28I-R2: active queue strip is a stable single-line summary.
    activeQueueSummaryLabel_->setWordWrap(false);
    activeQueueSummaryLabel_->setFixedHeight(24);
    activeQueueSummaryLabel_->setTextInteractionFlags(Qt::NoTextInteraction);
    activeQueueSummaryLabel_->setObjectName(QStringLiteral("QueueActiveBody"));
    activeQueueSummaryLabel_->setWordWrap(true);

    activeLayout->addWidget(eyebrow);
    activeLayout->addWidget(activeQueueTitleLabel_);
    activeLayout->addWidget(activeQueueSummaryLabel_);

    layout->addWidget(activeStrip);

    queueSearchEdit_ = new QLineEdit(root);
    queueSearchEdit_->setPlaceholderText(QStringLiteral("Search queue by prompt, model, or state"));
    // Pass 28J fixed filter row.
    queueSearchEdit_->setFixedHeight(30);

    queueStateFilter_ = new QComboBox(root);
    queueStateFilter_->setFixedHeight(30);
    queueStateFilter_->addItems({QStringLiteral("All States"),
                                 QStringLiteral("Queued"),
                                 QStringLiteral("Running"),
                                 QStringLiteral("Completed"),
                                 QStringLiteral("Failed")});

    auto *filtersLayout = new QHBoxLayout;
    filtersLayout->setContentsMargins(0, 0, 0, 0);
    filtersLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    filtersLayout->addWidget(queueSearchEdit_, 1);
    filtersLayout->addWidget(queueStateFilter_);
    layout->addLayout(filtersLayout);

    queueTableModel_ = new QueueTableModel(queueManager_, this);
    queueFilterProxyModel_ = new QueueFilterProxyModel(this);
    queueFilterProxyModel_->setSourceModel(queueTableModel_);

    queueTableView_ = new QTableView(root);
    queueTableView_->setModel(queueFilterProxyModel_);
    queueTableView_->setSelectionBehavior(QAbstractItemView::SelectRows);
    queueTableView_->setSelectionMode(QAbstractItemView::SingleSelection);
    queueTableView_->setAlternatingRowColors(true);

    // Pass 28I-R2 stable queue table geometry:
    // No ResizeToContents or wrapping on high-frequency progress/status updates.
    queueTableView_->setWordWrap(false);
    queueTableView_->setTextElideMode(Qt::ElideRight);
    queueTableView_->setSortingEnabled(false);
    queueTableView_->verticalHeader()->setVisible(false);
    queueTableView_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
    queueTableView_->verticalHeader()->setDefaultSectionSize(28);
    queueTableView_->verticalHeader()->setMinimumSectionSize(28);
    queueTableView_->horizontalHeader()->setStretchLastSection(true);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::StateColumn, QHeaderView::Fixed);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::CommandColumn, QHeaderView::Fixed);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::PromptColumn, QHeaderView::Stretch);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::VideoColumn, QHeaderView::Fixed);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::ProgressColumn, QHeaderView::Fixed);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::StatusColumn, QHeaderView::Fixed);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::QueueIdColumn, QHeaderView::Fixed);
    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::UpdatedAtColumn, QHeaderView::Fixed);

    // Pass 28J fixed queue columns.
    queueTableView_->horizontalHeader()->setStretchLastSection(false);
    queueTableView_->setColumnWidth(QueueTableModel::StateColumn, 104);
    queueTableView_->setColumnWidth(QueueTableModel::CommandColumn, 76);
    queueTableView_->setColumnWidth(QueueTableModel::VideoColumn, 116);
    queueTableView_->setColumnWidth(QueueTableModel::ProgressColumn, 96);
    queueTableView_->setColumnWidth(QueueTableModel::StatusColumn, 190);
    queueTableView_->setColumnWidth(QueueTableModel::QueueIdColumn, 150);
    queueTableView_->setColumnWidth(QueueTableModel::UpdatedAtColumn, 142);

    layout->addWidget(queueTableView_, 1);

    connect(queueSearchEdit_, &QLineEdit::textChanged, this, [this](const QString &text)
            {
        if (queueFilterProxyModel_)
            queueFilterProxyModel_->setTextFilter(text); });

    connect(queueStateFilter_, &QComboBox::currentTextChanged, this, [this](const QString &text)
            {
        if (queueFilterProxyModel_)
            queueFilterProxyModel_->setStateFilter(text); });

    connect(queueTableView_->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this]()
            { updateDetailsPanelForQueueSelection(); });

    applyQueuePresentationForCurrentMode();

    return root;
}

QWidget *MainWindow::createDetailsWidget()
{
    auto *root = new QWidget(this);
    auto *layout = new QVBoxLayout(root);
    layout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    layout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    auto *summaryCard = createPanelFrame(QStringLiteral("DetailsSummaryCard"), root);
    auto *summaryLayout = new QVBoxLayout(summaryCard);
    summaryLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    summaryLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

    auto *eyebrow = new QLabel(QStringLiteral("CONTEXT"), summaryCard);
    eyebrow->setObjectName(QStringLiteral("DetailsEyebrow"));

    detailsTitleLabel_ = new QLabel(QStringLiteral("Workspace"), summaryCard);
    detailsTitleLabel_->setObjectName(QStringLiteral("DetailsTitle"));

    detailsBodyLabel_ = new QLabel(QStringLiteral("Use the side rail to move between creation, workflows, and review."), summaryCard);
    detailsBodyLabel_->setObjectName(QStringLiteral("DetailsBody"));
    detailsBodyLabel_->setWordWrap(true);

    summaryLayout->addWidget(eyebrow);
    summaryLayout->addWidget(detailsTitleLabel_);
    summaryLayout->addWidget(detailsBodyLabel_);

    auto *metaGrid = new QGridLayout;
    metaGrid->setHorizontalSpacing(8);
    metaGrid->setVerticalSpacing(8);

    auto makeMetaRow = [&](int row, const QString &labelText, QLabel **valueLabel)
    {
        auto *label = new QLabel(labelText, summaryCard);
        label->setObjectName(QStringLiteral("DetailsMetaLabel"));
        auto *value = new QLabel(QStringLiteral("—"), summaryCard);
        value->setObjectName(QStringLiteral("DetailsMetaValue"));
        value->setWordWrap(true);
        metaGrid->addWidget(label, row, 0);
        metaGrid->addWidget(value, row, 1);
        *valueLabel = value;
    };

    makeMetaRow(0, QStringLiteral("Context"), &detailsContextValueLabel_);
    makeMetaRow(1, QStringLiteral("Selection"), &detailsSelectionValueLabel_);
    makeMetaRow(2, QStringLiteral("Queue"), &detailsQueueValueLabel_);
    makeMetaRow(3, QStringLiteral("Status"), &detailsStatusValueLabel_);

    summaryLayout->addLayout(metaGrid);
    layout->addWidget(summaryCard);

    auto *actionCard = createPanelFrame(QStringLiteral("DetailsActionCard"), root);
    auto *actionLayout = new QVBoxLayout(actionCard);
    actionLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    actionLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

    detailsPrimaryActionButton_ = new QPushButton(QStringLiteral("Primary Action"), actionCard);
    detailsPrimaryActionButton_->setObjectName(QStringLiteral("DetailsPrimaryActionButton"));
    detailsSecondaryActionButton_ = new QPushButton(QStringLiteral("Secondary Action"), actionCard);
    detailsSecondaryActionButton_->setObjectName(QStringLiteral("DetailsSecondaryActionButton"));
    detailsTertiaryActionButton_ = new QPushButton(QStringLiteral("Tertiary Action"), actionCard);
    detailsTertiaryActionButton_->setObjectName(QStringLiteral("DetailsActionButton"));

    actionLayout->addWidget(detailsPrimaryActionButton_);
    actionLayout->addWidget(detailsSecondaryActionButton_);
    actionLayout->addWidget(detailsTertiaryActionButton_);

    layout->addWidget(actionCard);
    layout->addStretch(1);

    connect(detailsPrimaryActionButton_, &QPushButton::clicked, this, [this]()
            { triggerDetailsAction(detailsPrimaryActionId_); });
    connect(detailsSecondaryActionButton_, &QPushButton::clicked, this, [this]()
            { triggerDetailsAction(detailsSecondaryActionId_); });
    connect(detailsTertiaryActionButton_, &QPushButton::clicked, this, [this]()
            { triggerDetailsAction(detailsTertiaryActionId_); });

    updateDetailsPanelForModeContext();
    return root;
}

QWidget *MainWindow::createLogsWidget()
{
    auto *root = new QWidget(this);
    auto *layout = new QVBoxLayout(root);
    layout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    layout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    auto *card = createPanelFrame(QStringLiteral("ExecutionLogCard"), root);
    auto *cardLayout = new QVBoxLayout(card);
    cardLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    cardLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

    auto *title = new QLabel(QStringLiteral("Execution Log"), card);
    title->setObjectName(QStringLiteral("DetailsTitle"));
    logsView_ = new QTextEdit(card);
    logsView_->setObjectName(QStringLiteral("LogsView"));
    logsView_->setReadOnly(true);

    cardLayout->addWidget(title);
    cardLayout->addWidget(logsView_, 1);

    layout->addWidget(card, 1);
    return root;
}

void MainWindow::showTitleBarMenu(const QString &menuId, const QPoint &globalPos)
{
    QMenu menu(this);

    if (menuId == QStringLiteral("file"))
    {
        auto *importWorkflowAction = menu.addAction(QStringLiteral("Import Workflow..."));
        connect(importWorkflowAction, &QAction::triggered, this, &MainWindow::openWorkflowImportDialog);

        menu.addSeparator();

        auto *quitAction = menu.addAction(QStringLiteral("Quit"));
        connect(quitAction, &QAction::triggered, this, &QWidget::close);
    }
    else if (menuId == QStringLiteral("workflows"))
    {
        auto *importWorkflowAction = menu.addAction(QStringLiteral("Import Workflow..."));
        connect(importWorkflowAction, &QAction::triggered, this, &MainWindow::openWorkflowImportDialog);
    }
    else
    {
        menu.addAction(QStringLiteral("No actions"));
    }

    menu.exec(globalPos);
}

void MainWindow::showLayoutMenu(const QPoint &globalPos)
{
    QMenu menu(this);

    auto *toggleQueue = menu.addAction(QStringLiteral("Toggle Bottom Utility"));
    connect(toggleQueue, &QAction::triggered, this, &MainWindow::toggleBottomPanels);

    auto *toggleDetails = menu.addAction(QStringLiteral("Show Details Tray"));
    connect(toggleDetails, &QAction::triggered, this, &MainWindow::toggleDetailsPanel);

    // Phase 5: Logs is no longer an always-on bottom button -- keep it discoverable here.
    auto *showLogs = menu.addAction(QStringLiteral("Show Logs"));
    connect(showLogs, &QAction::triggered, this, [this]()
    {
        detailsDockPinnedOpen_ = false;
        queueDockUserExpanded_ = true;
        bottomUtilityUserExpanded_ = true;
        if (bottomUtilityTabs_)
            bottomUtilityTabs_->setCurrentIndex(1); // Logs tab
        updateDockChrome();
    });

    menu.exec(globalPos);
}

void MainWindow::showSystemMenu(const QPoint &globalPos)
{
    QMenu menu(this);

    auto *minimizeAction = menu.addAction(QStringLiteral("Minimize"));
    connect(minimizeAction, &QAction::triggered, this, &QWidget::showMinimized);

    auto *maximizeAction = menu.addAction(isMaximized() ? QStringLiteral("Restore") : QStringLiteral("Maximize"));
    connect(maximizeAction, &QAction::triggered, this, [this]()
            { isMaximized() ? showNormal() : showMaximized(); });

    menu.addSeparator();

    auto *closeAction = menu.addAction(QStringLiteral("Close"));
    connect(closeAction, &QAction::triggered, this, &QWidget::close);

    menu.exec(globalPos);
}

void MainWindow::setDisclosureMode(bool advanced)
{
    // Phase 6 CONTROL ONLY: store + persist the global Simple/Advanced mode, reflect it on the
    // title-bar toggle, and broadcast it. No cockpit control reacts yet -- Phase 7 consumes
    // disclosureModeChanged()/isAdvancedMode() to actually show/hide controls.
    advancedMode_ = advanced;
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    settings.setValue(QStringLiteral("ui/advancedMode"), advanced);
    if (titleBar_)
        titleBar_->setDisclosureMode(advanced);
    emit disclosureModeChanged(advanced);
}

void MainWindow::showCommandPalette()
{
    if (!commandPaletteDialog_)
    {
        commandPaletteDialog_ = new CommandPaletteDialog(this);
        connect(commandPaletteDialog_, &CommandPaletteDialog::commandTriggered, this, &MainWindow::triggerCommand);
    }

    commandPaletteDialog_->setCommands({QStringLiteral("Go to Home"),
                                        QStringLiteral("Open Text to Image"),
                                        QStringLiteral("Open Image to Image"),
                                        QStringLiteral("Open Text to Video"),
                                        QStringLiteral("Open Image to Video"),
                                        QStringLiteral("Open Workflows"),
                                        QStringLiteral("Open History"),
                                        QStringLiteral("Open Inspiration"),
                                        QStringLiteral("Open Models"),
                                        QStringLiteral("Open Settings"),
                                        QStringLiteral("Import Workflow"),
                                        QStringLiteral("Toggle Left Rail"),
                                        QStringLiteral("Toggle Bottom Utility"),
                                        QStringLiteral("Show Details Tray"),
                                        QStringLiteral("Show Logs")});

    commandPaletteDialog_->show();
    commandPaletteDialog_->raise();
    commandPaletteDialog_->activateWindow();
}

void MainWindow::triggerCommand(const QString &command)
{
    const QString normalized = command.trimmed().toLower();

    if (normalized.contains(QStringLiteral("home")))
    {
        switchToMode(QStringLiteral("home"));
        return;
    }
    if (normalized.contains(QStringLiteral("text to image")))
    {
        switchToMode(QStringLiteral("t2i"));
        return;
    }
    if (normalized.contains(QStringLiteral("image to image")))
    {
        switchToMode(QStringLiteral("i2i"));
        return;
    }
    if (normalized.contains(QStringLiteral("text to video")))
    {
        switchToMode(QStringLiteral("t2v"));
        return;
    }
    if (normalized.contains(QStringLiteral("image to video")))
    {
        switchToMode(QStringLiteral("i2v"));
        return;
    }
    if (normalized.contains(QStringLiteral("workflows")))
    {
        switchToMode(QStringLiteral("workflows"));
        return;
    }
    if (normalized.contains(QStringLiteral("history")))
    {
        switchToMode(QStringLiteral("history"));
        return;
    }
    if (normalized.contains(QStringLiteral("inspiration")))
    {
        switchToMode(QStringLiteral("inspiration"));
        return;
    }
    if (normalized.contains(QStringLiteral("models")))
    {
        switchToMode(QStringLiteral("models"));
        return;
    }
    if (normalized.contains(QStringLiteral("settings")))
    {
        switchToMode(QStringLiteral("settings"));
        return;
    }
    if (normalized.contains(QStringLiteral("import workflow")))
    {
        openWorkflowImportDialog();
        return;
    }
    if (normalized.contains(QStringLiteral("left rail")))
    {
        togglePrimarySidebar();
        return;
    }
    if (normalized.contains(QStringLiteral("bottom panels")) || normalized.contains(QStringLiteral("bottom utility")))
    {
        toggleBottomPanels();
        return;
    }
    if (normalized.contains(QStringLiteral("details dock")) || normalized.contains(QStringLiteral("details tray")))
    {
        toggleDetailsPanel();
        return;
    }
    if (normalized.contains(QStringLiteral("logs")))
    {
        // Phase 6: mirror the Phase 5 "Show Logs" menu entry -- open the activity drawer on the
        // Logs tab via the same flag path + updateDockChrome choke.
        detailsDockPinnedOpen_ = false;
        queueDockUserExpanded_ = true;
        bottomUtilityUserExpanded_ = true;
        if (bottomUtilityTabs_)
            bottomUtilityTabs_->setCurrentIndex(1); // Logs tab
        updateDockChrome();
        return;
    }
}

void MainWindow::openWorkflowImportDialog()
{
    if (workflowImportProcess_)
    {
        QMessageBox::information(
            this,
            QStringLiteral("Workflow Import"),
            QStringLiteral("A workflow import is already running. Wait for it to finish before starting another."));
        return;
    }

    WorkflowImportDialog dialog(this);
    const QString projectRoot = resolveProjectRoot();
    dialog.setManagedComfyRoot(defaultManagedComfyRoot(projectRoot));
    dialog.setDefaultDestinationRoot(defaultImportedWorkflowsRoot(projectRoot));

    if (dialog.exec() != QDialog::Accepted)
        return;

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("import_workflow"));
    request.insert(QStringLiteral("source"), dialog.sourcePath());
    request.insert(QStringLiteral("destination_root"), dialog.destinationRoot());

    if (!dialog.profileName().trimmed().isEmpty())
        request.insert(QStringLiteral("profile_name"), dialog.profileName().trimmed());

    if (!dialog.comfyRoot().trimmed().isEmpty())
        request.insert(QStringLiteral("comfy_root"), dialog.comfyRoot().trimmed());

    request.insert(QStringLiteral("auto_apply_node_deps"), dialog.autoApplyNodeDeps());
    request.insert(QStringLiteral("auto_apply_model_deps"), dialog.autoApplyModelDeps());

    const QString pythonExecutable = resolvePythonExecutable();
    const QString workerClient = QDir(projectRoot).filePath(QStringLiteral("python/worker_client.py"));

    auto *process = new QProcess(this);
    workflowImportProcess_ = process;

    process->setProgram(pythonExecutable);
    process->setArguments({workerClient});
    process->setWorkingDirectory(projectRoot);

    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    const QString cacheRoot = QDir(projectRoot).filePath(QStringLiteral("hf_cache"));
    env.insert(QStringLiteral("HF_HOME"), cacheRoot);
    env.insert(QStringLiteral("HUGGINGFACE_HUB_CACHE"), cacheRoot);
    process->setProcessEnvironment(env);

    const QByteArray requestBytes = QJsonDocument(request).toJson(QJsonDocument::Compact) + "\n";

    appendLogLine(QStringLiteral("Starting workflow import: %1").arg(QFileInfo(dialog.sourcePath()).fileName()));
    if (bottomReadyLabel_)
        bottomReadyLabel_->setText(QStringLiteral("IMPORTING"));
    if (bottomStateLabel_)
        bottomStateLabel_->setText(QStringLiteral("Workflow import running"));

    connect(process, &QProcess::started, this, [process, requestBytes]()
            {
        process->write(requestBytes);
        process->closeWriteChannel(); });

    connect(process, &QProcess::errorOccurred, this, [this, process](QProcess::ProcessError)
            {
        if (workflowImportProcess_ != process)
        {
            process->deleteLater();
            return;
        }

        const QString stderrText = QString::fromUtf8(process->readAllStandardError()).trimmed();
        workflowImportProcess_ = nullptr;
        process->deleteLater();

        if (bottomReadyLabel_)
            bottomReadyLabel_->setText(QStringLiteral("READY"));
        if (bottomStateLabel_)
            bottomStateLabel_->setText(QStringLiteral("Idle"));

        appendLogLine(stderrText.isEmpty()
                          ? QStringLiteral("Workflow import failed to start.")
                          : QStringLiteral("Workflow import failed to start: %1").arg(stderrText));

        QMessageBox::warning(
            this,
            QStringLiteral("Workflow Import"),
            stderrText.isEmpty()
                ? QStringLiteral("Failed to start worker_client.py for workflow import.")
                : QStringLiteral("Failed to start worker_client.py for workflow import.\n\n%1").arg(stderrText)); });

    connect(process,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this,
            [this, process](int exitCode, QProcess::ExitStatus exitStatus)
            {
                if (workflowImportProcess_ != process)
                {
                    process->deleteLater();
                    return;
                }

                const QString stderrText = QString::fromUtf8(process->readAllStandardError()).trimmed();
                const QString stdoutText = QString::fromUtf8(process->readAllStandardOutput()).trimmed();

                workflowImportProcess_ = nullptr;
                process->deleteLater();

                if (bottomReadyLabel_)
                    bottomReadyLabel_->setText(QStringLiteral("READY"));
                if (bottomStateLabel_)
                    bottomStateLabel_->setText(QStringLiteral("Idle"));

                if (!stderrText.isEmpty())
                    appendLogLine(stderrText);

                if (exitStatus != QProcess::NormalExit || exitCode != 0)
                {
                    QMessageBox::warning(
                        this,
                        QStringLiteral("Workflow Import"),
                        stderrText.isEmpty()
                            ? QStringLiteral("Workflow import process exited with code %1.").arg(exitCode)
                            : QStringLiteral("Workflow import process exited with code %1.\n\n%2").arg(exitCode).arg(stderrText));
                    return;
                }

                QString parseErrorText;
                const QJsonObject response = parseLastJsonObjectFromStdout(stdoutText, &parseErrorText);
                if (response.isEmpty())
                {
                    QMessageBox::warning(
                        this,
                        QStringLiteral("Workflow Import"),
                        parseErrorText.isEmpty()
                            ? QStringLiteral("Worker returned no usable JSON payload for workflow import.")
                            : parseErrorText);
                    return;
                }

                showWorkflowImportResult(response, stderrText);
            });

    process->start();
}

void MainWindow::showWorkflowImportResult(const QJsonObject &response, const QString &stderrText)
{
    if (!stderrText.trimmed().isEmpty())
        appendLogLine(stderrText.trimmed());

    if (response.isEmpty())
    {
        QMessageBox::warning(
            this,
            QStringLiteral("Workflow Import"),
            QStringLiteral("Worker returned no JSON payload for workflow import."));
        return;
    }

    const bool ok = response.value(QStringLiteral("ok")).toBool(false);
    const QString inferredTask = response.value(QStringLiteral("inferred_task_command")).toString().trimmed();
    const QString inferredMedia = response.value(QStringLiteral("inferred_media_type")).toString().trimmed();

    const QJsonObject artifacts = response.value(QStringLiteral("artifacts")).toObject();
    const QJsonArray missingCustomNodes = response.value(QStringLiteral("missing_custom_nodes")).toArray();
    const QJsonArray modelReferences = response.value(QStringLiteral("model_references")).toArray();
    const QJsonArray warnings = response.value(QStringLiteral("warnings")).toArray();
    const QJsonArray errors = response.value(QStringLiteral("errors")).toArray();

    QStringList lines;
    lines << QStringLiteral("Import %1").arg(ok ? QStringLiteral("completed.") : QStringLiteral("reported issues."));
    if (!inferredTask.isEmpty())
        lines << QStringLiteral("Task: %1").arg(inferredTask);
    if (!inferredMedia.isEmpty())
        lines << QStringLiteral("Media: %1").arg(inferredMedia);
    if (!artifacts.value(QStringLiteral("import_root")).toString().trimmed().isEmpty())
        lines << QStringLiteral("Import Root: %1").arg(QDir::toNativeSeparators(artifacts.value(QStringLiteral("import_root")).toString().trimmed()));
    if (!artifacts.value(QStringLiteral("workflow_path")).toString().trimmed().isEmpty())
        lines << QStringLiteral("Workflow Path: %1").arg(QDir::toNativeSeparators(artifacts.value(QStringLiteral("workflow_path")).toString().trimmed()));
    if (!artifacts.value(QStringLiteral("profile_path")).toString().trimmed().isEmpty())
        lines << QStringLiteral("Profile Path: %1").arg(QDir::toNativeSeparators(artifacts.value(QStringLiteral("profile_path")).toString().trimmed()));
    if (!artifacts.value(QStringLiteral("scan_report_path")).toString().trimmed().isEmpty())
        lines << QStringLiteral("Scan Report: %1").arg(QDir::toNativeSeparators(artifacts.value(QStringLiteral("scan_report_path")).toString().trimmed()));

    lines << QStringLiteral("Missing Custom Nodes: %1").arg(missingCustomNodes.size());
    lines << QStringLiteral("Model References: %1").arg(modelReferences.size());

    auto joinArray = [](const QJsonArray &array)
    {
        QStringList out;
        for (const QJsonValue &value : array)
            out << value.toString();
        return out;
    };

    QString detailedText;
    if (!warnings.isEmpty())
        detailedText += QStringLiteral("Warnings:\n%1\n\n").arg(joinArray(warnings).join(QStringLiteral("\n")));
    if (!errors.isEmpty())
        detailedText += QStringLiteral("Errors:\n%1\n\n").arg(joinArray(errors).join(QStringLiteral("\n")));

    QMessageBox box(this);
    box.setIcon(ok ? QMessageBox::Information : QMessageBox::Warning);
    box.setWindowTitle(QStringLiteral("Workflow Import"));
    box.setText(lines.join(QStringLiteral("\n")));
    if (!detailedText.trimmed().isEmpty())
        box.setDetailedText(detailedText.trimmed());
    box.exec();

    if (workflowsPage_)
        workflowsPage_->refreshProfiles();

    appendLogLine(QStringLiteral("Workflow import finished • task=%1 • media=%2 • ok=%3")
                      .arg(inferredTask.isEmpty() ? QStringLiteral("unknown") : inferredTask,
                           inferredMedia.isEmpty() ? QStringLiteral("unknown") : inferredMedia,
                           ok ? QStringLiteral("true") : QStringLiteral("false")));
}

void MainWindow::togglePrimarySidebar()
{
    if (!sideRail_)
        return;
    sideRail_->setVisible(!sideRail_->isVisible());
}

void MainWindow::toggleBottomPanels()
{
    if (!queueOverlay_)
        return;

    queueDockUserExpanded_ = !queueDockUserExpanded_;
    bottomUtilityUserExpanded_ = queueDockUserExpanded_;
    if (!queueDockUserExpanded_)
        detailsDockPinnedOpen_ = false;

    updateDockChrome();
}

void MainWindow::toggleDetailsPanel()
{
    if (!queueOverlay_)
        return;

    detailsDockPinnedOpen_ = !detailsDockPinnedOpen_;
    if (detailsDockPinnedOpen_)
    {
        queueDockUserExpanded_ = true;
        bottomUtilityUserExpanded_ = true;
        if (bottomUtilityTabs_)
            bottomUtilityTabs_->setCurrentIndex(0);
    }

    updateDockChrome();
}

void MainWindow::applyShellStateForMode(const QString &modeId)
{
    if (titleBar_)
        titleBar_->setContextText(pageContextForMode(modeId));

    if (bottomPageLabel_)
        bottomPageLabel_->setText(modeId.toUpper());

    updateModeButtonState(modeId);
    updateDetailsPanelForModeContext();
    applyQueuePresentationForCurrentMode();
    updateDockChrome();
}

void MainWindow::setBottomPageContext(const QString &text)
{
    if (bottomPageLabel_)
        bottomPageLabel_->setText(text);
}




void MainWindow::startVramTelemetryPolling()
{
    if (vramTelemetryTimer_)
        return;

    vramTelemetryTimer_ = new QTimer(this);
    vramTelemetryTimer_->setInterval(2000);

    connect(vramTelemetryTimer_, &QTimer::timeout, this, &MainWindow::pollVramTelemetry);

    pollVramTelemetry();
    vramTelemetryTimer_->start();
}

void MainWindow::pollVramTelemetry()
{
    if (property("svVramTelemetryInFlight").toBool())
        return;

    setProperty("svVramTelemetryInFlight", true);

    auto *process = new QProcess(this);
    process->setProgram(QStringLiteral("nvidia-smi"));
    process->setArguments({
        QStringLiteral("--query-gpu=memory.used,memory.total"),
        QStringLiteral("--format=csv,noheader,nounits")
    });

    connect(process, &QProcess::errorOccurred, this, [this, process](QProcess::ProcessError) {
        if (process->property("svHandled").toBool())
            return;

        process->setProperty("svHandled", true);
        setProperty("svVramTelemetryInFlight", false);

        lastVramTelemetryText_ = QStringLiteral("VRAM: unavailable");
        syncBottomTelemetry();

        process->deleteLater();
    });

    connect(process, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, [this, process](int exitCode, QProcess::ExitStatus status) {
        if (process->property("svHandled").toBool())
            return;

        process->setProperty("svHandled", true);
        setProperty("svVramTelemetryInFlight", false);

        QString nextText = QStringLiteral("VRAM: unavailable");

        if (status == QProcess::NormalExit && exitCode == 0)
        {
            const QString output = QString::fromLocal8Bit(process->readAllStandardOutput()).trimmed();
            const QString firstLine = output.split(QRegularExpression(QStringLiteral("[\\r\\n]+")), Qt::SkipEmptyParts).value(0).trimmed();
            const QStringList parts = firstLine.split(QStringLiteral(","), Qt::SkipEmptyParts);

            if (parts.size() >= 2)
            {
                bool usedOk = false;
                bool totalOk = false;

                const double usedMb = parts.at(0).trimmed().toDouble(&usedOk);
                const double totalMb = parts.at(1).trimmed().toDouble(&totalOk);

                if (usedOk && totalOk)
                    nextText = pass28qFormatVramText(usedMb, totalMb);
            }
        }

        if (lastVramTelemetryText_ != nextText)
        {
            lastVramTelemetryText_ = nextText;
            syncBottomTelemetry();
        }

        process->deleteLater();
    });

    process->start();
}




void MainWindow::syncBottomTelemetry()
{
    const bool imageWorkspace = pass28qModeIsImage(currentModeId_);

    const QueueItem *activeItem = nullptr;
    int visibleQueueCount = 0;
    int activeProgress = 0;

    if (queueManager_)
    {
        const QVector<QueueItem> &items = queueManager_->items();

        for (const QueueItem &item : items)
        {
            if (!pass28qItemMatchesMode(item, currentModeId_))
                continue;

            if (pass28qItemIsActive(item))
            {
                activeItem = &item;
                activeProgress = qMax(activeProgress, item.progressPercent());
                continue;
            }

            if (imageWorkspace)
            {
                if (item.isTerminal())
                    ++visibleQueueCount;
            }
            else
            {
                ++visibleQueueCount;
            }
        }
    }

    if (queueTableView_ && queueTableView_->model())
        visibleQueueCount = queueTableView_->model()->rowCount();

    const bool explicitBusy =
        property("svTelemetryBusy").toBool() &&
        property("svTelemetryBusyMode").toString() == currentModeId_;

    const int completedRowsAtSubmit = property("svTelemetryCompletedRowsAtSubmit").toInt();

    const bool completedOutputObserved =
        explicitBusy &&
        imageWorkspace &&
        completedRowsAtSubmit >= 0 &&
        visibleQueueCount > completedRowsAtSubmit;

    // Pass 28T:
    // If a new completed image row appears after submission, completion wins
    // over any stale active row that may still say Running/89%.
    if (completedOutputObserved)
        activeItem = nullptr;

    const bool completionPulse = property("svTelemetryCompletionPulse").toBool();
    bool busy = activeItem != nullptr || explicitBusy || completionPulse;

    if (completedOutputObserved && !completionPulse)
    {
        setProperty("svTelemetryCompletionPulse", true);
        setProperty("svTelemetryBusy", false);
        setProperty("svTelemetryBusyState", QStringLiteral("Completed"));
        setProperty("svTelemetryPhaseRank", 0);
        setProperty("svTelemetryProgressTarget", 100);

        if (bottomProgressBar_)
        {
            bottomProgressBar_->setFormat(QStringLiteral("%p%"));
        }

        QTimer::singleShot(900, this, [this]() {
            setProperty("svTelemetryBusy", false);
            setProperty("svTelemetryBusyState", QStringLiteral("Idle"));
            setProperty("svTelemetryPhaseRank", 0);
            setProperty("svTelemetryProgressTarget", 0);
            setProperty("svTelemetryJobActive", false);
            setProperty("svTelemetryCompletionPulse", false);
            setProperty("svTelemetryCompletedRowsAtSubmit", 0);
            syncBottomTelemetry();
        });
    }

    const QString explicitBusyState = property("svTelemetryBusyState").toString().trimmed();

    const int observedRank = activeItem
        ? pass28sTelemetryRankFromState(activeItem->state)
        : (busy ? pass28sTelemetryRankFromText(explicitBusyState) : 0);

    int displayedRank = property("svTelemetryPhaseRank").toInt();

    if (busy && !completedOutputObserved && !completionPulse)
        displayedRank = qMax(displayedRank, observedRank);
    else if (!busy)
        displayedRank = 0;

    setProperty("svTelemetryPhaseRank", displayedRank);

    QString stateText = QStringLiteral("Idle");

    if (completedOutputObserved || completionPulse)
        stateText = QStringLiteral("Completed");
    else if (busy)
        stateText = pass28sTelemetryStateFromRank(displayedRank, explicitBusyState);

    int targetProgress = activeProgress;

    if (completedOutputObserved || completionPulse)
    {
        targetProgress = 100;
    }
    else if (busy)
    {
        targetProgress = qMax(targetProgress, pass28sMinimumProgressForRank(displayedRank));

        const int previousTarget = property("svTelemetryProgressTarget").toInt();
        targetProgress = qMax(targetProgress, previousTarget);
        targetProgress = qBound(0, targetProgress, 99);
    }
    else
    {
        targetProgress = 0;
    }

    setProperty("svTelemetryProgressTarget", targetProgress);

    auto setLabelText = [](QLabel *label, const QString &text) {
        if (!label)
            return;

        if (label->text() != text)
            label->setText(text);
    };

    setLabelText(bottomReadyLabel_, (busy || completionPulse || completedOutputObserved) ? QStringLiteral("Busy") : QStringLiteral("Ready"));
    setLabelText(bottomPageLabel_, pageContextForMode(currentModeId_));
    setLabelText(bottomRuntimeLabel_, QStringLiteral("Runtime: local"));
    setLabelText(bottomQueueLabel_, QStringLiteral("Queue: %1").arg(visibleQueueCount));
    setLabelText(bottomVramLabel_, lastVramTelemetryText_.trimmed().isEmpty()
        ? QStringLiteral("VRAM: checking")
        : lastVramTelemetryText_);

    ImageGenerationPage *page = generationPageForMode(currentModeId_);
    const QString modelValue = page ? page->selectedModelValue() : QString();
    const QString loraValue = page ? page->selectedLoraValue() : QString();

    setLabelText(bottomModelLabel_, QStringLiteral("Model: %1").arg(
        spellvision::shell::BottomTelemetryPresenter::shortAssetName(modelValue)));
    setLabelText(bottomLoraLabel_, QStringLiteral("LoRA: %1").arg(
        spellvision::shell::BottomTelemetryPresenter::shortAssetName(loraValue)));
    setLabelText(bottomStateLabel_, stateText);

    auto stabilizeLabel = [](QLabel *label, int width) {
        if (!label)
            return;

        label->setFixedWidth(width);
        label->setMinimumHeight(24);
        label->setMaximumHeight(24);
        label->setWordWrap(false);
        label->setTextInteractionFlags(Qt::NoTextInteraction);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    };

    stabilizeLabel(bottomReadyLabel_, 64);
    stabilizeLabel(bottomPageLabel_, 150);
    stabilizeLabel(bottomRuntimeLabel_, 150);
    stabilizeLabel(bottomQueueLabel_, 104);
    stabilizeLabel(bottomVramLabel_, 170);
    stabilizeLabel(bottomModelLabel_, 210);
    stabilizeLabel(bottomLoraLabel_, 150);
    stabilizeLabel(bottomStateLabel_, 96);

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setRange(0, 100);
        bottomProgressBar_->setTextVisible(true);
        bottomProgressBar_->setFormat((busy || completionPulse || completedOutputObserved) ? QStringLiteral("%p%") : QStringLiteral(""));
        bottomProgressBar_->setFixedSize(164, 18);
        bottomProgressBar_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);

        const int currentValue = bottomProgressBar_->value();
        const int currentTarget = bottomProgressBar_->property("svProgressAnimationTarget").toInt();

        if (currentTarget != targetProgress)
        {
            if (auto *oldAnimation = bottomProgressBar_->findChild<QPropertyAnimation *>(QStringLiteral("TelemetryProgressAnimation")))
            {
                oldAnimation->stop();
                oldAnimation->deleteLater();
            }

            bottomProgressBar_->setProperty("svProgressAnimationTarget", targetProgress);

            auto *animation = new QPropertyAnimation(bottomProgressBar_, "value", bottomProgressBar_);
            animation->setObjectName(QStringLiteral("TelemetryProgressAnimation"));
            animation->setDuration((busy || completionPulse || completedOutputObserved) ? 260 : 180);
            animation->setEasingCurve(QEasingCurve::OutCubic);
            animation->setStartValue(currentValue);
            animation->setEndValue(targetProgress);
            animation->start(QAbstractAnimation::DeleteWhenStopped);
        }
    }
}





void MainWindow::switchToMode(const QString &modeId)
{
    // On-demand construction: a deferred generation page is built here (idempotent)
    // before the modePages_ lookup, so navigating to a not-yet-warmed page builds it
    // now and then resolves normally. No-op for non-generation / already-built modes.
    ensureGenerationPageBuilt(modeId);

    const QString resolvedModeId = modePages_.contains(modeId) ? modeId : QStringLiteral("home");
    currentModeId_ = resolvedModeId;

    if (pageStack_)
        pageStack_->setCurrentWidget(modePages_.value(resolvedModeId, homePage_));

    applyShellStateForMode(resolvedModeId);
}

void MainWindow::openManager(const QString &managerId)
{
    if (managerId == QStringLiteral("models"))
    {
        switchToMode(QStringLiteral("models"));
        return;
    }
    if (managerId == QStringLiteral("workflows"))
    {
        switchToMode(QStringLiteral("workflows"));
        return;
    }
    if (managerId == QStringLiteral("inspiration"))
    {
        switchToMode(QStringLiteral("inspiration"));
        return;
    }
    if (managerId == QStringLiteral("history"))
    {
        switchToMode(QStringLiteral("history"));
        return;
    }
    if (managerId == QStringLiteral("settings"))
    {
        switchToMode(QStringLiteral("settings"));
        return;
    }
    if (managerId == QStringLiteral("downloads"))
    {
        switchToMode(QStringLiteral("models"));
        return;
    }
}





void MainWindow::onQueueChanged()
{
    // Pass 28O:
    // Queue polling is high-frequency. Do not synchronously rewrite telemetry,
    // strip labels, details, chrome, and the queue viewport on every snapshot.
    // Coalesce poll bursts into a single stable UI update.
    if (property("svBottomQueueUiFlushPending").toBool())
        return;

    setProperty("svBottomQueueUiFlushPending", true);

    QTimer::singleShot(140, this, [this]() {
        setProperty("svBottomQueueUiFlushPending", false);

        applyQueuePresentationForCurrentMode();
        syncBottomTelemetry();
        applyQueuePresentationForCurrentMode();

        const bool expanded = queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;
        const QString selectedId = selectedQueueId();

        const QString detailsKey = QStringLiteral("%1|%2")
            .arg(expanded ? QStringLiteral("expanded") : QStringLiteral("collapsed"), selectedId);

        if (property("svQueueDetailsKey").toString() != detailsKey)
        {
            setProperty("svQueueDetailsKey", detailsKey);
            updateDetailsPanelForQueueSelection();
        }

        const QString chromeKey = QStringLiteral("%1|%2|%3")
            .arg(queueDockUserExpanded_ ? 1 : 0)
            .arg(bottomUtilityUserExpanded_ ? 1 : 0)
            .arg(detailsDockPinnedOpen_ ? 1 : 0);

        if (property("svQueueChromeKey").toString() != chromeKey)
        {
            setProperty("svQueueChromeKey", chromeKey);
            updateDockChrome();
        }

        if (queueTableView_)
            queueTableView_->viewport()->update();
    });
}





void MainWindow::changeEvent(QEvent *event)
{
    QMainWindow::changeEvent(event);
    if (titleBar_)
        titleBar_->setMaximized(isMaximized());
    updateDockChrome();
}

bool MainWindow::nativeEvent(const QByteArray &eventType, void *message, qintptr *result)
{
#ifdef Q_OS_WIN
    Q_UNUSED(eventType);

    MSG *msg = static_cast<MSG *>(message);
    if (!msg || !result)
        return false;

    if (msg->message == WM_NCHITTEST)
    {
        const LONG borderWidth = 8;
        RECT winRect{};
        GetWindowRect(reinterpret_cast<HWND>(winId()), &winRect);

        const long x = GET_X_LPARAM(msg->lParam);
        const long y = GET_Y_LPARAM(msg->lParam);

        const bool resizeWidth = minimumWidth() != maximumWidth();
        const bool resizeHeight = minimumHeight() != maximumHeight();

        if (resizeWidth)
        {
            if (x >= winRect.left && x < winRect.left + borderWidth)
            {
                if (resizeHeight)
                {
                    if (y >= winRect.top && y < winRect.top + borderWidth)
                    {
                        *result = HTTOPLEFT;
                        return true;
                    }
                    if (y <= winRect.bottom && y > winRect.bottom - borderWidth)
                    {
                        *result = HTBOTTOMLEFT;
                        return true;
                    }
                }
                *result = HTLEFT;
                return true;
            }

            if (x < winRect.right && x >= winRect.right - borderWidth)
            {
                if (resizeHeight)
                {
                    if (y >= winRect.top && y < winRect.top + borderWidth)
                    {
                        *result = HTTOPRIGHT;
                        return true;
                    }
                    if (y <= winRect.bottom && y > winRect.bottom - borderWidth)
                    {
                        *result = HTBOTTOMRIGHT;
                        return true;
                    }
                }
                *result = HTRIGHT;
                return true;
            }
        }

        if (resizeHeight)
        {
            if (y >= winRect.top && y < winRect.top + borderWidth)
            {
                *result = HTTOP;
                return true;
            }

            if (y < winRect.bottom && y >= winRect.bottom - borderWidth)
            {
                *result = HTBOTTOM;
                return true;
            }
        }
    }

    // Collapse the non-client area so the native caption (WS_CAPTION is set despite the
    // frameless hint, style 0x96CF0000) is not drawn -- only the custom title bar shows.
    // Returning 0 with rgrc[0] left as the proposed window rect makes the client fill the
    // whole window (0 inset, proven by the Step-1 spike).
    if (msg->message == WM_NCCALCSIZE && msg->wParam == TRUE)
    {
        // When MAXIMIZED, Windows pads the window by the frame thickness
        // (SM_CXSIZEFRAME + SM_CXPADDEDBORDER, ~8px/side) and positions it -8,-8; with a
        // zero non-client that pushed the outer 8px of UI off every screen edge. Inset the
        // client by that frame thickness ONLY when zoomed, so the maximized client == the
        // monitor work area (no overflow, taskbar respected). Normal state stays 0-inset.
        if (IsZoomed(msg->hwnd))
        {
            auto *params = reinterpret_cast<NCCALCSIZE_PARAMS *>(msg->lParam);
            const int fx = GetSystemMetrics(SM_CXSIZEFRAME) + GetSystemMetrics(SM_CXPADDEDBORDER);
            const int fy = GetSystemMetrics(SM_CYSIZEFRAME) + GetSystemMetrics(SM_CXPADDEDBORDER);
            params->rgrc[0].left += fx;
            params->rgrc[0].top += fy;
            params->rgrc[0].right -= fx;
            params->rgrc[0].bottom -= fy;
        }
        *result = 0;
        return true;
    }
#else
    Q_UNUSED(eventType);
    Q_UNUSED(message);
    Q_UNUSED(result);
#endif
    return false;
}

void MainWindow::refreshDetailsPanel()
{
    updateDetailsPanelForQueueSelection();
}

void MainWindow::configureDetailsActions(const QString &primaryId,
                                         const QString &primaryText,
                                         const QString &secondaryId,
                                         const QString &secondaryText,
                                         const QString &tertiaryId,
                                         const QString &tertiaryText)
{
    detailsPrimaryActionId_ = primaryId;
    detailsSecondaryActionId_ = secondaryId;
    detailsTertiaryActionId_ = tertiaryId;

    if (detailsPrimaryActionButton_)
    {
        detailsPrimaryActionButton_->setText(primaryText);
        detailsPrimaryActionButton_->setVisible(!primaryText.trimmed().isEmpty());
    }

    if (detailsSecondaryActionButton_)
    {
        detailsSecondaryActionButton_->setText(secondaryText);
        detailsSecondaryActionButton_->setVisible(!secondaryText.trimmed().isEmpty());
    }

    if (detailsTertiaryActionButton_)
    {
        detailsTertiaryActionButton_->setText(tertiaryText);
        detailsTertiaryActionButton_->setVisible(!tertiaryText.trimmed().isEmpty());
    }
}

void MainWindow::triggerDetailsAction(const QString &actionId)
{
    if (actionId.startsWith(QStringLiteral("mode:")))
    {
        switchToMode(actionId.mid(QStringLiteral("mode:").size()));
        return;
    }
    if (actionId.startsWith(QStringLiteral("manager:")))
    {
        openManager(actionId.mid(QStringLiteral("manager:").size()));
        return;
    }
    if (actionId == QStringLiteral("toggle:queue"))
    {
        toggleBottomPanels();
        return;
    }
    if (actionId == QStringLiteral("toggle:details"))
    {
        toggleDetailsPanel();
        return;
    }

    auto selectedOrLatestVideoItem = [this](bool forceLatestVideo) -> QueueItem {
        if (!queueManager_)
            return latestPersistedVideoQueueItem(resolveProjectRoot());

        if (!forceLatestVideo)
        {
            const QString selectedId = selectedQueueId();
            if (!selectedId.isEmpty() && queueManager_->contains(selectedId))
                return queueManager_->itemById(selectedId);
        }

        for (auto it = queueManager_->items().crbegin(); it != queueManager_->items().crend(); ++it)
        {
            if (isVideoQueueItem(*it) && it->state == QueueItemState::Completed && !it->outputPath.trimmed().isEmpty())
                return *it;
        }
        const QueueItem persisted = latestPersistedVideoQueueItem(resolveProjectRoot());
        if (!persisted.id.trimmed().isEmpty())
            return persisted;
        return QueueItem{};
    };

    if (actionId == QStringLiteral("queue:openoutput") || actionId == QStringLiteral("queue:open_latest_video"))
    {
        const QueueItem item = selectedOrLatestVideoItem(actionId == QStringLiteral("queue:open_latest_video"));
        const QString outputPath = item.outputPath.trimmed();
        if (outputPath.isEmpty())
        {
            QMessageBox::information(this, QStringLiteral("Open Output"), QStringLiteral("No output file is available for this queue item yet."));
            return;
        }

        const QFileInfo info(outputPath);
        if (!info.exists())
        {
            QMessageBox::warning(this, QStringLiteral("Open Output"), QStringLiteral("The output file does not exist yet:\n\n%1").arg(QDir::toNativeSeparators(outputPath)));
            return;
        }

        QDesktopServices::openUrl(QUrl::fromLocalFile(info.absoluteFilePath()));
        return;
    }

    if (actionId == QStringLiteral("queue:revealfolder") || actionId == QStringLiteral("queue:reveal_latest_video"))
    {
        const QueueItem item = selectedOrLatestVideoItem(actionId == QStringLiteral("queue:reveal_latest_video"));
        const QString outputPath = item.outputPath.trimmed();
        if (outputPath.isEmpty())
        {
            QMessageBox::information(this, QStringLiteral("Reveal Output"), QStringLiteral("No output file is available for this queue item yet."));
            return;
        }

        const QFileInfo info(outputPath);
        const QDir dir = info.exists() ? info.absoluteDir() : QFileInfo(outputPath).absoluteDir();
        if (!dir.exists())
        {
            QMessageBox::warning(this, QStringLiteral("Reveal Output"), QStringLiteral("The output folder does not exist yet:\n\n%1").arg(QDir::toNativeSeparators(dir.absolutePath())));
            return;
        }

        QDesktopServices::openUrl(QUrl::fromLocalFile(dir.absolutePath()));
        return;
    }
}

void MainWindow::updateDetailsPanelForModeContext()
{
    if (!detailsTitleLabel_ || !detailsBodyLabel_ || !queueManager_)
        return;

    const QVector<QueueItem> &items = queueManager_->items();

    int pendingCount = 0;
    int runningCount = 0;
    int failedCount = 0;
    for (const QueueItem &item : items)
    {
        if (item.state == QueueItemState::Running)
            ++runningCount;
        else if (item.state == QueueItemState::Queued || item.state == QueueItemState::Preparing)
            ++pendingCount;
        else if (item.state == QueueItemState::Failed)
            ++failedCount;
    }

    const QString contextText = pageContextForMode(currentModeId_);
    QString selectionText = QStringLiteral("Nothing selected");
    QString bodyText = QStringLiteral("Use the side rail to navigate between creation, workflows, models, and review surfaces.");

    detailsTitleLabel_->setText(currentModeId_.toUpper());

    if (currentModeId_ == QStringLiteral("home"))
    {
        selectionText = QStringLiteral("Launch surface");
        bodyText = QStringLiteral("Home is the production launch deck. Use it to route into creation, workflow imports, models, and review.");
        configureDetailsActions(QStringLiteral("mode:t2i"), QStringLiteral("Open T2I"),
                                QStringLiteral("mode:workflows"), QStringLiteral("Open Workflows"),
                                QStringLiteral("mode:models"), QStringLiteral("Open Models"));
    }
    else if (currentModeId_ == QStringLiteral("t2i") || currentModeId_ == QStringLiteral("i2i"))
    {
        selectionText = currentModeId_ == QStringLiteral("t2i") ? QStringLiteral("Prompt-first canvas") : QStringLiteral("Restyle canvas");
        bodyText = QStringLiteral("Prompt, input, and quick controls stay prioritized in the left inspector. The right rail reports model, LoRA, workflow, and readiness state.");
        configureDetailsActions(QStringLiteral("manager:models"), QStringLiteral("Open Models"),
                                QStringLiteral("manager:workflows"), QStringLiteral("Open Workflows"),
                                QStringLiteral("toggle:queue"), QStringLiteral("Show Queue"));
    }
    else if (currentModeId_ == QStringLiteral("t2v") || currentModeId_ == QStringLiteral("i2v"))
    {
        selectionText = QStringLiteral("Motion workspace");
        bodyText = QStringLiteral("Wan T2V is now a validated production path. Use the queue details to inspect output video, playback readiness, duration, resolution, low/high Wan stack, and runtime memory mode such as Cold Start, Image → Video Cleanup, or Video Warm Reuse.");
        configureDetailsActions(QStringLiteral("toggle:queue"), QStringLiteral("Show Queue"),
                                QStringLiteral("manager:history"), QStringLiteral("Open History"),
                                QStringLiteral("manager:workflows"), QStringLiteral("Open Workflows"));
    }
    else if (currentModeId_ == QStringLiteral("workflows"))
    {
        selectionText = QStringLiteral("Workflow library");
        bodyText = QStringLiteral("Review imported starters, inspect dependencies, and flow the best presets back into Home and generation pages.");
        configureDetailsActions(QStringLiteral("manager:models"), QStringLiteral("Open Models"),
                                QStringLiteral("mode:home"), QStringLiteral("Go Home"),
                                QStringLiteral("manager:history"), QStringLiteral("Open History"));
    }
    else if (currentModeId_ == QStringLiteral("history"))
    {
        selectionText = QStringLiteral("Review workspace");
        bodyText = QStringLiteral("Inspect finished work, reroute promising outputs into I2I, and keep queue and workflow context close at hand.");

        QueueItem latestVideo;
        for (auto it = items.crbegin(); it != items.crend(); ++it)
        {
            if (isVideoQueueItem(*it) && it->state == QueueItemState::Completed && !it->outputPath.trimmed().isEmpty())
            {
                latestVideo = *it;
                break;
            }
        }

        if (latestVideo.id.trimmed().isEmpty())
            latestVideo = latestPersistedVideoQueueItem(resolveProjectRoot());

        if (!latestVideo.id.trimmed().isEmpty())
        {
            selectionText = latestVideo.videoDurationLabel.trimmed().isEmpty()
                                ? QStringLiteral("Latest completed video")
                                : QStringLiteral("Latest video • %1").arg(latestVideo.videoDurationLabel.trimmed());
            bodyText = QStringLiteral("Latest completed video output is ready for review.\n%1\n%2")
                           .arg(videoQueueSummary(latestVideo).isEmpty() ? QStringLiteral("Video metadata is available in the queue item.") : videoQueueSummary(latestVideo),
                                queueOutputFileStatus(latestVideo.outputPath));
            if (!latestVideo.metadataPath.trimmed().isEmpty())
                bodyText += QStringLiteral("\n%1").arg(queueMetadataFileStatus(latestVideo.metadataPath));
            const QString runtimeFacts = runtimeDiagnosticsSummary(latestVideo);
            if (!runtimeFacts.isEmpty())
                bodyText += QStringLiteral("\n") + runtimeFacts;
            configureDetailsActions(QStringLiteral("queue:open_latest_video"), QStringLiteral("Open Video"),
                                    QStringLiteral("queue:reveal_latest_video"), QStringLiteral("Reveal Folder"),
                                    QStringLiteral("toggle:queue"), QStringLiteral("Show Queue"));
        }
        else
        {
            configureDetailsActions(QStringLiteral("mode:i2i"), QStringLiteral("Send to I2I"),
                                    QStringLiteral("toggle:queue"), QStringLiteral("Show Queue"),
                                    QStringLiteral("mode:home"), QStringLiteral("Go Home"));
        }
    }
    else if (currentModeId_ == QStringLiteral("inspiration"))
    {
        selectionText = QStringLiteral("Moodboard");
        bodyText = QStringLiteral("Curated inspiration should route back into Home or directly into prompt-first generation without bloating the shell.");
        configureDetailsActions(QStringLiteral("mode:t2i"), QStringLiteral("Open T2I"),
                                QStringLiteral("manager:workflows"), QStringLiteral("Open Workflows"),
                                QStringLiteral("mode:home"), QStringLiteral("Send to Home"));
    }
    else if (currentModeId_ == QStringLiteral("models"))
    {
        selectionText = QStringLiteral("Model library");
        bodyText = QStringLiteral("Manage checkpoints, LoRAs, and dependencies here while creation pages stay focused on the active stack.");
        configureDetailsActions(QStringLiteral("manager:downloads"), QStringLiteral("Open Downloads"),
                                QStringLiteral("manager:settings"), QStringLiteral("Open Settings"),
                                QStringLiteral("mode:home"), QStringLiteral("Go Home"));
    }
    else if (currentModeId_ == QStringLiteral("settings"))
    {
        selectionText = QStringLiteral("Preferences");
        bodyText = QStringLiteral("Tune appearance, workspace behavior, and integrations without pushing configuration controls into creation pages.");
        configureDetailsActions(QStringLiteral("manager:models"), QStringLiteral("Open Models"),
                                QStringLiteral("mode:home"), QStringLiteral("Go Home"),
                                QStringLiteral("manager:workflows"), QStringLiteral("Open Workflows"));
    }

    detailsBodyLabel_->setText(bodyText);
    if (detailsContextValueLabel_)
        detailsContextValueLabel_->setText(contextText);
    if (detailsSelectionValueLabel_)
        detailsSelectionValueLabel_->setText(selectionText);
    if (detailsQueueValueLabel_)
        detailsQueueValueLabel_->setText(QStringLiteral("%1 running • %2 pending").arg(runningCount).arg(pendingCount));
    if (detailsStatusValueLabel_)
        detailsStatusValueLabel_->setText(failedCount > 0 ? QStringLiteral("%1 errors need review").arg(failedCount) : QStringLiteral("Ready"));
}

QString MainWindow::pageContextForMode(const QString &modeId) const
{
    return spellvision::shell::ShellNavigationController::pageContextForMode(modeId);
}

void MainWindow::updateModeButtonState(const QString &modeId)
{
    spellvision::shell::ShellNavigationController::updateModeButtonState(modeButtons_, modeId);
}


void MainWindow::updateActiveQueueStrip()
{
    // Pass 28O:
    // The old implementation scanned the global queue and rewrote active strip
    // labels on every poll. That caused the expanded bottom tray to breathe and
    // could surface stale T2V/LTX rows while the user was on T2I.
    //
    // Queue strip ownership now lives in applyQueuePresentationForCurrentMode().
    applyQueuePresentationForCurrentMode();
}


QString MainWindow::selectedQueueId() const
{

    return spellvision::shell::QueueUiPresenter::selectedQueueId(queueTableView_);
}

void MainWindow::updateDetailsPanelForQueueSelection()
{
    if (!detailsTitleLabel_ || !detailsBodyLabel_ || !queueManager_)
        return;

    const QString id = selectedQueueId();
    if (id.isEmpty())
    {
        updateDetailsPanelForModeContext();
        return;
    }

    const QueueItem item = queueManager_->itemById(id);
    detailsTitleLabel_->setText(QStringLiteral("%1 • %2").arg(item.command, queueStateDisplay(item.state)));

    QString bodyText = QStringLiteral("%1\nModel: %2")
                           .arg(summarizePrompt(item.prompt))
                           .arg(item.model.trimmed().isEmpty() ? QStringLiteral("none") : item.model);

    const bool videoItem = isVideoQueueItem(item);
    if (videoItem)
    {
        const QString videoFacts = videoQueueSummary(item);
        if (!videoFacts.isEmpty())
            bodyText += QStringLiteral("\n") + videoFacts;
        const QString runtimeFacts = runtimeDiagnosticsSummary(item);
        if (!runtimeFacts.isEmpty())
            bodyText += QStringLiteral("\n") + runtimeFacts;
    }

    if (!item.outputPath.trimmed().isEmpty())
        bodyText += QStringLiteral("\n%1").arg(queueOutputFileStatus(item.outputPath));
    if (!item.metadataPath.trimmed().isEmpty())
        bodyText += QStringLiteral("\n%1").arg(queueMetadataFileStatus(item.metadataPath));

    if (!item.statusText.trimmed().isEmpty())
        bodyText += QStringLiteral("\nStatus note: %1").arg(item.statusText);
    detailsBodyLabel_->setText(bodyText);

    if (detailsContextValueLabel_)
        detailsContextValueLabel_->setText(pageContextForMode(currentModeId_));
    if (detailsSelectionValueLabel_)
        detailsSelectionValueLabel_->setText(videoItem && !item.videoDurationLabel.trimmed().isEmpty()
                                                 ? QStringLiteral("%1 • %2").arg(item.command, item.videoDurationLabel.trimmed())
                                                 : item.command);
    if (detailsQueueValueLabel_)
        detailsQueueValueLabel_->setText(item.id);
    if (detailsStatusValueLabel_)
    {
        QString status = QStringLiteral("%1 • %2%%")
                             .arg(queueStateDisplay(item.state))
                             .arg(item.progressPercent());
        if (videoItem && !item.outputPath.trimmed().isEmpty())
            status += QStringLiteral(" • Output ready");
        const QString memoryMode = runtimeMemoryModeLabel(item);
        if (videoItem && !memoryMode.isEmpty())
            status += QStringLiteral(" • %1").arg(memoryMode);
        detailsStatusValueLabel_->setText(status);
    }

    if (item.isTerminal())
    {
        if (videoItem && !item.outputPath.trimmed().isEmpty())
        {
            configureDetailsActions(QStringLiteral("queue:openoutput"), QStringLiteral("Open Video"),
                                    QStringLiteral("queue:revealfolder"), QStringLiteral("Reveal Folder"),
                                    QStringLiteral("manager:history"), QStringLiteral("Open History"));
        }
        else
        {
            configureDetailsActions(QStringLiteral("queue:duplicate"), QStringLiteral("Duplicate Job"),
                                    QStringLiteral("mode:i2i"), QStringLiteral("Send to I2I"),
                                    QStringLiteral("manager:history"), QStringLiteral("Open History"));
        }
    }
    else
    {
        configureDetailsActions(QStringLiteral("queue:moveup"), QStringLiteral("Move Up"),
                                QStringLiteral("queue:duplicate"), QStringLiteral("Duplicate Job"),
                                QStringLiteral("toggle:queue"), QStringLiteral("Focus Queue"));
    }
}
