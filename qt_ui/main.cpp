#include <QApplication>

#include "shell/ProjectRoot.h"

#include "ThemeManager.h"
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFont>
#include <QFontInfo>
#include <QHash>
#include <QIODevice>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QSettings>
#include <QString>
#include <QStringList>
#include <QTextStream>
#include "MainWindow.h"
#include "ImageGenerationPage.h"
#include "chain/ChainSelfTest.h"
#include "assets/AssetCatalogScanner.h"
#include "generation/OutputPathHelpers.h"
#include "preview/MediaPreviewController.h"

#include <QImage>
#include <QLabel>
#include <QPixmap>
#include <QStackedWidget>
#include <QTimer>
#include <QVBoxLayout>
#include <QWidget>

namespace
{
// Resolve the project root by walking up from the executable until python/worker_client.py is found.
QString resolveProjectRootForSelfTest()
{
    // One resolver, in shell/ProjectRoot.h. The self-test searched from the application directory
    // only; the shared walk also tries the working directory, which is strictly more.
    return spellvision::shell::resolveProjectRoot();
}

// Batch classify via the worker (mirrors MainWindow::classifyModelsViaWorker) for the self-test.
QHash<QString, QString> selfTestWorkerClassify(const QStringList &paths)
{
    QHash<QString, QString> out;
    if (paths.isEmpty())
        return out;
    const QString projectRoot = resolveProjectRootForSelfTest();
    const QString python = QDir(projectRoot).filePath(QStringLiteral(".venv/Scripts/python.exe"));
    const QString client = QDir(projectRoot).filePath(QStringLiteral("python/worker_client.py"));

    QJsonObject req;
    req.insert(QStringLiteral("command"), QStringLiteral("classify_models"));
    req.insert(QStringLiteral("paths"), QJsonArray::fromStringList(paths));

    QProcess proc;
    proc.setWorkingDirectory(projectRoot);
    proc.start(python, {client});
    if (!proc.waitForStarted(5000))
        return out;
    proc.write(QJsonDocument(req).toJson(QJsonDocument::Compact));
    proc.write("\n");
    proc.closeWriteChannel();
    if (!proc.waitForFinished(20000))
    {
        proc.kill();
        return out;
    }
    const QList<QByteArray> lines = proc.readAllStandardOutput().split('\n');
    for (const QByteArray &raw : lines)
    {
        const QByteArray line = raw.trimmed();
        if (line.isEmpty())
            continue;
        const QJsonObject resp = QJsonDocument::fromJson(line).object();
        if (!resp.value(QStringLiteral("ok")).toBool(false))
            continue;
        for (const QJsonValue &v : resp.value(QStringLiteral("classifications")).toArray())
        {
            const QJsonObject e = v.toObject();
            out.insert(e.value(QStringLiteral("path")).toString(), e.value(QStringLiteral("family")).toString());
        }
    }
    return out;
}

// Prove Qt's scanner now consults the worker classifier (display == routing).
int runClassifySelfTest()
{
    using namespace spellvision::assets;
    QTextStream out(stdout);

    // Baseline: scan WITHOUT the classifier -> the old inferImageFamilyFromText guess.
    setModelFamilyClassifier(nullptr);
    const QString root = spellvision::generation::chooseModelsRootPath();
    const QVector<CatalogEntry> fallbackEntries = scanImageModelCatalog(root);
    QHash<QString, QString> fallbackFamily;
    for (const CatalogEntry &e : fallbackEntries)
        fallbackFamily.insert(e.value, e.family);

    // Now install the worker classifier and re-scan -> authoritative families.
    setModelFamilyClassifier(selfTestWorkerClassify);
    const QVector<CatalogEntry> entries = scanImageModelCatalog(root);
    if (entries.isEmpty())
    {
        out << "NO ENTRIES (models root: " << root << ") -- is the worker up?\n";
        return 2;
    }

    int changed = 0;
    int workerSourced = 0;
    out << "root=" << root << "  entries=" << entries.size() << "\n";
    out << "-- files where the worker family DIFFERS from the old substring guess --\n";
    for (const CatalogEntry &e : entries)
    {
        const QString fb = fallbackFamily.value(e.value);
        if (!fb.isEmpty() && fb != e.family)
        {
            ++changed;
            if (changed <= 30)
                out << QStringLiteral("  %1  worker=%2  oldguess=%3  label=%4\n")
                           .arg(QFileInfo(e.value).fileName().left(48), -48)
                           .arg(e.family, -16)
                           .arg(fb, -12)
                           .arg(e.note);
        }
    }
    // Was the worker actually consulted at all? (families that only the worker can produce)
    for (const CatalogEntry &e : entries)
        if (e.family == QStringLiteral("pony") || e.family == QStringLiteral("illustrious")
            || e.family == QStringLiteral("sdxl") || e.family == QStringLiteral("stable_diffusion"))
            ++workerSourced;

    out << "\nSUMMARY: " << changed << " of " << entries.size()
        << " files reclassified by the worker (display now == routing); "
        << workerSourced << " resolved to a canonical classifier family.\n";
    return (changed > 0 && workerSourced > 0) ? 0 : 1;
}

// Prove the on-navigate dirty-check probe: stable when unchanged (so the cheap
// probe skips the expensive rescan), and detects add + remove of a model file.
int runCatalogRefreshSelfTest()
{
    QTextStream out(stdout);
    const QString base = QDir::tempPath() + QStringLiteral("/sv_catalog_probe");
    QDir().mkpath(base + QStringLiteral("/checkpoints/sdxl"));
    const QString p1 = base + QStringLiteral("/checkpoints/sdxl/_probe1.safetensors");
    const QString p2 = base + QStringLiteral("/checkpoints/sdxl/_probe2.safetensors");
    auto touch = [](const QString &p) { QFile f(p); if (f.open(QIODevice::WriteOnly)) { f.write("x"); f.close(); } };
    QFile::remove(p1);
    QFile::remove(p2);

    const QString sigEmpty = ImageGenerationPage::catalogSignature(base);
    touch(p1);
    const QString sigA = ImageGenerationPage::catalogSignature(base);
    const QString sigA2 = ImageGenerationPage::catalogSignature(base); // no change between A and A2
    touch(p2);
    const QString sigB = ImageGenerationPage::catalogSignature(base);
    QFile::remove(p2);
    const QString sigC = ImageGenerationPage::catalogSignature(base);
    QFile::remove(p1);

    bool ok = true;
    auto check = [&](const char *name, bool cond) {
        out << (cond ? "  PASS  " : "  FAIL  ") << name << "\n";
        ok = ok && cond;
    };
    check("add detected            (sigA != sigEmpty)", sigA != sigEmpty && !sigA.isEmpty());
    check("STABLE when unchanged   (sigA2 == sigA) -> dirty-check SKIPS the rescan", sigA2 == sigA);
    check("second add detected     (sigB != sigA)", sigB != sigA);
    check("removal detected        (sigC == sigA, back to prior)", sigC == sigA);
    out << (ok ? "\nCATALOG-REFRESH SELFTEST: PASS\n" : "\nCATALOG-REFRESH SELFTEST: FAIL\n");
    return ok ? 0 : 1;
}

// Video-render PRODUCT-SURFACE gate: drive the REAL MediaPreviewController + its QLabel video
// surface with an mp4 and grab the surface -> prove decoded frames actually PAINT (non-black),
// not merely that the file exists / job completed. This is the surface that was silently broken.
// Usage: SpellVision.exe --video-render-selftest <mp4> [out.png]
int runVideoRenderSelfTest(const QStringList &args)
{
    QTextStream out(stdout);
    const int idx = args.indexOf(QStringLiteral("--video-render-selftest"));
    const QString mp4 = (idx >= 0 && idx + 1 < args.size()) ? args.at(idx + 1) : QString();
    const QString outPng = (idx >= 0 && idx + 2 < args.size()) ? args.at(idx + 2) : QString();
    if (mp4.isEmpty() || !QFileInfo::exists(mp4))
    {
        out << "VIDEO-RENDER SELFTEST: FAIL (missing/invalid mp4 argument)\n";
        return 1;
    }

    auto *stack = new QStackedWidget;
    auto *imagePage = new QWidget;
    auto *videoPage = new QWidget;
    auto *videoLayout = new QVBoxLayout(videoPage);
    videoLayout->setContentsMargins(0, 0, 0, 0);
    auto *surface = new QLabel(videoPage);
    surface->setAlignment(Qt::AlignCenter);
    surface->setMinimumSize(400, 400);
    videoLayout->addWidget(surface, 1);
    stack->addWidget(imagePage);
    stack->addWidget(videoPage);
    stack->resize(480, 480);
    stack->show();

    auto *ctrl = new spellvision::preview::MediaPreviewController;
    spellvision::preview::MediaPreviewBindings bindings;
    bindings.previewStack = stack;
    bindings.imagePage = imagePage;
    bindings.videoPage = videoPage;
    bindings.videoSurface = surface;
    ctrl->bind(bindings);
    ctrl->showVideoSurface(mp4, QStringLiteral("selftest"));

    QTimer::singleShot(3500, [ctrl, surface, outPng]() {
        QTextStream out(stdout);
        const QPixmap grab = surface->grab();
        const QImage img = grab.toImage();
        int nonBlack = 0;
        for (int y = 0; y < img.height(); y += 6)
            for (int x = 0; x < img.width(); x += 6)
            {
                const QRgb c = img.pixel(x, y);
                if (qRed(c) + qGreen(c) + qBlue(c) > 24)
                    ++nonBlack;
            }
        if (!outPng.isEmpty())
            grab.save(outPng);
        const bool loaded = !ctrl->currentVideoPath().isEmpty();
        const int err = static_cast<int>(ctrl->player()->error());
        const bool ok = loaded && err == 0 && nonBlack > 30;
        out << "surface " << img.width() << "x" << img.height()
            << "  nonblack_samples=" << nonBlack
            << "  player_error=" << err
            << "  status=" << static_cast<int>(ctrl->player()->mediaStatus())
            << "  path=" << (loaded ? "set" : "EMPTY") << "\n";
        out << (ok ? "VIDEO-RENDER SELFTEST: PASS\n" : "VIDEO-RENDER SELFTEST: FAIL\n");
        out.flush();
        QCoreApplication::exit(ok ? 0 : 1);
    });
    return QApplication::exec();
}

void migrateLegacySettingsNamespace()
{
    const QString migrationKey = QStringLiteral("settings/canonicalNamespaceMigration_v1");
    QSettings canonical(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    if (canonical.value(migrationKey, false).toBool())
        return;

    QSettings legacy(QStringLiteral("Dark Duck Studio"), QStringLiteral("SpellVision"));
    const QStringList legacyKeys = legacy.allKeys();
    for (const QString &key : legacyKeys)
    {
        if (!canonical.contains(key))
            canonical.setValue(key, legacy.value(key));
    }
    canonical.setValue(migrationKey, true);
    canonical.sync();
}
} // namespace

int main(int argc, char *argv[])
{
    // Configure the storage backend before QApplication initializes Qt's settings
    // machinery. This makes explicit QSettings(org, app) calls use the sandbox too.
    const QString settingsDir = QString::fromLocal8Bit(qgetenv("SPELLVISION_SETTINGS_DIR")).trimmed();
    if (!settingsDir.isEmpty())
    {
        QDir().mkpath(settingsDir);
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, settingsDir);
    }

