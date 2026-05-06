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

    // Pass 28D:
    // Queue polling is a discovery/fallback path only. It must not continuously
    // mutate the visible generation page, because repeated setBusy()/preview
    // writes can cause splitter/layout breathing while the user is working.
    //
    // Direct worker messages own active progress and normal terminal busy
    // recovery. Queue sync only binds a newly discovered completed output once.
    const QueueItem *newestCompleted = nullptr;
    qint64 newestSortKey = (std::numeric_limits<qint64>::min)();

    for (const QueueItem &item : items)
    {
        const QString itemModeId = generationModeIdForQueueItem(item);
        if (itemModeId != currentModeId_)
            continue;

        if (queueItemIsActiveForGeneration(item))
            continue;

        if (!item.completed || item.outputPath.trimmed().isEmpty())
            continue;

        const QString normalizedPath = normalizedPreviewPathKey(item.outputPath);
        if (normalizedPath.isEmpty())
            continue;

        const QFileInfo outputInfo(item.outputPath.trimmed());
        if (!outputInfo.exists())
            continue;

        const qint64 sortKey = queueItemPreviewSortKey(item);
        if (!newestCompleted || sortKey > newestSortKey ||
            (sortKey == newestSortKey && item.orderIndex > newestCompleted->orderIndex))
        {
            newestCompleted = &item;
            newestSortKey = sortKey;
        }
    }

    if (!newestCompleted)
        return;

    const QString normalizedPath = normalizedPreviewPathKey(newestCompleted->outputPath);
    const QString jobKey = newestCompleted->workerJobId.trimmed().isEmpty()
        ? newestCompleted->id.trimmed()
        : newestCompleted->workerJobId.trimmed();

    const QString stableKey = QStringLiteral("%1|%2|%3|%4")
        .arg(currentModeId_,
             normalizedPath,
             jobKey,
             previewFileRevisionKey(newestCompleted->outputPath));

    if (lastSyncedGenerationPreviewByMode_.value(currentModeId_) == stableKey)
        return;

    lastSyncedGenerationPreviewByMode_.insert(currentModeId_, stableKey);

    const QString caption = newestCompleted->statusText.trimmed().isEmpty()
        ? QStringLiteral("Completed output")
        : newestCompleted->statusText.trimmed();

    page->setPreviewImage(newestCompleted->outputPath, caption);

    // One terminal recovery write is acceptable when a genuinely new completed
    // output appears. Repeated queue polls now return above without touching UI.
    page->setBusy(false, QStringLiteral("Ready"));
}
'''

text = replace_function(text, "void MainWindow::syncGenerationPreviewsFromQueue()", replacement)
path.write_text(text, encoding="utf-8")

print("Applied Pass 28D: queue preview polling no longer repeatedly reshapes generation page.")
