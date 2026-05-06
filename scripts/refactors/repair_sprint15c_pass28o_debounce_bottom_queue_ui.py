from pathlib import Path

main_cpp_path = Path("qt_ui/MainWindow.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass28o_debounce_bottom_queue_ui.py")

text = main_cpp_path.read_text(encoding="utf-8")


def find_function_bounds(text: str, signature: str):
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

    return start, end


def replace_function(text: str, signature: str, replacement: str) -> str:
    start, end = find_function_bounds(text, signature)
    return text[:start] + replacement.rstrip() + "\n" + text[end:]


# ----------------------------------------------------------------------
# 1) Include QTimer if this file does not already have it.
# ----------------------------------------------------------------------

if "#include <QTimer>" not in text:
    text = text.replace("#include <QTableView>", "#include <QTableView>\n#include <QTimer>", 1)


# ----------------------------------------------------------------------
# 2) Harden the telemetry bar construction.
# ----------------------------------------------------------------------

build_replacement = r'''
void MainWindow::buildBottomTelemetryBar()
{
    spellvision::shell::BottomTelemetryPresenter::BuildBindings bindings;
    bindings.owner = this;
    bindings.statusBar = statusBar();
    bindings.readyLabel = &bottomReadyLabel_;
    bindings.pageLabel = &bottomPageLabel_;
    bindings.runtimeLabel = &bottomRuntimeLabel_;
    bindings.queueLabel = &bottomQueueLabel_;
    bindings.vramLabel = &bottomVramLabel_;
    bindings.modelLabel = &bottomModelLabel_;
    bindings.loraLabel = &bottomLoraLabel_;
    bindings.stateLabel = &bottomStateLabel_;
    bindings.progressBar = &bottomProgressBar_;

    spellvision::shell::BottomTelemetryPresenter::build(bindings);

    // Pass 28O:
    // The status bar is updated frequently. Give every telemetry cell a fixed
    // geometry so text changes cannot push/pull neighboring cells.
    if (statusBar())
    {
        statusBar()->setSizeGripEnabled(false);
        statusBar()->setFixedHeight(30);
        statusBar()->setMinimumHeight(30);
       ::build(bindings);

    // Pass 28O:
    // The status bar is updated frequently. Give every telemetry cell a fixed
    // geometry so text changes cannot push/pull neighboring cells.
 statusBar()->setMaximumHeight(30);
    }

    auto stabilizeLabel = [](QLabel *label, int width) {
        if (!label)
            return;

        label->setFixedWidth(width);
        label->setMinimumHeight(22);
        label->setMaximumHeight(22);
        label->setWordWrap(false);
        label->setTextInteractionFlags(Qt::NoTextInteraction);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    };

    stabilizeLabel(bottomReadyLabel_, 64);
    stabilizeLabel(bottomPageLabel_, 150);
    stabilizeLabel(bottomRuntimeLabel_, 150);
    stabilizeLabel(bottomQueueLabel_, 104);
    stabilizeLabel(bottomVramLabel_, 90);
    stabilizeLabel(bottomModelLabel_, 210);
    stabilizeLabel(bottomLoraLabel_, 150);
    stabilizeLabel(bottomStateLabel_, 84);

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setFixedWidth(120);
        bottomProgressBar_->setFixedHeight(8);
        bottomProgressBar_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    }
}
'''

text = replace_function(text, "void MainWindow::buildBottomTelemetryBar()", build_replacement)


# ----------------------------------------------------------------------
# 3) Make updateActiveQueueStrip harmless. No global queue scanning.
# ----------------------------------------------------------------------

active_strip_replacement = r'''
void MainWindow::updateActiveQueueStrip()
{
    // Pass 28O:
    // The old implementation scanned the global queue and rewrote active strip
    // labels on every poll. That caused the expanded bottom tray to breathe and
    // could surface stale T2V/LTX rows while the user was on T2I.
    //
    // Queue strip ownership now lives in applyQueuePresentationForCurrentMode().
    applyQueuePresentationForCurrentMode();
}
'''

text = replace_function(text, "void MainWindow::updateActiveQueueStrip()", active_strip_replacement)


# ----------------------------------------------------------------------
# 4) Replace onQueueChanged with a debounced bottom UI flush.
# ----------------------------------------------------------------------

on_queue_changed_replacement = r'''
void MainWindow::onQueueChanged()
{
    // Pass 28O:
    // Queue polling is high-frequency. Do not synchronously rewrite telemetry,
    // strip labels, details, chrome, and the queue viewport on every snapshot.
    // Coalesce poll bursts into a single stable UI update.
    if (property("svBottomQueueUiFlushPending").toBool())
        return;

    setProperty("svBottomQueueUiFlushPending", true);

    QTimer::singleShot(140, this, [this]() {
        setProperty("svBottomQueueUiFlushPending", false);

        applyQueuePresentationForCurrentMode();
        syncBottomTelemetry();
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
    });
}
'''

