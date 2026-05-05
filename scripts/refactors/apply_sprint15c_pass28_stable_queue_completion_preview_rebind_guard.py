from pathlib import Path

root = Path(".")
queue_cpp_path = root / "qt_ui" / "QueueManager.cpp"
main_h_path = root / "qt_ui" / "MainWindow.h"
main_cpp_path = root / "qt_ui" / "MainWindow.cpp"
image_cpp_path = root / "qt_ui" / "ImageGenerationPage.cpp"
worker_queue_path = root / "qt_ui" / "workers" / "WorkerQueueController.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS28_STABLE_QUEUE_COMPLETION_PREVIEW_REBIND_GUARD_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass28_stable_queue_completion_preview_rebind_guard.py"

queue_cpp = queue_cpp_path.read_text(encoding="utf-8")
main_h = main_h_path.read_text(encoding="utf-8")
main_cpp = main_cpp_path.read_text(encoding="utf-8")
image_cpp = image_cpp_path.read_text(encoding="utf-8")
worker_queue = worker_queue_path.read_text(encoding="utf-8")


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


# ----------------------------------------------------------------------
# 1) QueueManager: stable queue identity + terminal timestamp jitter guard.
# ----------------------------------------------------------------------

if "#include <initializer_list>" not in queue_cpp:
    queue_cpp = queue_cpp.replace(
        "#include <QUuid>",
        "#include <QUuid>\n#include <initializer_list>",
        1,
    )

queue_helpers = r'''
    QString firstSnapshotText(const QJsonObject &primary,
                              const QJsonObject &secondary,
                              std::initializer_list<const char *> keys)
    {
        for (const char *rawKey : keys)
        {
            const QString key = QString::fromLatin1(rawKey);

            const QString fromPrimary = primary.value(key).toString().trimmed();
            if (!fromPrimary.isEmpty())
                return fromPrimary;

            const QString fromSecondary = secondary.value(key).toString().trimmed();
            if (!fromSecondary.isEmpty())
                return fromSecondary;
        }

        return QString();
    }

    bool terminalStateForSnapshotCompare(const QueueItem &item)
    {
        return item.state == QueueItemState::Completed ||
               item.state == QueueItemState::Failed ||
               item.state == QueueItemState::Cancelled ||
               item.state == QueueItemState::Skipped ||
               item.completed ||
               item.failed ||
               item.cancelled;
    }

    bool sameQueueItemIgnoringTerminalTimestampJitter(const QueueItem &oldItem,
                                                      const QueueItem &newItem)
    {
        if (!terminalStateForSnapshotCompare(oldItem) || !terminalStateForSnapshotCompare(newItem))
            return false;

        return oldItem.id == newItem.id &&
               oldItem.command == newItem.command &&
               oldItem.prompt == newItem.prompt &&
               oldItem.model == newItem.model &&
               oldItem.outputPath == newItem.outputPath &&
               oldItem.metadataPath == newItem.metadataPath &&
               oldItem.workerJobId == newItem.workerJobId &&
               oldItem.sourceJobId == newItem.sourceJobId &&
               oldItem.statusText == newItem.statusText &&
               oldItem.errorText == newItem.errorText &&
               oldItem.mediaType == newItem.mediaType &&
               oldItem.videoFamily == newItem.videoFamily &&
               oldItem.videoBackendType == newItem.videoBackendType &&
               oldItem.videoBackendName == newItem.videoBackendName &&
               oldItem.videoDurationLabel == newItem.videoDurationLabel &&
               oldItem.videoResolution == newItem.videoResolution &&
               oldItem.videoStackSummary == newItem.videoStackSummary &&
               oldItem.runtimeTransition == newItem.runtimeTransition &&
               oldItem.runtimeTarget == newItem.runtimeTarget &&
               oldItem.runtimePrevious == newItem.runtimePrevious &&
               oldItem.steps == newItem.steps &&
               oldItem.currentStep == newItem.currentStep &&
               oldItem.priority == newItem.priority &&
               oldItem.orderIndex == newItem.orderIndex &&
               oldItem.retryCount == newItem.retryCount &&
               oldItem.running == newItem.running &&
               oldItem.completed == newItem.completed &&
               oldItem.failed == newItem.failed &&
               oldItem.cancelled == newItem.cancelled &&
               oldItem.warmReuseCandidate == newItem.warmReuseCandidate &&
               oldItem.state == newItem.state;
    }

'''

