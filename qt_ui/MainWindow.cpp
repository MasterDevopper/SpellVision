#include "MainWindow.h"

#include "CommandPaletteDialog.h"
#include "CustomTitleBar.h"
#include "HomePage.h"
// --- CHAIN STUDIO PASS 7C-PRELUDE RAIL ENTRY ---
#include "chain/ChainStudioPage.h"
#include "studios/CharacterStudioPage.h"
#include "studios/ComicStudioPage.h"
#include "studios/ConceptReferencePage.h"
#include "ImageGenerationPage.h"
#include "widgets/GlowProgressBar.h"
#include "ModePage.h"
#include "InspirationPage.h"
#include "Gen3DPage.h"
#include "ManagerPage.h"
#include "TrainPage.h"
#include "ModelManagerPage.h"
#include "DatasetGenerationPage.h"
#include "QueueFilterProxyModel.h"
#include "QueueManager.h"
#include "QueueTableModel.h"
#include "SettingsPage.h"
#include "T2VHistoryPage.h"
#include "ThemeManager.h"
#include "assets/AssetCatalogScanner.h"
#include "WorkflowImportDialog.h"
#include "WorkflowLibraryPage.h"
#include "workflows/WorkflowLaunchController.h"
#include "shell/FirstRunDialog.h"
#include "shell/GpuMemoryProbe.h"
#include "shell/RuntimeProfile.h"
#include "shell/SecureCredentialStore.h"
#include "assets/FamilyLicense.h"
#include "shell/MainWindowTrayController.h"
#include "shell/QueueUiPresenter.h"
#include "shell/ShellNavigationController.h"
#include "workers/WorkerQueueController.h"
#include "workers/WorkerSocketClient.h"
#include "workers/WorkerSubmissionPolicy.h"
#include "generation/OutputPathHelpers.h"

#include <QAbstractButton>
#include <QAbstractItemView>
#include <QAbstractItemModel>
#include <QAction>
#include <QClipboard>
#include <QCoreApplication>
#include <QDesktopServices>

#include <QColor>
#include <QDir>
#include <QGuiApplication>
#include <QCursor>
#include <QScreen>
#include <QSaveFile>
#include <QEvent>
#include <QPalette>
#include <QResizeEvent>
#include <QSettings>
#include <QShowEvent>
#include <QFileInfo>
#include <QFontMetrics>
#include <QFile>
#include <QItemSelectionModel>
#include <QIODevice>
#include <QUuid>
#include <QUrl>
#include <QTimer>
#include <QProcessEnvironment>
#include <QProcess>
#include <QPointer>
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
#include <QElapsedTimer>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QDockWidget>
#include <QFrame>
#include <QGridLayout>
#include <QHash>
#include <QIcon>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QKeySequence>
#include <QLabel>
#include <QLineEdit>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QSvgRenderer>
#include <QMenu>
#include <QMessageBox>

#include <initializer_list>
#include <QProgressBar>
#include <QScrollArea>
#include <QSizePolicy>
#include <QPushButton>
#include <QStatusBar>
#include <QStandardPaths>
#include <QTabWidget>
#include <QTableView>
#include <QTextEdit>
#include <QTcpSocket>

#include <QTime>
#include <QFont>

#include <QToolButton>
#include <QSplitter>
#include <QVBoxLayout>
#include <QWidget>

#include <memory>
#include <utility>
#include <algorithm>
#include <functional>
#include <limits>

#ifdef Q_OS_WIN
#include <windows.h>
#include <windowsx.h>
#include <dwmapi.h>
#endif

namespace
{

constexpr qint64 kStudioOutputSettleMs = 3000;
constexpr int kWorkerReadinessDeadlineMs = 30000;
constexpr int kComfyReadinessDeadlineMs = 90000;
constexpr int kRuntimeTerminateGraceMs = 2000;

QString comfyRuntimeStateRoot()
{
    QString root = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    if (root.trimmed().isEmpty())
        root = QDir::temp().filePath(QStringLiteral("SpellVision"));
    return QDir(root).filePath(QStringLiteral("runtime"));
}

QString comfyRuntimeSessionPath()
{
    return QDir(comfyRuntimeStateRoot()).filePath(QStringLiteral("comfy_runtime.session.json"));
}

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

// Basename of a model/LoRA path for the telemetry bar ("none" when empty). Harvested from the now-
// deleted BottomTelemetryPresenter::shortAssetName so that dead twin can go.
QString telemetryShortAssetName(const QString &value)
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return QStringLiteral("none");
    const QFileInfo info(trimmed);
    const QString baseName = info.completeBaseName().trimmed();
    if (!baseName.isEmpty())
        return baseName;
    const QString fileName = info.fileName().trimmed();
    return fileName.isEmpty() ? trimmed : fileName;
}

// "ETA: 12s" / "ETA: 1m30s" / "ETA: 1h05m" from a remaining-milliseconds estimate. Rounds seconds up
// so the readout never shows 0s while work is still in flight.
QString telemetryFormatEta(qint64 remainingMs)
{
    if (remainingMs < 0)
        remainingMs = 0;
    const qint64 totalSec = (remainingMs + 999) / 1000;
    if (totalSec >= 3600)
    {
        const qint64 h = totalSec / 3600;
        const qint64 m = (totalSec % 3600) / 60;
        return QStringLiteral("ETA: %1h%2m").arg(h).arg(m, 2, 10, QLatin1Char('0'));
    }
    if (totalSec >= 60)
    {
        const qint64 m = totalSec / 60;
        const qint64 s = totalSec % 60;
        return QStringLiteral("ETA: %1m%2s").arg(m).arg(s, 2, 10, QLatin1Char('0'));
    }
    return QStringLiteral("ETA: %1s").arg(totalSec);
}

// Set a fixed-width telemetry label: middle/right-elide long values to the label width (no more hard
// clip) and mirror the full value into the tooltip. setTip=false preserves a label's existing tooltip.
void applyTelemetryText(QLabel *label, const QString &full, bool elide, bool setTip)
{
    if (!label)
        return;
    QString shown = full;
    if (elide)
    {
        const int avail = label->width() - 6;
        if (avail > 0)
            shown = label->fontMetrics().elidedText(full, Qt::ElideRight, avail);
    }
    if (label->text() != shown)
        label->setText(shown);
    if (setTip && label->toolTip() != full)
        label->setToolTip(full);
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

    QStringList railIconSearchRoots()
    {
        QStringList roots;
        const QString appDir = QCoreApplication::applicationDirPath();
        roots << appDir
              << QDir(appDir).filePath(QStringLiteral("icons"))
              << QDir(appDir).filePath(QStringLiteral("../icons"))
              << QDir(appDir).filePath(QStringLiteral("../../qt_ui/icons"))
              << QDir(appDir).filePath(QStringLiteral("../../../qt_ui/icons"))
              << QDir::current().filePath(QStringLiteral("qt_ui/icons"))
              << QDir::current().filePath(QStringLiteral("icons"));
        // Walk up from app dir for source-tree qt_ui/icons during Debug runs.
        QDir climb(appDir);
        for (int i = 0; i < 6; ++i) {
            const QString candidate = climb.filePath(QStringLiteral("qt_ui/icons"));
            if (QDir(candidate).exists())
                roots << candidate;
            if (!climb.cdUp())
                break;
        }
        roots.removeDuplicates();
        return roots;
    }

    // The rail SVGs are authored with one fixed light stroke (#dfe6ef), which is
    // ~1.1:1 against the Ivory Holograph surfaces -- i.e. invisible on the light
    // preset. Re-ink them from the active theme instead of shipping per-theme
    // asset pairs. Mirrors what CustomTitleBar::applyThemeStyling already does
    // for its painted chrome glyphs.
    QIcon tintedRailSvg(const QString &path)
    {
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly))
            return {};
        QByteArray svg = file.readAll();
        file.close();
        if (svg.isEmpty())
            return {};

        const QByteArray ink =
            ThemeManager::instance().color(ThemeManager::Color::TextMid).name(QColor::HexRgb).toUtf8();
        svg.replace(QByteArrayLiteral("#dfe6ef"), ink);
        svg.replace(QByteArrayLiteral("#DFE6EF"), ink);
        svg.replace(QByteArrayLiteral("currentColor"), ink);

        QSvgRenderer renderer(svg);
        if (!renderer.isValid())
            return {};

        // Rail draws at 18px; carry 2x/3x frames so HiDPI stays crisp.
        QIcon icon;
        for (int px : {18, 24, 36, 54}) {
            QPixmap pm(px, px);
            pm.fill(Qt::transparent);
            QPainter painter(&pm);
            painter.setRenderHint(QPainter::Antialiasing, true);
            renderer.render(&painter);
            painter.end();
            icon.addPixmap(pm);
        }
        return icon;
    }

    QIcon loadRailIcon(const QString &modeId)
    {
        // Map modeId → icon basename (SVG under qt_ui/icons/).
        static const QHash<QString, QString> kIconByMode = {
            {QStringLiteral("home"), QStringLiteral("home")},
            {QStringLiteral("chain"), QStringLiteral("chain")},
            {QStringLiteral("t2i"), QStringLiteral("t2i")},
            {QStringLiteral("i2i"), QStringLiteral("i2i")},
            {QStringLiteral("t2v"), QStringLiteral("t2v")},
            {QStringLiteral("i2v"), QStringLiteral("i2v")},
            {QStringLiteral("character"), QStringLiteral("character")},
            {QStringLiteral("concept"), QStringLiteral("concept")},
            {QStringLiteral("comic"), QStringLiteral("comic")},
            {QStringLiteral("gen3d"), QStringLiteral("gen3d")},
            {QStringLiteral("dataset"), QStringLiteral("dataset")},
            {QStringLiteral("workflows"), QStringLiteral("workflows")},
            {QStringLiteral("history"), QStringLiteral("history")},
            {QStringLiteral("inspiration"), QStringLiteral("inspiration")},
            {QStringLiteral("models"), QStringLiteral("models")},
            {QStringLiteral("settings"), QStringLiteral("settings")},
            {QStringLiteral("runtime"), QStringLiteral("runtime")},
            {QStringLiteral("train"), QStringLiteral("train")},
        };

        const QString base = kIconByMode.value(modeId.trimmed().toLower(), modeId.trimmed().toLower());
        if (base.isEmpty())
            return {};

        const QStringList exts = {QStringLiteral("svg"), QStringLiteral("png")};
        for (const QString &root : railIconSearchRoots()) {
            for (const QString &ext : exts) {
                const QString path = QDir(root).filePath(base + QLatin1Char('.') + ext);
                if (QFileInfo::exists(path)) {
                    if (ext == QLatin1String("svg")) {
                        const QIcon tinted = tintedRailSvg(path);
                        if (!tinted.isNull())
                            return tinted;
                    }
                    QIcon icon(path);
                    if (!icon.isNull())
                        return icon;
                }
            }
        }
        return {};
    }

    QToolButton *createRailButton(const QString &modeId,
                                  const QString &text,
                                  const QString &toolTip,
                                  QWidget *parent = nullptr)
    {
        auto *button = new QToolButton(parent);
        button->setObjectName(QStringLiteral("SideRailButton"));
        button->setText(text);
        button->setToolTip(toolTip);
        button->setCheckable(true);
        button->setAutoRaise(true);
        button->setFixedSize(56, 48); // icon + label room
        button->setIconSize(QSize(18, 18));
        button->setToolButtonStyle(Qt::ToolButtonTextUnderIcon);
        button->setCursor(Qt::PointingHandCursor);

        const QIcon icon = loadRailIcon(modeId);
        if (!icon.isNull())
            button->setIcon(icon);
        else
            button->setToolButtonStyle(Qt::ToolButtonTextOnly); // graceful fallback

        // Pre-empt the Qt-internal "QFont::setPointSize: Point size <= 0"
        // warning that fires on rail-button :hover recompute. The shell
        // stylesheet sets font-size: 12px (a PIXEL size) on
        // QToolButton#SideRailButton; giving the button's QFont an explicit
        // pixelSize here means Qt's hover restyle reads a valid size instead
        // of the -1 "unset point size" sentinel. 12px matches the stylesheet,
        // so this is visually a no-op.
        QFont railButtonFont = button->font();
        railButtonFont.setPixelSize(10); // slightly tighter under-icon labels
        button->setFont(railButtonFont);

        return button;
    }

    QFrame *createDockHeaderFrame(const QString &objectName, QWidget *parent = nullptr)
    {
        auto *frame = createPanelFrame(objectName, parent);
        frame->setFixedHeight(34);
        return frame;
    }

    QString defaultManagedComfyRoot(const QString &)
        {
            const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_COMFY")).trimmed();
            if (!envPath.isEmpty())
                return QDir::fromNativeSeparators(QDir(envPath).absolutePath());

            QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
            const QString configured = settings.value(QStringLiteral("runtime/comfyRoot")).toString().trimmed();
            if (!configured.isEmpty())
                return QDir::fromNativeSeparators(QDir(configured).absolutePath());

            return {};
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
        const bool light = ThemeManager::instance().preset() == ThemeManager::Preset::IvoryHolograph;
        const QString stem = light ? QStringLiteral("SpellVision_Light") : QStringLiteral("SpellVision_Dark");
        QStringList starts = {QCoreApplication::applicationDirPath(), QDir::currentPath()};
        // PNG before ICO on purpose: QPixmap reads image index 0 of a .ico, and
        // our ico directories start at 16x16 -- loading those first gave a 16px
        // source that then got upscaled into the 22px title-bar badge and the
        // window icon. The PNGs are 256x256.
        QStringList names = {
            QStringLiteral("icons/%1.png").arg(stem),
            QStringLiteral("icons/%1.ico").arg(stem),
            QStringLiteral("qt_ui/icons/%1.png").arg(stem),
            QStringLiteral("qt_ui/icons/%1.ico").arg(stem),
            QStringLiteral("%1.png").arg(stem),
            QStringLiteral("%1.ico").arg(stem),
            QStringLiteral("icons/SpellVision.png"),
            QStringLiteral("icons/SpellVision.ico"),
            QStringLiteral("qt_ui/icons/SpellVision.png"),
            QStringLiteral("qt_ui/icons/SpellVision.ico"),
            QStringLiteral("SpellVision.png"),
            QStringLiteral("SpellVision.ico")};

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
        QPen border(ThemeManager::instance().color(ThemeManager::Color::Border)); // was stale blue #7f93dc
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

    QJsonObject sendWorkerRequestForRuntime(const QString &projectRoot,
                                            const QString &pythonExecutable,
                                            const QJsonObject &request,
                                            QString *stderrText,
                                            bool *startedOk,
                                            int timeoutMs)
    {
        if (stderrText)
            stderrText->clear();
        if (startedOk)
            *startedOk = false;

        const QString workerClient = QDir(projectRoot).filePath(QStringLiteral("python/worker_client.py"));
        QProcess process;
        process.setProgram(pythonExecutable);
        process.setArguments({workerClient});
        process.setWorkingDirectory(projectRoot);
        process.setProcessEnvironment(QProcessEnvironment::systemEnvironment());
        process.setProcessChannelMode(QProcess::SeparateChannels);
        process.start();

        const int effectiveTimeoutMs = timeoutMs > 0 ? timeoutMs : 120000;
        const bool started = process.waitForStarted(qMin(effectiveTimeoutMs, 5000));
        if (startedOk)
            *startedOk = started;
        if (!started)
        {
            if (stderrText)
                *stderrText = process.errorString();
            return {};
        }

        QByteArray payload = QJsonDocument(request).toJson(QJsonDocument::Compact);
        payload.append('\n');
        QStringList diagnostics;
        if (process.write(payload) != payload.size())
        {
            diagnostics << QStringLiteral("Failed to write complete worker request payload.");
            process.kill();
            process.waitForFinished(1000);
        }
        else
        {
            process.waitForBytesWritten(qMin(effectiveTimeoutMs, 1000));
            process.closeWriteChannel();
            if (!process.waitForFinished(effectiveTimeoutMs))
            {
                diagnostics << QStringLiteral("Worker process timed out while waiting for a response.");
                process.kill();
                process.waitForFinished(1000);
            }
        }

        const QByteArray stdoutBytes = process.readAllStandardOutput();
        const QString processStderr = QString::fromUtf8(process.readAllStandardError()).trimmed();
        if (!processStderr.isEmpty())
            diagnostics << processStderr;
        if (process.exitStatus() != QProcess::NormalExit)
            diagnostics << QStringLiteral("Worker process crashed.");
        if (process.exitCode() != 0)
            diagnostics << QStringLiteral("Worker process exited with code %1.").arg(process.exitCode());
        if (stdoutBytes.size() > 8 * 1024 * 1024)
        {
            diagnostics << QStringLiteral("Worker response exceeded 8 MiB limit.");
            if (stderrText)
                *stderrText = diagnostics.join(QChar('\n'));
            return {};
        }

        QString parseError;
        const QJsonObject response = parseLastJsonObjectFromStdout(
            QString::fromUtf8(stdoutBytes), &parseError);
        if (response.isEmpty() && !parseError.trimmed().isEmpty())
            diagnostics << parseError.trimmed();
        if (stderrText)
            *stderrText = diagnostics.join(QChar('\n'));
        return response;
    }

    QHash<QString, QString> classifyModelsViaWorkerRuntime(const QString &projectRoot,
                                                           const QString &pythonExecutable,
                                                           const QStringList &paths)
    {
        QHash<QString, QString> byPath;
        if (paths.isEmpty())
            return byPath;
        QJsonObject request;
        request.insert(QStringLiteral("command"), QStringLiteral("classify_models"));
        request.insert(QStringLiteral("paths"), QJsonArray::fromStringList(paths));
        bool startedOk = false;
        const QJsonObject response = sendWorkerRequestForRuntime(
            projectRoot, pythonExecutable, request, nullptr, &startedOk, 12000);
        if (!startedOk || !response.value(QStringLiteral("ok")).toBool(false))
            return byPath;
        const QJsonArray items = response.value(QStringLiteral("classifications")).toArray();
        for (const QJsonValue &value : items)
        {
            const QJsonObject entry = value.toObject();
            const QString path = entry.value(QStringLiteral("path")).toString();
            const QString family = entry.value(QStringLiteral("family")).toString();
            if (!path.isEmpty() && !family.isEmpty())
                byPath.insert(path, family);
        }
        return byPath;
    }
}

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    QFile ctorLog(QDir::currentPath() + QStringLiteral("/build/ui_startup_trace.log"));
    if (ctorLog.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text)) {
        QTextStream s(&ctorLog);
        s << "MainWindow ctor start\n";
        s.flush();
    }
    setObjectName(QStringLiteral("MainWindow"));
    setWindowTitle(QStringLiteral("SpellVision"));
    const QPixmap brandWindowIcon = loadBrandPixmap();
    if (!brandWindowIcon.isNull())
        setWindowIcon(QIcon(brandWindowIcon));
    setWindowFlags(Qt::Window | Qt::FramelessWindowHint | Qt::CustomizeWindowHint | Qt::WindowSystemMenuHint | Qt::WindowMinimizeButtonHint | Qt::WindowMaximizeButtonHint | Qt::WindowCloseButtonHint);
    setDockNestingEnabled(true);

    // ComfyUI is launched detached (Popen CREATE_NEW_PROCESS_GROUP) and no window-close path
    // tears it down, so it orphans holding :8188 + GPU. aboutToQuit fires on EVERY quit path
    // (close button, Alt+F4, menu Quit, QApplication::quit), so one hook covers them all.
    connect(qApp, &QCoreApplication::aboutToQuit, this, &MainWindow::tearDownComfyOnExit);

    queueManager_ = new QueueManager(this);
    connect(queueManager_, &QueueManager::queueChanged, this, &MainWindow::onQueueChanged);

    workerQueueController_ = new spellvision::workers::WorkerQueueController(this);
    spellvision::workers::WorkerQueueController::Bindings queueBindings;
    queueBindings.queueManager = queueManager_;
    queueBindings.sendRequestAsync = [this](
                                              const QJsonObject &request,
                                              spellvision::workers::WorkerQueueController::Bindings::RequestCompletion completion) {
        sendWorkerRequestAsync(request, std::move(completion));
    };
    queueBindings.appendLogLine = [this](const QString &text) {
        appendLogLine(text);
    };
    queueBindings.afterQueueSnapshotApplied = [this]() {
        syncGenerationPreviewsFromQueue();
        syncStudioPreviewsFromQueue();
        syncBottomTelemetry();

        // Pass 28N:
        // syncBottomTelemetry() reports global queue state. Re-apply the
        // mode-scoped queue presentation after telemetry sync so T2I/I2I keep
        // the visible-row count and stable ledger presentation.
        applyQueuePresentationForCurrentMode();
    };
    workerQueueController_->bind(queueBindings);
    // BREAK 2: a failed queue poll (worker unreachable) was emitted but connected to nothing —
    // surface it on the current generation page so worker-down isn't invisible.
    connect(workerQueueController_, &spellvision::workers::WorkerQueueController::queuePollFailed,
            this, [this](const QString &message) {
                Q_UNUSED(message); // already routed to the log by the controller's logLine
                workerReachable_ = false; // reset the latch: a later up-edge must re-scan again
            });
    connect(workerQueueController_, &spellvision::workers::WorkerQueueController::queueConnectivityLost,
            this, [this](const QString &message) {
                workerReachable_ = false;
                resetSubmissionTelemetry();
                if (ImageGenerationPage *page = generationPageForMode(currentModeId_))
                    page->showGenerationError(
                        message.trimmed().isEmpty()
                            ? QStringLiteral("Worker disappeared — generation stopped.")
                            : message);
            });
    // Detection-accelerator cold-start race: image pages built before the worker
    // bound :8765 scanned with the fallback matcher. Re-scan them once when the
    // worker becomes reachable so the displayed family matches classifier routing.
    // Use queuePollSucceeded (fires on any valid poll) NOT queueResponseApplied
    // (fires only on a queue CHANGE -> misses the worker coming up with an empty queue).
    connect(workerQueueController_, &spellvision::workers::WorkerQueueController::queuePollSucceeded,
            this, &MainWindow::onWorkerQueueReachable);

    resetSubmissionTelemetry();
    // See the note on pageTrace in buildPages(): env-gated, and timed so it can attribute cost.
    static const bool ctorTraceEnabled = qEnvironmentVariableIsSet("SPELLVISION_STARTUP_TRACE");
    QElapsedTimer ctorClock;
    ctorClock.start();
    qint64 ctorLast = 0;
    auto ctorTrace = [&ctorClock, &ctorLast](const char *label) {
        if (!ctorTraceEnabled)
            return;
        const qint64 now = ctorClock.elapsed();
        const qint64 delta = now - ctorLast;
        ctorLast = now;
        QFile f(QDir::currentPath() + QStringLiteral("/build/ui_startup_trace.log"));
        if (f.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text)) {
            QTextStream s(&f);
            s << QStringLiteral("%1  +%2ms  (t=%3ms)\n")
                     .arg(QString::fromUtf8(label), -34)
                     .arg(delta, 6)
                     .arg(now, 6);
            s.flush();
        }
    };
    ctorTrace("ctor after resetTelemetry");
    ensureWorkerServiceAvailable();
    ctorTrace("ctor after ensureWorker");
    ensureComfyRuntimeAvailable();
    ctorTrace("ctor after ensureComfy");
    workerQueueController_->startPolling(1800);
    ctorTrace("ctor after startPolling");

    // Detection accelerator (option A): install the worker-backed model-family
    // classifier BEFORE any page (and thus any catalog scan) is built, so the Qt
    // scanner consults the one layered classifier instead of its substring guess.
    const QString classifierProjectRoot = resolveProjectRoot();
    const QString classifierPythonExecutable = resolvePythonExecutable();
    spellvision::assets::setModelFamilyClassifier(
        [classifierProjectRoot, classifierPythonExecutable](const QStringList &paths) {
            return classifyModelsViaWorkerRuntime(
                classifierProjectRoot, classifierPythonExecutable, paths);
        });

    ctorTrace("ctor before buildShell");
    buildShell();
    ctorTrace("ctor after buildShell");
    buildPages();
    ctorTrace("ctor after buildPages");
    buildPersistentDocks();
    ctorTrace("ctor after buildPersistentDocks");
    buildBottomTelemetryBar();
    ctorTrace("ctor after buildBottomTelemetryBar");
    {
        QSettings disclosureSettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        setDisclosureMode(disclosureSettings.value(QStringLiteral("ui/advancedMode"), false).toBool());
    }
    QString startMode = QStringLiteral("home");
    {
        QSettings lastModeSettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        const QString lastMode = lastModeSettings.value(QStringLiteral("ui/lastModeId")).toString().trimmed();
        if (!lastMode.isEmpty())
            startMode = lastMode;
    }
    switchToMode(startMode);
    ctorTrace("ctor after switchToMode");
    setMinimumSize(1180, 760);
    resize(1760, 1020);
    if (QScreen *screen = QGuiApplication::screenAt(QCursor::pos()))
    {
        const QRect available = screen->availableGeometry();
        const QSize size(qMin(width(), available.width()), qMin(height(), available.height()));
        resize(size);
        move(available.x() + (available.width() - size.width()) / 2,
             available.y() + (available.height() - size.height()) / 2);
    }
    ctorTrace("ctor after geometry");

    QSettings firstRunSettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    if (!firstRunSettings.value(QStringLiteral("setup/firstRunWizard_v1"), false).toBool())
    {
        QTimer::singleShot(2000, this, [this]() {
            spellvision::shell::FirstRunDialog dialog(
                resolveProjectRoot(),
                ownedWorkerServiceProcess_ && ownedWorkerServiceProcess_->state() == QProcess::Running && !probeWorkerService(200),
                ownedComfyProcess_ && ownedComfyProcess_->state() == QProcess::Running && !probeComfyRuntime(200),
                this);
            if (dialog.exec() != QDialog::Accepted)
                return;

            if (dialog.suppressFuturePrompts())
            {
                QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
                settings.setValue(QStringLiteral("setup/firstRunWizard_v1"), true);
            }

            if (dialog.action() == spellvision::shell::FirstRunDialog::Action::OpenRuntime)
                switchToMode(QStringLiteral("runtime"));
            if (t2iPage_)
            {
                t2iPage_->rescanModelCatalog();
                t2iPage_->applyPersistedOutputFolder();
            }
            if (i2iPage_)
            {
                i2iPage_->rescanModelCatalog();
                i2iPage_->applyPersistedOutputFolder();
            }
        });
    }
    ctorTrace("ctor before end");
    {
        QFile ctorLog(QDir::currentPath() + QStringLiteral("/build/ui_startup_trace.log"));
        if (ctorLog.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text)) {
            QTextStream s(&ctorLog);
            s << "MainWindow ctor end\n";
            s.flush();
        }
    }
}

