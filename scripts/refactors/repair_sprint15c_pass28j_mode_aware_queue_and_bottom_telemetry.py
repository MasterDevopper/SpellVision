from pathlib import Path
import re

main_window_path = Path("qt_ui/MainWindow.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass28j_mode_aware_queue_and_bottom_telemetry.py")

text = main_window_path.read_text(encoding="utf-8")


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
# 1) Add local helper for queue tray mode awareness.
# ----------------------------------------------------------------------

helper = r'''
    bool queueModeIsVideoWorkspace(const QString &modeId)
    {
        return modeId == QStringLiteral("t2v") || modeId == QStringLiteral("i2v");
    }

    bool queueModeIsImageWorkspace(const QString &modeId)
    {
        return modeId == QStringLiteral("t2i") || modeId == QStringLiteral("i2i");
    }

'''

if "queueModeIsVideoWorkspace" not in text:
    text = text.replace("namespace\n{\n", "namespace\n{\n" + helper, 1)


# ----------------------------------------------------------------------
# 2) Stabilize bottom telemetry bar after presenter build.
# ----------------------------------------------------------------------

build_bottom = r'''
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

    // Pass 28J:
    // The bottom telemetry bar is updated frequently while queue/generation
    // state changes. Fixed label widths prevent the status bar from breathing
    // when text changes from Idle -> Live, Queue: 0 -> Queue: 1, etc.
    auto stabilizeTelemetryLabel = [](QLabel *label, int width) {
        if (!label)
            return;

        label->setWordWrap(false);
        label->setMinimumWidth(width);
        label->setMaximumWidth(width);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
    };

    stabilizeTelemetryLabel(bottomReadyLabel_, 64);
    stabilizeTelemetryLabel(bottomPageLabel_, 130);
    stabilizeTelemetryLabel(bottomRuntimeLabel_, 160);
    stabilizeTelemetryLabel(bottomQueueLabel_, 92);
    stabilizeTelemetryLabel(bottomVramLabel_, 90);
    stabilizeTelemetryLabel(bottomModelLabel_, 170);
    stabilizeTelemetryLabel(bottomLoraLabel_, 150);
    stabilizeTelemetryLabel(bottomStateLabel_, 70);

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setMinimumWidth(120);
        bottomProgressBar_->setMaximumWidth(120);
        bottomProgressBar_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
    }
}
'''

text = replace_function(text, "void MainWindow::buildBottomTelemetryBar()", build_bottom)


# ----------------------------------------------------------------------
# 3) Stabilize queue widget geometry.
# ----------------------------------------------------------------------

# Active queue strip: no wrapping/height changes.
if "Pass 28J: active queue strip is fixed-height" not in text:
    text = text.replace(
        '''    activeQueueSummaryLabel_ = new QLabel(QStringLiteral("Recent jobs will appear here when the queue is idle."), activeStrip);
    activeQueueSummaryLabel_->setObjectName(QStringLiteral("QueueActiveBody"));
    activeQueueSummaryLabel_->setWordWrap(true);''',
        '''    activeQueueSummaryLabel_ = new QLabel(QStringLiteral("Recent image jobs will appear here when the queue is idle."), activeStrip);
    activeQueueSummaryLabel_->setObjectName(QStringLiteral("QueueActiveBody"));
    // Pass 28J: active queue strip is fixed-height and single-line.
    activeQueueSummaryLabel_->setWordWrap(false);
    activeQueueSummaryLabel_->setFixedHeight(22);
    activeQueueSummaryLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);''',
        1,
    )

if "activeStrip->setFixedHeight" not in text:
    text = text.replace(
        '''    auto *activeStrip = createPanelFrame(QStringLiteral("QueueActiveStrip"), root);''',
        '''    auto *activeStrip = createPanelFrame(QStringLiteral("QueueActiveStrip"), root);
    activeStrip->setFixedHeight(78);''',
        1,
    )

# Queue search/filter row: fixed height.
if "Pass 28J fixed filter row" not in text:
    text = text.replace(
        '''    queueSearchEdit_ = new QLineEdit(root);
    queueSearchEdit_->setPlaceholderText(QStringLiteral("Search queue by prompt, model, or state"));''',
        '''    queueSearchEdit_ = new QLineEdit(root);
    queueSearchEdit_->setPlaceholderText(QStringLiteral("Search queue by prompt, model, or state"));
    // Pass 28J fixed filter row.
    queueSearchEdit_->setFixedHeight(30);''',
        1,
    )

    text = text.replace(
        '''    queueStateFilter_ = new QComboBox(root);
    queueStateFilter_->addItems({QStringLiteral("All States"),''',
        '''    queueStateFilter_ = new QComboBox(root);
    queueStateFilter_->setFixedHeight(30);
    queueStateFilter_->addItems({QStringLiteral("All States"),''',
        1,
    )