text = replace_function(text, "void MainWindow::onQueueChanged()", on_queue_changed_replacement)


# ----------------------------------------------------------------------
# 5) Make syncBottomTelemetry override all dynamic fields with fixed cells.
# ----------------------------------------------------------------------

sync_start, sync_end = find_function_bounds(text, "void MainWindow::syncBottomTelemetry()")
sync_body = text[sync_start:sync_end]

telemetry_override = r'''
    // Pass 28O:
    // BottomTelemetryPresenter may write global queue/model/state text first.
    // Clamp it back into fixed, mode-scoped telemetry cells after every sync.
    auto stabilizeLabel = [](QLabel *label, int width) {
        if (!label)
            return;

        label->setFixedWidth(width);
        label->setMinimumHeight(22);
        label->setMaximumHeight(22);
        label->setWordWrap(false);
        label->setTextInteractionFlags(Qt::NoTextInteraction);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    };

    stabilizeLabel(bottomReadyLabel_, 64);
    stabilizeLabel(bottomPageLabel_, 150);
    stabilizeLabel(bottomRuntimeLabel_, 150);
    stabilizeLabel(bottomQueueLabel_, 104);
    stabilizeLabel(bottomVramLabel_, 90);
    stabilizeLabel(bottomModelLabel_, 210);
    stabilizeLabel(bottomLoraLabel_, 150);
    stabilizeLabel(bottomStateLabel_, 84);

    if (bottomQueueLabel_)
    {
        int visibleRows = property("svVisibleQueueRowsForMode").toInt();

        if (queueTableView_ && queueTableView_->model())
            visibleRows = queueTableView_->model()->rowCount();

        const QString scopedQueueText = QStringLiteral("Queue: %1").arg(visibleRows);
        if (bottomQueueLabel_->text() != scopedQueueText)
            bottomQueueLabel_->setText(scopedQueueText);
    }

    if (bottomRuntimeLabel_ && bottomRuntimeLabel_->text().trimmed().isEmpty())
        bottomRuntimeLabel_->setText(QStringLiteral("Runtime: local"));

    if (bottomVramLabel_ && bottomVramLabel_->text().trimmed().isEmpty())
        bottomVramLabel_->setText(QStringLiteral("VRAM: n/a"));

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setFixedWidth(120);
        bottomProgressBar_->setFixedHeight(8);
        bottomProgressBar_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    }
'''

if "Pass 28O:" not in sync_body:
    text = text[:sync_end - 1] + "\n" + telemetry_override.rstrip() + "\n" + text[sync_end - 1:]


# ----------------------------------------------------------------------
# 6) Freeze expanded queue surface geometry enough that internal content cannot
#    resize the bottom tray.
# ----------------------------------------------------------------------

presentation_start, presentation_end = find_function_bounds(text, "void MainWindow::applyQueuePresentationForCurrentMode()")
presentation_body = text[presentation_start:presentation_end]

queue_geometry_block = r'''
    // Pass 28O:
    // Expanded queue internals should never resize the bottom dock. The tray
    // height is controlled by collapse/expand state, not row count or text width.
    if (queueTableView_)
    {
        queueTableView_->setSizeAdjustPolicy(QAbstractScrollArea::AdjustIgnored);
        queueTableView_->setWordWrap(false);
        queueTableView_->setTextElideMode(Qt::ElideRight);
        queueTableView_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
        queueTableView_->verticalHeader()->setDefaultSectionSize(28);
        queueTableView_->verticalHeader()->setMinimumSectionSize(28);
    }

    if (queueSearchEdit_)
    {
        queueSearchEdit_->setFixedHeight(30);
        queueSearchEdit_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    }

    if (queueStateFilter_)
    {
        queueStateFilter_->setFixedHeight(30);
        queueStateFilter_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    }
'''

if "Expanded queue internals should never resize the bottom dock" not in presentation_body:
    insert_at = text.find("    if (queueSearchEdit_)", presentation_start, presentation_end)
    if insert_at < 0:
        raise SystemExit("Could not find queueSearchEdit marker inside applyQueuePresentationForCurrentMode().")
    text = text[:insert_at] + queue_geometry_block + "\n" + text[insert_at:]


main_cpp_path.write_text(text, encoding="utf-8")
script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Pass 28O: debounced bottom queue UI and fixed telemetry geometry.")