MainWindow::~MainWindow()
{
    stopOwnedWorkerService();
}

bool MainWindow::probeWorkerService(int timeoutMs) const
{
    const spellvision::shell::RuntimeProfile profile = spellvision::shell::RuntimeProfile::load(resolveProjectRoot());
    return spellvision::shell::probeWorkerProtocol(profile.workerHost, profile.workerPort, timeoutMs);
}

void MainWindow::ensureWorkerServiceAvailable()
{
    const spellvision::shell::RuntimeProfile profile = spellvision::shell::RuntimeProfile::load(resolveProjectRoot());

    // A successful protocol pong identifies a healthy SpellVision worker. Adopt it:
    // this session may stop only processes it starts itself.
    if (probeWorkerService(350))
        return;

    if (!profile.workerPythonReady() || !profile.workerScriptReady())
        return;

    auto *process = new QProcess(this);
    process->setWorkingDirectory(profile.projectRoot);

    QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
    environment.insert(QStringLiteral("PYTHONUNBUFFERED"), QStringLiteral("1"));
    environment.insert(QStringLiteral("PYTHONNOUSERSITE"), QStringLiteral("1"));
    environment.remove(QStringLiteral("PYTHONPATH"));
    environment.remove(QStringLiteral("PYTHONHOME"));
    environment.insert(QStringLiteral("VIRTUAL_ENV"), QFileInfo(profile.workerPython).dir().absolutePath() + QStringLiteral("/.."));
    profile.applyToProcessEnvironment(environment);
    process->setProcessEnvironment(environment);

    QString logRoot = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    if (logRoot.trimmed().isEmpty())
        logRoot = QDir(profile.projectRoot).filePath(QStringLiteral("build"));
    QDir(logRoot).mkpath(QStringLiteral("logs"));
    const QString logs = QDir(logRoot).filePath(QStringLiteral("logs"));
    process->setStandardOutputFile(QDir(logs).filePath(QStringLiteral("worker_service.stdout.log")), QIODevice::Append);
    process->setStandardErrorFile(QDir(logs).filePath(QStringLiteral("worker_service.stderr.log")), QIODevice::Append);

    ownedWorkerServiceProcess_ = process;
    workerReachable_ = false;
    connect(process, &QProcess::started, this, [this, process]() {
        QTimer::singleShot(kWorkerReadinessDeadlineMs, process, [this, process]() {
            if (ownedWorkerServiceProcess_ != process
                || process->state() == QProcess::NotRunning
                || workerReachable_)
                return;
            appendLogLine(QStringLiteral("Worker process started but failed to become ready within 30 seconds."));
            process->terminate();
            QTimer::singleShot(kRuntimeTerminateGraceMs, process, [this, process]() {
                if (ownedWorkerServiceProcess_ == process
                    && process->state() != QProcess::NotRunning)
                    process->kill();
            });
        });
    });
    connect(process,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this,
            [this, process](int, QProcess::ExitStatus) {
                if (ownedWorkerServiceProcess_ != process)
                    return;
                ownedWorkerServiceProcess_ = nullptr;
                if (workerQueueController_)
                    workerQueueController_->confirmWorkerLost(
                        QStringLiteral("Worker disappeared because the app-owned backend process exited."));
                process->deleteLater();
            });
    connect(process, &QProcess::errorOccurred, this,
            [this, process](QProcess::ProcessError error) {
                if (error != QProcess::FailedToStart || ownedWorkerServiceProcess_ != process)
                    return;
                ownedWorkerServiceProcess_ = nullptr;
                appendLogLine(QStringLiteral("Worker process failed to start: %1").arg(process->errorString()));
                process->deleteLater();
            });
    process->start(profile.workerPython, {profile.workerScript});
}

void MainWindow::stopOwnedWorkerService()
{
    if (!ownedWorkerServiceProcess_)
        return;

    QProcess *process = ownedWorkerServiceProcess_;
    ownedWorkerServiceProcess_ = nullptr;
    if (process->state() != QProcess::NotRunning)
    {
#ifdef Q_OS_WIN
        const qint64 processId = process->processId();
        if (processId > 0)
        {
            QProcess taskkill;
            taskkill.start(QStringLiteral("taskkill.exe"),
                           {QStringLiteral("/PID"), QString::number(processId),
                            QStringLiteral("/T"), QStringLiteral("/F")});
            taskkill.waitForFinished(3000);
            process->waitForFinished(1000);
        }
#else
        process->terminate();
        if (!process->waitForFinished(2000))
        {
            process->kill();
            process->waitForFinished(1000);
        }
#endif
    }
    delete process;
}

bool MainWindow::probeComfyRuntime(int timeoutMs) const
{
    const spellvision::shell::RuntimeProfile profile = spellvision::shell::RuntimeProfile::load(resolveProjectRoot());
    return spellvision::shell::probeComfyProtocol(profile.comfyHost, profile.comfyPort, timeoutMs);
}

bool MainWindow::writeComfySessionFile(bool adoptedExisting, qint64 pid) const
{
    const spellvision::shell::RuntimeProfile profile = spellvision::shell::RuntimeProfile::load(resolveProjectRoot());
    const QString stateRoot = comfyRuntimeStateRoot();
    if (!QDir().mkpath(stateRoot))
        return false;
    // When adopting an already-running ComfyUI we know nothing about which install it came from,
    // and recording the CONFIGURED root here would assert something we did not check. That is how
    // the session file came to claim the D:\ rollback build while :8188 was actually served from
    // C:\sv_comfynext -- the stored root simply never caught up with the cutover. Prefer the
    // launcher's record of the instance it started, which comes from the real command line.
    QString comfyRoot = profile.comfyRoot;
    QString comfyMain = profile.comfyMainPath();
    if (adoptedExisting)
    {
        const QString liveRoot = spellvision::shell::resolveLiveComfyRoot(
            profile.projectRoot, profile.comfyHost, profile.comfyPort);
        if (!liveRoot.isEmpty())
        {
            comfyRoot = liveRoot;
            comfyMain = QDir(liveRoot).filePath(QStringLiteral("main.py"));
        }
    }

    QJsonObject payload;
    payload.insert(QStringLiteral("pid"), static_cast<double>(pid));
    payload.insert(QStringLiteral("host"), profile.comfyHost);
    payload.insert(QStringLiteral("port"), profile.comfyPort);
    payload.insert(QStringLiteral("project_root"), profile.projectRoot);
    payload.insert(QStringLiteral("python_exe"), profile.comfyPython);
    payload.insert(QStringLiteral("comfy_root"), comfyRoot);
    payload.insert(QStringLiteral("comfy_main"), comfyMain);
    payload.insert(QStringLiteral("adopted_existing"), adoptedExisting);
    payload.insert(QStringLiteral("started_by_script"), false);
    payload.insert(QStringLiteral("started_by_app"), !adoptedExisting);
    payload.insert(QStringLiteral("healthy"), adoptedExisting || probeComfyRuntime(200));
    payload.insert(QStringLiteral("detected_at"), QDateTime::currentDateTimeUtc().toString(Qt::ISODate));
    const QByteArray data = QJsonDocument(payload).toJson(QJsonDocument::Indented);
    QSaveFile sessionFile(comfyRuntimeSessionPath());
    if (!sessionFile.open(QIODevice::WriteOnly))
        return false;
    if (sessionFile.write(data) != data.size())
    {
        sessionFile.cancelWriting();
        return false;
    }
    return sessionFile.commit();
}

void MainWindow::ensureComfyRuntimeAvailable()
{
    const spellvision::shell::RuntimeProfile profile = spellvision::shell::RuntimeProfile::load(resolveProjectRoot());
    if (probeComfyRuntime(350))
    {
        writeComfySessionFile(true, 0);
        return;
    }
    if (ownedComfyProcess_ && ownedComfyProcess_->state() != QProcess::NotRunning)
        return;
    if (!profile.comfyRootReady() || !profile.comfyMainReady() || !profile.comfyPythonReady())
        return;

    auto *process = new QProcess(this);
    process->setWorkingDirectory(profile.comfyRoot);
    QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
    environment.insert(QStringLiteral("PYTHONUNBUFFERED"), QStringLiteral("1"));
    environment.insert(QStringLiteral("PYTHONNOUSERSITE"), QStringLiteral("1"));
    environment.insert(QStringLiteral("PYTHONUTF8"), QStringLiteral("1"));
    environment.insert(QStringLiteral("PYTHONIOENCODING"), QStringLiteral("utf-8"));
    environment.remove(QStringLiteral("PYTHONPATH"));
    environment.remove(QStringLiteral("PYTHONHOME"));
    profile.applyToProcessEnvironment(environment);
    process->setProcessEnvironment(environment);

    const QString stateRoot = comfyRuntimeStateRoot();
    if (!QDir().mkpath(stateRoot))
    {
        process->deleteLater();
        return;
    }
    process->setStandardOutputFile(QDir(stateRoot).filePath(QStringLiteral("comfy_runtime.stdout.log")), QIODevice::Append);
    process->setStandardErrorFile(QDir(stateRoot).filePath(QStringLiteral("comfy_runtime.stderr.log")), QIODevice::Append);

    ownedComfyProcess_ = process;
    comfyReachable_ = false;
    comfyHealthProbed_ = false;
    connect(process, &QProcess::started, this, [this, process]() {
        if (ownedComfyProcess_ == process)
            writeComfySessionFile(false, process->processId());
        QTimer::singleShot(kComfyReadinessDeadlineMs, process, [this, process]() {
            if (ownedComfyProcess_ != process
                || process->state() == QProcess::NotRunning
                || comfyReachable_)
                return;
            appendLogLine(QStringLiteral("ComfyUI process started but failed to become ready within 90 seconds."));
            QFile::remove(comfyRuntimeSessionPath());
            process->terminate();
            QTimer::singleShot(kRuntimeTerminateGraceMs, process, [this, process]() {
                if (ownedComfyProcess_ == process
                    && process->state() != QProcess::NotRunning)
                    process->kill();
            });
        });
    });
    connect(process, &QProcess::errorOccurred, this,
            [this, process](QProcess::ProcessError error) {
                if (error != QProcess::FailedToStart || ownedComfyProcess_ != process)
                    return;
                ownedComfyProcess_ = nullptr;
                QFile::remove(comfyRuntimeSessionPath());
                appendLogLine(QStringLiteral("ComfyUI process failed to start: %1").arg(process->errorString()));
                process->deleteLater();
            });
    connect(process,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this,
            [this, process](int, QProcess::ExitStatus) {
                if (ownedComfyProcess_ != process)
                    return;
                ownedComfyProcess_ = nullptr;
                QFile::remove(comfyRuntimeSessionPath());
                process->deleteLater();
            });
    process->start(profile.comfyPython,
                   {profile.comfyMainPath(),
                    QStringLiteral("--listen"),
                    profile.comfyHost,
                    QStringLiteral("--port"),
                    QString::number(profile.comfyPort)});
}