# Queue table stable geometry.
if "Pass 28J stable queue table geometry" not in text:
    text = text.replace(
        '''    queueTableView_->setAlternatingRowColors(true);
    queueTableView_->setSortingEnabled(false);''',
        '''    queueTableView_->setAlternatingRowColors(true);
    // Pass 28J stable queue table geometry:
    // no wrapping or resize-to-contents during high-frequency queue updates.
    queueTableView_->setWordWrap(false);
    queueTableView_->setTextElideMode(Qt::ElideRight);
    queueTableView_->setSortingEnabled(false);''',
        1,
    )

# Replace all queue-table ResizeToContents modes in MainWindow with Fixed.
text = text.replace("QHeaderView::ResizeToContents", "QHeaderView::Fixed")

if "queueTableView_->verticalHeader()->setDefaultSectionSize(28)" not in text:
    text = text.replace(
        '''    queueTableView_->verticalHeader()->setVisible(false);''',
        '''    queueTableView_->verticalHeader()->setVisible(false);
    queueTableView_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
    queueTableView_->verticalHeader()->setDefaultSectionSize(28);
    queueTableView_->verticalHeader()->setMinimumSectionSize(28);''',
        1,
    )

if "Pass 28J fixed queue columns" not in text:
    text = text.replace(
        '''    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::UpdatedAtColumn, QHeaderView::Fixed);''',
        '''    queueTableView_->horizontalHeader()->setSectionResizeMode(QueueTableModel::UpdatedAtColumn, QHeaderView::Fixed);

    // Pass 28J fixed queue columns.
    queueTableView_->horizontalHeader()->setStretchLastSection(false);
    queueTableView_->setColumnWidth(QueueTableModel::StateColumn, 104);
    queueTableView_->setColumnWidth(QueueTableModel::CommandColumn, 76);
    queueTableView_->setColumnWidth(QueueTableModel::VideoColumn, 116);
    queueTableView_->setColumnWidth(QueueTableModel::ProgressColumn, 96);
    queueTableView_->setColumnWidth(QueueTableModel::StatusColumn, 190);
    queueTableView_->setColumnWidth(QueueTableModel::QueueIdColumn, 150);
    queueTableView_->setColumnWidth(QueueTableModel::UpdatedAtColumn, 142);''',
        1,
    )


# ----------------------------------------------------------------------
# 4) Add/replace a queue presentation helper.
# ----------------------------------------------------------------------

queue_presentation = r'''
void MainWindow::applyQueuePresentationForCurrentMode()
{
    if (!queueTableView_)
        return;

    const bool videoMode = queueModeIsVideoWorkspace(currentModeId_);
    const bool imageMode = queueModeIsImageWorkspace(currentModeId_);

    // Pass 28J:
    // The queue tray should reflect the active workspace. T2I/I2I should not
    // look like a video queue, and video-only columns should not steal width.
    queueTableView_->setColumnHidden(QueueTableModel::VideoColumn, !videoMode);

    queueTableView_->setColumnWidth(QueueTableModel::StateColumn, 104);
    queueTableView_->setColumnWidth(QueueTableModel::CommandColumn, 76);
    queueTableView_->setColumnWidth(QueueTableModel::ProgressColumn, 96);
    queueTableView_->setColumnWidth(QueueTableModel::StatusColumn, imageMode ? 210 : 190);
    queueTableView_->setColumnWidth(QueueTableModel::QueueIdColumn, 150);
    queueTableView_->setColumnWidth(QueueTableModel::UpdatedAtColumn, 142);

    if (videoMode)
        queueTableView_->setColumnWidth(QueueTableModel::VideoColumn, 116);

    if (queueSearchEdit_)
    {
        queueSearchEdit_->setPlaceholderText(videoMode
            ? QStringLiteral("Search video queue by prompt, model, or state")
            : QStringLiteral("Search image queue by prompt, model, or state"));
    }

    if (activeQueueSummaryLabel_ && !hasActiveQueueWork())
    {
        activeQueueSummaryLabel_->setText(videoMode
            ? QStringLiteral("Recent video jobs will appear here when the queue is idle.")
            : QStringLiteral("Recent image jobs will appear here when the queue is idle."));
    }
}
'''

if "void MainWindow::applyQueuePresentationForCurrentMode()" in text:
    text = replace_function(text, "void MainWindow::applyQueuePresentationForCurrentMode()", queue_presentation)
else:
    insert_before = "void MainWindow::updateDockChrome()"
    index = text.find(insert_before)
    if index < 0:
        raise SystemExit("Could not find updateDockChrome insertion point.")
    text = text[:index] + queue_presentation + "\n\n" + text[index:]

