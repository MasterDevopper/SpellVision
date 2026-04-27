#pragma once

#include <QString>

namespace spellvision::generation
{

class GenerationResultRouter
{
public:
    enum class RouteKind
    {
        Clear,
        ImagePreview,
        VideoPreview
    };

    struct Input
    {
        QString incomingPath;
        QString caption;
        QString currentGeneratedPath;
    };

    struct Route
    {
        RouteKind kind = RouteKind::Clear;
        QString normalizedPath;
        QString normalizedCaption;
        bool sameGeneratedPath = false;
        bool shouldPersistOutput = false;
        bool shouldStopVideo = false;
        bool shouldShowImageSurface = false;
        bool shouldClearImageCache = false;
        bool shouldClearImageCachePreserveVideoMarker = false;
        bool shouldMarkVideoRendered = false;
        int previewRefreshDelayMs = 0;
    };

    static Route routePreviewResult(const Input &input);

    static bool isImageAssetPath(const QString &path);
    static bool isVideoAssetPath(const QString &path);
};

} // namespace spellvision::generation
