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


helper = r'''
    qint64 queueItemPreviewSortKey(const QueueItem &item)
    {
        if (item.finishedAt.isValid())
            return item.finishedAt.toMSecsSinceEpoch();

        if (item.updatedAt.isValid())
            return item.updatedAt.toMSecsSinceEpoch();

        if (item.startedAt.isValid())
            return item.startedAt.toMSecsSinceEpoch();

        if (item.createdAt.isValid())
            return item.createdAt.toMSecsSinceEpoch();

        return static_cast<qint64>(item.orderIndex);
    }

    QString previewFileRevisionKey(const QString &path)
    {
        const QFileInfo info(path.trimmed());
        if (!info.exists())
            return QStringLiteral("missing");

        return QStringLiteral("%1:%2")
            .arg(info.lastModified().toUTC().toMSecsSinceEpoch())
            .arg(info.size());
    }

'''

if "queueItemPreviewSortKey" not in text:
    marker = "    bool queueItemIsActiveForGeneration(const QueueItem &item)\n    {\n"
    marker_index = text.find(marker)
    if marker_index < 0:
        raise SystemExit("Could not find queueItemIsActiveForGeneration helper marker.")

    # Insert helper after the queueItemIsActiveForGeneration function.
    brace = text.find("{", marker_index)
    depth = 0
    end = None
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break

    if end is None:
        raise SystemExit("Could not find queueItemIsActiveForGeneration helper end.")

    text = text[:end] + "\n" + helper + text[end:]


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

    // Pass 28C:
    // Queue order is not a reliable proxy for newest output. Scan all queue
    // items for the active generation mode and choose the newest completed
    // output by terminal timestamps. This prevents the first completed output
    // from permanently winning the preview surface.
    const QueueItem *newestCompleted = nullptr;
    qint64 newestSortKey = std::numeric_limits<qint64>::min();

    for (const QueueItem &item : items)
    {
        const QString itemModeId = generationModeIdForQueueItem(item);
        if (itemModeId != currentModeId_)
            continue;

        // Active/running status is owned by direct worker messages. Do not
        // call setBusy(true) from queue polling.
        if (queueItemIsActiveForGeneration(item))
            continue;

        if (!item.completed || item.outputPath.trimmed().isEmpty())
            continue;

        const QString normalizedPath = normalizedPreviewPathKey(item.outputPath);
        if (normalizedPath.isEmpty())
            continue;

        const qint64 sortKey = queueItemPreviewSortKey(item);
        if (!newestCompleted || sortKey > newestSortKey ||
            (sortKey == newestSortKey && item.orderIndex > newestCompleted->orderIndex))
        {
            newestCompleted = &item;
            newestSortKey = sortKey;
        }
    }

    if (newestCompleted)
    {
        const QString normalizedPath = normalizedPreviewPathKey(newestCompleted->outputPath);
        const QString jobKey = newestCompleted->workerJobId.trimmed().isEmpty()
            ? newestCompleted->id.trimmed()
            : newestCompleted->workerJobId.trimmed();

        const QString stableKey = QStringLiteral("%1|%2|%3|%4")
            .arg(currentModeId_,
                 normalizedPath,
                 jobKey,
                 previewFileRevisionKey(newestCompleted->outputPath));

        if (lastSyncedGenerationPreviewByMode_.value(currentModeId_) != stableKey)
        {
            lastSyncedGenerationPreviewByMode_.insert(currentModeId_, stableKey);

            const QString caption = newestCompleted->statusText.trimmed().isEmpty()
                ? QStringLiteral("Completed output")
                : newestCompleted->statusText.trimmed();

            page->setPreviewImage(newestCompleted->outputPath, caption);
        }

        page->setBusy(false, QStringLiteral("Ready"));
        return;
    }

    for (const QueueItem &item : items)
    {
        const QString itemModeId = generationModeIdForQueueItem(item);
        if (itemModeId != currentModeId_)
            continue;

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

print("Applied Pass 28C: preview sync now chooses newest completed output instead of first match.")