void MainWindow::buildShell()
{
    titleBar_ = new CustomTitleBar(this);
    titleBar_->setObjectName(QStringLiteral("CustomTitleBar"));
    titleBar_->setWindowTitleText(QString());
    titleBar_->setContextText(QStringLiteral("Home"));

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
        const QPixmap brandWindowIcon = loadBrandPixmap();
        if (!brandWindowIcon.isNull()) {
            const QIcon brand(brandWindowIcon);
            setWindowIcon(brand);
            // Also set it application-wide so dialogs and the first-run wizard
            // -- top-levels MainWindow does not own -- stop showing the stock
            // Qt icon.
            QGuiApplication::setWindowIcon(brand);
        }

        // Rail glyphs are re-inked from the theme (see tintedRailSvg), so they
        // have to be regenerated on every switch -- a stylesheet reload does not
        // touch a QIcon. Empty on the first call; the rail is built afterwards.
        for (auto it = modeButtons_.constBegin(); it != modeButtons_.constEnd(); ++it) {
            const QIcon icon = loadRailIcon(it.key());
            if (icon.isNull() || !it.value())
                continue;
            it.value()->setIcon(icon);
            if (auto *toolButton = qobject_cast<QToolButton *>(it.value()))
                toolButton->setToolButtonStyle(Qt::ToolButtonTextUnderIcon);
        }
    };
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, applyTheme);
}

QWidget *MainWindow::createSideRail()
{
    auto &tm = ThemeManager::instance();
    const int snug = tm.spacing(ThemeManager::Spacing::Snug);
    const int card = tm.spacing(ThemeManager::Spacing::Card);

    // Outer rail: fixed width, brand badge PINNED at the top, and the mode column below it lives in a
    // QScrollArea so the rail SCROLLS instead of clipping the bottom entries once there are more pages
    // than fit the viewport (it was a plain non-scrolling QVBoxLayout with fixed-height buttons).
    auto *rail = new QWidget(this);
    rail->setObjectName(QStringLiteral("SideRail"));
    rail->setFixedWidth(ThemeManager::instance().chrome(ThemeManager::Chrome::ModeRailWidth));
    auto *railLayout = new QVBoxLayout(rail);
    railLayout->setContentsMargins(0, card, 0, card);
    railLayout->setSpacing(snug);

    // Brand lives in the title bar only — no second logo above Home.
    auto *scroll = new QScrollArea(rail);
    scroll->setObjectName(QStringLiteral("SideRailScroll"));
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll->setAutoFillBackground(false);
    scroll->viewport()->setAutoFillBackground(false); // let the #SideRail gradient show through
    // Thin, unobtrusive scrollbar in a neutral steel that reads on every theme (fixed, so it survives
    // theme switches without re-styling); keeps the 58px buttons uncrushed inside the 74px rail.
    scroll->setStyleSheet(QStringLiteral(
        "QScrollArea#SideRailScroll { background: transparent; border: none; }"
        "QWidget#SideRailColumn { background: transparent; }"
        "QScrollArea#SideRailScroll QScrollBar:vertical { width: 5px; background: transparent; margin: 2px 0; }"
        "QScrollArea#SideRailScroll QScrollBar::handle:vertical { background: rgba(140,146,173,0.45); border-radius: 2px; min-height: 24px; }"
        "QScrollArea#SideRailScroll QScrollBar::handle:vertical:hover { background: rgba(140,146,173,0.75); }"
        "QScrollArea#SideRailScroll QScrollBar::add-line:vertical, QScrollArea#SideRailScroll QScrollBar::sub-line:vertical { height: 0; }"
        "QScrollArea#SideRailScroll QScrollBar::add-page:vertical, QScrollArea#SideRailScroll QScrollBar::sub-page:vertical { background: transparent; }"));

    auto *column = new QWidget;
    column->setObjectName(QStringLiteral("SideRailColumn"));
    auto *layout = new QVBoxLayout(column);
    layout->setContentsMargins(snug, 0, snug, 0);
    layout->setSpacing(snug);

    const auto specs = spellvision::shell::ShellNavigationController::railButtonSpecs();

    // Flat rail — no CREATE/MANAGE/SYSTEM chrome. Mode buttons only; order already groups Create→Manage→System.
    for (const auto &spec : specs)
    {
        auto *button = createRailButton(spec.modeId, spec.text, spec.toolTip, column);
        // VSCode-style hover: the tooltip shows the name + shortcut, and the shortcut actually
        // navigates (window-wide). QAbstractButton::setShortcut fires click() -> switchToMode.
        if (!spec.shortcut.isEmpty())
        {
            const QKeySequence seq(spec.shortcut);
            button->setShortcut(seq);
            button->setToolTip(QStringLiteral("%1  (%2)").arg(spec.toolTip, seq.toString(QKeySequence::NativeText)));
        }
        connect(button, &QToolButton::clicked, this, [this, spec]()
                { switchToMode(spec.modeId); });
        layout->addWidget(button, 0, Qt::AlignHCenter);
        modeButtons_.insert(spec.modeId, button);
    }

    layout->addStretch(1);
    scroll->setWidget(column);
    railLayout->addWidget(scroll, 1);
    return rail;
}

void MainWindow::buildPages()
{
    // Startup trace. Off unless SPELLVISION_STARTUP_TRACE is set: this used to open, append,
    // flush and close the log on every one of ~25 calls, on the startup critical path, in every
    // build. It also recorded no timings, so it could say WHICH pages were constructed but never
    // what they cost -- which is the only reason to have it. Now it carries elapsed-ms and
    // per-step deltas, and costs a branch when disabled.
    static const bool traceEnabled = qEnvironmentVariableIsSet("SPELLVISION_STARTUP_TRACE");
    QElapsedTimer pageClock;
    pageClock.start();
    qint64 lastElapsed = 0;
    auto pageTrace = [&pageClock, &lastElapsed](const char *label) {
        if (!traceEnabled)
            return;
        const qint64 now = pageClock.elapsed();
        const qint64 delta = now - lastElapsed;
        lastElapsed = now;
        QFile f(QDir::currentPath() + QStringLiteral("/build/ui_startup_trace.log"));
        if (f.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text)) {
            QTextStream s(&f);
            s << QStringLiteral("%1  +%2ms  (t=%3ms)\n")
                     .arg(QString::fromUtf8(label), -34)
                     .arg(delta, 6)
                     .arg(now, 6);
            s.flush();
        }
    };
    pageTrace("buildPages start");
    homePage_ = new HomePage(this);
    pageTrace("homePage");
    // --- CHAIN STUDIO PASS 7C-PRELUDE RAIL ENTRY ---
    // Deferred: chain is nav-hidden unless SPELLVISION_SHOW_ALL_MODES, so on a default build
    // this ~80ms construction never runs at all.
    registerDeferredPage(QStringLiteral("chain"), [this]() {
        chainStudioPage_ = new spellvision::chain::ChainStudioPage(this);
        modePages_.insert(QStringLiteral("chain"), chainStudioPage_);
    });
    pageTrace("chainStudioPage deferred");
    // The three studios are the single most expensive eager block on the startup path
    // (~785ms combined). Each builder carries the page's FULL eager wiring -- construction,
    // project root, every connect, the modePages_ registration, and the updateDisclosure
    // seed -- so a lazily-built page is identical to what the eager path produced.
    registerDeferredPage(QStringLiteral("character"), [this]() {
        characterStudioPage_ = new spellvision::studios::CharacterStudioPage(this);
        modePages_.insert(QStringLiteral("character"), characterStudioPage_);
        characterStudioPage_->setProjectRoot(resolveProjectRoot());
        connect(characterStudioPage_, &spellvision::studios::CharacterStudioPage::navigateRequested,
                this, &MainWindow::switchToMode);
        connect(characterStudioPage_, &spellvision::studios::CharacterStudioPage::generateRequested,
                this, [this](const QString &modeId, const QJsonObject &payload, bool enqueueOnly) {
                    submitStudioGenerationRequest(QStringLiteral("character"), modeId, payload, enqueueOnly);
                });
        connect(characterStudioPage_, &spellvision::studios::CharacterStudioPage::openModelsRequested,
                this, [this]() { switchToMode(QStringLiteral("models")); });
        connect(characterStudioPage_, &spellvision::studios::CharacterStudioPage::openWorkflowsRequested,
                this, [this]() { switchToMode(QStringLiteral("workflows")); });
        connect(this, &MainWindow::disclosureModeChanged,
                characterStudioPage_, &spellvision::studios::CharacterStudioPage::updateDisclosure);
        characterStudioPage_->updateDisclosure(isAdvancedMode());
    });
    pageTrace("characterStudioPage deferred");
    registerDeferredPage(QStringLiteral("comic"), [this]() {
        comicStudioPage_ = new spellvision::studios::ComicStudioPage(this);
        modePages_.insert(QStringLiteral("comic"), comicStudioPage_);
        comicStudioPage_->setProjectRoot(resolveProjectRoot());
        connect(comicStudioPage_, &spellvision::studios::ComicStudioPage::navigateRequested,
                this, &MainWindow::switchToMode);
        connect(comicStudioPage_, &spellvision::studios::ComicStudioPage::generateRequested,
                this, [this](const QString &modeId, const QJsonObject &payload, bool enqueueOnly) {
                    submitStudioGenerationRequest(QStringLiteral("comic"), modeId, payload, enqueueOnly);
                });
        connect(comicStudioPage_, &spellvision::studios::ComicStudioPage::openModelsRequested,
                this, [this]() { switchToMode(QStringLiteral("models")); });
        connect(this, &MainWindow::disclosureModeChanged,
                comicStudioPage_, &spellvision::studios::ComicStudioPage::updateDisclosure);
        comicStudioPage_->updateDisclosure(isAdvancedMode());
    });
    pageTrace("comicStudioPage deferred");
    registerDeferredPage(QStringLiteral("concept"), [this]() {
        conceptReferencePage_ = new spellvision::studios::ConceptReferencePage(this);
        modePages_.insert(QStringLiteral("concept"), conceptReferencePage_);
        conceptReferencePage_->setProjectRoot(resolveProjectRoot());
        connect(conceptReferencePage_, &spellvision::studios::ConceptReferencePage::navigateRequested,
                this, &MainWindow::switchToMode);
        connect(conceptReferencePage_, &spellvision::studios::ConceptReferencePage::generateRequested,
                this, [this](const QString &modeId, const QJsonObject &payload, bool enqueueOnly) {
                    submitStudioGenerationRequest(QStringLiteral("concept"), modeId, payload, enqueueOnly);
                });
        connect(conceptReferencePage_, &spellvision::studios::ConceptReferencePage::openModelsRequested,
                this, [this]() { switchToMode(QStringLiteral("models")); });
        connect(conceptReferencePage_, &spellvision::studios::ConceptReferencePage::sendToCharacterStudioRequested,
                this, [this](const QString &imagePath, const QString &prompt) {
                    // Character Studio is the RECEIVER here and may not be built yet -- build it
                    // before the handoff, otherwise the null guard would silently drop the reference.
                    ensureDeferredPageBuilt(QStringLiteral("character"));
                    if (characterStudioPage_)
                        characterStudioPage_->acceptConceptReference(imagePath, prompt);
                });
        connect(this, &MainWindow::disclosureModeChanged,
                conceptReferencePage_, &spellvision::studios::ConceptReferencePage::updateDisclosure);
        conceptReferencePage_->updateDisclosure(isAdvancedMode());
    });
    pageTrace("conceptReferencePage deferred");
    workflowsPage_ = new WorkflowLibraryPage(this);
    pageTrace("workflowsPage");
    workflowsPage_->setProjectRoot(resolveProjectRoot());
    workflowsPage_->setPythonExecutable(resolvePythonExecutable());
    workflowsPage_->setProfilesRoot(defaultImportedWorkflowsRoot(resolveProjectRoot()));
    workflowsPage_->setComfyWorkflowsRoot(
        QDir(defaultManagedComfyRoot(resolveProjectRoot())).filePath(QStringLiteral("user/default/workflows")));
    connect(workflowsPage_, &WorkflowLibraryPage::importWorkflowRequested, this, &MainWindow::openWorkflowImportDialog);
    registerDeferredPage(QStringLiteral("history"), [this]() {
        historyPage_ = new T2VHistoryPage(this);
        modePages_.insert(QStringLiteral("history"), historyPage_);
        historyPage_->setProjectRoot(resolveProjectRoot());
    });
    pageTrace("historyPage deferred");
    registerDeferredPage(QStringLiteral("inspiration"), [this]() {
        inspirationPage_ = new InspirationPage(this);
        modePages_.insert(QStringLiteral("inspiration"), inspirationPage_);
        inspirationPage_->setProjectRoot(resolveProjectRoot());
        connect(inspirationPage_, &InspirationPage::navigateRequested, this, &MainWindow::switchToMode);
        connect(inspirationPage_, &InspirationPage::openHistoryRequested, this,
                [this]() { switchToMode(QStringLiteral("history")); });
        connect(inspirationPage_, &InspirationPage::sendToGenerationRequested, this,
                [this](const QString &modeId, const QJsonObject &draft) {
                    ensureGenerationPageBuilt(modeId);
                    ImageGenerationPage *page = generationPageForMode(modeId);
                    if (!page)
                        return;
                    page->applyWorkflowDraft(draft);
                    const QString input = draft.value(QStringLiteral("input_image")).toString().trimmed();
                    if (!input.isEmpty())
                        page->useImageAsInput(input);
                    switchToMode(modeId);
                });
    });
    pageTrace("inspirationPage deferred");
    // Restored (fix: orphaned since b4e1d6b, which swapped this real page for a ModePage stub).
    // ModelManagerPage is the Stage-1 model-inventory browser; registration below is QWidget*-generic.
    modelsPage_ = new ModelManagerPage(this);
    pageTrace("modelsPage");
    modelsPage_->setProjectRoot(resolveProjectRoot());
    // Warm the model inventory cache after the UI is up, matching what ManagerPage already does
    // below. loadCache() parses the whole model_inventory_cache.json (~232ms on the startup path)
    // and refreshInventory() is threaded anyway, so none of this needs to precede first paint.
    // The page renders its own "refreshing..." state until the warm lands.
    QTimer::singleShot(2500, this, [this]() {
        if (modelsPage_)
            modelsPage_->warmCache();
    });
    pageTrace("modelsPage warmCache deferred");
    // S2 send-to router: a card's Load/Add action routes by type + family (doc 22 §3).
    connect(modelsPage_, &ModelManagerPage::useModelRequested, this, &MainWindow::sendModelToGeneration);

    // Model Library Arc — Stage 3. "Use workflow": launch the model's bound workflow with THIS model
    // substituted (the explicit-override primary path; empty modelValue = a dual-loader launch unbound).
    connect(modelsPage_, &ModelManagerPage::useWorkflowRequested, this,
            [this](const QJsonObject &profile, const QString &modelValue, const QString &loraValue) {
                launchWorkflowProfileWithModel(profile, modelValue, loraValue, /*hasExplicitOverride=*/true);
            });
    // "Resolve dependencies": jump to the Flows page with that workflow selected, where the existing
    // Retry Dependencies action (dependency_plan.json) does the rescan/install -- reused, not rebuilt.
    connect(modelsPage_, &ModelManagerPage::resolveWorkflowDependenciesRequested, this,
            [this](const QString &slug) {
                switchToMode(QStringLiteral("workflows"));
                if (workflowsPage_)
                    workflowsPage_->selectWorkflowBySlug(slug);
            });
    // Keep the Models page's workflow catalog in sync with the Flows library (readiness + new imports).
    connect(workflowsPage_, &WorkflowLibraryPage::libraryRefreshed, this, [this]() {
        if (modelsPage_)
            modelsPage_->setImportedWorkflows(workflowsPage_->importedWorkflowLaunchProfiles());
    });

    // Deferred like the studios; the body below is the unchanged eager wiring.
    registerDeferredPage(QStringLiteral("dataset"), [this]() {
    datasetPage_ = new DatasetGenerationPage(this);
    modePages_.insert(QStringLiteral("dataset"), datasetPage_);
    datasetPage_->setProjectRoot(resolveProjectRoot());
    connect(datasetPage_, &DatasetGenerationPage::generateDatasetRequested, this,
            [this](const QJsonObject &payload) {
                QJsonObject req = payload;
                // Merge model stack from T2I cockpit when the dataset page has no model.
                ensureGenerationPageBuilt(QStringLiteral("t2i"));
                if (t2iPage_) {
                    const QJsonObject draft = t2iPage_->buildRequestPayload();
                    const auto takeIfMissing = [&](const char *key) {
                        const QString k = QString::fromUtf8(key);
                        if (!req.contains(k)) {
                            if (draft.contains(k))
                                req.insert(k, draft.value(k));
                            return;
                        }
                        const QJsonValue cur = req.value(k);
                        if (cur.isString() && cur.toString().trimmed().isEmpty() && draft.contains(k))
                            req.insert(k, draft.value(k));
                    };
                    takeIfMissing("model");
                    takeIfMissing("model_display");
                    if (!req.contains(QStringLiteral("loras")) && draft.contains(QStringLiteral("loras")))
                        req.insert(QStringLiteral("loras"), draft.value(QStringLiteral("loras")));
                    takeIfMissing("sampler");
                    takeIfMissing("scheduler");
                    takeIfMissing("cfg");
                    takeIfMissing("steps");
                    takeIfMissing("negative_prompt");
                }
                if (req.value(QStringLiteral("model")).toString().trimmed().isEmpty()) {
                    if (datasetPage_) {
                        datasetPage_->setBusy(false, QStringLiteral("No checkpoint — pick a model on T2I first"));
                        datasetPage_->applyQueueAck(QJsonObject{
                            {QStringLiteral("ok"), false},
                            {QStringLiteral("error"),
                             QStringLiteral("No checkpoint selected. Open T2I, pick a model, then retry.")},
                        });
                    }
                    appendLogLine(QStringLiteral("Dataset: blocked — no model on T2I cockpit."));
                    return;
                }

                const QPointer<DatasetGenerationPage> pageGuard(datasetPage_);
                sendWorkerRequestAsync(
                    req,
                    [this, pageGuard](
                        const QJsonObject &response, const QString &stderrText, bool startedOk) {
                        QJsonObject acknowledgement = response;
                        if (!startedOk || acknowledgement.isEmpty())
                        {
                            acknowledgement.insert(QStringLiteral("ok"), false);
                            acknowledgement.insert(
                                QStringLiteral("error"),
                                stderrText.trimmed().isEmpty()
                                    ? QStringLiteral("Worker did not respond to dataset submission.")
                                    : stderrText.trimmed());
                        }
                        if (pageGuard)
                            pageGuard->applyQueueAck(acknowledgement);
                        if (startedOk && response.value(QStringLiteral("ok")).toBool())
                        {
                            appendLogLine(QStringLiteral("Dataset: queued %1 jobs → %2")
                                              .arg(response.value(QStringLiteral("queued_count")).toInt())
                                              .arg(response.value(QStringLiteral("dataset_root")).toString()));
                            pollWorkerQueueStatus();
                        }
                        else
                        {
                            appendLogLine(QStringLiteral("Dataset enqueue failed: %1")
                                              .arg(acknowledgement.value(QStringLiteral("error")).toString(
                                                  QStringLiteral("worker error"))));
                        }
                    },
                    120000);
            });
    connect(datasetPage_, &DatasetGenerationPage::openModelsRequested, this,
            [this]() { switchToMode(QStringLiteral("models")); });
    });
    pageTrace("datasetPage deferred");
    // Deferred: gen3d is nav-hidden unless SPELLVISION_SHOW_ALL_MODES, so on a default build
    // this construction never runs. The builder carries the FULL eager wiring -- including the
    // disclosureModeChanged connect and the initial updateDisclosure, which a lazily-built page
    // would otherwise never receive.
    registerDeferredPage(QStringLiteral("gen3d"), [this]() {
    gen3dPage_ = new Gen3DPage(this);
    modePages_.insert(QStringLiteral("gen3d"), gen3dPage_);
    gen3dPage_->setProjectRoot(resolveProjectRoot());
    connect(gen3dPage_, &Gen3DPage::navigateRequested, this, &MainWindow::switchToMode);
    connect(gen3dPage_, &Gen3DPage::openWorkflowsRequested, this, [this]() {
        switchToMode(QStringLiteral("workflows"));
    });
    connect(gen3dPage_, &Gen3DPage::comfyGenerateRequested, this, [this](const QJsonObject &req) {
        // Comfy-only path. Never spawn external GPU processes from the UI.
        QJsonObject request = req;
        if (!request.contains(QStringLiteral("command")))
            request.insert(QStringLiteral("command"), QStringLiteral("enqueue"));
        const QPointer<Gen3DPage> pageGuard(gen3dPage_);
        sendWorkerRequestAsync(
            request,
            [this, pageGuard](const QJsonObject &response, const QString &stderrText, bool startedOk) {
                if (!stderrText.trimmed().isEmpty())
                    appendLogLine(stderrText.trimmed());
                if (!startedOk || response.isEmpty() || !response.value(QStringLiteral("ok")).toBool(false))
                {
                    const QString error = response.value(QStringLiteral("error")).toString(
                        QStringLiteral("i23d enqueue failed — install a Trellis/Pixal Comfy workflow + nodes, or check worker logs"));
                    appendLogLine(QStringLiteral("Gen3D: %1").arg(error));
                    if (pageGuard)
                        pageGuard->setBusy(false, error);
                    return;
                }
                applyWorkerQueueResponse(response);
                pollWorkerQueueStatus();
                if (pageGuard)
                    pageGuard->setBusy(false, QStringLiteral("Queued on Comfy — watch Queue / History for .glb"));
                appendLogLine(QStringLiteral("Gen3D queued via ComfyUI"));
            });
    });
    // Seed workflow list once Flows page exists.
    if (workflowsPage_ && gen3dPage_)
        gen3dPage_->setAvailableWorkflows(workflowsPage_->importedWorkflowLaunchProfiles());
    connect(this, &MainWindow::disclosureModeChanged, gen3dPage_, &Gen3DPage::updateDisclosure);
    gen3dPage_->updateDisclosure(isAdvancedMode());
    });
    pageTrace("gen3dPage deferred");

    registerDeferredPage(QStringLiteral("runtime"), [this]() {
        managerPage_ = new ManagerPage(this);
        modePages_.insert(QStringLiteral("runtime"), managerPage_);
        managerPage_->setProjectRoot(resolveProjectRoot());
        managerPage_->setPythonExecutable(QDir(resolveProjectRoot()).filePath(QStringLiteral(".venv/Scripts/python.exe")));
        connect(managerPage_, &ManagerPage::statusMessageChanged, this, [this](const QString &msg) {
            if (!msg.trimmed().isEmpty())
                appendLogLine(msg.trimmed());
        });
        // The eager path warmed this on a 2.5s timer to keep it off startup. Now the page is
        // only built when the user navigates to it, so warm it immediately -- the reason to
        // delay (not blocking first paint) no longer applies.
        managerPage_->warmCache();
    });
    pageTrace("managerPage deferred");

    registerDeferredPage(QStringLiteral("train"), [this]() {
        trainPage_ = new TrainPage(this);
        modePages_.insert(QStringLiteral("train"), trainPage_);
        trainPage_->setProjectRoot(resolveProjectRoot());
        connect(trainPage_, &TrainPage::navigateRequested, this, &MainWindow::switchToMode);
        connect(trainPage_, &TrainPage::openDatasetRequested, this, [this]() {
            switchToMode(QStringLiteral("dataset"));
        });
    });
    pageTrace("trainPage deferred");

    // Deferred like the rest; the body below is the unchanged eager wiring. The disclosure and
    // theme seeds inside read the CURRENT values at build time, which is what the eager path's
    // post-restore emit used to deliver.
    registerDeferredPage(QStringLiteral("settings"), [this]() {
    settingsPage_ = new SettingsPage(this);
    modePages_.insert(QStringLiteral("settings"), settingsPage_);
    // Phase 7 capstone: the Settings "Workspace Mode" dropdown is a SECOND entry point to the same
    // persisted advancedMode_ that the title-bar toggle drives. A user pick routes through
    // setDisclosureMode (the single writer); disclosureModeChanged reflects it back so the two stay
    // in sync (last write wins). buildPages() runs before the constructor's restore, so the restore's
    // emit lands here too -- the explicit seed below just covers the pre-restore default.
    connect(settingsPage_, &SettingsPage::disclosureModeChangeRequested, this, &MainWindow::setDisclosureMode);
    connect(this, &MainWindow::disclosureModeChanged, settingsPage_, &SettingsPage::setDisclosureMode);
    settingsPage_->setDisclosureMode(isAdvancedMode());

    // Theme migration Phase 1: route the Settings theme-preset dropdown into ThemeManager
    // (the previously-dormant switch glue -- mirrors the disclosure capstone above).
    // setPresetByIndex changes the active preset, rebuilds the canonical color tokens, and
    // emits themeChanged() -- which the pilot widgets (and generator-styled pages) subscribe
    // to and re-style live. Presets resolve by their display name's index.
    connect(settingsPage_, &SettingsPage::presetChanged, this, [](const QString &name) {
        ThemeManager &tm = ThemeManager::instance();
        const int idx = tm.presetNames().indexOf(name);
        if (idx >= 0)
            tm.setPresetByIndex(idx);
    });
    connect(settingsPage_, &SettingsPage::usePresetAccentChanged, this, [](bool enabled) {
        ThemeManager::instance().setUsePresetAccent(enabled);
    });
    connect(settingsPage_, &SettingsPage::chooseAccentColorRequested, this, [this]() {
        ThemeManager &tm = ThemeManager::instance();
        const QColor current = tm.accentColor();
        const QColor picked = QColorDialog::getColor(current, this, QStringLiteral("Choose accent color"));
        if (picked.isValid())
            tm.setAccentOverride(picked);
    });
    connect(settingsPage_, &SettingsPage::effectsWeightChanged, this, [](int value) {
        ThemeManager::instance().setEffectsWeight(value);
    });
    connect(settingsPage_, &SettingsPage::restoreDefaultsRequested, this, [this]() {
        ThemeManager::instance().resetToDefaults();
        if (settingsPage_) {
            const QStringList names = ThemeManager::instance().presetNames();
            if (!names.isEmpty())
                settingsPage_->setCurrentPreset(names.first());
            settingsPage_->setUsePresetAccent(true);
            settingsPage_->setEffectsWeight(ThemeManager::instance().effectsWeight());
            settingsPage_->refreshThemePreview();
        }
        appendLogLine(QStringLiteral("Appearance restored to defaults"));
    });
    connect(settingsPage_, &SettingsPage::homeDashboardConfigChanged, this, [this](const HomeDashboardConfig &cfg) {
        if (homePage_)
            homePage_->setDashboardConfig(cfg);
    });
    connect(settingsPage_, &SettingsPage::homeDashboardCustomizeRequested, this, [this]() {
        // Home owns the live customize surface.
        switchToMode(QStringLiteral("home"));
        if (homePage_ && settingsPage_) {
            homePage_->setDashboardConfig(settingsPage_->homeDashboardConfig());
            homePage_->setCustomizeMode(true);
        }
        appendLogLine(QStringLiteral("Home dashboard customize mode on"));
    });
    // Seed Settings appearance from live ThemeManager so the panel reflects truth.
    {
        ThemeManager &tm = ThemeManager::instance();
        const QStringList names = tm.presetNames();
        if (tm.presetIndex() >= 0 && tm.presetIndex() < names.size())
            settingsPage_->setCurrentPreset(names.at(tm.presetIndex()));
        settingsPage_->setUsePresetAccent(tm.usePresetAccent());
        settingsPage_->setEffectsWeight(tm.effectsWeight());
        settingsPage_->refreshThemePreview();
        if (homePage_)
            settingsPage_->setHomeDashboardConfig(homePage_->dashboardConfig());
    }
    // Keep Settings theme preview in sync when theme changes elsewhere. Registered inside the
    // builder: a theme change before Settings exists is picked up by the seed above at build time.
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() {
        if (!settingsPage_)
            return;
        settingsPage_->refreshThemePreview();
    });
    });
    pageTrace("settingsPage deferred");

    // The four ImageGenerationPages (t2i/i2i/t2v/i2v) are NOT built here -- they are
    // the ~6s of intrinsic widget-tree construction that used to block the window from
    // painting until ~9.8s. They are deferred to ensureGenerationPageBuilt(), reached
    // on first navigation (on-demand) or via the idle pre-warm started below. Only the
    // eager (cheap) pages are constructed + registered here.

