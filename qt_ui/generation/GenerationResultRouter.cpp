#include "GenerationResultRouter.h"

#include <QFileInfo>
#include <QStringList>

namespace spellvision::generation
{

bool GenerationResultRouter::isImageAssetPath(const QString &path)
{
    const QString suffix = QFileInfo(path.trimmed()).suffix().toLower();
    return QStringList{QStringLiteral("png"),
                       QStringLiteral("jpg"),
                       QStringLiteral("jpeg"),
                       QStringLiteral("webp"),
                       QStringLiteral("bmp"),
                       QStringLiteral("gif")}
        .contains(suffix);
}

bool GenerationResultRouter::isVideoAssetPath(const QString &path)
{
    const QString suffix = QFileInfo(path.trimmed()).suffix().toLower();
    return QStringList{QStringLiteral("mp4"),
                       QStringLiteral("webm"),
                       QStringLiteral("mov"),
                       QStringLiteral("mkv"),
                       QStringLiteral("avi"),
                       QStringLiteral("gif")}
        .contains(suffix);
}

GenerationResultRouter::Route GenerationResultRouter::routePreviewResult(const Input &input)
{
    Route route;
    route.normalizedPath = input.incomingPath.trimmed();
    route.normalizedCaption = input.caption.trimmed();

    if (route.normalizedPath.isEmpty())
    {
        route.kind = RouteKind::Clear;
        route.shouldStopVideo = true;
        route.shouldShowImageSurface = true;
        route.shouldClearImageCache = true;
        route.previewRefreshDelayMs = 0;
        return route;
    }

    route.sameGeneratedPath = input.currentGeneratedPath.trimmed().compare(route.normalizedPath, Qt::CaseInsensitive) == 0;
    route.shouldPersistOutput = true;

    const bool incomingIsImage = isImageAssetPath(route.normalizedPath);
    const bool incomingIsVideo = isVideoAssetPath(route.normalizedPath) && !incomingIsImage;

    if (incomingIsVideo)
    {
        route.kind = RouteKind::VideoPreview;
        route.shouldStopVideo = false;
        route.shouldShowImageSurface = false;
        route.shouldClearImageCache = true;
        route.shouldClearImageCachePreserveVideoMarker = true;
        route.shouldMarkVideoRendered = true;
        route.previewRefreshDelayMs = route.sameGeneratedPath ? 250 : 0;
        return route;
    }

    route.kind = RouteKind::ImagePreview;
    route.shouldStopVideo = true;
    route.shouldShowImageSurface = true;
    route.shouldClearImageCache = true;
    route.previewRefreshDelayMs = 0;
    return route;
}

} // namespace spellvision::generation
