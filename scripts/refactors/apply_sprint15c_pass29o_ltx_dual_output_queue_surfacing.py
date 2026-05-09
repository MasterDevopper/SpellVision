from pathlib import Path
import re

h_path = Path("qt_ui/QueueManager.h")
cpp_path = Path("qt_ui/QueueManager.cpp")

h = h_path.read_text(encoding="utf-8")
cpp = cpp_path.read_text(encoding="utf-8")

# ------------------------------------------------------------
# Patch 1: Add fields to QueueItem.
# ------------------------------------------------------------
if "QJsonArray videoOutputs;" not in h:
    # Prefer inserting after metadataPath because this is output/result-adjacent.
    needle = "    QString metadataPath;\n"
    insert = """    QString metadataPath;
    QJsonArray videoOutputs;
    int videoOutputCount = 0;
    QString videoPrimaryOutputRole;
    QString videoSecondaryOutput;
    QString videoSecondaryMetadataOutput;
    QString ltxFullOutput;
    QString ltxFullMetadataOutput;
    QString ltxDistilledOutput;
    QString ltxDistilledMetadataOutput;
    QString ltxDualOutputSummary;
"""
    if needle not in h:
        raise SystemExit("Could not find QueueItem metadataPath field in qt_ui/QueueManager.h")
    h = h.replace(needle, insert, 1)

if "#include <QJsonArray>" not in h:
    if "#include <QJsonObject>" in h:
        h = h.replace("#include <QJsonObject>", "#include <QJsonObject>\n#include <QJsonArray>", 1)
    else:
        h = h.replace("#include <QString>", "#include <QString>\n#include <QJsonArray>", 1)

# ------------------------------------------------------------
# Patch 2: Ensure QueueManager.cpp has QJsonArray include.
# ------------------------------------------------------------
if "#include <QJsonArray>" not in cpp:
    if "#include <QJsonObject>" in cpp:
        cpp = cpp.replace("#include <QJsonObject>", "#include <QJsonObject>\n#include <QJsonArray>", 1)
    else:
        cpp = cpp.replace("#include <QJsonDocument>", "#include <QJsonDocument>\n#include <QJsonArray>", 1)

# ------------------------------------------------------------
# Patch 3: Add helper functions near existing local helpers.
# ------------------------------------------------------------
if "ltxOutputRoleLabelForQueue" not in cpp:
    helper = r'''

namespace
{
QString ltxOutputRoleLabelForQueue(const QString& role)
{
    const QString normalized = role.trimmed().toLower();

    if (normalized == QStringLiteral("full"))
        return QStringLiteral("LTX Full");

    if (normalized == QStringLiteral("distilled"))
        return QStringLiteral("LTX Distilled");

    if (normalized.isEmpty())
        return QStringLiteral("LTX Output");

    return normalized.left(1).toUpper() + normalized.mid(1);
}

QString ltxDualOutputSummaryForQueue(const QJsonObject& result)
{
    const QJsonArray outputs = result.value(QStringLiteral("video_outputs")).toArray();
    const QString fullOutput = result.value(QStringLiteral("ltx_full_output")).toString().trimmed();
    const QString distilledOutput = result.value(QStringLiteral("ltx_distilled_output")).toString().trimmed();
    const QString primaryRole = result.value(QStringLiteral("video_primary_output_role")).toString().trimmed();

    if (outputs.isEmpty() && fullOutput.isEmpty() && distilledOutput.isEmpty())
        return {};

    QStringList lines;
    lines << QStringLiteral("LTX outputs");

    if (!primaryRole.isEmpty())
        lines << QStringLiteral("Primary: %1").arg(ltxOutputRoleLabelForQueue(primaryRole));

    for (const QJsonValue& value : outputs)
    {
        if (!value.isObject())
            continue;

        const QJsonObject output = value.toObject();
        const QString role = output.value(QStringLiteral("role")).toString();
        const QString label = output.value(QStringLiteral("label")).toString(ltxOutputRoleLabelForQueue(role));
        const QString path = output.value(QStringLiteral("path")).toString().trimmed();
        const bool exists = output.value(QStringLiteral("exists")).toBool(false);
        const qint64 sizeBytes = static_cast<qint64>(output.value(QStringLiteral("size_bytes")).toDouble(0.0));

        QString status = exists ? QStringLiteral("ready") : QStringLiteral("missing");
        if (exists && sizeBytes > 0)
            status += QStringLiteral(", %1 KB").arg(QString::number(sizeBytes / 1024));

        lines << QStringLiteral("• %1 — %2").arg(label, status);

        if (!path.isEmpty())
            lines << QStringLiteral("  %1").arg(path);
    }

    if (outputs.isEmpty())
    {
        if (!fullOutput.isEmpty())
            lines << QStringLiteral("• LTX Full — %1").arg(fullOutput);
        if (!distilledOutput.isEmpty())
            lines << QStringLiteral("• LTX Distilled — %1").arg(distilledOutput);
    }

    return lines.join(QStringLiteral("\\n"));
}
} // namespace

'''
    # If the file already has an anonymous namespace, avoid nesting by inserting
    # before QueueManager methods instead.
    method_marker = "QueueItem QueueManager::itemFromSnapshotObject"
    idx = cpp.find(method_marker)
    if idx < 0:
        raise SystemExit("Could not find QueueManager::itemFromSnapshotObject in qt_ui/QueueManager.cpp")

    cpp = cpp[:idx] + helper + "\n" + cpp[idx:]