/* TEMP lazy addWidget: switched to on-demand in switchToMode
    for (QWidget *page : {static_cast<QWidget *>(homePage_),
                          static_cast<QWidget *>(chainStudioPage_),
                          static_cast<QWidget *>(characterStudioPage_),
                          static_cast<QWidget *>(comicStudioPage_),
                          static_cast<QWidget *>(conceptReferencePage_),
                          static_cast<QWidget *>(historyPage_),
                          static_cast<QWidget *>(inspirationPage_),
                          static_cast<QWidget *>(workflowsPage_),
                          static_cast<QWidget *>(modelsPage_),
                          static_cast<QWidget *>(datasetPage_),
                          static_cast<QWidget *>(gen3dPage_),
                          static_cast<QWidget *>(managerPage_),
                          static_cast<QWidget *>(trainPage_),
                          static_cast<QWidget *>(settingsPage_)})
    {
        const QString name = page ? page->objectName() : QStringLiteral("null");
        pageTrace(("addWidget start " + name).toUtf8().constData());
        pageStack_->addWidget(page);
        pageTrace(("addWidget end " + name).toUtf8().constData());
    }
*/
    pageTrace("after addWidgets");

    // Only the pages still constructed eagerly are registered here. Everything else --
    // chain, gen3d, the three studios, history, inspiration, dataset, runtime, train,
    // settings, and t2i/i2i/t2v/i2v -- inserts its own entry from its builder when built.
    modePages_.insert(QStringLiteral("home"), homePage_);
    modePages_.insert(QStringLiteral("workflows"), workflowsPage_);
    modePages_.insert(QStringLiteral("models"), modelsPage_);
    pageTrace("after modePages");

    // The studio connects moved into the three deferred builders above -- the pages no
    // longer exist at this point.

    connect(homePage_, &HomePage::modeRequested, this, &MainWindow::switchToMode);
    connect(homePage_, &HomePage::managerRequested, this, &MainWindow::openManager);
    connect(homePage_, &HomePage::launchRequested, this, [this](const QString &modeId,
                                                                const QString &title,
                                                                const QString &subtitle,
                                                                const QString &sourceLabel) {
        handleHomeLaunchRequest(modeId, title, subtitle, sourceLabel);
    });
    // Gallery click -> open the output in its originating cockpit (switch mode + show it on canvas).
    connect(homePage_, &HomePage::openOutputRequested, this, [this](const QString &modeId, const QString &path) {
        QString mode = modeId.trimmed().toLower();
        if (mode != QStringLiteral("t2i") && mode != QStringLiteral("i2i") &&
            mode != QStringLiteral("t2v") && mode != QStringLiteral("i2v"))
            mode = QStringLiteral("t2i"); // only generation modes host a canvas
        ensureGenerationPageBuilt(mode);
        switchToMode(mode);
        const QString outputPath = path;
        QTimer::singleShot(0, this, [this, mode, outputPath]() {
            if (ImageGenerationPage *page = generationPageForMode(mode))
                page->setPreviewImage(outputPath, QStringLiteral("From Home gallery"));
        });
    });
    // Gallery hover secondary -> send an output to a cockpit as INPUT (image -> I2I).
    connect(homePage_, &HomePage::sendOutputToInputRequested, this, [this](const QString &targetMode, const QString &path) {
        QString mode = targetMode.trimmed().toLower();
        if (mode != QStringLiteral("i2i") && mode != QStringLiteral("i2v"))
            mode = QStringLiteral("i2i");
        ensureGenerationPageBuilt(mode);
        switchToMode(mode);
        const QString inputPath = path;
        QTimer::singleShot(0, this, [this, mode, inputPath]() {
            if (ImageGenerationPage *page = generationPageForMode(mode))
                page->useImageAsInput(inputPath);
        });
    });

    // The four generation pages are wired inside ensureGenerationPageBuilt (via
    // connectGenerationPage) at build time, not here -- they no longer exist yet.

    pageTrace("before refreshProfiles");
    workflowsPage_->refreshProfiles();
    pageTrace("after refreshProfiles");

    connect(workflowsPage_, &WorkflowLibraryPage::importWorkflowRequested, this, &MainWindow::openWorkflowImportDialog);
    connect(workflowsPage_, &WorkflowLibraryPage::launchWorkflowRequested, this, &MainWindow::launchWorkflowProfile);
    connect(workflowsPage_, &WorkflowLibraryPage::workflowDraftRequested,
            this, &MainWindow::openWorkflowDraft);

    // Idle pre-warm is kicked off from showEvent() (first show), NOT here: scheduling
    // it from the constructor anchors the delay to ctor time, which elapses before the
    // event loop even starts, so the first build would race the window's first paint.
    // showEvent runs after show(), so the first-build delay is relative to the window
    // actually appearing.
    pageTrace("buildPages end");
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
    bar->setFixedHeight(40);
    bar->setMinimumHeight(40);
    bar->setMaximumHeight(40);

    auto *container = new QFrame(bar);
    container->setObjectName(QStringLiteral("BottomTelemetryContainer"));
    container->setFrameShape(QFrame::NoFrame);
    container->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    container->setMinimumHeight(34);
    container->setMaximumHeight(34);

    auto *layout = new QHBoxLayout(container);
    layout->setContentsMargins(8, 2, 10, 2);
    layout->setSpacing(6);

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

    auto addSeparator = [container, layout]() -> QFrame * {
        auto *separator = new QFrame(container);
        separator->setObjectName(QStringLiteral("BottomTelemetrySeparator"));
        separator->setFrameShape(QFrame::VLine);
        separator->setFixedWidth(1);
        separator->setMinimumHeight(22);
        separator->setMaximumHeight(22);
        // Phase 6: styled by the shell stylesheet (#BottomTelemetrySeparator) so it switches.
        layout->addWidget(separator);
        return separator;
    };

    // Phase 8 wave 1 (clipping fix): the fixed telemetry widths summed to ~1258px + separators, which
    // overflowed the ~1184px-usable status bar at common window widths -> the rightmost widget (the
    // progress bar) clipped on the right. Trim the over-generous widths (each still exceeds its text)
    // so the bar fits; Model stays generous for checkpoint names. Fixed widths preserve the Pass-28R
    // no-jump behaviour; this just fits the budget.
    // Now that long values elide (applyTelemetryText) instead of hard-clipping, the generous
    // Model/LoRA/Runtime widths are trimmed to buy room for the new ETA readout while keeping the
    // fixed-width sum under the ~1184px-usable budget the Phase 8 clipping fix established.
    bottomReadyLabel_ = makeTelemetryLabel(QStringLiteral("BottomReadyLabel"), QStringLiteral("Ready"), 56);
    bottomPageLabel_ = makeTelemetryLabel(QStringLiteral("BottomPageLabel"), QStringLiteral("Home"), 128, Qt::AlignLeft | Qt::AlignVCenter);
    // Backend health: two dots (Worker :8765 + Comfy :8188). Rich text so each dot colors
    // independently; text is set by updateBackendHealthLabel(), not the plain eliding path.
    bottomBackendLabel_ = makeTelemetryLabel(QStringLiteral("BottomBackendLabel"), QString(), 112);
    bottomBackendLabel_->setTextFormat(Qt::RichText);
    bottomQueueLabel_ = makeTelemetryLabel(QStringLiteral("BottomQueueLabel"), QStringLiteral("Queue: 0"), 86);
    // Phase 5: this telemetry item is the primary trigger for the activity drawer (eventFilter).
    bottomQueueLabel_->setCursor(Qt::PointingHandCursor);
    bottomQueueLabel_->setToolTip(QStringLiteral("Open the activity drawer (queue · details · logs)"));
    bottomQueueLabel_->installEventFilter(this);
    bottomVramLabel_ = makeTelemetryLabel(QStringLiteral("BottomVramLabel"), QStringLiteral("VRAM: checking"), 150);
    bottomModelLabel_ = makeTelemetryLabel(QStringLiteral("BottomModelLabel"), QStringLiteral("Model: none"), 178);
    bottomLoraLabel_ = makeTelemetryLabel(QStringLiteral("BottomLoraLabel"), QStringLiteral("LoRA: none"), 110);
    bottomStateLabel_ = makeTelemetryLabel(QStringLiteral("BottomStateLabel"), QStringLiteral("Idle"), 96);
    // ETA is empty when idle; it fills only while a job is running (see syncBottomTelemetry). Reserved
    // width keeps the no-jump behaviour when it appears/clears.
    bottomEtaLabel_ = makeTelemetryLabel(QStringLiteral("BottomEtaLabel"), QString(), 78);
    bottomEtaLabel_->setToolTip(QStringLiteral("Estimated time remaining for the active job"));

    bottomProgressBar_ = new GlowProgressBar(container);
    bottomProgressBar_->setObjectName(QStringLiteral("BottomProgressBar"));
    bottomProgressBar_->setRange(0, 100);
    bottomProgressBar_->setValue(0);
    bottomProgressBar_->setTextVisible(true);
    bottomProgressBar_->setFormat(QStringLiteral(""));
    bottomProgressBar_->setFixedSize(164, 18);
    bottomProgressBar_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    // Phase 6: styled by the shell stylesheet (#BottomProgressBar) so it switches with the theme.

    // No pipe dividers — chips sit with breathing room; Model/LoRA get stretch for long names.
    layout->addWidget(bottomReadyLabel_);
    layout->addWidget(bottomPageLabel_);
    layout->addStretch(1);
    layout->addWidget(bottomBackendLabel_);
    layout->addWidget(bottomQueueLabel_);
    layout->addWidget(bottomVramLabel_);
    layout->addWidget(bottomModelLabel_, /*stretch*/ 3);
    layout->addWidget(bottomLoraLabel_, /*stretch*/ 2);
    layout->addWidget(bottomStateLabel_);
    layout->addWidget(bottomEtaLabel_);
    layout->addWidget(bottomProgressBar_);
    bottomLoraSeparator_ = nullptr;
    bottomEtaSeparator_ = nullptr;

    bar->addWidget(container, 1);

    updateBackendHealthLabel();
    startVramTelemetryPolling();
    startComfyHealthPolling();
    reflowBottomTelemetryWidths(width() > 0 ? width() : 1440);
    syncBottomTelemetry();
}

