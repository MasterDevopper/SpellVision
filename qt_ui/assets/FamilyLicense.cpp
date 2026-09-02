#include "FamilyLicense.h"

#include "FamilyLicenseTable.h"

#include <QLatin1String>
#include <QSettings>
#include <QStringList>

namespace spellvision::assets
{
namespace
{

using generated::kFamilyLicenseFallbackKey;
using generated::kFamilyLicenseTable;
using generated::FamilyLicenseRow;

constexpr int kRowCount = static_cast<int>(sizeof(kFamilyLicenseTable) / sizeof(FamilyLicenseRow));

// The one place the settings key is spelled. A second QSettings read of it anywhere is a second
// resolver of the same question, which is how the badge and the warn could come to disagree about
// whether the user does commercial work.
constexpr auto kCommercialUseKey = "usage/commercialUse";

QSettings appSettings()
{
    return QSettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
}

const FamilyLicenseRow *rowFor(const QString &needle)
{
    if (needle.isEmpty())
        return nullptr;

    // Exact key first, exactly as resolve_model_capabilities does.
    for (const FamilyLicenseRow &row : kFamilyLicenseTable)
    {
        if (needle.compare(QLatin1String(row.key), Qt::CaseInsensitive) == 0)
            return &row;
    }
    // Then exact ALIAS. Never a substring: `contains("anima")` is true of animagine, animatediff
    // and animation, and that false positive is the defect this file was rewritten to remove.
    for (const FamilyLicenseRow &row : kFamilyLicenseTable)
    {
        const QString aliases = QString::fromUtf8(row.aliases);
        if (aliases.isEmpty())
            continue;
        const QStringList parts = aliases.split(QLatin1Char('|'), Qt::SkipEmptyParts);
        for (const QString &alias : parts)
        {
            if (needle.compare(alias, Qt::CaseInsensitive) == 0)
                return &row;
        }
    }
    return nullptr;
}

const FamilyLicenseRow *fallbackRow()
{
    for (const FamilyLicenseRow &row : kFamilyLicenseTable)
    {
        if (QLatin1String(row.key) == QLatin1String(kFamilyLicenseFallbackKey))
            return &row;
    }
    return nullptr;
}

} // namespace

FamilyLicense familyLicense(const QString &familyKeyOrAlias)
{
    // The family key travels normalised: model_registry lower-cases and hyphen-normalises, and the
    // Qt scanner sends back what the worker classifier returned. Trim + fold here anyway, because
    // the studios read theirs out of a project.json a user could have edited.
    const QString needle = familyKeyOrAlias.trimmed().toLower();

    FamilyLicense out;
    const FamilyLicenseRow *row = rowFor(needle);
    if (row != nullptr)
    {
        out.matched = true;
    }
    else
    {
        // Not a default written here: the registry answers an unrecognised family with
        // MODEL_FAMILIES["unknown"], so this uses that row.
        row = fallbackRow();
        out.matched = false;
    }
    if (row == nullptr)
    {
        // The generated table lost its fallback row. Say so loudly by key rather than quietly
        // answering "commercially licensed" -- familyLicenseRowCount() is what a test asserts on.
        out.key = QStringLiteral("<no table>");
        return out;
    }
    out.key = QString::fromUtf8(row->key);
    out.commercialUse = row->commercialUse;
    out.note = QString::fromUtf8(row->licenseNote);
    return out;
}

bool familyAllowsCommercialUse(const QString &familyKeyOrAlias)
{
    return familyLicense(familyKeyOrAlias).commercialUse;
}

QString familyLicenseBadgeText(const QString &familyKeyOrAlias)
{
    if (familyAllowsCommercialUse(familyKeyOrAlias))
        return {};
    return QStringLiteral("Non-commercial");
}

QString familyLicenseNote(const QString &familyKeyOrAlias)
{
    return familyLicense(familyKeyOrAlias).note;
}

bool commercialUseDeclared()
{
    QSettings settings = appSettings();
    return settings.value(QLatin1String(kCommercialUseKey), true).toBool();
}

void setCommercialUseDeclared(bool declared)
{
    QSettings settings = appSettings();
    settings.setValue(QLatin1String(kCommercialUseKey), declared);
}

LicenseGate licenseGateFor(const QString &familyKeyOrAlias, bool commercialUseIsDeclared)
{
    if (!commercialUseIsDeclared)
        return LicenseGate::Proceed;
    if (familyAllowsCommercialUse(familyKeyOrAlias))
        return LicenseGate::Proceed;
    return LicenseGate::WarnThenProceed;
}

int familyLicenseRowCount()
{
    return kRowCount;
}

} // namespace spellvision::assets
