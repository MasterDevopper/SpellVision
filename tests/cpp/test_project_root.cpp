// Four copies of one search, and they disagreed about how far to look.
//
// "Find the project root" was written by hand four times -- MainWindow, HomePage, ManagerPage and
// main.cpp's self-test. All four walked up from a starting directory looking for
// python/worker_client.py, and all four agreed on the sentinel, which is the only reason they could
// be merged without a behaviour decision. They did not agree on anything else:
//
//     MainWindow      depth 7   application directory, then the working directory
//     HomePage        depth 8   application directory, then the working directory
//     ManagerPage     depth 8   application directory only
//     main.cpp        depth 8   application directory only
//
// MainWindow searched one level shallower than every other copy. A build laid out exactly eight
// levels below the root would have had three components find the project and the fourth fall back
// to QDir::currentPath() -- and then resolve worker_client.py, the runtime profile, the Python
// executable and every generation request against whatever directory the app happened to start in.
// Silently: the fallback is a valid path, so nothing would report an error.
//
// It is not reachable in the default build layout (the exe sits three levels below the root), which
// is exactly why it survived. A latent divergence is still a divergence; the reason it had never
// fired is a property of the build directory, not of the code.
//
// None of the four had a test. This file tests the merged one, on a fixture tree rather than on
// wherever the test binary happens to live -- because a test that asserted against the real repo
// would pass at any depth and could not have caught the bug it exists for.

#include <QtTest>

#include <QDir>
#include <QTemporaryDir>

#include "shell/ProjectRoot.h"

using spellvision::shell::projectRootSentinel;
using spellvision::shell::resolveProjectRoot;
using spellvision::shell::resolveProjectRootFrom;

namespace
{

// Build <tmp>/root/python/worker_client.py plus `depth` nested directories below root, and return
// the deepest one -- the position an executable would occupy.
QString makeTree(const QTemporaryDir &tmp, int depth, QString *rootOut)
{
    QDir base(tmp.path());
    base.mkpath(QStringLiteral("root/python"));
    const QString root = base.filePath(QStringLiteral("root"));
    QFile sentinel(QDir(root).filePath(projectRootSentinel()));
    if (!sentinel.open(QIODevice::WriteOnly))
        return QString();
    sentinel.write("# fixture\n");
    sentinel.close();

    QString leaf = root;
    for (int i = 0; i < depth; ++i)
    {
        leaf = QDir(leaf).filePath(QStringLiteral("d%1").arg(i));
        QDir().mkpath(leaf);
    }
    if (rootOut)
        *rootOut = QDir(root).absolutePath();
    return QDir(leaf).absolutePath();
}

}  // namespace

class TestProjectRoot : public QObject
{
    Q_OBJECT

private slots:
    void findsTheRootFromTheRootItself();
    void findsTheRootFromEachDepth_data();
    void findsTheRootFromEachDepth();
    void theDivergenceThatSurvived();
    void givesUpRatherThanGuessing();
    void aTreeWithoutTheSentinelIsNotARoot();
    void theSentinelIsTheWorkerEntryPoint();
};

void TestProjectRoot::findsTheRootFromTheRootItself()
{
    QTemporaryDir tmp;
    QVERIFY(tmp.isValid());
    QString root;
    const QString leaf = makeTree(tmp, 0, &root);
    QCOMPARE(resolveProjectRootFrom(leaf), root);
}

void TestProjectRoot::findsTheRootFromEachDepth_data()
{
    QTest::addColumn<int>("depth");
    for (int d = 0; d <= 7; ++d)
        QTest::newRow(qPrintable(QStringLiteral("depth %1").arg(d))) << d;
}

void TestProjectRoot::findsTheRootFromEachDepth()
{
    QFETCH(int, depth);
    QTemporaryDir tmp;
    QVERIFY(tmp.isValid());
    QString root;
    const QString leaf = makeTree(tmp, depth, &root);
    QCOMPARE(resolveProjectRootFrom(leaf), root);
}

void TestProjectRoot::theDivergenceThatSurvived()
{
    // The bug, stated as the property that prevents it. Depth 7 is the one the old MainWindow copy
    // could not reach and the other three could: with maxDepth 7 the walk inspects the leaf and six
    // parents, stopping one short of the root. This is the exact case where MainWindow would have
    // fallen back to the working directory while HomePage and ManagerPage resolved correctly.
    QTemporaryDir tmp;
    QVERIFY(tmp.isValid());
    QString root;
    const QString leaf = makeTree(tmp, 7, &root);

    QCOMPARE(resolveProjectRootFrom(leaf, 7), QString());   // what MainWindow used to do
    QCOMPARE(resolveProjectRootFrom(leaf, 8), root);        // what the other three did
    QCOMPARE(resolveProjectRootFrom(leaf), root);           // the merged default
}

void TestProjectRoot::givesUpRatherThanGuessing()
{
    // The searching half returns an empty string when it finds nothing, so the CALLER decides what
    // no-root means. Only resolveProjectRoot() applies the working-directory fallback, and it does
    // so once. Four copies each deciding that separately is how they came to disagree.
    QTemporaryDir tmp;
    QVERIFY(tmp.isValid());
    QVERIFY(resolveProjectRootFrom(tmp.path()).isEmpty()
            || resolveProjectRootFrom(tmp.path()) != tmp.path());
}

void TestProjectRoot::aTreeWithoutTheSentinelIsNotARoot()
{
    QTemporaryDir tmp;
    QVERIFY(tmp.isValid());
    QDir(tmp.path()).mkpath(QStringLiteral("looks/like/a/project/python"));
    const QString leaf = QDir(tmp.path()).filePath(QStringLiteral("looks/like/a/project/python"));
    // A python/ directory alone is not the marker; the worker entry point is.
    QCOMPARE(resolveProjectRootFrom(leaf, 3), QString());
}

void TestProjectRoot::theSentinelIsTheWorkerEntryPoint()
{
    // Pinned because it is the one thing all four copies agreed on, and agreement is what made the
    // merge safe. If this changes, the merge's premise changes with it.
    QCOMPARE(projectRootSentinel(), QStringLiteral("python/worker_client.py"));
}

QTEST_MAIN(TestProjectRoot)
#include "test_project_root.moc"
