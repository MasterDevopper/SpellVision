from pathlib import Path

path = Path("qt_ui/MainWindow.cpp")
text = path.read_text(encoding="utf-8")

def replace_function(text: str, signature: str, replacement: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"Could not find function signature: {signature}")

    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"Could not find opening brace for: {signature}")

    depth = 0
    end = None
    in_string = False
    in_char = False
    escaped = False

    for index in range(brace, len(text)):
        ch = text[index]

        if escaped:
            escaped = False
            continue

        if ch == "\\":
            escaped = True
            continue

        if ch == '"' and not in_char:
            in_string = not in_string
            continue

        if ch == "'" and not in_string:
            in_char = not in_char
            continue

        if in_string or in_char:
            continue

        if ch == "{":
            depth += 1
            continue

        if ch == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break

    if end is None:
        raise SystemExit(f"Could not find closing brace for: {signature}")

    return text[:start] + replacement.rstrip() + "\n" + text[end:]


replacement = r'''
void MainWindow::syncGenerationPreviewsFromQueue()
{
    if (!queueManager_)
        return;

    if (!isGenerationWorkspaceMode())
        return;

    ImageGenerationPage *page = generationPageForMode(currentModeId_);
    if (!page)
        return;

    const QVector<QueueItem> &items = queueManager_->items();
    for (auto it = items.crbegin(); it != items.crend(); ++it)
    {
        const QueueItem &item = *it;
        const QString itemModeId = generationModeIdForQueueItem(item);
        if (itemModeId != currentModeId_)
            continue;

        // Pass 28B:
        // Active/running generation status is owned by direct worker messages.
        // Queue polling runs repeatedly and must not call setBusy(true), because
        // that causes the generation page to churn/re-layout while jobs are active.
        if (queueItemIsActiveForGeneration(item))
            return;

        if (item.completed && !item.outputPath.trimmed().isEmpty())
        {
            const QString normalizedPath = normalizedPreviewPathKey(item.outputPath);
            if (normalizedPath.isEmpty())
                continue;

            const QString jobKey = item.workerJobId.trimmed().isEmpty()
                ? item.id.trimmed()
                : item.workerJobId.trimmed();

            const QString stableKey = QStringLiteral("%1|%2|%3").arg(itemModeId, normalizedPath, jobKey);

            if (lastSyncedGenerationPreviewByMode_.value(itemModeId) != stableKey)
            {
                lastSyncedGenerationPreviewByMode_.insert(itemModeId, stableKey);

                const QString caption = item.statusText.trimmed().isEmpty()
                    ? QStringLiteral("Completed output")
                    : item.statusText.trimmed();

                page->setPreviewImage(item.outputPath, caption);
            }

            page->setBusy(false, QStringLiteral("Ready"));
            return;
        }

        if (item.failed || item.cancelled || item.isTerminal())
        {
            const QString message = item.errorText.trimmed().isEmpty()
                ? QStringLiteral("Ready")
                : item.errorText.trimmed();

            page->setBusy(false, message);
            return;
        }
    }
}
'''

text = replace_function(text, "void MainWindow::syncGenerationPreviewsFromQueue()", replacement)
path.write_text(text, encoding="utf-8")

print("Applied Pass 28B: queue polling no longer drives active generation busy UI.")
