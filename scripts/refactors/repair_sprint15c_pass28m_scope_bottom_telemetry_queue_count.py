from pathlib import Path

main_cpp_path = Path("qt_ui/MainWindow.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass28m_scope_bottom_telemetry_queue_count.py")

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
                end = index
                break

    if end is None:
        raise SystemExit(f"Could not find closing brace for: {signature}")

    return start, brace, end


def insert_before_function_end(text: str, signature: str, block: str, guard: str) -> str:
    start, brace, end = find_function_bounds(text, signature)
    function_body = text[start:end]

    if guard in function_body:
        return text

    return text[:end] + "\n" + block.rstrip() + "\n" + text[end:]


# Store the visible mode-scoped queue count when queue presentation runs.
presentation_sig = "void MainWindow::applyQueuePresentationForCurrentMode()"
start, brace, end = find_function_bounds(text, presentation_sig)
presentation_body = text[start:end]

if "svVisibleQueueRowsForMode" not in presentation_body:
    marker = '''    if (queueSearchEdit_)
    {'''
    insert = '''    setProperty("svVisibleQueueRowsForMode", visibleRows);

'''
    if marker not in presentation_body:
        raise SystemExit("Could not find queueSearchEdit marker in applyQueuePresentationForCurrentMode().")

    absolute_marker = text.find(marker, start, end)
    text = text[:absolute_marker] + insert + text[absolute_marker:]


# After BottomTelemetryPresenter/global telemetry sync runs, override Queue text
# with the visible proxy row count for the current workspace.
telemetry_fix = r'''
    // Pass 28M:
    // BottomTelemetryPresenter reports the backend/global queue count. The
    // expanded tray is now workspace-filtered through QueueFilterProxyModel, so
    // the bottom telemetry bar must use the same visible row count. Otherwise
    // it keeps changing Queue: 9 / Queue: 11 while T2I only shows 2–3 rows,
    // which also causes status-bar breathing.
    if (bottomQueueLabel_)
    {
        int visibleRows = property("svVisibleQueueRowsForMode").toInt();

        if (queueTableView_ && queueTableView_->model())
            visibleRows = queueTableView_->model()->rowCount();

        const QString scopedQueueText = QStringLiteral("Queue: %1").arg(visibleRows);

        if (bottomQueueLabel_->text() != scopedQueueText)
            bottomQueueLabel_->setText(scopedQueueText);

        bottomQueueLabel_->setFixedWidth(104);
        bottomQueueLabel_->setWordWrap(false);
        bottomQueueLabel_->setAlignment(Qt::AlignCenter);
        bottomQueueLabel_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
    }

    if (bottomRuntimeLabel_)
    {
        bottomRuntimeLabel_->setFixedWidth(160);
        bottomRuntimeLabel_->setWordWrap(false);
        bottomRuntimeLabel_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
    }

    if (bottomVramLabel_)
    {
        bottomVramLabel_->setFixedWidth(90);
        bottomVramLabel_->setWordWrap(false);
        bottomVramLabel_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
    }

    if (bottomModelLabel_)
    {
        bottomModelLabel_->setFixedWidth(190);
        bottomModelLabel_->setWordWrap(false);
        bottomModelLabel_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
    }

    if (bottomLoraLabel_)
    {
        bottomLoraLabel_->setFixedWidth(150);
        bottomLoraLabel_->setWordWrap(false);
        bottomLoraLabel_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
    }

    if (bottomStateLabel_)
    {
        bottomStateLabel_->setFixedWidth(70);
        bottomStateLabel_->setWordWrap(false);
        bottomStateLabel_->setAlignment(Qt::AlignCenter);
        bottomStateLabel_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
    }

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setFixedWidth(120);
        bottomProgressBar_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
    }
'''

text = insert_before_function_end(
    text,
    "void MainWindow::syncBottomTelemetry()",
    telemetry_fix,
    "Pass 28M:"
)

main_cpp_path.write_text(text, encoding="utf-8")
script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Pass 28M: bottom telemetry queue count now follows visible workspace rows.")