if "firstSnapshotText" not in queue_cpp:
    queue_cpp = queue_cpp.replace("namespace\n{\n", "namespace\n{\n" + queue_helpers, 1)

old_queue_id = '''    item.id = obj.value(QStringLiteral("queue_item_id")).toString().trimmed();
    item.command = obj.value(QStringLiteral("command")).toString().trimmed();
    item.prompt = obj.value(QStringLiteral("prompt")).toString();
    item.model = obj.value(QStringLiteral("model")).toString();

    const QJsonObject result = obj.value(QStringLiteral("result")).toObject();'''

new_queue_id = '''    const QJsonObject result = obj.value(QStringLiteral("result")).toObject();

    item.id = firstSnapshotText(obj, result, {"queue_item_id", "id", "job_id", "worker_job_id", "source_job_id"});
    item.command = obj.value(QStringLiteral("command")).toString().trimmed();
    item.prompt = obj.value(QStringLiteral("prompt")).toString();
    item.model = obj.value(QStringLiteral("model")).toString();'''

if old_queue_id not in queue_cpp and "firstSnapshotText(obj, result" not in queue_cpp:
    raise SystemExit("Could not patch QueueManager queue identity block.")

if old_queue_id in queue_cpp:
    queue_cpp = queue_cpp.replace(old_queue_id, new_queue_id, 1)

old_timestamp = '''    item.updatedAt = parseIsoDateTime(timestamps.value(QStringLiteral("updated_at")));

    return item;'''

new_timestamp = '''    item.updatedAt = parseIsoDateTime(timestamps.value(QStringLiteral("updated_at")));

    // Pass 28: terminal queue snapshots can be replayed with updated_at jitter.
    // Keep terminal timestamps stable so polling does not cause repeated queueChanged
    // emissions and preview rebinding.
    if (item.isTerminal())
    {
        if (item.finishedAt.isValid())
            item.updatedAt = item.finishedAt;
        else if (item.startedAt.isValid())
            item.updatedAt = item.startedAt;
        else if (item.createdAt.isValid())
            item.updatedAt = item.createdAt;
    }

    return item;'''

if old_timestamp not in queue_cpp and "terminal queue snapshots can be replayed" not in queue_cpp:
    raise SystemExit("Could not patch QueueManager terminal timestamp block.")

if old_timestamp in queue_cpp:
    queue_cpp = queue_cpp.replace(old_timestamp, new_timestamp, 1)

old_compare = '''            if (oldItem.id != newItem.id ||
                oldItem.command != newItem.command ||'''

new_compare = '''            if (sameQueueItemIgnoringTerminalTimestampJitter(oldItem, newItem))
                continue;

            if (oldItem.id != newItem.id ||
                oldItem.command != newItem.command ||'''

if old_compare not in queue_cpp and "sameQueueItemIgnoringTerminalTimestampJitter(oldItem, newItem)" not in queue_cpp:
    raise SystemExit("Could not patch QueueManager comparison block.")

if old_compare in queue_cpp:
    queue_cpp = queue_cpp.replace(old_compare, new_compare, 1)

queue_cpp_path.write_text(queue_cpp, encoding="utf-8")


# ----------------------------------------------------------------------
# 2) WorkerQueueController: ensure LTX registry items expose queue_item_id.
# ----------------------------------------------------------------------

old_ltx_id = '''    out.insert(QStringLiteral("id"), id.isEmpty() ? QStringLiteral("ltx-registry-%1").arg(orderIndex) : id);
    out.insert(QStringLiteral("job_id"), firstString(item, {"prompt_id"}));'''

