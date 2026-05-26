from pathlib import Path

path = Path("qt_ui/shell/QueueUiPresenter.cpp")
text = path.read_text(encoding="utf-8")

old = '''QString QueueUiPresenter::queueSummaryText(const QueueItem &item)
{
    if (item.id.trimmed().isEmpty())
        return QStringLiteral("No active queue item.");

    QStringList parts;

    const QString command = item.command.trimmed().isEmpty()
                                ? QStringLiteral("job")
                                : item.command.trimmed().toUpper();
    parts << command;

    parts << queueStateDisplay(item.state);
'''

new = '''QString QueueUiPresenter::queueSummaryText(const QueueItem &item)
{
    if (item.id.trimmed().isEmpty())
        return QStringLiteral("No active queue item.");

    // Sprint 15C Pass 29Q v3:
    // If this is an LTX dual-output job, prefer a readable multiline details block
    // instead of flattening the action-ready output paths into one long status row.
    if (!item.ltxDualOutputSummary.trimmed().isEmpty() ||
        !item.ltxDualOutputActionsSummary.trimmed().isEmpty())
    {
        QStringList lines;

        const QString command = item.command.trimmed().isEmpty()
                                    ? QStringLiteral("JOB")
                                    : item.command.trimmed().toUpper();

        lines << QStringLiteral("%1 • %2").arg(command, queueStateDisplay(item.state));

        if (!item.videoDurationLabel.trimmed().isEmpty())
            lines << QStringLiteral("Duration: %1").arg(item.videoDurationLabel.trimmed());

        if (!item.videoResolution.trimmed().isEmpty())
            lines << QStringLiteral("Resolution: %1").arg(item.videoResolution.trimmed());

        if (!item.outputPath.trimmed().isEmpty())
            lines << QStringLiteral("Primary output: %1").arg(item.outputPath.trimmed());

        if (!item.metadataPath.trimmed().isEmpty())
            lines << QStringLiteral("Primary metadata: %1").arg(item.metadataPath.trimmed());

        if (!item.ltxDualOutputSummary.trimmed().isEmpty())
            lines << QStringLiteral("\\n%1").arg(item.ltxDualOutputSummary.trimmed());

        if (!item.ltxDualOutputActionsSummary.trimmed().isEmpty())
            lines << QStringLiteral("\\n%1").arg(item.ltxDualOutputActionsSummary.trimmed());

        if (!item.errorText.trimmed().isEmpty())
            lines << QStringLiteral("\\nError: %1").arg(item.errorText.trimmed());

        return lines.join(QStringLiteral("\\n"));
    }

    QStringList parts;

    const QString command = item.command.trimmed().isEmpty()
                                ? QStringLiteral("job")
                                : item.command.trimmed().toUpper();
    parts << command;

    parts << queueStateDisplay(item.state);
'''

if old not in text:
    raise SystemExit("Could not find QueueUiPresenter::queueSummaryText opening block.")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

print("Applied Sprint 15C Pass 29Q v3: Queue presenter renders LTX dual-output action summary.")
