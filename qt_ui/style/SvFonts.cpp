#include "style/SvFonts.h"

#include <QCoreApplication>
#include <QDir>
#include <QFontDatabase>
#include <QFileInfo>

namespace spellvision::style
{
namespace
{
QStringList &registeredFamilies()
{
    static QStringList families;
    return families;
}

bool &registrationDone()
{
    static bool done = false;
    return done;
}

// IBM Plex's static weight files don't consistently carry a shared "typographic family" (OpenType
// name ID 16): IBM Plex Sans's Medium/SemiBold instances do, so QFontDatabase reports BOTH the
// per-weight name ("IBM Plex Sans Medium") and the shared one ("IBM Plex Sans") for those files;
// IBM Plex Mono's Medium instance carries no such entry, so QFontDatabase reports only "IBM Plex
// Mono Medium". Either way, the family the rest of the app asks for is the base name -- font(Type)
// and every stylesheet site name "IBM Plex Sans" / "IBM Plex Mono" and select weight numerically,
// never "IBM Plex Sans Medium" by name -- so this folds a reported name back to the base family
// SvFonts ships. bundledFamilies() then answers "which typefaces did we register", not "how many
// distinct name-table strings did the files happen to carry".
QString canonicalFamily(const QString &reported)
{
    static const QStringList bases = {QStringLiteral("IBM Plex Sans"), QStringLiteral("IBM Plex Mono")};
    for (const QString &base : bases)
    {
        if (reported == base || reported.startsWith(base + QStringLiteral(" ")))
            return base;
    }
    return reported;
}
} // namespace

QString fontsDirectory()
{
    const QString exeDir = QCoreApplication::applicationDirPath();
    const QStringList candidates = {
        exeDir + QStringLiteral("/fonts"),
        exeDir + QStringLiteral("/../../qt_ui/fonts"),
        QDir::currentPath() + QStringLiteral("/qt_ui/fonts"),
    };
    for (const QString &candidate : candidates)
    {
        if (QFileInfo(candidate).isDir())
            return QDir(candidate).canonicalPath();
    }
    return candidates.first();
}

QStringList registerBundledFonts()
{
    if (registrationDone())
        return registeredFamilies();
    registrationDone() = true;

    QDir dir(fontsDirectory());
    const QStringList files = dir.entryList({QStringLiteral("*.ttf"), QStringLiteral("*.otf")},
                                            QDir::Files, QDir::Name);
    for (const QString &file : files)
    {
        const int id = QFontDatabase::addApplicationFont(dir.filePath(file));
        if (id < 0)
            continue;
        for (const QString &rawFamily : QFontDatabase::applicationFontFamilies(id))
        {
            const QString family = canonicalFamily(rawFamily);
            if (!registeredFamilies().contains(family))
                registeredFamilies().append(family);
        }
    }
    return registeredFamilies();
}

QStringList bundledFamilies()
{
    return registeredFamilies();
}

} // namespace spellvision::style