new_ltx_id = '''    const QString stableId = id.isEmpty() ? QStringLiteral("ltx-registry-%1").arg(orderIndex) : id;
    out.insert(QStringLiteral("id"), stableId);
    out.insert(QStringLiteral("queue_item_id"), stableId);
    out.insert(QStringLiteral("job_id"), firstString(item, {"prompt_id"}));'''

if old_ltx_id in worker_queue:
    worker_queue = worker_queue.replace(old_ltx_id, new_ltx_id, 1)
elif "queue_item_id" not in worker_queue:
    raise SystemExit("Could not patch LTX registry queue item id block.")

worker_queue_path.write_text(worker_queue, encoding="utf-8")


# ----------------------------------------------------------------------
# 3) MainWindow: stop hidden-page preview rebinding and dedupe visible preview sync.
# ----------------------------------------------------------------------

if "lastSyncedGenerationPreviewByMode_" not in main_h:
    main_h = main_h.replace(
        "    QMap<QString, QWidget *> modePages_;",
        "    QMap<QString, QWidget *> modePages_;\n    QMap<QString, QString> lastSyncedGenerationPreviewByMode_;",
        1,
    )

main_h_path.write_text(main_h, encoding="utf-8")

main_helpers = r'''
    QString generationModeIdForQueueItem(const QueueItem &item)
    {
        const QString command = item.command.trimmed().toLower();
        const QString mediaType = item.mediaType.trimmed().toLower();

        if (command == QStringLiteral("t2i") || command == QStringLiteral("txt2img") || command == QStringLiteral("text_to_image"))
            return QStringLiteral("t2i");
        if (command == QStringLiteral("i2i") || command == QStringLiteral("img2img") || command == QStringLiteral("image_to_image"))
            return QStringLiteral("i2i");
        if (command == QStringLiteral("t2v") || command == QStringLiteral("text_to_video"))
            return QStringLiteral("t2v");
        if (command == QStringLiteral("i2v") || command == QStringLiteral("image_to_video"))
            return QStringLiteral("i2v");
        if (mediaType == QStringLiteral("video"))
            return QStringLiteral("t2v");
        if (mediaType == QStringLiteral("image"))
            return QStringLiteral("t2i");

        return {};
    }

    QString normalizedPreviewPathKey(const QString &path)
    {
        const QString trimmed = path.trimmed();
        if (trimmed.isEmpty())
            return {};

        return QDir::fromNativeSeparators(QFileInfo(trimmed).absoluteFilePath()).toLower();
    }

    bool queueItemIsActiveForGeneration(const QueueItem &item)
    {
        return item.state == QueueItemState::Queued ||
               item.state == QueueItemState::Preparing ||
               item.state == QueueItemState::Running ||
               item.running;
    }

'''

if "generationModeIdForQueueItem" not in main_cpp:
    main_cpp = main_cpp.replace("namespace\n{\n", "namespace\n{\n" + main_helpers, 1)

sync_impl = r'''
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

        if (queueItemIsActiveForGeneration(item))
        {
            const QString message = item.statusText.trimmed().isEmpty()
                ? QStringLiteral("Generation running…")
                : item.statusText.trimmed();

            page->setBusy(true, message);
            return;
        }

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

main_cpp = replace_function(main_cpp, "void MainWindow::syncGenerationPreviewsFromQueue()", sync_impl)
main_cpp_path.write_text(main_cpp, encoding="utf-8")


# ----------------------------------------------------------------------
# 4) ImageGenerationPage: hard recovery from terminal worker messages.
# ----------------------------------------------------------------------

set_busy_sig = "void ImageGenerationPage::setBusy(bool busy, const QString &message)\n{\n"
if set_busy_sig not in image_cpp:
    raise SystemExit("Could not find ImageGenerationPage::setBusy.")

if "Pass 28: clearing busy must also release stale submit locks" not in image_cpp:
    image_cpp = image_cpp.replace(
        set_busy_sig,
        set_busy_sig +
        '''    // Pass 28: clearing busy must also release stale submit locks from a prior terminal job.
    if (!busy)
    {
        generateSubmitLocked_ = false;
        busyMessage_.clear();
    }

