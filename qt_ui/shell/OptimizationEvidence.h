#pragma once

#include <QJsonObject>
#include <QList>
#include <QString>

namespace spellvision::shell
{

// What the Runtime page's optimization panel says about one lever.
//
// Three facts are currently invisible in this app, and they are different facts:
//
//   * **installed** -- is the package there at all. `sageattention` IS installed in ComfyUI's venv
//     on this box right now.
//   * **active** -- did the RUNNING process get the flag. It did not: ComfyUI was launched with
//     sage this morning, died, was relaunched without it, and nothing said so. Renders before and
//     after were indistinguishable afterwards.
//   * **measured** -- is there a verified delta in the ledger. Usually there is not, and "no
//     measurement" rendered as a blank looks exactly like zero.
//
// Conflating the first two is the defect this panel exists to remove, so a lever that is installed
// and not active must never read as a benefit -- and a historical delta shown beside an inactive
// lever is a benefit claim unless it says it is historical.
enum class OptimizationVerdict
{
    Used,      // the running process was launched with it
    Skipped,   // it could have run and did not (installed-not-active, or absent)
    Broke,     // a quality guard failed on a recorded row
    Blocked,   // SpellVision cannot ask for it -- a gap in this repository, not in ComfyUI
    Unknown,   // could not be read: the probe failed, or the lever is set per render
};

struct OptimizationEvidenceRow
{
    QString leverId;
    QString label;

    QString installed;
    QString active;
    QString measured;
    QString verdict;

    OptimizationVerdict verdictKind = OptimizationVerdict::Unknown;

    // "the probe asked and found nothing" is not "the probe could not ask". Kept as a flag as well
    // as in the text, so a caller cannot accidentally collapse them by comparing strings loosely.
    bool installedProbed = false;
    bool installedPresent = false;
    // Whether the LIVE ARGV answered. False for a lever that is chosen per render and has no argv
    // answer at all, and for a probe that could not read the running process.
    bool activeKnown = false;
    bool activeNow = false;
    // False whenever `measured` is a "not timed" string. Never true for a blank.
    bool measuredIsKnown = false;

    QString toolTip;
};

// Turns one `optimization_results` reply into the rows of the panel. Pure: no worker, no socket, no
// ComfyUI -- a fake ledger and a fake probe block drive it in tests/cpp/test_optimization_panel.cpp.
class OptimizationEvidence
{
public:
    // The exact words. Held as constants because the honesty rules are assertions about these
    // strings: "not timed" must never be a blank, and "not probed" must never read like
    // "not installed".
    static QString notTimedText();
    static QString notProbedText();
    static QString notInstalledText();

    static QStringList columnHeadings();

    // `reply` is the whole payload: `catalogue`, `rows`, `provenance`. One row per catalogue entry,
    // in catalogue order, whether or not the ledger holds anything for it -- a lever nobody has
    // measured vanishing from the table is the invisibility this panel removes.
    static QList<OptimizationEvidenceRow> rows(const QJsonObject &reply);

    // The line under the table: where the ledger is and what the running process is, or why neither
    // could be read.
    static QString summaryText(const QJsonObject &reply);
};

} // namespace spellvision::shell
