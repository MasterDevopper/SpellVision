#include <QtTest>

#include <QDir>
#include <QFileInfo>
#include <QTemporaryDir>

#include "shell/ModelsLibraryPaths.h"

using spellvision::shell::proposedModelsLibraryOnVolume;
using spellvision::shell::resolveModelsLibraryRoot;
using spellvision::shell::scannableModelsRoots;

class ModelsLibraryPathsTest : public QObject
{
    Q_OBJECT

private slots:
    void empty_volume_proposes_nothing();
    void a_picked_drive_gets_ai_assets_models();
    void missing_and_unready_roots_are_skipped_not_fatal();
    void a_drive_or_assets_folder_resolves_to_the_models_library();
};

void ModelsLibraryPathsTest::empty_volume_proposes_nothing()
{
    QVERIFY(proposedModelsLibraryOnVolume(QString()).isEmpty());
    QVERIFY(proposedModelsLibraryOnVolume(QStringLiteral("   ")).isEmpty());
}

void ModelsLibraryPathsTest::a_picked_drive_gets_ai_assets_models()
{
    QCOMPARE(proposedModelsLibraryOnVolume(QStringLiteral("D:/")),
             QStringLiteral("D:/AI_ASSETS/models"));
    QCOMPARE(proposedModelsLibraryOnVolume(QStringLiteral("E:\\")),
             QStringLiteral("E:/AI_ASSETS/models"));
}

void ModelsLibraryPathsTest::missing_and_unready_roots_are_skipped_not_fatal()
{
    QTemporaryDir live;
    QVERIFY(live.isValid());
    const QString liveRoot = live.path();
    const QString missing = liveRoot + QStringLiteral("/does-not-exist");

    const QStringList scanned = scannableModelsRoots(missing, {liveRoot});
    QCOMPARE(scanned.size(), 1);
    QCOMPARE(QDir::fromNativeSeparators(scanned.first()),
             QDir::fromNativeSeparators(QFileInfo(liveRoot).absoluteFilePath()));
}

void ModelsLibraryPathsTest::a_drive_or_assets_folder_resolves_to_the_models_library()
{
    QTemporaryDir live;
    QVERIFY(live.isValid());
    QVERIFY(QDir(live.path()).mkpath(QStringLiteral("AI_ASSETS/models/checkpoints")));
    const QString drive = QDir::fromNativeSeparators(QFileInfo(live.path()).absoluteFilePath());
    const QString library = drive + QStringLiteral("/AI_ASSETS/models");
    QCOMPARE(QDir::fromNativeSeparators(resolveModelsLibraryRoot(drive)), library);
    QCOMPARE(QDir::fromNativeSeparators(resolveModelsLibraryRoot(drive + QStringLiteral("/AI_ASSETS"))), library);
    QCOMPARE(QDir::fromNativeSeparators(resolveModelsLibraryRoot(library)), library);
    const QStringList scanned = scannableModelsRoots(QString(), {drive, drive + QStringLiteral("/AI_ASSETS")});
    QCOMPARE(scanned.size(), 1);
    QCOMPARE(QDir::fromNativeSeparators(scanned.first()), library);
}

QTEST_MAIN(ModelsLibraryPathsTest)
#include "test_models_library_paths.moc"