    QCoreApplication::setOrganizationName(QStringLiteral("DarkDuck"));
    QCoreApplication::setApplicationName(QStringLiteral("SpellVision"));
    QApplication app(argc, argv);
    migrateLegacySettingsNamespace();

    // Showcase typography: Segoe UI is always present on Windows and matches the dense DCC
    // instrument feel. Prefer "Segoe UI Variable" when installed; fall back cleanly.
    {
        QFont ui(QStringLiteral("Segoe UI"));
        if (QFontInfo(ui).family().contains(QStringLiteral("Segoe"), Qt::CaseInsensitive)) {
            ui.setStyleHint(QFont::SansSerif);
            ui.setHintingPreference(QFont::PreferFullHinting);
            ui.setPixelSize(12);
            QApplication::setFont(ui);
        }
    }

    // Theme the top-level popups that escape the MainWindow stylesheet cascade (tooltips, menus,
    // message boxes, combo popups): push the themed palette + overlay sheet onto qApp up front so
    // even a dialog shown before MainWindow is themed, not native grey. Re-applies on theme switch.
    ThemeManager::instance().applyApplicationChrome();

    // --- CHAIN STUDIO PASS 6 SELF-TEST ---
    // Headless verification entry point. When --chain-selftest is
    // present we run the chain studio engine harness and exit
    // with the number of failed scenarios (0 == all passed).
    // MainWindow is NEVER constructed in this path.
    if (QCoreApplication::arguments().contains(QStringLiteral("--chain-selftest")))
        return spellvision::chain::runChainSelfTest();