void MainWindow::reflowBottomTelemetryWidths(int windowWidth)
{
    // Showcase P1: at half-screen / restore widths the fixed telemetry sum (~1.1k+) can
    // overflow the status bar. Compress Model/LoRA/VRAM/Page earlier; hide ETA then LoRA
    // at the tightest budgets. Fixed widths preserve the no-jump bar; only the budget changes.
    const int w = windowWidth > 0 ? windowWidth : width();

    auto setW = [](QLabel *label, int tw, bool visible, bool expandable = false) {
        if (!label)
            return;
        label->setVisible(visible);
        if (!visible)
            return;
        if (expandable) {
            // Model/LoRA: min width + stretch (not fixed) so long names get room.
            label->setMinimumWidth(tw);
            label->setMaximumWidth(QWIDGETSIZE_MAX);
            label->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
            label->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
        } else {
            label->setFixedWidth(tw);
            label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
        }
    };

    const bool tight = w < 1100;
    const bool narrow = w < 1280;
    const bool mid = w < 1500;

    auto pick = [&](int wide, int midW, int narrowW) {
        if (tight)
            return narrowW;
        if (narrow)
            return midW;
        if (mid)
            return (wide + midW) / 2;
        return wide;
    };

    setW(bottomReadyLabel_, pick(52, 48, 44), true);
    setW(bottomPageLabel_, pick(110, 88, 68), true);
    setW(bottomBackendLabel_, pick(96, 84, 72), true);
    setW(bottomQueueLabel_, pick(78, 68, 60), true);
    setW(bottomVramLabel_, pick(128, 108, 88), true);
    // Model + LoRA claim leftover width — long checkpoint/LoRA basenames.
    setW(bottomModelLabel_, pick(160, 120, 90), true, true);
    const bool showLora = w >= 1000;
    const bool showEta = w >= 1280;
    setW(bottomLoraLabel_, pick(120, 90, 70), showLora, true);
    if (bottomLoraSeparator_)
        bottomLoraSeparator_->setVisible(showLora);
    setW(bottomStateLabel_, pick(72, 64, 56), true);
    setW(bottomEtaLabel_, pick(72, 60, 52), showEta);
    if (bottomEtaSeparator_)
        bottomEtaSeparator_->setVisible(showEta);

    if (bottomProgressBar_) {
        if (tight)
            bottomProgressBar_->setFixedSize(120, 18);
        else if (narrow)
            bottomProgressBar_->setFixedSize(140, 18);
        else
            bottomProgressBar_->setFixedSize(164, 18);
    }
}

void MainWindow::resizeEvent(QResizeEvent *event)
{
    QMainWindow::resizeEvent(event);
    reflowBottomTelemetryWidths(event ? event->size().width() : width());
    positionQueueOverlay();
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
    // A2: wire the cockpit's component auto-populate to the worker round-trip (the A1 engine).
    (*slot)->setComponentStackResolver(
        [this](const QString &primary,
               const QString &family,
               const QString &task,
               const QJsonObject &choices,
               std::function<void(const QJsonArray &)> completion) {
            resolveComponentStackViaWorker(primary, family, task, choices, std::move(completion));
        });
    // Phase 3b: the fast/quality operating-point table provider (lazy cached fetch).
    (*slot)->setOperatingPointsProvider(
        [this](const QString &family) { return operatingPointsForFamily(family); });
    const QPointer<ImageGenerationPage> pageGuard(*slot);
    fetchOperatingPointsAsync([pageGuard]() {
        if (pageGuard)
            pageGuard->refreshOperatingPointSelector();
    });
    pageStack_->addWidget(*slot);
    modePages_.insert(modeId, *slot);
    connectGenerationPage(*slot, modeId);
}

void MainWindow::registerDeferredPage(const QString &modeId, std::function<void()> builder)
{
    deferredPageBuilders_.insert(modeId, std::move(builder));
}

// Runs a deferred page's builder exactly once. The entry is erased BEFORE the builder runs, so
// a builder that re-enters (a connect() lambda calling switchToMode, say) cannot recurse into a
// second construction. A no-op for eager modes and for anything already built.
void MainWindow::ensureDeferredPageBuilt(const QString &modeId)
{
    const auto it = deferredPageBuilders_.find(modeId);
    if (it == deferredPageBuilders_.end())
        return;

    const std::function<void()> builder = *it;
    deferredPageBuilders_.erase(it);
    if (builder)
        builder();
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
    connect(page, &ImageGenerationPage::workflowFileDropped, this, [this, page, modeId](const QString &path) {
        // Import through the worker, then open as editable draft on this cockpit.
        // If import already exists / succeeds, also offer a direct launch profile.
        QJsonObject request;
        request.insert(QStringLiteral("command"), QStringLiteral("import_workflow"));
        request.insert(QStringLiteral("source"), path);
        request.insert(QStringLiteral("auto_apply_node_deps"), false);
        request.insert(QStringLiteral("auto_apply_model_deps"), false);
        const QPointer<ImageGenerationPage> pageGuard(page);
        page->setBusy(true, QStringLiteral("Importing workflow…"));
        sendWorkerRequestAsync(
            request,
            [this, pageGuard, modeId, path](
                const QJsonObject &response, const QString &stderrText, bool startedOk) {
        if (!pageGuard)
            return;
        pageGuard->setBusy(false, QString());
        if (!stderrText.trimmed().isEmpty())
            appendLogLine(stderrText.trimmed());
        if (!startedOk || response.isEmpty() || !response.value(QStringLiteral("ok")).toBool(false)) {
            const QString err = response.value(QStringLiteral("error")).toString(
                QStringLiteral("Workflow import failed"));
            appendLogLine(QStringLiteral("Workflow drop import failed: %1").arg(err));
            // Still try to open a lightweight draft from the raw path so the user can edit
            // prompts against the graph once assets resolve.
            QJsonObject draft;
            draft.insert(QStringLiteral("source_name"), QFileInfo(path).fileName());
            draft.insert(QStringLiteral("source_workflow_path"), path);
            draft.insert(QStringLiteral("workflow_path"), path);
            draft.insert(QStringLiteral("safe_to_submit"), false);
            draft.insert(QStringLiteral("warnings"),
                         QJsonArray{QStringLiteral("Import incomplete — review models/nodes in Flows.")});
            pageGuard->applyWorkflowDraft(draft);
            return;
        }

        // Build the draft from the response the worker ACTUALLY sends.
        //
        // This previously read response["draft"] and response["result"], neither of which
        // handle_import_workflow_command emits -- it returns a FLAT WorkflowImportResult
        // (ok / import_slug / artifacts / missing_custom_nodes / warnings). Every lookup therefore
        // resolved empty and `safe_to_submit` fell through to .toBool(true) on an absent object, so
        // a dropped workflow was ALWAYS treated as ready and queue-launched unconditionally --
        // including workflows whose nodes or models are missing.
        const QJsonObject artifacts = response.value(QStringLiteral("artifacts")).toObject();
        const QJsonArray missingNodes = response.value(QStringLiteral("missing_custom_nodes")).toArray();

        QJsonObject draft;
        draft.insert(QStringLiteral("source_name"),
                     response.value(QStringLiteral("import_slug")).toString(QFileInfo(path).fileName()));
        draft.insert(QStringLiteral("source_profile_path"),
                     artifacts.value(QStringLiteral("profile_path")).toString());
        draft.insert(QStringLiteral("source_workflow_path"),
                     artifacts.value(QStringLiteral("workflow_path")).toString(path));
        draft.insert(QStringLiteral("workflow_path"),
                     artifacts.value(QStringLiteral("workflow_path")).toString(path));
        // The importer reports no launch readiness, so there is nothing here that could justify
        // auto-submitting. Default CLOSED and let the user press Generate. Drop-and-run returns
        // once readiness is real and the worker sends it (plan A8).
        draft.insert(QStringLiteral("safe_to_submit"), false);
        if (!missingNodes.isEmpty()) {
            draft.insert(QStringLiteral("warnings"),
                         QJsonArray{QStringLiteral("Imported with %1 unresolved node class(es) — check Flows.")
                                        .arg(missingNodes.size())});
        }
        if (draft.value(QStringLiteral("source_workflow_path")).toString().isEmpty())
            draft.insert(QStringLiteral("source_workflow_path"), path);
        pageGuard->applyWorkflowDraft(draft);
        appendLogLine(QStringLiteral("Workflow loaded into cockpit: %1")
                          .arg(draft.value(QStringLiteral("source_name")).toString(QFileInfo(path).fileName())));

        // If ready, also queue-launch with cockpit model overrides (drop-and-run).
        // Default CLOSED: an absent or malformed readiness signal must never mean "go".
        if (draft.value(QStringLiteral("safe_to_submit")).toBool(false)) {
            QJsonObject profile;
            profile.insert(QStringLiteral("profile_name"),
                           draft.value(QStringLiteral("source_name")).toString());
            profile.insert(QStringLiteral("name"), draft.value(QStringLiteral("source_name")).toString());
            profile.insert(QStringLiteral("task_command"), modeId);
            profile.insert(QStringLiteral("profile_path"),
                           draft.value(QStringLiteral("source_profile_path")).toString());
            profile.insert(QStringLiteral("workflow_path"),
                           draft.value(QStringLiteral("workflow_path")).toString(
                               draft.value(QStringLiteral("source_workflow_path")).toString(path)));
            profile.insert(QStringLiteral("compiled_prompt_path"),
                           draft.value(QStringLiteral("compiled_prompt_path")).toString());
            const QString model = pageGuard->selectedModelValue();
            const QString lora = pageGuard->selectedLoraValue();
            launchWorkflowProfileWithModel(profile, model, lora, /*hasExplicitOverride=*/true);
        }

        if (workflowsPage_)
            workflowsPage_->refreshLibrary();
            });
    });
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

void MainWindow::resetSubmissionTelemetry()
{
    setProperty("svTelemetryBusy", false);
    setProperty("svTelemetryBusyMode", QString());
    setProperty("svTelemetryBusyState", QStringLiteral("Idle"));
    setProperty("svTelemetryPhaseRank", 0);
    setProperty("svTelemetryProgressTarget", 0);
    setProperty("svTelemetryJobActive", false);
    setProperty("svTelemetryCompletionPulse", false);
    setProperty("svTelemetryCompletedRowsAtSubmit", 0);
    setProperty("svTelemetrySawActive", false);
    if (bottomProgressBar_)
    {
        bottomProgressBar_->setValue(0);
        bottomProgressBar_->setFormat(QStringLiteral("%p%"));
    }
    syncBottomTelemetry();
}

// --- CHAIN STUDIO PASS 8C.1: chain submission variant ---
// Mirrors submitGenerationRequest below, MINUS the page-specific
// bits: no page parameter, no page->setBusy calls, no enqueueOnly
// flag (chain stages always submit as "Submitting" rather than
// "Queued"-only). The chain page's UX is driven by engine signals,
// not setBusy, so the page does not need to be told to spin.
//
// Calls completion(true) if the worker accepted (response.ok == true and a
// queue_item_id is present); completion(false) on any validation rejection or
// transport error. ChainEngine interprets false as a submission rejection and
// rolls back the pending variation.
void MainWindow::submitChainGenerationRequestAsync(const QString &modeId,
                                                   const QJsonObject &payload,
                                                   const QString &queueItemId,
                                                   std::function<void(bool accepted)> completion)
{
    auto finish = [&completion](bool accepted) {
        if (completion)
            completion(accepted);
    };

    const QString taskCommand = workerTaskCommandForMode(modeId);
    if (taskCommand.isEmpty())
    {
        appendLogLine(QStringLiteral("Chain submission rejected: unknown mode %1.").arg(modeId));
        finish(false);
        return;
    }

    const bool videoMode = taskCommand == QStringLiteral("t2v") || taskCommand == QStringLiteral("i2v");
    const bool hasWorkflowBinding = spellvision::workers::WorkerSubmissionPolicy::hasWorkflowBinding(payload);
    const bool hasNativeVideoStack = videoMode && spellvision::workers::WorkerSubmissionPolicy::hasNativeVideoStackPayload(payload);
    const QString modelValue = spellvision::workers::WorkerSubmissionPolicy::resolvedModelValueFromPayload(payload);

    if (modelValue.isEmpty() && !(videoMode && (hasWorkflowBinding || hasNativeVideoStack)))
    {
        const QString message = spellvision::workers::WorkerSubmissionPolicy::missingModelMessage(modeId, videoMode);
        appendLogLine(QStringLiteral("Chain submission rejected: %1").arg(message));
        finish(false);
        return;
    }

    if ((taskCommand == QStringLiteral("i2i") || taskCommand == QStringLiteral("i2v")) &&
        payload.value(QStringLiteral("input_image")).toString().trimmed().isEmpty())
    {
        appendLogLine(QStringLiteral("Chain %1 submission rejected: missing input image.").arg(modeId.toUpper()));
        finish(false);
        return;
    }

    QJsonObject payloadWithId = payload;
    if (!queueItemId.trimmed().isEmpty())
        payloadWithId.insert(QStringLiteral("queue_item_id"), queueItemId);
    QString dest = payloadWithId.value(QStringLiteral("output_folder")).toString().trimmed();
    if (dest.startsWith(QLatin1String("Not set"), Qt::CaseInsensitive))
        dest.clear();
    if (dest.isEmpty())
        dest = spellvision::generation::userGenerationDestFolder();
    if (dest.isEmpty() || !QDir(dest).exists())
    {
        appendLogLine(QStringLiteral("Chain submission rejected: choose an output folder to generate."));
        finish(false);
        return;
    }
    payloadWithId.insert(QStringLiteral("output_folder"), dest);

    appendLogLine(spellvision::workers::WorkerSubmissionPolicy::acceptedRequestLogLine(
        modeId,
        videoMode,
        hasWorkflowBinding,
        modelValue));

    setProperty("svTelemetryBusy", true);
    setProperty("svTelemetryBusyMode", modeId);
    setProperty("svTelemetryBusyState", QStringLiteral("Submitting"));
    setProperty("svTelemetryPhaseRank", 1);
    setProperty("svTelemetryProgressTarget", 3);
    setProperty("svTelemetryJobActive", true);
    setProperty("svTelemetryCompletionPulse", false);
    setProperty("svTelemetrySawActive", false);

    const int completedRowsAtSubmit =
        (queueTableView_ && queueTableView_->model()) ? queueTableView_->model()->rowCount() : 0;
    setProperty("svTelemetryCompletedRowsAtSubmit", completedRowsAtSubmit);

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setValue(0);
        bottomProgressBar_->setFormat(QStringLiteral("%p%"));
    }

    syncBottomTelemetry();

    const QJsonObject request = buildWorkerGenerationRequest(modeId, payloadWithId);
    sendWorkerRequestAsync(
        request,
        [this, modeId, completion = std::move(completion)](
            const QJsonObject &response, const QString &stderrText, bool startedOk) mutable {
            auto finishLocal = [&completion](bool accepted) {
                if (completion)
                    completion(accepted);
            };

            if (!stderrText.trimmed().isEmpty())
                appendLogLine(stderrText.trimmed());

            if (!startedOk)
            {
                appendLogLine(QStringLiteral("Chain submission failed: could not start worker_client.py for %1.").arg(modeId.toUpper()));
                resetSubmissionTelemetry();
                finishLocal(false);
                return;
            }

            if (response.isEmpty())
            {
                appendLogLine(QStringLiteral("Chain submission failed: worker returned no JSON payload for %1.").arg(modeId.toUpper()));
                resetSubmissionTelemetry();
                finishLocal(false);
                return;
            }

            const bool ok = response.value(QStringLiteral("ok")).toBool(false);
            const QString errorText = response.value(QStringLiteral("error")).toString().trimmed();
            if (!ok)
            {
                if (!errorText.isEmpty())
                    appendLogLine(QStringLiteral("Chain %1 request failed: %2").arg(modeId.toUpper(), errorText));
                else
                    appendLogLine(QStringLiteral("Chain %1 request failed (no error text).").arg(modeId.toUpper()));
                resetSubmissionTelemetry();
                finishLocal(false);
                return;
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

            finishLocal(true);
        });
}

void MainWindow::submitGenerationRequest(
    ImageGenerationPage *page,
    const QString &modeId,
    const QJsonObject &payload,
    bool enqueueOnly,
    std::function<void(const QString &queueId, const QString &jobId, bool accepted)> completion)
{
    const auto completeRejected = [&completion]() {
        if (completion)
            completion({}, {}, false);
    };

    if (!page)
    {
        completeRejected();
        return;
    }

    const QString taskCommand = workerTaskCommandForMode(modeId);
    if (taskCommand.isEmpty())
    {
        const QString message = QStringLiteral("%1 backend is not wired to the Python worker yet. Start with T2I or I2I first.")
                                    .arg(pageContextForMode(modeId));
        appendLogLine(message);
        page->setBusy(false, message);
        completeRejected();
        return;
    }

    const QString modelFamily = payload.value(QStringLiteral("model_family")).toString();
    const QString modelHint = payload.value(QStringLiteral("model")).toString();
    QSettings commercialSettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    if (commercialSettings.value(QStringLiteral("usage/commercialUse"), true).toBool()
        && !spellvision::assets::familyAllowsCommercialUse(modelFamily, modelHint))
    {
        const auto answer = QMessageBox::warning(
            this,
            QStringLiteral("Non-commercial family"),
            QStringLiteral("%1 is licensed for non-commercial use. Continue this generate anyway?")
                .arg(modelFamily.isEmpty() ? QStringLiteral("This model") : modelFamily),
            QMessageBox::Yes | QMessageBox::No,
            QMessageBox::No);
        if (answer != QMessageBox::Yes)
        {
            page->setBusy(false, QStringLiteral("Cancelled — non-commercial family"));
            completeRejected();
            return;
        }
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
        completeRejected();
        return;
    }

    if ((taskCommand == QStringLiteral("i2i") || taskCommand == QStringLiteral("i2v")) &&
        payload.value(QStringLiteral("input_image")).toString().trimmed().isEmpty())
    {
        appendLogLine(QStringLiteral("%1 request blocked: choose an input image first.").arg(modeId.toUpper()));
        completeRejected();
        return;
    }

    QJsonObject requestPayload = payload;
    QString dest = requestPayload.value(QStringLiteral("output_folder")).toString().trimmed();
    if (dest.startsWith(QLatin1String("Not set"), Qt::CaseInsensitive))
        dest.clear();
    if (dest.isEmpty())
        dest = spellvision::generation::userGenerationDestFolder();
    if (dest.isEmpty() || !QDir(dest).exists())
    {
        const QString message = QStringLiteral("Choose an output folder to generate.");
        appendLogLine(message);
        page->setBusy(false, message);
        completeRejected();
        return;
    }
    requestPayload.insert(QStringLiteral("output_folder"), dest);

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
    setProperty("svTelemetrySawActive", false);

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

    // A new submit clears any stale error banner from the previous attempt.
    page->clearGenerationError();
    page->setBusy(true, enqueueOnly ? QStringLiteral("Queueing request…") : QStringLiteral("Submitting generation…"));

    const QJsonObject request = buildWorkerGenerationRequest(modeId, requestPayload);
    const QPointer<ImageGenerationPage> pageGuard(page);
    sendWorkerRequestAsync(
        request,
        [this, pageGuard, modeId, completion = std::move(completion)](
            const QJsonObject &response, const QString &stderrText, bool startedOk) mutable {
            if (!stderrText.trimmed().isEmpty())
                appendLogLine(stderrText.trimmed());
            if (pageGuard)
                pageGuard->setBusy(false, QString());

            if (!startedOk)
            {
                appendLogLine(QStringLiteral("Failed to start worker_client.py for %1.").arg(modeId.toUpper()));
                if (pageGuard)
                    pageGuard->showGenerationError(QStringLiteral("Worker didn't start — is the backend running?"));
                resetSubmissionTelemetry();
                if (completion)
                    completion({}, {}, false);
                return;
            }
            if (response.isEmpty())
            {
                appendLogLine(QStringLiteral("Worker returned no JSON payload for %1.").arg(modeId.toUpper()));
                if (pageGuard)
                    pageGuard->showGenerationError(QStringLiteral("Worker didn't respond — is it running?"));
                resetSubmissionTelemetry();
                if (completion)
                    completion({}, {}, false);
                return;
            }

            const bool ok = response.value(QStringLiteral("ok")).toBool(false);
            const QString errorText = response.value(QStringLiteral("error")).toString().trimmed();
            if (!ok)
            {
                const QString visibleError = errorText.isEmpty()
                    ? QStringLiteral("Worker rejected the request without an error message.")
                    : errorText;
                appendLogLine(QStringLiteral("%1 request failed: %2").arg(modeId.toUpper(), visibleError));
                const QString traceback = response.value(QStringLiteral("traceback")).toString().trimmed();
                if (!traceback.isEmpty())
                    appendLogLine(QStringLiteral("[%1 traceback]\n%2").arg(modeId.toUpper(), traceback));
                if (pageGuard)
                    pageGuard->showGenerationError(visibleError);
                resetSubmissionTelemetry();
                if (completion)
                    completion({}, {}, false);
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
            if (queueDock_ && !queueDock_->isVisible())
            {
                queueDock_->show();
                updateDockChrome();
            }
            if (completion)
                completion(queueId, jobId, true);
        });
}

void MainWindow::onWorkerQueueReachable()
{
    if (workerReachable_)
        return; // fire only on the false->true edge, never per-poll (no churn)

    // Latch before scheduling refresh so repeated successful polls cannot enqueue duplicate scans.
    workerReachable_ = true;

    // Defer off the queue controller's signal stack. Catalog traversal and classification
    // run in the page's background scan pipeline.
    QTimer::singleShot(0, this, [this]() {
        // Only the image pages consult the worker classifier; t2v_/i2v_ use the
        // untouched video-stack scan. Null-checks cover the window before lazy build.
        if (t2iPage_)
            t2iPage_->rescanModelCatalog();
        if (i2iPage_)
            i2iPage_->rescanModelCatalog();
        appendLogLine(QStringLiteral("worker-ready: re-scanned image catalogs"));
    });
}


void MainWindow::resolveComponentStackViaWorker(
    const QString &primary,
    const QString &family,
    const QString &task,
    const QJsonObject &choices,
    std::function<void(const QJsonArray &)> completion)
{
    if (primary.trimmed().isEmpty())
    {
        if (completion)
            completion({});
        return;
    }

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("resolve_component_stack"));
    request.insert(QStringLiteral("primary"), primary);
    if (!family.trimmed().isEmpty())
        request.insert(QStringLiteral("family"), family);
    if (!task.trimmed().isEmpty())
        request.insert(QStringLiteral("task"), task);
    request.insert(QStringLiteral("choices"), choices);

    sendWorkerRequestAsync(
        request,
        [completionFn = std::move(completion)](
            const QJsonObject &response, const QString &, bool startedOk) mutable {
            QJsonArray slotArray;
            if (startedOk && response.value(QStringLiteral("ok")).toBool(false))
                slotArray = response.value(QStringLiteral("slots")).toArray();
            if (completionFn)
                completionFn(slotArray);
        },
        12000);
}

void MainWindow::fetchOperatingPointsAsync(std::function<void()> completion)
{
    if (operatingPointsFetched_)
    {
        if (completion)
            completion();
        return;
    }
    if (completion)
        operatingPointsFetchWaiters_.push_back(std::move(completion));
    if (operatingPointsFetchInFlight_)
        return;

    operatingPointsFetchInFlight_ = true;
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("video_family_contracts"));
    sendWorkerRequestAsync(
        request,
        [this](const QJsonObject &response, const QString &, bool startedOk) {
            operatingPointsFetchInFlight_ = false;
            if (startedOk && response.value(QStringLiteral("ok")).toBool(false))
            {
                operatingPointsByFamily_.clear();
            const QJsonObject families = response.value(QStringLiteral("families")).toObject();
            for (auto it = families.constBegin(); it != families.constEnd(); ++it)
            {
                const QJsonObject fam = it.value().toObject();
                QJsonObject entry;
                entry.insert(QStringLiteral("operating_points"), fam.value(QStringLiteral("operating_points")));
                entry.insert(QStringLiteral("default_operating_point"), fam.value(QStringLiteral("default_operating_point")));
                entry.insert(QStringLiteral("samplers"), fam.value(QStringLiteral("samplers")));
                entry.insert(QStringLiteral("schedulers"), fam.value(QStringLiteral("schedulers")));
                entry.insert(QStringLiteral("default_sampler"), fam.value(QStringLiteral("default_sampler")));
                entry.insert(QStringLiteral("default_scheduler"), fam.value(QStringLiteral("default_scheduler")));
                operatingPointsByFamily_.insert(it.key().toLower(), entry);
            }
            const QJsonObject sampling = response.value(QStringLiteral("sampling")).toObject();
            for (auto sit = sampling.constBegin(); sit != sampling.constEnd(); ++sit)
            {
                const QString skey = sit.key().toLower();
                QJsonObject entry = operatingPointsByFamily_.value(skey);
                const QJsonObject block = sit.value().toObject();
                entry.insert(QStringLiteral("samplers"), block.value(QStringLiteral("samplers")));
                entry.insert(QStringLiteral("schedulers"), block.value(QStringLiteral("schedulers")));
                entry.insert(QStringLiteral("default_sampler"), block.value(QStringLiteral("default_sampler")));
                entry.insert(QStringLiteral("default_scheduler"), block.value(QStringLiteral("default_scheduler")));
                operatingPointsByFamily_.insert(skey, entry);
            }
                operatingPointsFetched_ = true;
            }

            auto waiters = std::move(operatingPointsFetchWaiters_);
            operatingPointsFetchWaiters_.clear();
            for (auto &waiter : waiters)
            {
                if (waiter)
                    waiter();
            }
        },
        12000);
}

