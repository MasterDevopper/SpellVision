#include "shell/ProjectRoot.h"

#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QStringList>

namespace spellvision::shell
{

namespace
{
// Every copy used this literal. It is the worker entry point, so a tree that has it is a tree the
// app can actually run against -- which is what "project root" means here.
constexpr auto kSentinel = "python/worker_client.py";

// The depth the majority of the copies used. MainWindow's 7 was the outlier.
constexpr int kMaxDepth = 8;
}  // namespace

QString projectRootSentinel()
{
    return QStringLiteral("python/worker_client.py");
}

QString resolveProjectRootFrom(const QString &startDirectory, int maxDepth)
{
    QDir dir(startDirectory);
    for (int depth = 0; depth < maxDepth; ++depth)
    {
        if (QFileInfo::exists(dir.filePath(QLatin1String(kSentinel))))
            return dir.absolutePath();
        if (!dir.cdUp())
            break;
    }
    return QString();
}

QString resolveProjectRoot()
{
    const QStringList starts = {QCoreApplication::applicationDirPath(), QDir::currentPath()};
    for (const QString &start : starts)
    {
        const QString found = resolveProjectRootFrom(start, kMaxDepth);
        if (!found.isEmpty())
            return found;
    }
    return QDir::currentPath();
}

}  // namespace spellvision::shell
