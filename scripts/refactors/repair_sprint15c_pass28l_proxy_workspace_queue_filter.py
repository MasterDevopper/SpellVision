from pathlib import Path

proxy_h_path = Path("qt_ui/QueueFilterProxyModel.h")
proxy_cpp_path = Path("qt_ui/QueueFilterProxyModel.cpp")
main_cpp_path = Path("qt_ui/MainWindow.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass28l_proxy_workspace_queue_filter.py")

proxy_h = proxy_h_path.read_text(encoding="utf-8")
proxy_cpp = proxy_cpp_path.read_text(encoding="utf-8")
main_cpp = main_cpp_path.read_text(encoding="utf-8")


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
# 1) QueueFilterProxyModel: add command/workspace filtering.
# ----------------------------------------------------------------------

if "#include <QStringList>" not in proxy_h:
    proxy_h = proxy_h.replace("#include <QString>", "#include <QString>\n#include <QStringList>", 1)

if "void setCommandFilter" not in proxy_h:
    proxy_h = proxy_h.replace(
        "    void setStateFilter(const QString &state);\n",
        "    void setStateFilter(const QString &state);\n    void setCommandFilter(const QStringList &commands);\n",
        1,
    )

if "QStringList commandFilter_" not in proxy_h:
    proxy_h = proxy_h.replace(
        "    QString stateFilter_;\n",
        "    QString stateFilter_;\n    QStringList commandFilter_;\n",
        1,
    )

proxy_h_path.write_text(proxy_h, encoding="utf-8")


proxy_cpp = '''#include "QueueFilterProxyModel.h"
#include "QueueTableModel.h"

#include <QAbstractItemModel>

QueueFilterProxyModel::QueueFilterProxyModel(QObject *parent)
    : QSortFilterProxyModel(parent)
{
    setDynamicSortFilter(true);
}

void QueueFilterProxyModel::setTextFilter(const QString &text)
{
    const QString next = text.trimmed().toLower();
    if (textFilter_ == next)
        return;

    textFilter_ = next;
    invalidateFilter();
}

void QueueFilterProxyModel::setStateFilter(const QString &state)
{
    const QString next = state.trimmed().toLower();
    if (stateFilter_ == next)
        return;

    stateFilter_ = next;
    invalidateFilter();
}

void QueueFilterProxyModel::setCommandFilter(const QStringList &commands)
{
    QStringList normalized;
    normalized.reserve(commands.size());

    for (const QString &command : commands)
    {
        const QString value = command.trimmed().toLower();
        if (value.isEmpty())
            continue;

        if (!normalized.contains(value))
            normalized << value;
    }

    normalized.sort();

    if (commandFilter_ == normalized)
        return;

    commandFilter_ = normalized;
    invalidateFilter();
}

bool QueueFilterProxyModel::filterAcceptsRow(int sourceRow, const QModelIndex &sourceParent) const
{
    if (!sourceModel())
        return true;

    const QModelIndex stateIdx = sourceModel()->index(sourceRow, QueueTableModel::StateColumn, sourceParent);
    const QModelIndex cmdIdx = sourceModel()->index(sourceRow, QueueTableModel::CommandColumn, sourceParent);
    const QModelIndex promptIdx = sourceModel()->index(sourceRow, QueueTableModel::PromptColumn, sourceParent);
    const QModelIndex progressIdx = sourceModel()->index(sourceRow, QueueTableModel::ProgressColumn, sourceParent);
    const QModelIndex statusIdx = sourceModel()->index(sourceRow, QueueTableModel::StatusColumn, sourceParent);
    const QModelIndex idIdx = sourceModel()->index(sourceRow, QueueTableModel::QueueIdColumn, sourceParent);

    const QString stateText = sourceModel()->data(stateIdx, Qt::DisplayRole).toString().toLower();
    const QString commandText = sourceModel()->data(cmdIdx, Qt::DisplayRole).toString().trimmed().toLower();

    const bool commandMatch =
        commandFilter_.isEmpty() ||
        commandFilter_.contains(commandText);

    if (!commandMatch)
        return false;

    const QString rowText =
        commandText + " " +
        sourceModel()->data(promptIdx, Qt::DisplayRole).toString().toLower() + " " +
        sourceModel()->data(progressIdx, Qt::DisplayRole).toString().toLower() + " " +
        sourceModel()->data(statusIdx, Qt::DisplayRole).toString().toLower() + " " +
        sourceModel()->data(idIdx, Qt::DisplayRole).toString().toLower();

    const bool textMatch =
        textFilter_.isEmpty() || rowText.contains(textFilter_);

    const bool stateMatch =
        stateFilter_.isEmpty() ||
        stateFilter_ == "all states" ||
        stateText.contains(stateFilter_);

    return textMatch && stateMatch;
}
'''

