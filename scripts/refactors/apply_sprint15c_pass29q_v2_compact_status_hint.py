from pathlib import Path

path = Path("qt_ui/QueueManager.cpp")
text = path.read_text(encoding="utf-8")

needle = '''    if (!item.ltxDualOutputActionsSummary.isEmpty())
    {
        if (item.statusText.trimmed().isEmpty())
            item.statusText = item.ltxDualOutputActionsSummary;
        else if (!item.statusText.contains(item.ltxDualOutputActionsSummary))
            item.statusText += QStringLiteral("\\n\\n") + item.ltxDualOutputActionsSummary;
    }
'''

replacement = '''    if (!item.ltxDualOutputActionsSummary.isEmpty())
    {
        if (item.statusText.trimmed().isEmpty())
            item.statusText = item.ltxDualOutputActionsSummary;
        else if (!item.statusText.contains(item.ltxDualOutputActionsSummary))
            item.statusText += QStringLiteral("\\n\\n") + item.ltxDualOutputActionsSummary;

        // Sprint 15C Pass 29Q v2:
        // Keep the table status compact but visibly signal that this completed LTX job
        // has action-ready Full/Distilled outputs in the row details/tooltips.
        if (item.state.trimmed().compare(QStringLiteral("completed"), Qt::CaseInsensitive) == 0)
        {
            const QString compactLtxActionStatus = QStringLiteral("completed — LTX outputs ready: primary, distilled, full, metadata");
            if (!item.statusText.startsWith(compactLtxActionStatus))
                item.statusText = compactLtxActionStatus + QStringLiteral("\\n\\n") + item.statusText;
        }
    }
'''

if needle not in text:
    raise SystemExit("Could not find Pass 29Q action summary status block in QueueManager.cpp")

text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")

print("Applied Sprint 15C Pass 29Q v2: compact queue status now advertises LTX output actions.")
