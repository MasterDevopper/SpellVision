#include "GenerationModeState.h"

namespace spellvision::generation
{

GenerationModeProfile GenerationModeState::profile(GenerationMode mode)
{
    switch (mode)
    {
    case GenerationMode::TextToImage:
        return {
            GenerationMode::TextToImage,
            QStringLiteral("t2i"),
            QStringLiteral("Text to Image"),
            false,
            false,
            false,
        };
    case GenerationMode::ImageToImage:
        return {
            GenerationMode::ImageToImage,
            QStringLiteral("i2i"),
            QStringLiteral("Image to Image"),
            true,
            false,
            true,
        };
    case GenerationMode::TextToVideo:
        return {
            GenerationMode::TextToVideo,
            QStringLiteral("t2v"),
            QStringLiteral("Text to Video"),
            false,
            true,
            false,
        };
    case GenerationMode::ImageToVideo:
        return {
            GenerationMode::ImageToVideo,
            QStringLiteral("i2v"),
            QStringLiteral("Image to Video"),
            true,
            true,
            true,
        };
    }

    return profile(GenerationMode::TextToImage);
}

QString GenerationModeState::key(GenerationMode mode)
{
    return profile(mode).key;
}

QString GenerationModeState::title(GenerationMode mode)
{
    return profile(mode).title;
}

bool GenerationModeState::requiresImageInput(GenerationMode mode)
{
    return profile(mode).requiresImageInput;
}

bool GenerationModeState::isVideoMode(GenerationMode mode)
{
    return profile(mode).videoMode;
}

bool GenerationModeState::usesStrengthControl(GenerationMode mode)
{
    return profile(mode).strengthControl;
}

} // namespace spellvision::generation