    // Detection accelerator (option A): prove the Qt scanner consults the worker's
    // one layered classifier. Requires the worker (:8765) to be up.
    if (QCoreApplication::arguments().contains(QStringLiteral("--classify-selftest")))
        return runClassifySelfTest();

    // Runtime model pickup: prove the dirty-check probe (stable/add/remove). Worker-free.
    if (QCoreApplication::arguments().contains(QStringLiteral("--catalog-refresh-selftest")))
        return runCatalogRefreshSelfTest();

    // Video-render product-surface gate: prove the real MediaPreviewController paints mp4
    // frames onto its QLabel surface (the leg that silently failed with QVideoWidget).
    if (QCoreApplication::arguments().contains(QStringLiteral("--video-render-selftest")))
        return runVideoRenderSelfTest(QCoreApplication::arguments());

    MainWindow window;
    QFile logFile(QDir::currentPath() + QStringLiteral("/build/ui_startup_trace.log"));
    logFile.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text);
    QTextStream log(&logFile);
    log << "main: before show\n";
    log.flush();
    window.show();
    log << "main: after show visible=" << window.isVisible()
        << " winId=" << window.winId() << " geometry=" << window.geometry().x()
        << "," << window.geometry().y() << " " << window.geometry().width()
        << "x" << window.geometry().height() << "\n";
    log.flush();

    return app.exec();
}