QJsonObject MainWindow::operatingPointsForFamily(const QString &family) const
{
    const QString key = family.trimmed().toLower();
    if (key.isEmpty())
        return {};
    return operatingPointsByFamily_.value(key);
}

void MainWindow::sendWorkerRequestAsync(
    const QJsonObject &request,
    std::function<void(const QJsonObject &response, const QString &stderrText, bool startedOk)> completion,
    int timeoutMs)
{
    // Native socket for one-shot control commands -- the whole reason worker_client.py was spawned
    // is normalization this request does not need. ~78ms of CPython start per call, on a 1.8s poll
    // timer, for a protocol that is one JSON line each way. Streaming commands still take the
    // subprocess route below.
    if (spellvision::workers::WorkerSocketClient::canHandle(request))
    {
        spellvision::workers::WorkerSocketClient::send(this, request, timeoutMs, std::move(completion));
        return;
    }

    struct RequestState
    {
        QByteArray stdoutData;
        QByteArray stderrData;
        QStringList errors;
        bool started = false;
        bool done = false;
    };

    const QString projectRoot = resolveProjectRoot();
    const QString pythonExecutable = resolvePythonExecutable();
    const QString workerClient = QDir(projectRoot).filePath(QStringLiteral("python/worker_client.py"));
    auto *process = new QProcess(this);
    auto *timeout = new QTimer(process);
    timeout->setSingleShot(true);
    process->setWorkingDirectory(projectRoot);
    QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
    environment.insert(QStringLiteral("SPELLVISION_WORKER_CLIENT_TIMEOUT_SEC"),
                       QString::number(qMax(1, timeoutMs / 1000)));
    process->setProcessEnvironment(environment);

    const auto state = std::make_shared<RequestState>();
    const QPointer<MainWindow> self(this);
    const auto finish = std::make_shared<std::function<void()>>();
    *finish = [self, process, timeout, state, completion = std::move(completion)]() mutable {
        if (state->done)
            return;
        state->done = true;
        timeout->stop();
        state->stdoutData.append(process->readAllStandardOutput());
        state->stderrData.append(process->readAllStandardError());

        QString parseError;
        const QJsonObject response = parseLastJsonObjectFromStdout(
            QString::fromUtf8(state->stdoutData), &parseError);
        QStringList diagnostics;
        const QString stderrOutput = QString::fromUtf8(state->stderrData).trimmed();
        if (!stderrOutput.isEmpty())
            diagnostics << stderrOutput;
        diagnostics.append(state->errors);
        if (response.isEmpty() && !parseError.trimmed().isEmpty())
            diagnostics << parseError.trimmed();
        diagnostics.removeAll(QString());
        if (self && completion)
            completion(response, diagnostics.join(QChar('\n')), state->started);
        process->deleteLater();
    };

    constexpr qsizetype kMaxWorkerClientOutputBytes = 8 * 1024 * 1024;
    connect(process, &QProcess::readyReadStandardOutput, this, [process, state, finish]() {
        state->stdoutData.append(process->readAllStandardOutput());
        if (state->stdoutData.size() > kMaxWorkerClientOutputBytes)
        {
            state->errors << QStringLiteral("Worker response exceeded 8 MiB safety limit.");
            process->kill();
            (*finish)();
        }
    });
    connect(process, &QProcess::readyReadStandardError, this, [process, state, finish]() {
        state->stderrData.append(process->readAllStandardError());
        if (state->stderrData.size() > kMaxWorkerClientOutputBytes)
        {
            state->errors << QStringLiteral("Worker diagnostics exceeded 8 MiB safety limit.");
            process->kill();
            (*finish)();
        }
    });
    connect(process, &QProcess::started, this, [process, request, state, finish]() {
        state->started = true;
        const QByteArray payload = QJsonDocument(request).toJson(QJsonDocument::Compact) + '\n';
        if (process->write(payload) != payload.size())
        {
            state->errors << QStringLiteral("Failed to write worker request payload.");
            process->kill();
            (*finish)();
            return;
        }
        process->closeWriteChannel();
    });
    connect(process,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this,
            [state, finish](int exitCode, QProcess::ExitStatus exitStatus) {
                if (exitStatus != QProcess::NormalExit)
                    state->errors << QStringLiteral("Worker client process crashed.");
                else if (exitCode != 0)
                    state->errors << QStringLiteral("Worker client exited with code %1.").arg(exitCode);
                (*finish)();
            });
    connect(process, &QProcess::errorOccurred, this, [process, state, finish](QProcess::ProcessError error) {
        state->errors << process->errorString();
        if (error == QProcess::FailedToStart)
            (*finish)();
    });
    connect(timeout, &QTimer::timeout, this, [process, state, finish]() {
        state->errors << QStringLiteral("Worker request timed out.");
        if (process->state() != QProcess::NotRunning)
            process->kill();
        (*finish)();
    });

    timeout->start(qMax(1, timeoutMs));
    process->start(pythonExecutable, {workerClient});
}

void MainWindow::tearDownComfyOnExit()
{
    QProcess *ownedProcess = ownedComfyProcess_;
    if (!ownedProcess)
        return;

    if (ownedProcess->state() == QProcess::NotRunning)
    {
        ownedComfyProcess_ = nullptr;
        QFile::remove(comfyRuntimeSessionPath());
        ownedProcess->deleteLater();
        return;
    }

    const spellvision::shell::RuntimeProfile profile =
        spellvision::shell::RuntimeProfile::load(resolveProjectRoot());
    const spellvision::shell::ComfyQueueState queueState =
        spellvision::shell::probeComfyQueueState(profile.comfyHost, profile.comfyPort, 500);
    if (queueState != spellvision::shell::ComfyQueueState::Idle)
    {
        appendLogLine(queueState == spellvision::shell::ComfyQueueState::Busy
                          ? QStringLiteral("ComfyUI still has active work; leaving the app-started runtime running.")
                          : QStringLiteral("Could not verify ComfyUI queue state; leaving the app-started runtime running."));
        disconnect(ownedProcess, nullptr, this, nullptr);
        ownedProcess->setParent(nullptr);
        ownedComfyProcess_ = nullptr;
        QFile::remove(comfyRuntimeSessionPath());
        return;
    }

    ownedProcess->terminate();
    if (!ownedProcess->waitForFinished(2000))
    {
        ownedProcess->kill();
        ownedProcess->waitForFinished(2000);
    }
    ownedComfyProcess_ = nullptr;
    QFile::remove(comfyRuntimeSessionPath());
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
    const spellvision::shell::RuntimeProfile profile = spellvision::shell::RuntimeProfile::load(resolveProjectRoot());
    if (profile.workerPythonReady())
        return profile.workerPython;
    return QStringLiteral("python");
}

QJsonObject MainWindow::buildWorkerGenerationRequest(const QString &modeId, const QJsonObject &payload) const
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
    spellvision::shell::RuntimeProfile::load(resolveProjectRoot()).applyToWorkerRequest(request);
    if (!kStudioExecutionCommands.contains(studioCommand))
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

QJsonObject MainWindow::buildWorkflowLaunchRequest(const QJsonObject &profile,
                                                   const QString &modelOverride,
                                                   const QString &loraOverride,
                                                   const QString &loraScaleOverride) const
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

    const QString comfyRoot = defaultManagedComfyRoot(projectRoot);

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

void MainWindow::launchWorkflowProfile(const QJsonObject &profile)
{
    // Flows-page launch: no model chosen by the user here, so fall back to dev hook / cockpit.
    launchWorkflowProfileWithModel(profile, QString(), QString(), /*hasExplicitOverride=*/false);
}

