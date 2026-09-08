#pragma once

#include "shell/ShellLayout.h"

#include <QWidget>

class QPaintEvent;

namespace spellvision::shell
{

// Three selectable cards -- Instrument, Canvas, Workspaces -- each a small diagram of its
// arrangement painted from live theme tokens, a name and a sentence (spec
// docs/superpowers/specs/2026-09-08-shell-layouts-design.md, sections 2.7-2.8). Shared between
// Settings (task 8) and the first-run wizard (task 9), which is why it is its own widget rather
// than inlined into either page.
//
// A card's own click handler mutates ShellLayout DIRECTLY -- the Surface Style pattern
// (SettingsPage.cpp's surfaceStyleCombo_ connection calls ThemeManager::setStyleByIndex straight
// off the combo), not the theme-preset one that detours through a page signal into MainWindow glue.
// layoutPicked is a NOTIFICATION, not a second mutation path: it exists so a consumer that needs to
// know a pick happened -- task 9's dialog, enabling its Next button -- does not have to own or
// repeat the write.
//
// Selection is never cached on a member a click sets. Every card asks
// ShellLayout::instance().layout() at paint time, so a change from anywhere -- another instance of
// this widget, a future keyboard shortcut, a restored setting -- is reflected the moment
// layoutChanged repaints it, rather than only when THIS widget's own click set it.
class LayoutPickerWidget : public QWidget
{
    Q_OBJECT

public:
    explicit LayoutPickerWidget(QWidget *parent = nullptr);

signals:
    void layoutPicked(ShellLayout::Layout layout);

protected:
    // A QWidget subclass does not get its stylesheet background for free (see
    // shell/SideRail.cpp's paintEvent, same reason, same fix). This widget draws no chrome of its
    // own -- the three cards paint theirs -- but the primitive is still asked for so a future
    // stylesheet rule aimed at this class is not silently inert.
    void paintEvent(QPaintEvent *event) override;
};

} // namespace spellvision::shell