# ------------------------------------------------------------
# Patch 4: Populate dual-output fields from result JSON.
# ------------------------------------------------------------
if "item.videoOutputs = result.value(QStringLiteral(\"video_outputs\")).toArray();" not in cpp:
    needle = """    if (item.metadataPath.isEmpty())
        item.metadataPath = obj.value(QStringLiteral("metadata_output")).toString().trimmed();
"""
    insert = """    if (item.metadataPath.isEmpty())
        item.metadataPath = obj.value(QStringLiteral("metadata_output")).toString().trimmed();

    item.videoOutputs = result.value(QStringLiteral("video_outputs")).toArray();
    item.videoOutputCount = result.value(QStringLiteral("video_output_count")).toInt(item.videoOutputs.size());
    item.videoPrimaryOutputRole = result.value(QStringLiteral("video_primary_output_role")).toString().trimmed();
    item.videoSecondaryOutput = result.value(QStringLiteral("video_secondary_output")).toString().trimmed();
    item.videoSecondaryMetadataOutput = result.value(QStringLiteral("video_secondary_metadata_output")).toString().trimmed();
    item.ltxFullOutput = result.value(QStringLiteral("ltx_full_output")).toString().trimmed();
    item.ltxFullMetadataOutput = result.value(QStringLiteral("ltx_full_metadata_output")).toString().trimmed();
    item.ltxDistilledOutput = result.value(QStringLiteral("ltx_distilled_output")).toString().trimmed();
    item.ltxDistilledMetadataOutput = result.value(QStringLiteral("ltx_distilled_metadata_output")).toString().trimmed();
    item.ltxDualOutputSummary = ltxDualOutputSummaryForQueue(result);
"""
    if needle not in cpp:
        raise SystemExit("Could not find metadataPath block in QueueManager.cpp")
    cpp = cpp.replace(needle, insert, 1)

# ------------------------------------------------------------
# Patch 5: Make the summary visible through tooltip/status text without
# disturbing the primary preview path.
# ------------------------------------------------------------
if "Pass 29O: append LTX dual-output summary" not in cpp:
    needle = """    item.statusText = progress.value(QStringLiteral("message")).toString();
"""
    insert = """    item.statusText = progress.value(QStringLiteral("message")).toString();

    // Sprint 15C Pass 29O: append LTX dual-output summary for Queue details/tooltips.
    if (!item.ltxDualOutputSummary.isEmpty())
    {
        if (item.statusText.trimmed().isEmpty())
            item.statusText = item.ltxDualOutputSummary;
        else if (!item.statusText.contains(item.ltxDualOutputSummary))
            item.statusText += QStringLiteral("\\n\\n") + item.ltxDualOutputSummary;
    }
"""
    if needle not in cpp:
        raise SystemExit("Could not find statusText assignment in QueueManager.cpp")
    cpp = cpp.replace(needle, insert, 1)

h_path.write_text(h, encoding="utf-8")
cpp_path.write_text(cpp, encoding="utf-8")

print("Applied Sprint 15C Pass 29O: QueueItem captures and surfaces LTX full/distilled outputs.")
