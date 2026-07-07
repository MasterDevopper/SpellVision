#include <QApplication>
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QString>
#include <QStringList>
#include <QTextStream>
#include "MainWindow.h"
#include "ImageGenerationPage.h"
#include "chain/ChainSelfTest.h"
#include "assets/AssetCatalogScanner.h"
#include "generation/OutputPathHelpers.h"

namespace
{
// Resolve the project root by walking up from the executable until python/worker_client.py is found.
QString resolveProjectRootForSelfTest()
{
    QDir dir(QCoreApplication::applicationDirPath());
    for (int i = 0; i < 8; ++i)
    {
        if (QFileInfo::exists(dir.filePath(QStringLiteral("python/worker_client.py"))))
            return dir.absolutePath();
        if (!dir.cdUp())
            break;
    }
    return QDir::currentPath();
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
} // namespace

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    QApplication::setApplicationName("SpellVision");
    QApplication::setOrganizationName("Dark Duck Studio");

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

    MainWindow window;
    window.show();

    return app.exec();
}