void MainWindow::launchWorkflowProfileWithModel(const QJsonObject &profile,
                                                const QString &explicitModel,
                                                const QString &explicitLora,
                                                bool hasExplicitOverride)
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

    // Model override precedence (Stage 3 makes the real path primary):
    //   1. An explicit override from the Models page "Use workflow" -- wins outright, including the
    //      deliberate empty override used for a dual-loader workflow (launch unbound; baked-in pair wins).
    //   2. Otherwise (Flows-page launch): the dev hook, then the cockpit page's selected model/LoRA.
    QString modelOverride;
    QString loraOverride;
    QString loraScaleOverride;
    if (hasExplicitOverride)
    {
        modelOverride = explicitModel.trimmed();
        loraOverride = explicitLora.trimmed();
    }
    else
    {
        modelOverride = qEnvironmentVariable("SPELLVISION_WORKFLOW_MODEL_OVERRIDE").trimmed();
        if (modelOverride.isEmpty())
        {
            const QString workflowMode = profile.value(QStringLiteral("task_command")).toString().trimmed();
            if (ImageGenerationPage *page = generationPageForMode(workflowMode))
            {
                modelOverride = page->selectedModelValue().trimmed();
                loraOverride = page->selectedLoraValue().trimmed();
            }
        }
    }

    const QJsonObject request = buildWorkflowLaunchRequest(profile, modelOverride, loraOverride, loraScaleOverride);
    appendLogLine(QStringLiteral("Workflow submission started: %1")
                      .arg(profileName.isEmpty() ? QStringLiteral("Imported Workflow") : profileName));
    sendWorkerRequestAsync(
        request,
        [this, profileName, missingCustomNodeCount](
            const QJsonObject &response, const QString &stderrText, bool startedOk) {
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
            if (!ok)
            {
                QMessageBox::warning(
                    this,
                    QStringLiteral("Workflow Launch"),
                    errorText.isEmpty()
                        ? QStringLiteral("Workflow launch failed without an error message.")
                        : QStringLiteral("Workflow launch failed: %1").arg(errorText));
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
        });
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

    // BREAK 1: surface the newest FAILED job for this mode on the page's error banner, when a
    // failure is the newest terminal item (a later completion supersedes it). This is the live
    // path for a job that submits OK then fails during execution.
    {
        const QueueItem *newestFailed = nullptr;
        qint64 newestFailedKey = (std::numeric_limits<qint64>::min)();
        for (const QueueItem &item : items)
        {
            if (generationModeIdForQueueItem(item) != currentModeId_)
                continue;
            if (queueItemIsActiveForGeneration(item))
                continue;
            if (!item.failed)
                continue;
            const qint64 sortKey = queueItemPreviewSortKey(item);
            if (!newestFailed || sortKey > newestFailedKey ||
                (sortKey == newestFailedKey && item.orderIndex > newestFailed->orderIndex))
            {
                newestFailed = &item;
                newestFailedKey = sortKey;
            }
        }

        if (newestFailed && (!newestCompleted || newestFailedKey >= newestSortKey))
        {
            const QString jobKey = newestFailed->workerJobId.trimmed().isEmpty()
                ? newestFailed->id.trimmed()
                : newestFailed->workerJobId.trimmed();
            const QString errKey = QStringLiteral("%1|%2|%3")
                                       .arg(currentModeId_, jobKey, newestFailed->errorText);
            if (lastSyncedGenerationErrorByMode_.value(currentModeId_) != errKey)
            {
                lastSyncedGenerationErrorByMode_.insert(currentModeId_, errKey);
                const QString msg = newestFailed->errorText.trimmed().isEmpty()
                    ? QStringLiteral("Generation failed — the worker reported no message.")
                    : newestFailed->errorText.trimmed();
                page->showGenerationError(msg);
                // The traceback is never shown on the banner; route it to the log for debugging.
                if (!newestFailed->errorTraceback.trimmed().isEmpty())
                    appendLogLine(QStringLiteral("[%1 failure traceback]\n%2")
                                      .arg(currentModeId_.toUpper(),
                                           newestFailed->errorTraceback.trimmed()));
            }
            return; // a fresh failure is the newest terminal state — don't bind an older completed
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

    // A genuinely new completed output supersedes any error banner from a prior failure.
    page->clearGenerationError();
    lastSyncedGenerationErrorByMode_.remove(currentModeId_);

    page->setPreviewImage(newestCompleted->outputPath, caption);

    // One terminal recovery write is acceptable when a genuinely new completed
    // output appears. Repeated queue polls now return above without touching UI.
    page->setBusy(false, QStringLiteral("Ready"));
}

void MainWindow::submitStudioGenerationRequest(const QString &studioMode,
                                               const QString &modeId,
                                               QJsonObject payload,
                                               bool enqueueOnly)
{
    QString effectiveMode = modeId.trimmed().isEmpty() ? QStringLiteral("t2i") : modeId.trimmed().toLower();
    const QString inputImage = payload.value(QStringLiteral("input_image")).toString().trimmed();
    if (effectiveMode == QStringLiteral("t2i") && !inputImage.isEmpty())
        effectiveMode = QStringLiteral("i2i");

    ensureGenerationPageBuilt(effectiveMode);
    ImageGenerationPage *page = generationPageForMode(effectiveMode);
    if (!page) {
        appendLogLine(QStringLiteral("Studio submit failed: no generation page for %1").arg(effectiveMode));
        return;
    }

    const QString studio = studioMode.trimmed().toLower();
    const int comicPanelIndex = payload.value(QStringLiteral("_comic_panel_index")).toInt(-1);
    const QString prefix = payload.value(QStringLiteral("output_prefix")).toString().trimmed();
    payload.remove(QStringLiteral("_comic_panel_index"));
    payload.remove(QStringLiteral("_comic_project"));

    const QJsonObject pagePayload = page->buildRequestPayload();
    const auto takeIfMissing = [&](const QString &key) {
        const QString cur = payload.value(key).toString().trimmed();
        if (cur.isEmpty() && pagePayload.contains(key))
            payload.insert(key, pagePayload.value(key));
    };
    const bool studioHasModel = !payload.value(QStringLiteral("model")).toString().trimmed().isEmpty();
    takeIfMissing(QStringLiteral("model"));
    takeIfMissing(QStringLiteral("model_display"));
    // C1: never steal family/modality from another cockpit when the studio already picked a checkpoint.
    if (!studioHasModel) {
        takeIfMissing(QStringLiteral("model_family"));
        takeIfMissing(QStringLiteral("model_modality"));
    }
    takeIfMissing(QStringLiteral("sampler"));
    takeIfMissing(QStringLiteral("scheduler"));
    takeIfMissing(QStringLiteral("output_folder"));
    if (!payload.contains(QStringLiteral("loras")) && pagePayload.contains(QStringLiteral("loras")))
        payload.insert(QStringLiteral("loras"), pagePayload.value(QStringLiteral("loras")));
    if (!payload.contains(QStringLiteral("model_stack")) && pagePayload.contains(QStringLiteral("model_stack")))
        payload.insert(QStringLiteral("model_stack"), pagePayload.value(QStringLiteral("model_stack")));

    appendLogLine(QStringLiteral("Studio[%1] → %2 submit").arg(studio, effectiveMode.toUpper()));

    if (characterStudioPage_ && studio == QStringLiteral("character"))
        characterStudioPage_->setBusy(true, QStringLiteral("Submitting…"));
    if (comicStudioPage_ && studio == QStringLiteral("comic"))
        comicStudioPage_->setBusy(true, QStringLiteral("Submitting…"));
    if (conceptReferencePage_ && studio == QStringLiteral("concept"))
        conceptReferencePage_->setBusy(true, QStringLiteral("Submitting…"));

    submitGenerationRequest(
        page,
        effectiveMode,
        payload,
        enqueueOnly,
        [this, studio, comicPanelIndex, prefix](
            const QString &queueId, const QString &jobId, bool accepted) {
            const QString key = !queueId.isEmpty() ? queueId : jobId;
            if (!accepted || key.isEmpty())
            {
                if (characterStudioPage_ && studio == QStringLiteral("character"))
                    characterStudioPage_->setBusy(false, QStringLiteral("Submit failed"));
                if (comicStudioPage_ && studio == QStringLiteral("comic"))
                    comicStudioPage_->setBusy(false, QStringLiteral("Submit failed"));
                if (conceptReferencePage_ && studio == QStringLiteral("concept"))
                    conceptReferencePage_->setBusy(false, QStringLiteral("Submit failed"));
                return;
            }

            PendingStudioPreview preview;
            preview.studioMode = studio;
            preview.comicPanelIndex = comicPanelIndex;
            preview.prefix = prefix;
            preview.submitMs = QDateTime::currentMSecsSinceEpoch();
            preview.correlationKeys = {key};
            if (!jobId.isEmpty() && !preview.correlationKeys.contains(jobId))
                preview.correlationKeys.push_back(jobId);
            if (!queueId.isEmpty() && !preview.correlationKeys.contains(queueId))
                preview.correlationKeys.push_back(queueId);
            for (const QString &correlationKey : preview.correlationKeys)
                pendingStudioPreviews_.insert(correlationKey, preview);
        });
}

void MainWindow::syncStudioPreviewsFromQueue()
{
    if (pendingStudioPreviews_.isEmpty() || !queueManager_)
        return;

    const QVector<QueueItem> &items = queueManager_->items();
    QStringList resolvedKeys;

    auto matchKey = [this](const QueueItem &item) -> QString {
        const QStringList handles = {
            item.id.trimmed(),
            item.workerJobId.trimmed(),
            item.sourceJobId.trimmed(),
        };
        for (const QString &handle : handles) {
            if (!handle.isEmpty() && pendingStudioPreviews_.contains(handle))
                return handle;
        }
        return {};
    };

    auto dropItemKeys = [&](const QueueItem &item, const QString &matched) {
        resolvedKeys.append(matched);
        const PendingStudioPreview correlated = pendingStudioPreviews_.value(matched);
        resolvedKeys.append(correlated.correlationKeys);
        const QStringList handles = {
            item.id.trimmed(),
            item.workerJobId.trimmed(),
            item.sourceJobId.trimmed(),
        };
        for (const QString &handle : handles) {
            if (!handle.isEmpty())
                resolvedKeys.append(handle);
        }
    };

    auto clearStudioBusy = [this](const QString &studio, const QString &message) {
        if (studio == QStringLiteral("character") && characterStudioPage_)
            characterStudioPage_->setBusy(false, message);
        else if (studio == QStringLiteral("comic") && comicStudioPage_)
            comicStudioPage_->setBusy(false, message);
        else if (studio == QStringLiteral("concept") && conceptReferencePage_)
            conceptReferencePage_->setBusy(false, message);
    };

    for (const QueueItem &item : items) {
        const QString key = matchKey(item);
        if (key.isEmpty())
            continue;

        const PendingStudioPreview preview = pendingStudioPreviews_.value(key);
        const bool failed = item.failed || item.cancelled
            || item.state == QueueItemState::Failed
            || item.state == QueueItemState::Cancelled;
        const bool completed = item.completed || item.state == QueueItemState::Completed;

        if (failed) {
            clearStudioBusy(preview.studioMode, QStringLiteral("Generation failed"));
            dropItemKeys(item, key);
            continue;
        }

        if (!completed)
            continue;

        const QString out = item.outputPath.trimmed();
        if (out.isEmpty() || !QFileInfo::exists(out)) {
            const qint64 terminalMs = item.finishedAt.isValid()
                ? item.finishedAt.toMSecsSinceEpoch()
                : (item.updatedAt.isValid() ? item.updatedAt.toMSecsSinceEpoch() : 0);
            const qint64 nowMs = QDateTime::currentMSecsSinceEpoch();
            const bool withinSettleGrace = terminalMs > 0
                && nowMs >= terminalMs
                && nowMs - terminalMs < kStudioOutputSettleMs;
            if (withinSettleGrace) {
                if (!preview.settleRetryScheduled) {
                    for (const QString &correlationKey : preview.correlationKeys) {
                        auto correlated = pendingStudioPreviews_.find(correlationKey);
                        if (correlated != pendingStudioPreviews_.end())
                            correlated->settleRetryScheduled = true;
                    }
                    const int retryDelayMs = static_cast<int>(
                        qMax<qint64>(1, kStudioOutputSettleMs - (nowMs - terminalMs) + 50));
                    QTimer::singleShot(retryDelayMs, this, [this]() {
                        syncStudioPreviewsFromQueue();
                    });
                }
                continue;
            }

            clearStudioBusy(
                preview.studioMode,
                QStringLiteral("Generation completed, but no output file was produced"));
            dropItemKeys(item, key);
            continue;
        }

        if (preview.submitMs > 0) {
            const qint64 finished = item.finishedAt.isValid() ? item.finishedAt.toMSecsSinceEpoch()
                                   : (item.updatedAt.isValid() ? item.updatedAt.toMSecsSinceEpoch() : 0);
            if (finished > 0 && finished + 250 < preview.submitMs)
                continue;
        }

        if (preview.studioMode == QStringLiteral("character") && characterStudioPage_) {
            characterStudioPage_->setPreviewImage(out, QStringLiteral("From queue"));
            characterStudioPage_->setBusy(false, QStringLiteral("Ready"));
        } else if (preview.studioMode == QStringLiteral("comic") && comicStudioPage_) {
            comicStudioPage_->setPanelResult(preview.comicPanelIndex, out);
            comicStudioPage_->setBusy(false, QStringLiteral("Ready"));
        } else if (preview.studioMode == QStringLiteral("concept") && conceptReferencePage_) {
            conceptReferencePage_->setPreviewImage(out, QStringLiteral("From queue"));
            conceptReferencePage_->setBusy(false, QStringLiteral("Ready"));
        }

        dropItemKeys(item, key);
    }

    for (const QString &key : resolvedKeys)
        pendingStudioPreviews_.remove(key);
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
        // Width owned by reflowBottomTelemetryWidths — do not force 104 here.
        bottomQueueLabel_->setWordWrap(false);
        bottomQueueLabel_->setAlignment(Qt::AlignCenter);
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
        commandPaletteDialog_ = new CommandPaletteDialog(this);

    populatePaletteTopLevel();

    commandPaletteDialog_->show();
    commandPaletteDialog_->raise();
    commandPaletteDialog_->activateWindow();
}

void MainWindow::populatePaletteTopLevel()
{
    if (!commandPaletteDialog_)
        return;

    using Command = CommandPaletteDialog::Command;
    QVector<Command> cmds;
    const auto add = [&cmds](const QString &id, const QString &title, const QString &category,
                             const QString &shortcut, std::function<void()> action, bool keepOpen = false,
                             const QString &keywords = QString()) {
        Command c;
        c.id = id;
        c.title = title;
        c.category = category;
        c.keywords = keywords;
        c.shortcut = shortcut;
        c.action = std::move(action);
        c.keepOpen = keepOpen;
        cmds.push_back(c);
    };

    const QString nav = QStringLiteral("Navigation");
    add(QStringLiteral("nav.home"), QStringLiteral("Home"), nav, QString(), [this]() { switchToMode(QStringLiteral("home")); }, false, QStringLiteral("gallery outputs"));
    add(QStringLiteral("nav.t2i"), QStringLiteral("Text to Image"), nav, QString(), [this]() { switchToMode(QStringLiteral("t2i")); }, false, QStringLiteral("t2i txt2img"));
    add(QStringLiteral("nav.i2i"), QStringLiteral("Image to Image"), nav, QString(), [this]() { switchToMode(QStringLiteral("i2i")); }, false, QStringLiteral("i2i img2img"));
    add(QStringLiteral("nav.t2v"), QStringLiteral("Text to Video"), nav, QString(), [this]() { switchToMode(QStringLiteral("t2v")); }, false, QStringLiteral("t2v txt2vid"));
    add(QStringLiteral("nav.i2v"), QStringLiteral("Image to Video"), nav, QString(), [this]() { switchToMode(QStringLiteral("i2v")); }, false, QStringLiteral("i2v img2vid"));
    // v1.0 nav gate: only offer Chain Studio in the palette when it isn't hidden (see isModeHidden).
    if (!spellvision::shell::ShellNavigationController::isModeHidden(QStringLiteral("chain")))
        add(QStringLiteral("nav.chain"), QStringLiteral("Chain Studio"), nav, QString(), [this]() { switchToMode(QStringLiteral("chain")); });
    add(QStringLiteral("nav.character"), QStringLiteral("Character Studio"), nav, QString(), [this]() { switchToMode(QStringLiteral("character")); }, false, QStringLiteral("character 3d pipeline"));
    add(QStringLiteral("nav.concept"), QStringLiteral("Concept Reference Lab"), nav, QString(), [this]() { switchToMode(QStringLiteral("concept")); }, false, QStringLiteral("multiview concept sfw nsfw reference packs"));
    add(QStringLiteral("nav.comic"), QStringLiteral("Comic Studio"), nav, QString(), [this]() { switchToMode(QStringLiteral("comic")); }, false, QStringLiteral("comic panels manga"));
    if (!spellvision::shell::ShellNavigationController::isModeHidden(QStringLiteral("gen3d")))
        add(QStringLiteral("nav.gen3d"), QStringLiteral("Image to 3D"), nav, QStringLiteral("Ctrl+Shift+3"), [this]() { switchToMode(QStringLiteral("gen3d")); }, false, QStringLiteral("gen3d i23d mesh trellis"));
    add(QStringLiteral("nav.dataset"), QStringLiteral("Dataset Generator"), nav, QStringLiteral("Ctrl+Shift+D"), [this]() { switchToMode(QStringLiteral("dataset")); }, false, QStringLiteral("dataset batch t2i"));
    add(QStringLiteral("nav.models"), QStringLiteral("Models"), nav, QString(), [this]() { switchToMode(QStringLiteral("models")); });
    add(QStringLiteral("nav.workflows"), QStringLiteral("Workflows"), nav, QString(), [this]() { switchToMode(QStringLiteral("workflows")); });
    add(QStringLiteral("nav.history"), QStringLiteral("History"), nav, QString(), [this]() { switchToMode(QStringLiteral("history")); });
    add(QStringLiteral("nav.inspiration"), QStringLiteral("Inspiration"), nav, QStringLiteral("Ctrl+9"), [this]() { switchToMode(QStringLiteral("inspiration")); }, false, QStringLiteral("inspire moodboard gallery"));
    add(QStringLiteral("nav.runtime"), QStringLiteral("Runtime"), nav, QStringLiteral("Ctrl+Shift+U"), [this]() { switchToMode(QStringLiteral("runtime")); }, false, QStringLiteral("comfy manager nodes restart"));
    add(QStringLiteral("nav.train"), QStringLiteral("Train"), nav, QStringLiteral("Ctrl+Shift+T"), [this]() { switchToMode(QStringLiteral("train")); }, false, QStringLiteral("sohya house lora trainer"));
    add(QStringLiteral("nav.settings"), QStringLiteral("Settings"), nav, QString(), [this]() { switchToMode(QStringLiteral("settings")); });

    // Generation / Prompt / Output commands act on the ACTIVE generation cockpit; only offer them when
    // one is current (on Home/Models there's no page to target).
    ImageGenerationPage *page = generationPageForMode(currentModeId_);
    const QString gen = QStringLiteral("Generation");
    if (page)
    {
        add(QStringLiteral("gen.generate"), QStringLiteral("Generate"), gen, QString(), [page]() { page->triggerGenerate(); });
        add(QStringLiteral("gen.randseed"), QStringLiteral("Randomize seed"), gen, QString(), [page]() { page->randomizeSeed(); });
        add(QStringLiteral("gen.uselast"), QStringLiteral("Use last output as input"), gen, QString(), [page]() { page->useLatestForI2I(); });
    }

    // Models -- "Load model…" / "Add LoRA…" open the second-level picker (keepOpen: the palette stays
    // up and repopulates with inventory instead of closing).
    const QString models = QStringLiteral("Models");
    add(QStringLiteral("model.load"), QStringLiteral("Load model…"), models, QString(), [this]() { enterModelPickerMode(false); }, true);
    add(QStringLiteral("model.lora"), QStringLiteral("Add LoRA…"), models, QString(), [this]() { enterModelPickerMode(true); }, true);
    if (page)
        add(QStringLiteral("model.clearlora"), QStringLiteral("Clear LoRA stack"), models, QString(), [page]() { page->clearLoraStack(); });

    const QString prompt = QStringLiteral("Prompt");
    if (page)
    {
        add(QStringLiteral("prompt.copy"), QStringLiteral("Copy prompt"), prompt, QString(), [page]() { page->copyPromptToClipboard(); });
        add(QStringLiteral("prompt.clear"), QStringLiteral("Clear prompt"), prompt, QString(), [page]() { page->clearPromptText(); });
    }

    const QString output = QStringLiteral("Output");
    if (page)
    {
        add(QStringLiteral("out.folder"), QStringLiteral("Open output folder"), output, QString(), [page]() {
            const QString p = page->latestGeneratedOutputPath();
            if (!p.isEmpty())
                QDesktopServices::openUrl(QUrl::fromLocalFile(QFileInfo(p).absolutePath()));
        });
        add(QStringLiteral("out.open"), QStringLiteral("Open last output"), output, QString(), [page]() {
            const QString p = page->latestGeneratedOutputPath();
            if (!p.isEmpty())
                QDesktopServices::openUrl(QUrl::fromLocalFile(p));
        });
        add(QStringLiteral("out.copypath"), QStringLiteral("Copy last output path"), output, QString(), [page]() {
            const QString p = page->latestGeneratedOutputPath();
            if (!p.isEmpty())
                if (QClipboard *clip = QGuiApplication::clipboard())
                    clip->setText(p);
        });
    }

    const QString workflows = QStringLiteral("Workflows");
    add(QStringLiteral("wf.import"), QStringLiteral("Import Workflow"), workflows, QString(), [this]() { openWorkflowImportDialog(); });
    add(QStringLiteral("wf.library"), QStringLiteral("Open Workflow Library"), workflows, QString(), [this]() { switchToMode(QStringLiteral("workflows")); });

    const QString system = QStringLiteral("System");
    add(QStringLiteral("sys.theme"), QStringLiteral("Cycle theme"), system, QString(), [this]() { cycleTheme(); });
    add(QStringLiteral("sys.rail"), QStringLiteral("Toggle rail"), system, QString(), [this]() { togglePrimarySidebar(); });
    add(QStringLiteral("sys.inspector"), QStringLiteral("Toggle inspector"), system, QString(), [this]() { toggleDetailsPanel(); });
    add(QStringLiteral("sys.bottom"), QStringLiteral("Toggle bottom panel"), system, QString(), [this]() { toggleBottomPanels(); });
    add(QStringLiteral("sys.quit"), QStringLiteral("Quit"), system, QString(), [this]() { close(); });

    commandPaletteDialog_->setCommands(cmds, QStringLiteral("Search commands, models…"));
}

void MainWindow::enterModelPickerMode(bool loraOnly)
{
    if (!commandPaletteDialog_)
        return;

    using Command = CommandPaletteDialog::Command;
    QVector<Command> cmds;
    if (modelsPage_)
    {
        const auto inventory = modelsPage_->inventorySnapshot();
        for (const auto &item : inventory)
        {
            // detectType() buckets: "Model" (checkpoint), "LoRA", "VAE", "Encoder", "Upscaler",
            // "ControlNet". Only checkpoints and LoRAs have a generation-slot destination, so filter to
            // exactly the one this picker is for -- upscalers/VAEs/encoders/controlnets would just fail
            // the handoff.
            const QString typeLower = item.type.trimmed().toLower();
            if (loraOnly)
            {
                if (typeLower != QStringLiteral("lora"))
                    continue;
            }
            else if (typeLower != QStringLiteral("model"))
            {
                continue;
            }

            Command c;
            c.id = QStringLiteral("model:") + item.path;
            c.title = item.name;
            c.subtitle = item.type + QStringLiteral(" · ") + item.family; // show type + family in the row
            const QString name = item.name;
            const QString family = item.family;
            const QString type = item.type;
            const QString meta = item.metadataPath;
            c.action = [this, name, family, type, meta]() {
                const QStringList triggers = modelsPage_ ? modelsPage_->triggerWordsFor(meta) : QStringList();
                sendModelToGeneration(name, family, type, triggers); // routes by family + applies handoff
            };
            cmds.push_back(c);
        }
    }

    std::sort(cmds.begin(), cmds.end(), [](const Command &a, const Command &b) {
        return a.title.compare(b.title, Qt::CaseInsensitive) < 0;
    });

    commandPaletteDialog_->setCommands(cmds, loraOnly ? QStringLiteral("Search LoRAs…   (Esc: back)")
                                                      : QStringLiteral("Search models…   (Esc: back)"));
    // Esc returns to the top-level command set instead of closing.
    commandPaletteDialog_->setBackHandler([this]() { populatePaletteTopLevel(); });
}

void MainWindow::cycleTheme()
{
    ThemeManager &tm = ThemeManager::instance();
    const int count = tm.presetNames().size();
    if (count <= 1)
        return;
    tm.setPresetByIndex((tm.presetIndex() + 1) % count);
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

    // The key the user saved in Settings never reached the import path, so a Civitai link that
    // needs auth failed with a 401 the user had already given us the answer to. Only sent for
    // civitai.com, and never forwarded across a redirect (see workflow_url_import).
    const QString civitaiKey = SecureCredentialStore::credential(QStringLiteral("civitai_api_key"));
    if (!civitaiKey.isEmpty())
        request.insert(QStringLiteral("civitai_api_key"), civitaiKey);

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

    // NVML answers in ~3us with no process; nvidia-smi cost ~46ms per spawn, 30 times a minute
    // for the whole life of the app. Fall through to nvidia-smi only when NVML is unavailable.
    const GpuMemoryProbe::Reading reading = GpuMemoryProbe::instance().read();
    if (reading.valid)
    {
        const QString nextText = pass28qFormatVramText(reading.usedMb, reading.totalMb);
        if (lastVramTelemetryText_ != nextText)
        {
            lastVramTelemetryText_ = nextText;
            applyTelemetryText(bottomVramLabel_, lastVramTelemetryText_, true, true); // VRAM label only (see below)
        }
        return;
    }

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
        // FLASH FIX: update ONLY the VRAM label -- do NOT re-run the full sync (which recomputes
        // busy/progress from off-beat queue state on the 2000ms VRAM cadence, racing the 1800ms poll).
        applyTelemetryText(bottomVramLabel_, lastVramTelemetryText_, true, true);

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
            applyTelemetryText(bottomVramLabel_, lastVramTelemetryText_, true, true); // VRAM label only (see above)
        }

        process->deleteLater();
    });

    process->start();
}




