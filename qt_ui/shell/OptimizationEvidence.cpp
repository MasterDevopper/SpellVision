#include "shell/OptimizationEvidence.h"

#include <QJsonArray>
#include <QJsonValue>
#include <QStringList>
#include <QtGlobal>

#include <limits>

namespace spellvision::shell
{
namespace
{

// How a lever's ACTIVE answer is read out of the live argv. The mapping is here rather than in the
// worker reply because the argv block is what a test fakes: the derivation and its test have to be
// on the same side of the wire, or the test proves nothing about what the panel shows.
enum class ActiveProbe
{
    Attention,      // provenance.attention_backend == value
    FastFeature,    // provenance.fast_flags contains value
    ReserveVram,    // provenance.reserve_vram_gb is set
    DynamicVramOff, // provenance.dynamic_vram is false
    PerRender,      // a graph lever: chosen on the request, never on the command line
};

struct LeverProbe
{
    const char *id;
    // The key in provenance.packages this lever needs. Empty means the lever ships with the core
    // itself, so "is it installed" has no package to ask about and is not a question.
    const char *packageKey;
    ActiveProbe activeProbe;
    const char *activeValue;
};

// Every lever in python/optimization_levers.py. A lever NOT listed here still renders -- it just
// renders honestly, as an arm this build cannot read, rather than silently as "not active".
constexpr LeverProbe kLeverProbes[] = {
    {"sdpa_baseline",           "",              ActiveProbe::Attention,      "sdpa"},
    {"sage_attention",          "sageattention", ActiveProbe::Attention,      "sage"},
    {"fast_fp16_accumulation",  "",              ActiveProbe::FastFeature,    "fp16_accumulation"},
    {"fast_fp8_matrix_mult",    "",              ActiveProbe::FastFeature,    "fp8_matrix_mult"},
    {"fixed_vram_budget",       "",              ActiveProbe::ReserveVram,    ""},
    {"dynamic_vram_off",        "comfy_aimdo",   ActiveProbe::DynamicVramOff, ""},
    {"vae_tiling",              "",              ActiveProbe::PerRender,      ""},
    {"ck_int8_attention",       "comfy_kitchen", ActiveProbe::Attention,      "ck"},
    {"easycache",               "",              ActiveProbe::PerRender,      ""},
    {"pruna_vaed",              "",              ActiveProbe::PerRender,      ""},
    {"fp16_cast",               "",              ActiveProbe::PerRender,      ""},
};

const LeverProbe *probeFor(const QString &leverId)
{
    for (const LeverProbe &probe : kLeverProbes)
    {
        if (leverId == QLatin1String(probe.id))
            return &probe;
    }
    return nullptr;
}

// The running process answered at all. An empty argv or an "unknown" backend means the probe could
// not read it -- which is a state of its own and never SDPA-by-default. Defaulting there is what
// turned a silent relaunch into two indistinguishable sessions.
bool argvWasRead(const QJsonObject &provenance)
{
    if (provenance.isEmpty())
        return false;
    if (!provenance.value(QStringLiteral("probe_error")).isNull()
        && provenance.value(QStringLiteral("probe_error")).toString().trimmed().length() > 0)
        return false;
    if (provenance.value(QStringLiteral("attention_backend")).toString() == QStringLiteral("unknown"))
        return false;
    return !provenance.value(QStringLiteral("comfy_argv")).toArray().isEmpty();
}

QString formatPercent(double delta)
{
    // Built by concatenation rather than by arg(): a literal '%' next to a place marker is exactly
    // the shape QString::arg misreads, and this string is half percent signs.
    const QString magnitude = QString::number(qAbs(delta), 'f', 1) + QStringLiteral("%");
    if (delta < 0.0)
        return QString(QChar(0x2212)) + magnitude + QStringLiteral(" faster");
    if (delta > 0.0)
        return QStringLiteral("+") + magnitude + QStringLiteral(" slower");
    return magnitude + QStringLiteral(" -- no difference measured");
}

struct Measurement
{
    bool known = false;
    bool anyRowRecorded = false;
    bool guardFailed = false;
    int recordedRows = 0;
    double deltaPct = 0.0;
    int runs = 0;
    QString family;
    QString mode;
};

Measurement bestMeasurement(const QJsonArray &ledger, const QString &leverId)
{
    Measurement best;
    double bestDelta = std::numeric_limits<double>::max();

    for (const QJsonValue &value : ledger)
    {
        const QJsonObject row = value.toObject();
        if (row.value(QStringLiteral("lever")).toString() != leverId)
            continue;

        best.anyRowRecorded = true;
        best.recordedRows += 1;

        if (row.value(QStringLiteral("quality")).toObject().value(QStringLiteral("status")).toString()
            == QStringLiteral("fail"))
            best.guardFailed = true;

        if (row.value(QStringLiteral("excluded_from_delta")).toBool(false))
            continue;

        const QJsonValue delta = row.value(QStringLiteral("delta_pct"));
        if (!delta.isDouble())
            continue;

        if (delta.toDouble() < bestDelta)
        {
            bestDelta = delta.toDouble();
            best.known = true;
            best.deltaPct = bestDelta;
            best.runs = row.value(QStringLiteral("seconds")).toArray().size();
            best.family = row.value(QStringLiteral("family")).toString();
            best.mode = row.value(QStringLiteral("mode")).toString();
        }
    }
    return best;
}

} // namespace

QString OptimizationEvidence::notTimedText()
{
    return QStringLiteral("not timed");
}

QString OptimizationEvidence::notProbedText()
{
    return QStringLiteral("not probed");
}

QString OptimizationEvidence::notInstalledText()
{
    return QStringLiteral("not installed");
}

QStringList OptimizationEvidence::columnHeadings()
{
    return {
        QStringLiteral("Optimization"),
        QStringLiteral("Installed"),
        QStringLiteral("Active now"),
        QStringLiteral("Measured"),
        QStringLiteral("Verdict"),
    };
}

QList<OptimizationEvidenceRow> OptimizationEvidence::rows(const QJsonObject &reply)
{
    const QJsonArray catalogue = reply.value(QStringLiteral("catalogue")).toArray();
    const QJsonArray ledger = reply.value(QStringLiteral("rows")).toArray();
    const QJsonObject provenance = reply.value(QStringLiteral("provenance")).toObject();
    const QJsonObject packages = provenance.value(QStringLiteral("packages")).toObject();
    const bool argvKnown = argvWasRead(provenance);

    QList<OptimizationEvidenceRow> out;
    out.reserve(catalogue.size());

    for (const QJsonValue &entry : catalogue)
    {
        const QJsonObject lever = entry.toObject();
        OptimizationEvidenceRow row;
        row.leverId = lever.value(QStringLiteral("id")).toString();
        row.label = lever.value(QStringLiteral("label")).toString();
        if (row.label.isEmpty())
            row.label = row.leverId;

        const LeverProbe *probe = probeFor(row.leverId);
        const bool blocked = lever.value(QStringLiteral("status")).toString() == QStringLiteral("blocked");
        const bool hasPackage = probe && QLatin1String(probe->packageKey).size() > 0;

        // --- installed ------------------------------------------------------------------------
        if (!hasPackage)
        {
            // Nothing to ask about: the flag or the node ships with ComfyUI itself.
            row.installed = QStringLiteral("built in");
            row.installedProbed = true;
            row.installedPresent = true;
        }
        else
        {
            const QJsonValue value = packages.value(QLatin1String(probe->packageKey));
            if (value.isUndefined() || value.isNull())
            {
                // The probe could not ask. Deliberately NOT the same words as "asked and did not
                // find it" -- collapsing those two is what let two knowable package versions read
                // as unknowable for a whole task.
                row.installed = notProbedText();
                row.installedProbed = false;
            }
            else if (value.isString())
            {
                // Named, not just versioned: "installed 0.4.15" beside --disable-dynamic-vram
                // reads as though the FLAG had a version. It is comfy-aimdo that does.
                row.installed = QStringLiteral("%1 %2")
                                    .arg(QString(QLatin1String(probe->packageKey)).replace(QLatin1Char('_'), QLatin1Char('-')),
                                         value.toString());
                row.installedProbed = true;
                row.installedPresent = true;
            }
            else if (value.toBool(false))
            {
                row.installed = QStringLiteral("installed");
                row.installedProbed = true;
                row.installedPresent = true;
            }
            else
            {
                row.installed = notInstalledText();
                row.installedProbed = true;
                row.installedPresent = false;
            }
        }

        // --- active (the live argv, never the launcher's intent) --------------------------------
        if (probe && probe->activeProbe == ActiveProbe::PerRender)
        {
            row.active = QStringLiteral("per render");
            row.activeKnown = false;
        }
        else if (!probe)
        {
            row.active = QStringLiteral("unknown -- this build cannot read that arm");
            row.activeKnown = false;
        }
        else if (!argvKnown)
        {
            row.active = QStringLiteral("unknown -- the running process could not be read");
            row.activeKnown = false;
        }
        else
        {
            row.activeKnown = true;
            switch (probe->activeProbe)
            {
            case ActiveProbe::Attention:
            {
                const QString backend = provenance.value(QStringLiteral("attention_backend")).toString();
                row.activeNow = backend == QLatin1String(probe->activeValue);
                row.active = row.activeNow
                                 ? QStringLiteral("active")
                                 : QStringLiteral("not active (running: %1)").arg(backend);
                break;
            }
            case ActiveProbe::FastFeature:
            {
                const QJsonArray flags = provenance.value(QStringLiteral("fast_flags")).toArray();
                for (const QJsonValue &flag : flags)
                {
                    if (flag.toString() == QLatin1String(probe->activeValue))
                        row.activeNow = true;
                }
                row.active = row.activeNow ? QStringLiteral("active") : QStringLiteral("not active");
                break;
            }
            case ActiveProbe::ReserveVram:
            {
                const QJsonValue reserve = provenance.value(QStringLiteral("reserve_vram_gb"));
                row.activeNow = reserve.isDouble();
                row.active = row.activeNow
                                 ? QStringLiteral("active (%1 GB)").arg(reserve.toDouble())
                                 : QStringLiteral("not active");
                break;
            }
            case ActiveProbe::DynamicVramOff:
            {
                const QJsonValue dynamic = provenance.value(QStringLiteral("dynamic_vram"));
                if (!dynamic.isBool())
                {
                    row.activeKnown = false;
                    row.active = QStringLiteral("unknown -- the running process could not be read");
                    break;
                }
                row.activeNow = !dynamic.toBool();
                row.active = row.activeNow ? QStringLiteral("active") : QStringLiteral("not active");
                break;
            }
            case ActiveProbe::PerRender:
                break;
            }
        }

        // --- measured -------------------------------------------------------------------------
        const Measurement measurement = bestMeasurement(ledger, row.leverId);
        if (!measurement.known)
        {
            row.measuredIsKnown = false;
            row.measured = measurement.anyRowRecorded
                               ? QStringLiteral("%1 (%2 recorded, none comparable)")
                                     .arg(notTimedText())
                                     .arg(measurement.recordedRows)
                               : notTimedText();
        }
        else
        {
            row.measuredIsKnown = true;
            row.measured = QStringLiteral("%1 (%2 runs, %3 %4)")
                               .arg(formatPercent(measurement.deltaPct))
                               .arg(measurement.runs)
                               .arg(measurement.family, measurement.mode)
                               .trimmed();
            // A delta shown beside a lever that is not running reads as a benefit the user is
            // getting. It is not -- it is a benefit they are not getting -- so the number says when
            // it applied rather than standing alone.
            if (!row.activeNow)
                row.measured += QStringLiteral(" -- measured then, not active now");
        }

        // --- verdict --------------------------------------------------------------------------
        if (blocked)
        {
            row.verdictKind = OptimizationVerdict::Blocked;
            row.verdict = QStringLiteral("blocked -- SpellVision cannot ask for it");
        }
        else if (measurement.guardFailed)
        {
            row.verdictKind = OptimizationVerdict::Broke;
            row.verdict = QStringLiteral("broke -- a quality guard failed");
        }
        else if (probe && probe->activeProbe == ActiveProbe::PerRender)
        {
            row.verdictKind = OptimizationVerdict::Unknown;
            row.verdict = QStringLiteral("per render -- set on the request, not at launch");
        }
        else if (!row.activeKnown)
        {
            row.verdictKind = OptimizationVerdict::Unknown;
            row.verdict = QStringLiteral("unknown -- the running process could not be read");
        }
        else if (row.activeNow)
        {
            row.verdictKind = OptimizationVerdict::Used;
            row.verdict = QStringLiteral("used");
        }
        else if (!row.installedProbed)
        {
            row.verdictKind = OptimizationVerdict::Unknown;
            row.verdict = QStringLiteral("unknown -- installation not probed");
        }
        else if (row.installedPresent)
        {
            row.verdictKind = OptimizationVerdict::Skipped;
            // A core flag is not "installed" in any sense a user would recognise -- it ships with
            // ComfyUI. Only a lever with a real package gets the installed-versus-active wording,
            // which is the distinction that wording exists to draw.
            row.verdict = hasPackage ? QStringLiteral("skipped -- installed, not active")
                                     : QStringLiteral("skipped -- not active");
        }
        else
        {
            row.verdictKind = OptimizationVerdict::Skipped;
            row.verdict = QStringLiteral("skipped -- not installed");
        }

        QStringList tip;
        const QString note = lever.value(QStringLiteral("note")).toString();
        if (!note.isEmpty())
            tip << note;
        const QString blockedReason = lever.value(QStringLiteral("blocked_reason")).toString();
        if (!blockedReason.isEmpty())
            tip << QStringLiteral("Blocked: %1").arg(blockedReason);
        if (!row.measuredIsKnown)
            tip << QStringLiteral("No verified delta in the ledger. Nothing here is an estimate.");
        row.toolTip = tip.join(QStringLiteral("\n\n"));

        out.append(row);
    }

    return out;
}

QString OptimizationEvidence::summaryText(const QJsonObject &reply)
{
    const QJsonObject provenance = reply.value(QStringLiteral("provenance")).toObject();
    if (!argvWasRead(provenance))
    {
        const QString error = provenance.value(QStringLiteral("probe_error")).toString();
        return error.isEmpty()
                   ? QStringLiteral("Running ComfyUI could not be read, so nothing below says what "
                                    "is active. Installed is not active.")
                   : QStringLiteral("Running ComfyUI could not be read (%1). Installed is not active.")
                         .arg(error);
    }

    const QJsonArray fast = provenance.value(QStringLiteral("fast_flags")).toArray();
    QStringList names;
    for (const QJsonValue &flag : fast)
        names << flag.toString();

    return QStringLiteral("Running ComfyUI %1 -- attention %2, --fast %3. Read from the live "
                          "command line, not from the launcher's intent.")
        .arg(provenance.value(QStringLiteral("comfy_version")).toString(QStringLiteral("(version unknown)")),
             provenance.value(QStringLiteral("attention_backend")).toString(),
             names.isEmpty() ? QStringLiteral("(none)") : names.join(QStringLiteral(", ")));
}

} // namespace spellvision::shell