proxy_cpp_path.write_text(proxy_cpp, encoding="utf-8")


# ----------------------------------------------------------------------
# 2) MainWindow: replace unsafe setRowHidden filtering with proxy filtering.
# ----------------------------------------------------------------------

if "#include <QStringList>" not in main_cpp:
    main_cpp = main_cpp.replace("#include <QString>", "#include <QString>\n#include <QStringList>", 1)

replacement = r'''
void MainWindow::applyQueuePresentationForCurrentMode()
{
    const bool videoMode = queueModeIsVideoWorkspace(currentModeId_);
    const bool imageMode = queueModeIsImageWorkspace(currentModeId_);

    QStringList acceptedCommands;

    if (currentModeId_ == QStringLiteral("t2i"))
        acceptedCommands = {QStringLiteral("t2i"), QStringLiteral("txt2img"), QStringLiteral("text_to_image")};
    else if (currentModeId_ == QStringLiteral("i2i"))
        acceptedCommands = {QStringLiteral("i2i"), QStringLiteral("img2img"), QStringLiteral("image_to_image")};
    else if (currentModeId_ == QStringLiteral("t2v"))
        acceptedCommands = {QStringLiteral("t2v"), QStringLiteral("text_to_video")};
    else if (currentModeId_ == QStringLiteral("i2v"))
        acceptedCommands = {QStringLiteral("i2v"), QStringLiteral("image_to_video")};

    // Pass 28L:
    // Workspace filtering belongs in the proxy model. Do not use
    // QTableView::setRowHidden() against a dynamic proxy model; that can race
    // model invalidation and trigger Qt QList index-out-of-range asserts.
    if (queueFilterProxyModel_)
        queueFilterProxyModel_->setCommandFilter(acceptedCommands);

    int visibleRows = 0;

    if (queueTableView_)
    {
        QAbstractItemModel *model = queueTableView_->model();
        visibleRows = model ? model->rowCount() : 0;

        queueTableView_->setUpdatesEnabled(false);

        const int columnCount = model ? model->columnCount() : QueueTableModel::ColumnCount;

        auto setColumnHiddenIfPresent = [&](int column, bool hidden) {
            if (column < 0 || column >= columnCount)
                return;

            queueTableView_->setColumnHidden(column, hidden);
        };

        auto setColumnWidthIfPresent = [&](int column, int width) {
            if (column < 0 || column >= columnCount)
                return;

            queueTableView_->setColumnWidth(column, width);
        };

        const QString geometryKey = QStringLiteral("%1|%2|%3")
            .arg(currentModeId_)
            .arg(columnCount)
            .arg(videoMode ? 1 : 0);

        const bool geometryChanged =
            queueTableView_->property("svQueueModeGeometryKey").toString() != geometryKey;

        if (geometryChanged)
        {
            queueTableView_->setProperty("svQueueModeGeometryKey", geometryKey);

            setColumnHiddenIfPresent(QueueTableModel::VideoColumn, !videoMode);

            queueTableView_->horizontalHeader()->setStretchLastSection(false);
            queueTableView_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
            queueTableView_->verticalHeader()->setDefaultSectionSize(28);
            queueTableView_->verticalHeader()->setMinimumSectionSize(28);
            queueTableView_->setWordWrap(false);
            queueTableView_->setTextElideMode(Qt::ElideRight);

            setColumnWidthIfPresent(QueueTableModel::StateColumn, 104);
            setColumnWidthIfPresent(QueueTableModel::CommandColumn, 76);
            setColumnWidthIfPresent(QueueTableModel::ProgressColumn, 96);
            setColumnWidthIfPresent(QueueTableModel::StatusColumn, imageMode ? 210 : 190);
            setColumnWidthIfPresent(QueueTableModel::QueueIdColumn, 150);
            setColumnWidthIfPresent(QueueTableModel::UpdatedAtColumn, 142);

            if (videoMode)
                setColumnWidthIfPresent(QueueTableModel::VideoColumn, 116);
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

    QWidget *activeStrip = findChild<QWidget *>(QStringLiteral("QueueActiveStrip"));
    if (!activeStrip)
        return;

    activeStrip->setFixedHeight(78);
    activeStrip->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    const QString title = QStringLiteral("%1 Queue").arg(currentModeId_.toUpper());
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
'''

main_cpp = replace_function(main_cpp, "void MainWindow::applyQueuePresentationForCurrentMode()", replacement)

main_cpp_path.write_text(main_cpp, encoding="utf-8")
script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Pass 28L: workspace queue filtering moved into QueueFilterProxyModel.")