void MainWindow::startComfyHealthPolling()
{
    if (!comfyHealthNam_)
        comfyHealthNam_ = new QNetworkAccessManager(this);

    if (!comfyHealthTimer_)
    {
        comfyHealthTimer_ = new QTimer(this);
        comfyHealthTimer_->setInterval(3000); // Comfy state changes slowly; 3s cadence is plenty
        connect(comfyHealthTimer_, &QTimer::timeout, this, &MainWindow::pollComfyHealth);
    }

    // Re-color the dots when the theme switches (the rich text bakes in hex colors).
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged,
            this, &MainWindow::updateBackendHealthLabel);

    if (!comfyHealthTimer_->isActive())
        comfyHealthTimer_->start();

    pollComfyHealth(); // seed now instead of waiting a full interval
}

void MainWindow::pollComfyHealth()
{
    if (!comfyHealthNam_ || comfyHealthInFlight_)
        return;

    const int envPort = qEnvironmentVariableIntValue("SPELLVISION_COMFY_PORT");
    const int comfyPort = envPort > 0 ? envPort : 8188;

    QNetworkRequest request(QUrl(QStringLiteral("http://127.0.0.1:%1/system_stats").arg(comfyPort)));
    request.setTransferTimeout(1500); // a hung Comfy must read as down, not stall the probe
    request.setAttribute(QNetworkRequest::CacheLoadControlAttribute, QNetworkRequest::AlwaysNetwork);

    comfyHealthInFlight_ = true;
    QNetworkReply *reply = comfyHealthNam_->get(request);
    connect(reply, &QNetworkReply::finished, this, [this, reply]() {
        const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        comfyReachable_ = (reply->error() == QNetworkReply::NoError) && (status == 200);
        comfyHealthProbed_ = true;
        comfyHealthInFlight_ = false;
        updateBackendHealthLabel();
        reply->deleteLater();
    });
}

void MainWindow::updateBackendHealthLabel()
{
    if (!bottomBackendLabel_)
        return;

    ThemeManager &theme = ThemeManager::instance();
    const QString online = theme.css(ThemeManager::Color::Success);
    const QString offline = theme.css(ThemeManager::Color::Error);
    const QString checking = theme.css(ThemeManager::Color::TextLo);

    const QString workerColor = workerReachable_ ? online : offline;
    const QString comfyColor = !comfyHealthProbed_ ? checking : (comfyReachable_ ? online : offline);

    // "Backend" caption + two dots. Left dot = Worker (:8765), right dot = Comfy (:8188) — the
    // tooltip spells it out. Aggregate at-a-glance: both green = healthy, any red = something down.
    const QString html = QStringLiteral(
        "Backend&nbsp;&nbsp;"
        "<span style='color:%1'>&#9679;</span>&nbsp;"
        "<span style='color:%2'>&#9679;</span>")
        .arg(workerColor, comfyColor);
    if (bottomBackendLabel_->text() != html)
        bottomBackendLabel_->setText(html);

    const QString workerState = workerReachable_ ? QStringLiteral("online") : QStringLiteral("offline");
    const QString comfyState = !comfyHealthProbed_
        ? QStringLiteral("checking…")
        : (comfyReachable_ ? QStringLiteral("online") : QStringLiteral("offline"));
    const QString tip = QStringLiteral("Backend health\nWorker (:8765) — %1\nComfy (:8188) — %2")
        .arg(workerState, comfyState);
    if (bottomBackendLabel_->toolTip() != tip)
        bottomBackendLabel_->setToolTip(tip);
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

    // Latch that this mode's submitted job was actually seen running, so the video-completion
    // detector below can't be tripped by the submit -> first-poll window (stale prior items).
    if (activeItem != nullptr)
        setProperty("svTelemetrySawActive", true);

    const bool explicitBusy =
        property("svTelemetryBusy").toBool() &&
        property("svTelemetryBusyMode").toString() == currentModeId_;

    const int completedRowsAtSubmit = property("svTelemetryCompletedRowsAtSubmit").toInt();

    // Video workspaces (i2v/t2v) have no completed-row ledger, so the image heuristic below
    // never fires for them -> the bar would latch at "Running 95%" forever after a video render
    // finished. Detect video completion as: busy latched for this mode + we saw the job run +
    // the worker no longer reports an active job for it (render done, success or error).
    const bool videoCompletionObserved =
        explicitBusy &&
        !imageWorkspace &&
        activeItem == nullptr &&
        property("svTelemetrySawActive").toBool();

    // FLASH FIX: image completion must require the worker no longer reports an ACTIVE job for this
    // mode (activeItem == nullptr) -- same discipline the video path already uses. Previously a new
    // terminal row appearing while the job was still running tripped completion, which fired the
    // 900ms idle-reset pulse mid-render; the next poll saw the job still active and re-filled the bar
    // -> the reported idle<->progress flash. Gating on activeItem==nullptr keeps `busy` latched
    // through the whole render so the monotonic progress guards below hold.
    const bool completedOutputObserved =
        (explicitBusy &&
         imageWorkspace &&
         activeItem == nullptr &&
         completedRowsAtSubmit >= 0 &&
         visibleQueueCount > completedRowsAtSubmit) ||
        videoCompletionObserved;

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
            setProperty("svTelemetrySawActive", false);
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

    applyTelemetryText(bottomReadyLabel_, (busy || completionPulse || completedOutputObserved) ? QStringLiteral("Busy") : QStringLiteral("Ready"), false, false);
    applyTelemetryText(bottomPageLabel_, pageContextForMode(currentModeId_), false, false);
    updateBackendHealthLabel(); // worker (:8765) reachability may have flipped since last sync
    applyTelemetryText(bottomQueueLabel_, QStringLiteral("Queue: %1").arg(visibleQueueCount), false, false); // keep its drawer tooltip

    applyTelemetryText(bottomVramLabel_, lastVramTelemetryText_.trimmed().isEmpty()
        ? QStringLiteral("VRAM: checking")
        : lastVramTelemetryText_, true, true);

    ImageGenerationPage *page = generationPageForMode(currentModeId_);
    const QString modelValue = page ? page->selectedModelValue() : QString();
    const QString loraValue = page ? page->selectedLoraValue() : QString();

    applyTelemetryText(bottomModelLabel_, QStringLiteral("Model: %1").arg(telemetryShortAssetName(modelValue)), true, true);
    applyTelemetryText(bottomLoraLabel_, QStringLiteral("LoRA: %1").arg(telemetryShortAssetName(loraValue)), true, true);
    applyTelemetryText(bottomStateLabel_, stateText, false, false);

    // ETA: client-side estimate from step/steps + startedAt (no worker plumbing). Linear extrapolation
    // -- remaining = elapsed * (steps - currentStep) / currentStep -- which is good enough for a
    // running readout. Empty when idle; "ETA: —" while active but before the first step lands (no
    // rate yet). activeItem is cleared on completion above, so this naturally blanks then.
    QString etaText;
    if (busy && !completedOutputObserved && !completionPulse && activeItem)
    {
        if (activeItem->steps > 0 && activeItem->currentStep > 0 &&
            activeItem->currentStep < activeItem->steps && activeItem->startedAt.isValid())
        {
            const qint64 elapsedMs = activeItem->startedAt.msecsTo(QDateTime::currentDateTime());
            if (elapsedMs > 0)
            {
                const qint64 remainingMs = elapsedMs *
                    static_cast<qint64>(activeItem->steps - activeItem->currentStep) /
                    activeItem->currentStep;
                etaText = telemetryFormatEta(remainingMs);
            }
            else
            {
                etaText = QStringLiteral("ETA: —");
            }
        }
        else
        {
            etaText = QStringLiteral("ETA: —");
        }
    }
    applyTelemetryText(bottomEtaLabel_, etaText, false, false);

    // Telemetry-transition diagnostics (env-gated by SPELLVISION_TELEMETRY_LOG): log whenever the
    // displayed busy/state/progress changes, with the inputs that drove it -- so a flash (a spurious
    // busy<->idle transition mid-render) is captured as a concrete sequence instead of guessed at.
    static const bool telemetryLog = !qEnvironmentVariableIsEmpty("SPELLVISION_TELEMETRY_LOG");
    if (telemetryLog)
    {
        const QString sig = QStringLiteral("b%1|%2|%3").arg(busy ? 1 : 0).arg(stateText).arg(targetProgress);
        if (property("svTelemetryLastLoggedSig").toString() != sig)
        {
            setProperty("svTelemetryLastLoggedSig", sig);
            qWarning().noquote() << QStringLiteral(
                "[TELEMETRY] mode=%1 busy=%2 state=%3 prog=%4 | activeItem=%5 explicitBusy=%6 "
                "completionPulse=%7 completedObs=%8 videoCompObs=%9 visibleQueue=%10 sawActive=%11")
                .arg(currentModeId_).arg(busy ? 1 : 0).arg(stateText).arg(targetProgress)
                .arg(activeItem ? 1 : 0).arg(explicitBusy ? 1 : 0)
                .arg(completionPulse ? 1 : 0).arg(completedOutputObserved ? 1 : 0)
                .arg(videoCompletionObserved ? 1 : 0).arg(visibleQueueCount)
                .arg(property("svTelemetrySawActive").toBool() ? 1 : 0);
        }
    }

    // De-clip: label widths/policies are set ONCE in buildBottomTelemetryBar() (the fitted "no-jump"
    // widths). The old per-sync stabilizeLabel re-inflated them to LARGER values on every refresh --
    // undoing the clipping fix and overflowing the bar -- so it is removed. Long values now
    // middle/right-elide (via applyTelemetryText) instead of hard-clipping, with the full text on hover.

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setRange(0, 100);
        bottomProgressBar_->setTextVisible(true);
        bottomProgressBar_->setFormat((busy || completionPulse || completedOutputObserved) ? QStringLiteral("%p%") : QStringLiteral(""));
        // Width is owned by reflowBottomTelemetryWidths() — do not force 164 here (undoes half-screen).
        bottomProgressBar_->setFixedHeight(18);
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
    // v1.0 nav gate: hidden modes (Chain) are unreachable -- any stray caller (command
    // palette, Home action, session restore) lands on Home instead. Reversible via
    // SPELLVISION_SHOW_ALL_MODES (see ShellNavigationController::isModeHidden). Home is never hidden,
    // so the redirect cannot recurse.
    if (spellvision::shell::ShellNavigationController::isModeHidden(modeId))
    {
        if (modeId != QStringLiteral("home"))
            switchToMode(QStringLiteral("home"));
        return;
    }
    // On-demand construction: a deferred generation page is built here (idempotent)
    // before the modePages_ lookup, so navigating to a not-yet-warmed page builds it
    // now and then resolves normally. No-op for non-generation / already-built modes.
    ensureGenerationPageBuilt(modeId);
    // Same on-demand contract for the deferred rail pages (chain / gen3d), which register a
    // builder in buildPages() instead of constructing there. Must run BEFORE the modePages_
    // lookup below, since the builder is what inserts the entry.
    ensureDeferredPageBuilt(modeId);

    const QString resolvedModeId = modePages_.contains(modeId) ? modeId : QStringLiteral("home");
    currentModeId_ = resolvedModeId;

    if (pageStack_) {
        QWidget *target = modePages_.value(resolvedModeId, homePage_);
        if (target && pageStack_->indexOf(target) < 0)
            pageStack_->addWidget(target);
        pageStack_->setCurrentWidget(target);
    }

    if (resolvedModeId == QStringLiteral("inspiration") && inspirationPage_)
        inspirationPage_->refreshGallery();

    if (resolvedModeId == QStringLiteral("gen3d") && gen3dPage_ && workflowsPage_)
        gen3dPage_->setAvailableWorkflows(workflowsPage_->importedWorkflowLaunchProfiles());

    if (resolvedModeId == QStringLiteral("runtime") && managerPage_)
        managerPage_->refreshStatus();

    applyShellStateForMode(resolvedModeId);
    QSettings lastModeSettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    lastModeSettings.setValue(QStringLiteral("ui/lastModeId"), resolvedModeId);
}

void MainWindow::sendModelToGeneration(const QString &value, const QString &family, const QString &type,
                                       const QStringList &triggerWords)
{
    if (value.trimmed().isEmpty())
        return;

    const QString t = type.trimmed().toLower();
    if (t == QStringLiteral("vae"))
        return; // no VAE slot yet (§3.3); the card disables this, guard anyway.

    const bool isLora = (t == QStringLiteral("lora"));

    // Route BOTH checkpoints and LoRAs by family: a video family (wan/ltx/hunyuan_video/cogvideox/
    // mochi) -> a video cockpit; everything else -> an image cockpit. A video LoRA must not cross into
    // image generation (and vice versa) -- this is the fix for a Wan LoRA landing in T2I.
    const QString mode = spellvision::assets::isVideoFamily(family)
        ? QStringLiteral("t2v")
        : QStringLiteral("t2i");

    ensureGenerationPageBuilt(mode); // lazy pages: build before handoff
    switchToMode(mode);

    // Defer the handoff one tick so a just-built page finishes showing + loading its catalog before
    // we resolve the value against it (same gotcha the cockpit component auto-populate hit).
    const QString v = value;
    const QString fam = family;
    const QStringList triggers = triggerWords;
    QTimer::singleShot(0, this, [this, mode, v, isLora, triggers, fam]() {
        ImageGenerationPage *page = generationPageForMode(mode);
        if (!page)
            return;
        const bool matched = isLora ? page->applyLoraHandoff(v) : page->applyModelHandoff(v);

        // Pin the video family bar (Wan/LTX) to the handoff so it reflects reality immediately, rather
        // than Auto-resolving from a primary the user hasn't picked yet.
        if (spellvision::assets::isVideoFamily(fam))
            page->pinVideoFamily(fam);

        if (!matched)
        {
            appendLogLine(QStringLiteral("Send-to: '%1' not found in the %2 catalog.").arg(v, mode.toUpper()));
            return;
        }
        // Auto-populate the model/LoRA's trigger words into the prompt (only once it's actually active).
        if (!triggers.isEmpty())
            page->appendTriggerWords(triggers);
    });
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
    else if (currentModeId_ == QStringLiteral("character"))
    {
        selectionText = QStringLiteral("Character pipeline");
        bodyText = QStringLiteral("Guided character creation: concept lock → multi-view → mesh → refine → game-ready → garments → export. Uses SpellBound's image-to-3D chain when available.");
        configureDetailsActions(QStringLiteral("mode:concept"), QStringLiteral("Concept Lab"),
                                QStringLiteral("mode:t2i"), QStringLiteral("Open T2I"),
                                QStringLiteral("mode:home"), QStringLiteral("Go Home"));
    }
    else if (currentModeId_ == QStringLiteral("concept"))
    {
        selectionText = QStringLiteral("Multi-view concept packs");
        bodyText = QStringLiteral("Asset-type + SFW/NSFW prompt packs tuned for multi-view adherence: even light, empty backgrounds, locked identity. Send locked heroes into Character Studio.");
        configureDetailsActions(QStringLiteral("mode:character"), QStringLiteral("Character Studio"),
                                QStringLiteral("mode:t2i"), QStringLiteral("Open T2I"),
                                QStringLiteral("mode:home"), QStringLiteral("Go Home"));
    }
    else if (currentModeId_ == QStringLiteral("comic"))
    {
        selectionText = QStringLiteral("Comic page");
        bodyText = QStringLiteral("Panel-grid comic composer. Script beats become style-locked T2I panels, then export as a composite page.");
        configureDetailsActions(QStringLiteral("mode:t2i"), QStringLiteral("Open T2I"),
                                QStringLiteral("mode:character"), QStringLiteral("Character Studio"),
                                QStringLiteral("mode:home"), QStringLiteral("Go Home"));
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
