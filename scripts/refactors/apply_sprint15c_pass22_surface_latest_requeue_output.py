from pathlib import Path
import re

root = Path(".")
h_path = root / "qt_ui" / "T2VHistoryPage.h"
cpp_path = root / "qt_ui" / "T2VHistoryPage.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS22_SURFACE_LATEST_REQUEUE_OUTPUT_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass22_surface_latest_requeue_output.py"

h = h_path.read_text(encoding="utf-8")
cpp = cpp_path.read_text(encoding="utf-8")

# Header declarations.
if "focusLatestLtxRequeueOutputAfterRefresh" not in h:
    h = h.replace(
        "    void scheduleRefreshAfterLtxRequeueSubmit(const QJsonObject &response);\n",
        "    void scheduleRefreshAfterLtxRequeueSubmit(const QJsonObject &response);\n"
        "    void focusLatestLtxRequeueOutputAfterRefresh();\n",
        1,
    )

if "pendingLtxRequeuePromptId_" not in h:
    h = h.replace(
        "    QString validatedRequeueDraftPath_;\n",
        "    QString validatedRequeueDraftPath_;\n"
        "    QString pendingLtxRequeuePromptId_;\n"
        "    QString pendingLtxRequeuePrimaryOutputPath_;\n",
        1,
    )

h_path.write_text(h, encoding="utf-8")

# Includes needed for generic table focusing.
for include in [
    "#include <QAbstractItemModel>",
    "#include <QItemSelectionModel>",
    "#include <QTableView>",
    "#include <QTableWidget>",
]:
    if include not in cpp:
        cpp = cpp.replace("#include <QTimer>", "#include <QTimer>\n" + include, 1)

# Add a small helper for searching any visible table-like model text.
helpers = r'''
bool rowContainsNeedle(const QAbstractItemModel *model, int row, const QStringList &needles)
{
    if (!model || row < 0)
        return false;

    for (int column = 0; column < model->columnCount(); ++column)
    {
        const QString value = model->index(row, column).data(Qt::DisplayRole).toString();

        for (const QString &needle : needles)
        {
            if (needle.isEmpty())
                continue;

            if (value.contains(needle, Qt::CaseInsensitive))
                return true;
        }
    }

    return false;
}

QString fileNameFromPathText(const QString &pathText)
{
    if (pathText.isEmpty())
        return {};

    return QFileInfo(pathText).fileName();
}

'''

if "bool rowContainsNeedle(const QAbstractItemModel *model" not in cpp:
    namespace_match = re.search(r"namespace\s*\{", cpp)
    if not namespace_match:
        raise SystemExit("Could not find anonymous namespace in T2VHistoryPage.cpp.")
    cpp = cpp[:namespace_match.end()] + "\n" + helpers + cpp[namespace_match.end():]

# Replace/upgrade scheduleRefreshAfterLtxRequeueSubmit to remember pending output and focus after refresh.
old_schedule = re.search(
    r'void T2VHistoryPage::scheduleRefreshAfterLtxRequeueSubmit\(const QJsonObject &response\)\s*\{.*?\n\}\n',
    cpp,
    flags=re.DOTALL,
)

if not old_schedule:
    raise SystemExit("Could not find scheduleRefreshAfterLtxRequeueSubmit implementation.")

new_schedule = r'''void T2VHistoryPage::scheduleRefreshAfterLtxRequeueSubmit(const QJsonObject &response)
{
    const QString promptId = response.value(QStringLiteral("prompt_id")).toString();

    QString primaryOutputPath;
    const QJsonObject primaryOutput = response.value(QStringLiteral("primary_output")).toObject();
    if (!primaryOutput.isEmpty())
        primaryOutputPath = primaryOutput.value(QStringLiteral("path")).toString();

    if (primaryOutputPath.isEmpty())
    {
        const QJsonObject spellvisionResult = response.value(QStringLiteral("spellvision_result")).toObject();
        const QJsonObject resultPrimaryOutput = spellvisionResult.value(QStringLiteral("primary_output")).toObject();
        primaryOutputPath = resultPrimaryOutput.value(QStringLiteral("path")).toString();
    }

    pendingLtxRequeuePromptId_ = promptId;
    pendingLtxRequeuePrimaryOutputPath_ = primaryOutputPath;

    emit ltxRequeueSubmitted(promptId, primaryOutputPath);

    auto clickRefreshButton = [this]()
    {
        const QList<QPushButton *> buttons = findChildren<QPushButton *>();
        for (QPushButton *button : buttons)
        {
            if (!button)
                continue;

            if (button->text().compare(QStringLiteral("Refresh"), Qt::CaseInsensitive) == 0)
            {
                button->click();
                return;
            }
        }
    };

    QTimer::singleShot(250, this, clickRefreshButton);
    QTimer::singleShot(1500, this, clickRefreshButton);
    QTimer::singleShot(2200, this, &T2VHistoryPage::focusLatestLtxRequeueOutputAfterRefresh);
    QTimer::singleShot(3200, this, &T2VHistoryPage::focusLatestLtxRequeueOutputAfterRefresh);
}
'''

