from pathlib import Path

h_path = Path("qt_ui/QueueManager.h")
cpp_path = Path("qt_ui/QueueManager.cpp")

h = h_path.read_text(encoding="utf-8")
cpp = cpp_path.read_text(encoding="utf-8")

# ------------------------------------------------------------
# Sprint 15C Pass 29Q
# Surface LTX dual-output action targets in the queue model/details.
# ------------------------------------------------------------

# Header: add action-ready fields to QueueItem.
if "QString ltxDualOutputActionsSummary;" not in h:
    needle = "    QString ltxDualOutputSummary;\n"
    insert = """    QString ltxDualOutputSummary;
    QString ltxDualOutputActionsSummary;
    QJsonObject ltxOutputActions;
"""
    if needle not in h:
        raise SystemExit("Could not find ltxDualOutputSummary field in QueueManager.h")
    h = h.replace(needle, insert, 1)

if "#include <QJsonObject>" not in h:
    if "#include <QJsonArray>" in h:
        h = h.replace("#include <QJsonArray>", "#include <QJsonArray>\n#include <QJsonObject>", 1)
    else:
        h = h.replace("#include <QString>", "#include <QString>\n#include <QJsonObject>", 1)

# Source includes.
if "#include <QFileInfo>" not in cpp:
    cpp = "#include <QFileInfo>\n" + cpp

if "#include <QJsonObject>" not in cpp:
    if "#include <QJsonArray>" in cpp:
        cpp = cpp.replace("#include <QJsonArray>", "#include <QJsonArray>\n#include <QJsonObject>", 1)
    else:
        cpp = "#include <QJsonObject>\n" + cpp

# Add action helper near existing LTX queue helpers.
if "ltxDualOutputActionsForQueue" not in cpp:
    helper = r'''

QJsonObject ltxDualOutputActionsForQueue(const QJsonObject& result)
{
    const QString primaryPath = result.value(QStringLiteral("video_output")).toString(
        result.value(QStringLiteral("output")).toString()).trimmed();

    const QString primaryMetadata = result.value(QStringLiteral("video_metadata_output")).toString(
        result.value(QStringLiteral("metadata_output")).toString()).trimmed();

    const QString fullPath = result.value(QStringLiteral("ltx_full_output")).toString().trimmed();
    const QString fullMetadata = result.value(QStringLiteral("ltx_full_metadata_output")).toString().trimmed();

    const QString distilledPath = result.value(QStringLiteral("ltx_distilled_output")).toString().trimmed();
    const QString distilledMetadata = result.value(QStringLiteral("ltx_distilled_metadata_output")).toString().trimmed();

    const QString secondaryPath = result.value(QStringLiteral("video_secondary_output")).toString().trimmed();
    const QString secondaryMetadata = result.value(QStringLiteral("video_secondary_metadata_output")).toString().trimmed();

    QJsonObject actions;
    actions.insert(QStringLiteral("open_primary"), primaryPath);
    actions.insert(QStringLiteral("reveal_primary_metadata"), primaryMetadata);
    actions.insert(QStringLiteral("open_full"), fullPath);
    actions.insert(QStringLiteral("reveal_full_metadata"), fullMetadata);
    actions.insert(QStringLiteral("open_distilled"), distilledPath);
    actions.insert(QStringLiteral("reveal_distilled_metadata"), distilledMetadata);
    actions.insert(QStringLiteral("open_secondary"), secondaryPath);
    actions.insert(QStringLiteral("reveal_secondary_metadata"), secondaryMetadata);

    const QString folderSource = !primaryPath.isEmpty() ? primaryPath
        : (!fullPath.isEmpty() ? fullPath : distilledPath);

    if (!folderSource.isEmpty())
        actions.insert(QStringLiteral("reveal_output_folder"), QFileInfo(folderSource).absolutePath());

    return actions;
}

QString ltxDualOutputActionsSummaryForQueue(const QJsonObject& result)
{
    const QJsonObject actions = ltxDualOutputActionsForQueue(result);
    const QString primaryRole = result.value(QStringLiteral("video_primary_output_role")).toString().trimmed();
    const QString preferredRole = result.value(QStringLiteral("video_preferred_output_role")).toString().trimmed();

    const QString primaryPath = actions.value(QStringLiteral("open_primary")).toString().trimmed();
    const QString fullPath = actions.value(QStringLiteral("open_full")).toString().trimmed();
    const QString distilledPath = actions.value(QStringLiteral("open_distilled")).toString().trimmed();
    const QString primaryMetadata = actions.value(QStringLiteral("reveal_primary_metadata")).toString().trimmed();
    const QString fullMetadata = actions.value(QStringLiteral("reveal_full_metadata")).toString().trimmed();
    const QString distilledMetadata = actions.value(QStringLiteral("reveal_distilled_metadata")).toString().trimmed();
    const QString outputFolder = actions.value(QStringLiteral("reveal_output_folder")).toString().trimmed();

    if (primaryPath.isEmpty() && fullPath.isEmpty() && distilledPath.isEmpty())
        return {};

    QStringList lines;
    lines << QStringLiteral("LTX actions");

    if (!preferredRole.isEmpty())
        lines << QStringLiteral("Preferred: %1").arg(ltxOutputRoleLabelForQueue(preferredRole));

    if (!primaryRole.isEmpty())
        lines << QStringLiteral("Primary action target: %1").arg(ltxOutputRoleLabelForQueue(primaryRole));

    if (!primaryPath.isEmpty())
        lines << QStringLiteral("• Open Primary: %1").arg(primaryPath);

    if (!distilledPath.isEmpty())
        lines << QStringLiteral("• Open Distilled: %1").arg(distilledPath);

    if (!fullPath.isEmpty())
        lines << QStringLiteral("• Open Full: %1").arg(fullPath);

    if (!primaryMetadata.isEmpty())
        lines << QStringLiteral("• Reveal Primary Metadata: %1").arg(primaryMetadata);

    if (!distilledMetadata.isEmpty())
        lines << QStringLiteral("• Reveal Distilled Metadata: %1").arg(distilledMetadata);

    if (!fullMetadata.isEmpty())
        lines << QStringLiteral("• Reveal Full Metadata: %1").arg(fullMetadata);

    if (!outputFolder.isEmpty())
        lines << QStringLiteral("• Reveal Output Folder: %1").arg(outputFolder);

    return lines.join(QStringLiteral("\\n"));
}

'''
    marker = "QueueItem QueueManager::itemFromSnapshotObject"
    idx = cpp.find(marker)
    if idx < 0:
        raise SystemExit("Could not find QueueManager::itemFromSnapshotObject insertion point.")
    cpp = cpp[:idx] + helper + "\n" + cpp[idx:]