''',
        1,
    )

apply_sig = "void ImageGenerationPage::applyWorkerMessage(const QJsonObject &payload)\n{\n"
if apply_sig not in image_cpp:
    raise SystemExit("Could not find ImageGenerationPage::applyWorkerMessage.")

if "terminalWorkerMessage" not in image_cpp:
    terminal_guard = r'''    const QString workerType = payload.value(QStringLiteral("type")).toString().trimmed().toLower();
    const QString workerState = payload.value(QStringLiteral("state")).toString().trimmed().toLower();
    const bool terminalWorkerMessage =
        workerState == QStringLiteral("completed") ||
        workerState == QStringLiteral("failed") ||
        workerState == QStringLiteral("cancelled") ||
        workerState == QStringLiteral("canceled") ||
        workerType == QStringLiteral("result") ||
        workerType == QStringLiteral("error") ||
        workerType == QStringLiteral("client_error");

    if (terminalWorkerMessage)
    {
        busy_ = false;
        busyMessage_.clear();
        generateSubmitLocked_ = false;
    }

'''
    image_cpp = image_cpp.replace(apply_sig, apply_sig + terminal_guard, 1)

    image_cpp = replace_function(
        image_cpp,
        "void ImageGenerationPage::applyWorkerMessage(const QJsonObject &payload)",
        image_cpp[image_cpp.find("void ImageGenerationPage::applyWorkerMessage(const QJsonObject &payload)"):
                  image_cpp.find("void ImageGenerationPage::setWorkspaceTelemetry", image_cpp.find("void ImageGenerationPage::applyWorkerMessage(const QJsonObject &payload)"))].rstrip()
        + r'''

    // Pass 28 terminal safety repaint: terminal worker messages must always
    // leave the page able to submit the next generation.
    if (terminalWorkerMessage)
        updatePrimaryActionAvailability();
}
'''
    )

image_cpp_path.write_text(image_cpp, encoding="utf-8")


# ----------------------------------------------------------------------
# 5) Docs + script copy.
# ----------------------------------------------------------------------

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    "# Sprint 15C Pass 28 — Stable Queue Completion and Preview Rebind Guard\n\n"
    "Fixes post-completion state instability after successful T2I jobs.\n\n"
    "Files changed:\n\n"
    "- `qt_ui/QueueManager.cpp`\n"
    "- `qt_ui/workers/WorkerQueueController.cpp`\n"
    "- `qt_ui/MainWindow.cpp`\n"
    "- `qt_ui/MainWindow.h`\n"
    "- `qt_ui/ImageGenerationPage.cpp`\n\n"
    "Fixes:\n\n"
    "- Queue item identity now falls back to `id`, `job_id`, `worker_job_id`, and `source_job_id` when `queue_item_id` is missing.\n"
    "- LTX registry queue items now publish `queue_item_id` directly.\n"
    "- Completed/failed/cancelled queue items normalize terminal `updatedAt` so polling timestamp jitter does not retrigger preview sync.\n"
    "- Terminal queue comparison ignores timestamp-only jitter.\n"
    "- `MainWindow::syncGenerationPreviewsFromQueue()` now only updates the currently visible generation workspace.\n"
    "- Preview binding is deduplicated by mode/output/job key.\n"
    "- `ImageGenerationPage` clears stale busy/submit-lock state on terminal worker messages and on `setBusy(false)`.\n\n"
    "Expected runtime behavior:\n\n"
    "- First T2I generation completes.\n"
    "- Preview updates once.\n"
    "- Generate becomes available again.\n"
    "- Second T2I generation can start without restarting SpellVision.\n",
    encoding="utf-8",
)

script_path.parent.mkdir(parents=True, exist_ok=True)
script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 28 stable queue completion and preview rebind guard.")
