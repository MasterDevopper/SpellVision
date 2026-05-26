from pathlib import Path

path = Path("qt_ui/shell/QueueUiPresenter.cpp")
text = path.read_text(encoding="utf-8")

needle = '''        lines << QStringLiteral("%1 • %2").arg(command, queueStateDisplay(item.state));

        if (!item.videoDurationLabel.trimmed().isEmpty())
            lines << QStringLiteral("Duration: %1").arg(item.videoDurationLabel.trimmed());
'''

replacement = '''        lines << QStringLiteral("%1 • %2").arg(command, queueStateDisplay(item.state));

        // Sprint 15C Pass 29Q v4:
        // Keep LTX actions visible in the compact details card before long paths.
        const QString primaryRole = item.videoPrimaryOutputRole.trimmed().isEmpty()
                                        ? QStringLiteral("primary")
                                        : item.videoPrimaryOutputRole.trimmed();

        QStringList readyVariants;
        if (!item.ltxDistilledOutput.trimmed().isEmpty())
            readyVariants << QStringLiteral("Distilled");
        if (!item.ltxFullOutput.trimmed().isEmpty())
            readyVariants << QStringLiteral("Full");

        lines << QStringLiteral("LTX outputs ready: %1").arg(
            readyVariants.isEmpty() ? QStringLiteral("primary output") : readyVariants.join(QStringLiteral(" + ")));

        lines << QStringLiteral("Primary: %1").arg(primaryRole.left(1).toUpper() + primaryRole.mid(1).toLower());
        lines << QStringLiteral("Actions: Open Primary • Open Distilled • Open Full • Reveal Metadata • Reveal Folder");

        if (!item.videoDurationLabel.trimmed().isEmpty())
            lines << QStringLiteral("Duration: %1").arg(item.videoDurationLabel.trimmed());
'''

if needle not in text:
    raise SystemExit("Could not find LTX details insertion point in QueueUiPresenter.cpp")

text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")

print("Applied Sprint 15C Pass 29Q v4: compact LTX actions are visible at top of details summary.")
