from pathlib import Path

root = Path(".")
h_path = root / "qt_ui" / "T2VHistoryPage.h"
cpp_path = root / "qt_ui" / "T2VHistoryPage.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS21_REFRESH_AFTER_LTX_REQUEUE_SUBMIT_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass21_refresh_after_ltx_requeue_submit.py"

h = h_path.read_text(encoding="utf-8")
cpp = cpp_path.read_text(encoding="utf-8")

# Add signal + helper declaration.
if "ltxRequeueSubmitted" not in h:
    if "Q_OBJECT" not in h:
        raise SystemExit("T2VHistoryPage.h does not appear to be a QObject/QWidget header.")

    if "signals:" in h:
        h = h.replace(
            "signals:\n",
            "signals:\n"
            "    void ltxRequeueSubmitted(const QString &promptId, const QString &primaryOutputPath);\n",
            1,
        )
    else:
        # Insert before private slots/private area if no signals section exists.
        marker = "private slots:"
        if marker not in h:
            marker = "private:"
        if marker not in h:
            raise SystemExit("Could not find insertion point for signals in T2VHistoryPage.h.")
        h = h.replace(
            marker,
            "signals:\n"
            "    void ltxRequeueSubmitted(const QString &promptId, const QString &primaryOutputPath);\n\n"
            + marker,
            1,
        )

if "scheduleRefreshAfterLtxRequeueSubmit" not in h:
    h = h.replace(
        "    void submitSelectedLtxRequeueDraft();\n",
        "    void submitSelectedLtxRequeueDraft();\n"
        "    void scheduleRefreshAfterLtxRequeueSubmit(const QJsonObject &response);\n",
        1,
    )

h_path.write_text(h, encoding="utf-8")

# Includes.
for include in [
    "#include <QTimer>",
    "#include <QPushButton>",
]:
    if include not in cpp:
        cpp = cpp.replace("#include <QProcess>", "#include <QProcess>\n" + include, 1)

# Helper function implementation.
impl = r'''
void T2VHistoryPage::scheduleRefreshAfterLtxRequeueSubmit(const QJsonObject &response)
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
}

'''

if "void T2VHistoryPage::scheduleRefreshAfterLtxRequeueSubmit(const QJsonObject &response)" not in cpp:
    anchor = "void T2VHistoryPage::submitSelectedLtxRequeueDraft()"
    index = cpp.find(anchor)
    if index < 0:
        raise SystemExit("Could not find submitSelectedLtxRequeueDraft implementation.")
    cpp = cpp[:index] + impl + "\n" + cpp[index:]

# Call refresh hook on successful submit before modal.
old = '''    QMessageBox::information(this,
                             QStringLiteral("Requeue Submitted"),
                             QStringLiteral("LTX requeue was submitted to Comfy.\\n\\nStatus: %1\\nMode: %2\\nPrompt ID: %3")
                                 .arg(status, mode, promptIdResult));
}
'''

new = '''    scheduleRefreshAfterLtxRequeueSubmit(response);

    QMessageBox::information(this,
                             QStringLiteral("Requeue Submitted"),
                             QStringLiteral("LTX requeue was submitted to Comfy.\\n\\nStatus: %1\\nMode: %2\\nPrompt ID: %3\\n\\nHistory and queue views are refreshing.")
                                 .arg(status, mode, promptIdResult));
}
'''

if old not in cpp:
    raise SystemExit("Could not find Submit Requeue success modal block.")

cpp = cpp.replace(old, new, 1)

cpp_path.write_text(cpp, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    "# Sprint 15C Pass 21 — Refresh History/Queue After LTX Requeue Submit\n\n"
    "Adds a post-submit refresh hook after successful LTX requeue submission from T2V History.\n\n"
    "Behavior:\n\n"
    "- Emits `ltxRequeueSubmitted(promptId, primaryOutputPath)`.\n"
    "- Automatically clicks the History page Refresh button shortly after submit.\n"
    "- Repeats the refresh after a short delay so registry writes have time to settle.\n"
    "- Updates the success modal to tell the user that history and queue views are refreshing.\n\n"
    "This keeps Pass 20's guarded confirmation flow while reducing the need to manually refresh after requeue submission.\n",
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 21 refresh after LTX requeue submit.")
