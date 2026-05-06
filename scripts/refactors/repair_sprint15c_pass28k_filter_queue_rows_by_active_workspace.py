from pathlib import Path

main_cpp_path = Path("qt_ui/MainWindow.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass28k_filter_queue_rows_by_active_workspace.py")

text = main_cpp_path.read_text(encoding="utf-8")


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


if "#include <QAbstractItemModel>" not in text:
    text = text.replace("#include <QAction>", "#include <QAbstractItemModel>\n#include <QAction>", 1)

if "#include <QLabel>" not in text:
    text = text.replace("#include <QKeySequence>", "#include <QKeySequence>\n#include <QLabel>", 1)


replacement = r'''
void MainWindow::applyQueuePresentationForCurrentMode()
{
    const bool videoMode = queueModeIsVideoWorkspace(currentModeId_);
    const bool imageMode = queueModeIsImageWorkspace(currentModeId_);

    int visibleRows = 0;
    QString commandKey;

    if (queueTableView_)
    {
        QAbstractItemModel *model = queueTableView_->model();
        const int rowCount = model ? model->rowCount() : 0;

        QStringList rowCommands;
        rowCommands.reserve(rowCount);

        for (int row = 0; row < rowCount; ++row)
        {
            const QModelIndex commandIndex = model->index(row, QueueTableModel::CommandColumn);
            rowCommands << model->data(commandIndex, Qt::DisplayRole).toString().trimmed().toLower();
        }

        commandKey = QStringLiteral("%1|%2|%3")
            .arg(currentModeId_)
            .arg(rowCount)
            .arg(rowCommands.join(QStringLiteral(",")));

        const bool geometryKeyChanged =
            queueTableView_->property("svQueueModeGeometryKey").toString() != commandKey;

        queueTableView_->setUpdatesEnabled(false);

        // Pass 28K:
        // The queue table is global, but the visible tray should be scoped to
        // the active workspace. Otherwise old LTX/T2V retained rows dominate
        // T2I and make the image page look video-oriented.
        for (int row = 0; row < rowCount; ++row)
        {
            const QString command = rowCommands.value(row);
            bool rowMatchesMode = true;

            if (imageMode || videoMode)
            {
                rowMatchesMode =
                    command == currentModeId_ ||
                    (currentModeId_ == QStringLiteral("t2i") &&
                        (command == QStringLiteral("txt2img") || command == QStringLiteral("text_to_image"))) ||
                    (currentModeId_ == QStringLiteral("i2i") &&
                        (command == QStringLiteral("img2img") || command == QStringLiteral("image_to_image"))) ||
                    (currentModeId_ == QStringLiteral("t2v") &&
                        command == QStringLiteral("text_to_video")) ||
                    (currentModeId_ == QStringLiteral("i2v") &&
                        command == QStringLiteral("image_to_video"));
            }

            const bool hide = !rowMatchesMode;
            if (queueTableView_->isRowHidden(row) != hide)
                queueTableView_->setRowHidden(row, hide);

            if (!hide)
                ++visibleRows;
        }

        if (geometryKeyChanged)
        {
            queueTableView_->setProperty("svQueueModeGeometryKey", commandKey);

            queueTableView_->setColumnHidden(QueueTableModel::VideoColumn, !videoMode);
            queueTableView_->horizontalHeader()->setStretchLastSection(false);
            queueTableView_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
            queueTableView_->verticalHeader()->setDefaultSectionSize(28);
            queueTableView_->verticalHeader()->setMinimumSectionSize(28);
            queueTableView_->setWordWrap(false);
            queueTableView_->setTextElideMode(Qt::ElideRight);

            queueTableView_->setColumnWidth(QueueTableModel::StateColumn, 104);
            queueTableView_->setColumnWidth(QueueTableModel::CommandColumn, 76);
            queueTableView_->setColumnWidth(QueueTableModel::ProgressColumn, 96);
            queueTableView_->setColumnWidth(QueueTableModel::StatusColumn, imageMode ? 210 : 190);
            queueTableView_->setColumnWidth(QueueTableModel::QueueIdColumn, 150);
            queueTableView_->setColumnWidth(QueueTableModel::UpdatedAtColumn, 142);

            if (videoMode)
                queueTableView_->setColumnWidth(QueueTableModel::VideoColumn, 116);
        }

        queueTableView_->setUpdatesEnabled(true);
    }

    if (queueSearchEdit_)
    {
        queueSearchEdit_->setPlaceholderText(videoMode
            ? QStringLiteral("Search video queue by prompt, model, or state")
            : QStringLiteral("Search image queue by prompt, model, or state"));
    }

    if (bottomQueueLabel_)
    {
        bottomQueueLabel_->setText(QStringLiteral("Queue: %1").arg(visibleRows));
        bottomQueueLabel_->setMinimumWidth(92);
        bottomQueueLabel_->setMaximumWidth(92);
        bottomQueueLabel_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
    }

    // Pass 28K:
    // Replace the old dynamic active-queue strip with a stable, mode-aware
    // summary. updateActiveQueueStrip() was selecting retained T2V rows and
    // rewriting wrapped labels every poll, causing bottom-tray breathing.
    QWidget *activeStrip = findChild<QWidget *>(QStringLiteral("QueueActiveStrip"));
    if (activeStrip)
    {
        activeStrip->setFixedHeight(78);
        activeStrip->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

        const QString title = videoMode
            ? QStringLiteral("%1 Queue").arg(currentModeId_.toUpper())
            : QStringLiteral("%1 Queue").arg(currentModeId_.toUpper());

        const QString summary = videoMode
            ? QStringLiteral("%1 video job(s) visible for this workspace.").arg(visibleRows)
            : QStringLiteral("%1 image job(s) visible for this workspace.").arg(visibleRows);

        const QList<QLabel *> labels = activeStrip->findChildren<QLabel *>();
        for (QLabel *label : labels)
        {
            if (!label)
                continue;

            label->setWordWrap(false);
            label->setTextInteractionFlags(Qt::NoTextInteraction);
            label->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

            const QString objectName = label->objectName().toLower();
            const QString currentText = label->text();

            if (objectName.contains(QStringLiteral("body")) ||
                objectName.contains(QStringLiteral("summary")) ||
                currentText.contains(QStringLiteral("Recent ")) ||
                currentText.contains(QStringLiteral("visible for this workspace")))
            {
                label->setFixedHeight(22);
                label->setText(summary);
                continue;
            }

            if (objectName.contains(QStringLiteral("title")) ||
                objectName.contains(QStringLiteral("headline")) ||
                currentText.contains(QStringLiteral("•")) ||
                currentText.contains(QStringLiteral("Completed")) ||
                currentText.contains(QStringLiteral("Running")) ||
                currentText.contains(QStringLiteral("Pending")))
            {
                label->setFixedHeight(28);
                label->setText(title);
            }
        }
    }
}
'''

