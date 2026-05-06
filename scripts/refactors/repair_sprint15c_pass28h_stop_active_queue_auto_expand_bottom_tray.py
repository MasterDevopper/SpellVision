from pathlib import Path

path = Path("qt_ui/MainWindow.cpp")
text = path.read_text(encoding="utf-8")

old_chrome = '''    const bool active = hasActiveQueueWork();
    const bool showExpanded = active || queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;'''

new_chrome = '''    const bool active = hasActiveQueueWork();

    // Pass 28H:
    // Active queue work should update the tray state label, but it must not
    // auto-expand the bottom utility tray. Auto-expansion steals vertical space
    // from the generation workspace and causes visible in-window breathing.
    const bool showExpanded = queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;'''

if old_chrome not in text and "Active queue work should update the tray state label" not in text:
    raise SystemExit("Could not find applyQueueDockChrome expansion block.")

if old_chrome in text:
    text = text.replace(old_chrome, new_chrome, 1)


old_tray = '''    const bool active = hasActiveQueueWork();
    const bool expanded = active || queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;
    const bool compact = isCompactShellWidth();'''

new_tray = '''    const bool active = hasActiveQueueWork();

    // Pass 28H:
    // Keep tray height user-controlled. Live queue status is shown in the header
    // without resizing the generation workspace.
    const bool expanded = queueDockUserExpanded_ || bottomUtilityUserExpanded_ || detailsDockPinnedOpen_;
    const bool compact = isCompactShellWidth();'''

if old_tray not in text and "Keep tray height user-controlled" not in text:
    raise SystemExit("Could not find applyBottomUtilityTrayChrome expansion block.")

if old_tray in text:
    text = text.replace(old_tray, new_tray, 1)


old_splitter = '''    if (bottomUtilitySplitter_)
    {
        const int totalWidth = qMax(bottomUtilitySplitter_->width(), width() - 120);
        const bool active = hasActiveQueueWork();
        int detailsWidth = compact ? 560 : 680;
        if (!active && bottomUtilityTabs_ && bottomUtilityTabs_->currentIndex() == 0)
            detailsWidth = compact ? 640 : 780;
        if (bottomUtilityTabs_ && bottomUtilityTabs_->currentIndex() == 1)
            detailsWidth = compact ? 520 : 580;
        detailsWidth = qBound(460, detailsWidth, qMax(520, totalWidth / 2));
        const int queueWidth = qMax(active ? 560 : 500, totalWidth - detailsWidth);
        bottomUtilitySplitter_->setSizes({queueWidth, detailsWidth});
    }'''

new_splitter = '''    if (expanded && bottomUtilitySplitter_)
    {
        const int totalWidth = qMax(bottomUtilitySplitter_->width(), width() - 120);
        int detailsWidth = compact ? 560 : 680;
        if (bottomUtilityTabs_ && bottomUtilityTabs_->currentIndex() == 0)
            detailsWidth = compact ? 640 : 780;
        if (bottomUtilityTabs_ && bottomUtilityTabs_->currentIndex() == 1)
            detailsWidth = compact ? 520 : 580;
        detailsWidth = qBound(460, detailsWidth, qMax(520, totalWidth / 2));
        const int queueWidth = qMax(500, totalWidth - detailsWidth);
        bottomUtilitySplitter_->setSizes({queueWidth, detailsWidth});
    }'''

if old_splitter in text:
    text = text.replace(old_splitter, new_splitter, 1)


old_auto_show = '''    if (!queueDock_ || !queueDock_->isVisible())
        toggleBottomPanels();'''

new_auto_show = '''    // Pass 28H:
    // Do not auto-expand the bottom tray after enqueue. The compact header can
    // still show Live/Idle state, and users can expand Queue/Details manually.
    if (queueDock_ && !queueDock_->isVisible())
    {
        queueDock_->show();
        updateDockChrome();
    }'''

if old_auto_show in text:
    text = text.replace(old_auto_show, new_auto_show, 1)

path.write_text(text, encoding="utf-8")

print("Applied Pass 28H: active queue no longer auto-expands bottom tray.")
