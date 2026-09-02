#pragma once

// The ONE licence answer on the Qt side (Doc 28 section 2: "Non-commercial surfaced").
//
// What was here before:
//
//     return !(hay.contains("anima") || hay.contains("hunyuan"));
//
// Two family names hardcoded in C++ and matched as SUBSTRINGS. Wrong in both directions.
// It false-positives on animagine / animatediff / animation -- the exact decoy collision the anima
// spec's own comment in python/model_registry.py says its narrow aliases exist to avoid, so a user
// picking animagineXL got a "Non-commercial" badge and a warning dialog on a model that carries
// neither. And it silently answers "commercial use is fine" for any non-commercial family the
// registry gains after it was written, with nothing anywhere that would notice: a badge that is
// absent looks exactly like a badge that is not needed.
//
// The answer now comes from python/model_registry.py, rendered into FamilyLicenseTable.h by
// scripts/dev/generate_family_license_table.py and re-rendered + compared on every pytest run by
// tests/test_family_license_surfaced.py. Lookup is by EXACT registry key or EXACT alias, mirroring
// resolve_model_capabilities, and an unrecognised family falls back to the registry's own "unknown"
// row rather than to a default written here.

#include <QString>

namespace spellvision::assets
{

// Three states, not two (Doc 50 rule 3). `matched == false` means "this family key is in no
// registry row", which is a different fact from "this family permits commercial use" even though
// the registry answers both the same way -- and it is the fact a caller needs when deciding whether
// silence is an answer or an absence.
struct FamilyLicense
{
    QString key;                 // the registry key this resolved to; "unknown" when nothing matched
    bool commercialUse = true;   // the registry's answer, never a default invented here
    QString note;                // the registry's license_note; empty for most families
    bool matched = false;        // false -> fell back to the registry's "unknown" row
};

// Doc 28 section 2 and the 2026-08-17 owner lock are explicit: "commercial-use setting on -> soft
// warn on generate (**not a hard block**)". This enum is how that is made structural rather than
// remembered: it has exactly two states and NEITHER of them is a block, so no call site can spell
// one. A rule you can only violate by editing the type is a rule that stays kept.
enum class LicenseGate
{
    Proceed,          // nothing to say
    WarnThenProceed,  // warn, and let the user go on -- the user's answer decides, not the licence
};

// Resolve by exact key, then by exact alias, then to the registry's "unknown" row.
FamilyLicense familyLicense(const QString &familyKeyOrAlias);

bool familyAllowsCommercialUse(const QString &familyKeyOrAlias);

// "" when the family permits commercial use; the badge text otherwise. Painted by ModelCardDelegate
// and shown as a label by the studios.
QString familyLicenseBadgeText(const QString &familyKeyOrAlias);

// The registry's license_note, for a tooltip or a dialog body. Empty when the registry has none.
QString familyLicenseNote(const QString &familyKeyOrAlias);

// The commercial-use declaration, stored in QSettings under DarkDuck/SpellVision. The key
// itself is spelled once, in FamilyLicense.cpp -- deliberately not repeated here, because a
// ratchet counts its occurrences across the tree and a comment is indistinguishable from a
// second reader to a text scan.
// One reader and one writer, here, so the key literal is spelled once in the tree -- the same shape
// as devToolsVisible() and its one env read.
bool commercialUseDeclared();
void setCommercialUseDeclared(bool declared);

// The whole decision, in one pure function so it can be tested without a dialog or a settings file.
LicenseGate licenseGateFor(const QString &familyKeyOrAlias, bool commercialUseIsDeclared);

// How many rows the generated table carries. Exposed so a test can assert the table is not empty --
// an empty table would make every family look commercially licensed, silently.
int familyLicenseRowCount();

} // namespace spellvision::assets
