#pragma once

#include <QString>

namespace spellvision::generation
{

enum class GenerationMode
{
    TextToImage,
    ImageToImage,
    TextToVideo,
    ImageToVideo
};

struct GenerationModeProfile
{
    GenerationMode mode = GenerationMode::TextToImage;
    QString key;
    QString title;
    bool requiresImageInput = false;
    bool videoMode = false;
    bool strengthControl = false;
};

class GenerationModeState final
{
public:
    static GenerationModeProfile profile(GenerationMode mode);
    static QString key(GenerationMode mode);
    static QString title(GenerationMode mode);
    static bool requiresImageInput(GenerationMode mode);
    static bool isVideoMode(GenerationMode mode);
    static bool usesStrengthControl(GenerationMode mode);
};

} // namespace spellvision::generation