# Populate action fields.
if "item.ltxOutputActions = ltxDualOutputActionsForQueue(result);" not in cpp:
    needle = "    item.ltxDualOutputSummary = ltxDualOutputSummaryForQueue(result);\n"
    insert = """    item.ltxDualOutputSummary = ltxDualOutputSummaryForQueue(result);
    item.ltxOutputActions = ltxDualOutputActionsForQueue(result);
    item.ltxDualOutputActionsSummary = ltxDualOutputActionsSummaryForQueue(result);
"""
    if needle not in cpp:
        raise SystemExit("Could not find ltxDualOutputSummary assignment in QueueManager.cpp")
    cpp = cpp.replace(needle, insert, 1)

# Append action summary to visible queue details/status text.
if "Sprint 15C Pass 29Q: append LTX action summary" not in cpp:
    needle = """    if (!item.ltxDualOutputSummary.isEmpty())
    {
        if (item.statusText.trimmed().isEmpty())
            item.statusText = item.ltxDualOutputSummary;
        else if (!item.statusText.contains(item.ltxDualOutputSummary))
            item.statusText += QStringLiteral("\\n\\n") + item.ltxDualOutputSummary;
    }
"""
    insert = """    if (!item.ltxDualOutputSummary.isEmpty())
    {
        if (item.statusText.trimmed().isEmpty())
            item.statusText = item.ltxDualOutputSummary;
        else if (!item.statusText.contains(item.ltxDualOutputSummary))
            item.statusText += QStringLiteral("\\n\\n") + item.ltxDualOutputSummary;
    }

    // Sprint 15C Pass 29Q: append LTX action summary for Queue details/tooltips.
    if (!item.ltxDualOutputActionsSummary.isEmpty())
    {
        if (item.statusText.trimmed().isEmpty())
            item.statusText = item.ltxDualOutputActionsSummary;
        else if (!item.statusText.contains(item.ltxDualOutputActionsSummary))
            item.statusText += QStringLiteral("\\n\\n") + item.ltxDualOutputActionsSummary;
    }
"""
    if needle not in cpp:
        raise SystemExit("Could not find Pass 29O statusText LTX summary block.")
    cpp = cpp.replace(needle, insert, 1)

h_path.write_text(h, encoding="utf-8")
cpp_path.write_text(cpp, encoding="utf-8")

print("Applied Sprint 15C Pass 29Q: LTX dual-output action targets surfaced in QueueItem/details.")