# Call presentation from createQueueWidget after table setup.
if "applyQueuePresentationForCurrentMode();" not in text[text.find("QWidget *MainWindow::createQueueWidget()"):text.find("QWidget *MainWindow::createDetailsWidget()")]:
    text = text.replace(
        '''    connect(queueTableView_->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this]()
            { updateDetailsPanelForQueueSelection(); });

    return root;''',
        '''    connect(queueTableView_->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this]()
            { updateDetailsPanelForQueueSelection(); });

    applyQueuePresentationForCurrentMode();

    return root;''',
        1,
    )

# Call presentation from mode changes.
if "applyQueuePresentationForCurrentMode();" not in text[text.find("void MainWindow::applyShellStateForMode"):text.find("void MainWindow::setBottomPageContext")]:
    text = text.replace(
        '''    updateModeButtonState(modeId);
    updateDetailsPanelForModeContext();
    updateDockChrome();''',
        '''    updateModeButtonState(modeId);
    updateDetailsPanelForModeContext();
    applyQueuePresentationForCurrentMode();
    updateDockChrome();''',
        1,
    )

# Call presentation from queue changes, but do not spam details/chrome.
on_queue_changed = r'''
void MainWindow::onQueueChanged()
{
    syncBottomTelemetry();
    updateActiveQueueStrip();
    applyQueuePresentationForCurrentMode();

    const bool expanded = queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;
    const QString selectedId = selectedQueueId();

    const QString detailsKey = QStringLiteral("%1|%2")
        .arg(expanded ? QStringLiteral("expanded") : QStringLiteral("collapsed"), selectedId);

    // Pass 28J:
    // Details text can wrap and resize the expanded tray. Only rewrite it when
    // selection/expanded state changes, not on every queue progress poll.
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


# ----------------------------------------------------------------------
# 5) Ensure bottom tray height is user-controlled, not active-queue controlled.
# ----------------------------------------------------------------------

text = text.replace(
    '''    const bool active = hasActiveQueueWork();
    const bool showExpanded = active || queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;''',
    '''    const bool active = hasActiveQueueWork();

    // Pass 28J: active queue work updates labels but must not resize the tray.
    const bool showExpanded = queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;'''
)

text = text.replace(
    '''    const bool active = hasActiveQueueWork();
    const bool expanded = active || queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;
    const bool compact = isCompactShellWidth();''',
    '''    const bool active = hasActiveQueueWork();

    // Pass 28J: expanded height is user-controlled, not activity-controlled.
    const bool expanded = queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;
    const bool compact = isCompactShellWidth();'''
)

# Stabilize bottom splitter: only set sizes when expanded and layout key changes.
splitter_pattern = re.compile(
    r'''    if \((?:expanded && )?bottomUtilitySplitter_\)\n    \{\n        const int totalWidth = qMax\(bottomUtilitySplitter_->width\(\), width\(\) - 120\);\n.*?bottomUtilitySplitter_->setSizes\(\{queueWidth, detailsWidth\}\);\n    \}''',
    re.DOTALL,
)

splitter_replacement = '''    if (expanded && bottomUtilitySplitter_)
    {
        const int totalWidth = qMax(bottomUtilitySplitter_->width(), width() - 120);
        const int currentTab = bottomUtilityTabs_ ? bottomUtilityTabs_->currentIndex() : 0;
        const QString splitterKey = QStringLiteral("%1|%2|%3|%4")
            .arg(totalWidth)
            .arg(compact ? 1 : 0)
            .arg(currentTab)
            .arg(currentModeId_);

        // Pass 28J: do not reset splitter sizes on every queue progress tick.
        if (bottomUtilitySplitter_->property("svLastQueueSplitterKey").toString() != splitterKey)
        {
            int detailsWidth = compact ? 560 : 680;
            if (currentTab == 0)
                detailsWidth = compact ? 640 : 780;
            if (currentTab == 1)
                detailsWidth = compact ? 520 : 580;
            detailsWidth = qBound(460, detailsWidth, qMax(520, totalWidth / 2));
            const int queueWidth = qMax(500, totalWidth - detailsWidth);
            bottomUtilitySplitter_->setSizes({queueWidth, detailsWidth});
            bottomUtilitySplitter_->setProperty("svLastQueueSplitterKey", splitterKey);
        }
    }'''

text, replacements = splitter_pattern.subn(splitter_replacement, text, count=1)
if replacements == 0 and "svLastQueueSplitterKey" not in text:
    raise SystemExit("Could not patch bottom splitter sizing block.")

main_window_path.write_text(text, encoding="utf-8")
script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Pass 28J: mode-aware queue tray and stable bottom telemetry.")