text = replace_function(text, "void MainWindow::applyQueuePresentationForCurrentMode()", replacement)


on_queue_changed = r'''
void MainWindow::onQueueChanged()
{
    syncBottomTelemetry();

    // Pass 28K:
    // Do not call updateActiveQueueStrip() here. It scans the global queue and
    // can pick retained T2V/LTX rows while the user is on T2I, then rewrites
    // wrapped labels every poll. applyQueuePresentationForCurrentMode() now owns
    // the stable, mode-filtered queue strip.
    applyQueuePresentationForCurrentMode();

    const bool expanded = queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;
    const QString selectedId = selectedQueueId();

    const QString detailsKey = QStringLiteral("%1|%2")
        .arg(expanded ? QStringLiteral("expanded") : QStringLiteral("collapsed"), selectedId);

    if (property("svQueueDetailsKey").toString() != detailsKey)
    {
        setProperty("svQueueDetailsKey", detailsKey);
        updateDetailsPanelForQueueSelection();
    }

    const QString chromeKey = QStringLiteral("%1|%2|%3")
        .arg(queueDockUserExpanded_ ? 1 : 0)
        .arg(bottomUtilityUserExpanded_ ? 1 : 0)
        .arg(detailsDockPinnedOpen_ ? 1 : 0);

    if (property("svQueueChromeKey").toString() != chromeKey)
    {
        setProperty("svQueueChromeKey", chromeKey);
        updateDockChrome();
    }

    if (queueTableView_)
        queueTableView_->viewport()->update();
}
'''

text = replace_function(text, "void MainWindow::onQueueChanged()", on_queue_changed)

main_cpp_path.write_text(text, encoding="utf-8")
script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Pass 28K: queue rows are filtered by active workspace and bottom strip geometry is stable.")