cpp = cpp[:old_schedule.start()] + new_schedule + cpp[old_schedule.end():]

# Add focus implementation before scheduleRefresh if not present.
focus_impl = r'''
void T2VHistoryPage::focusLatestLtxRequeueOutputAfterRefresh()
{
    if (pendingLtxRequeuePromptId_.isEmpty() && pendingLtxRequeuePrimaryOutputPath_.isEmpty())
        return;

    QStringList needles;
    needles << pendingLtxRequeuePromptId_;
    needles << pendingLtxRequeuePrimaryOutputPath_;
    needles << fileNameFromPathText(pendingLtxRequeuePrimaryOutputPath_);

    for (QTableWidget *table : findChildren<QTableWidget *>())
    {
        if (!table)
            continue;

        for (int row = 0; row < table->rowCount(); ++row)
        {
            bool matched = false;
            for (int column = 0; column < table->columnCount() && !matched; ++column)
            {
                const QTableWidgetItem *item = table->item(row, column);
                if (!item)
                    continue;

                const QString value = item->text();
                for (const QString &needle : needles)
                {
                    if (!needle.isEmpty() && value.contains(needle, Qt::CaseInsensitive))
                    {
                        matched = true;
                        break;
                    }
                }
            }

            if (!matched)
                continue;

            table->setCurrentCell(row, 0);
            table->selectRow(row);
            table->scrollToItem(table->item(row, 0), QAbstractItemView::PositionAtCenter);
            pendingLtxRequeuePromptId_.clear();
            pendingLtxRequeuePrimaryOutputPath_.clear();
            return;
        }
    }

    for (QTableView *view : findChildren<QTableView *>())
    {
        if (!view || !view->model())
            continue;

        QAbstractItemModel *model = view->model();
        for (int row = 0; row < model->rowCount(); ++row)
        {
            if (!rowContainsNeedle(model, row, needles))
                continue;

            const QModelIndex index = model->index(row, 0);
            view->setCurrentIndex(index);
            if (view->selectionModel())
                view->selectionModel()->select(index, QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
            view->scrollTo(index, QAbstractItemView::PositionAtCenter);
            pendingLtxRequeuePromptId_.clear();
            pendingLtxRequeuePrimaryOutputPath_.clear();
            return;
        }
    }
}

'''

if "void T2VHistoryPage::focusLatestLtxRequeueOutputAfterRefresh()" not in cpp:
    anchor = "void T2VHistoryPage::scheduleRefreshAfterLtxRequeueSubmit"
    index = cpp.find(anchor)
    if index < 0:
        raise SystemExit("Could not find scheduleRefreshAfterLtxRequeueSubmit anchor.")
    cpp = cpp[:index] + focus_impl + "\n" + cpp[index:]

# Improve success modal wording to mention latest output focus.
cpp = cpp.replace(
    "History and queue views are refreshing.",
    "History and queue views are refreshing. The latest requeue output will be selected when it appears.",
    1,
)

cpp_path.write_text(cpp, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    "# Sprint 15C Pass 22 — Surface Latest Requeue Output in Preview/Queue After Refresh\n\n"
    "Adds post-submit tracking for the latest LTX requeue prompt/output.\n\n"
    "After a successful Submit Requeue action, the T2V History page now stores the returned prompt id and primary output path, refreshes the page, and attempts to select the matching row after registry updates settle.\n\n"
    "This keeps the current guarded submit flow while making the newest requeue result easier to find in History and details/preview surfaces.\n",
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 22 latest requeue output surfacing.")
