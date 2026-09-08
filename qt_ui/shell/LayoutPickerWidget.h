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
// A card's own click (or Space/Return) reports the pick to THIS widget through reportPick(), which
// decides what a pick MEANS -- see CommitMode. In Immediate mode (Settings' unchanged behaviour) a
// pick mutates ShellLayout directly, the Surface Style pattern (SettingsPage.cpp's
// surfaceStyleCombo_ connection calls ThemeManager::setStyleByIndex straight off the combo), not the
// theme-preset one that detours through a page signal into MainWindow glue. layoutPicked fires ONLY
// for a pick made through one of THIS widget's own cards (fix round 1, item I4) -- it used to forward
// every ShellLayout::layoutChanged verbatim, which meant a consumer heard about changes it had
// nothing to do with.
//
// Selection is never cached on a member a click sets in Immediate mode: selectedLayout() reads
// ShellLayout::instance().layout() live, so a change from anywhere -- another instance of this
// widget, a future keyboard shortcut, a restored setting -- is reflected the moment layoutChanged
// repaints it, rather than only when THIS widget's own click set it. Deferred mode is the one
// sanctioned exception: it exists because task 9's first-run dialog must not write a real setting
// before the user accepts (spec 2.7 -- dismissing first run is never a trap), so a pick there can
// only move the widget's OWN, explicitly separate selection until the consumer calls
// commitSelection().
class LayoutPickerWidget : public QWidget
{
    Q_OBJECT

public:
    enum class CommitMode
    {
        Immediate, // a pick reaches ShellLayout the moment it happens (Settings)
        Deferred   // a pick only moves this widget's own selection until commitSelection() is called
    };

    explicit LayoutPickerWidget(QWidget *parent = nullptr);

    void setCommitMode(CommitMode mode);
    CommitMode commitMode() const { return mode_; }

    // The widget's own selection: ShellLayout::instance().layout() in Immediate mode, the last pick
    // (or the singleton's value if nothing has been picked yet) in Deferred mode. Every card asks
    // this, never the singleton directly, so the same paint code is correct in both modes.
    ShellLayout::Layout selectedLayout() const;

    // Deferred mode only: applies the widget's own selection to the real ShellLayout singleton. A
    // no-op in Immediate mode, where every pick already reached it.
    void commitSelection();

    // Called by a card's own click/keyboard handler when it is picked. Public because the cards
    // (LayoutCard, defined in LayoutPickerWidget.cpp's anonymous namespace -- a `friend` declaration
    // here would name a DIFFERENT, empty class in this namespace, not that one) hold a pointer to
    // their owning picker and call it directly; an external caller invoking it behaves exactly like a
    // click on that card, which is harmless.
    void reportPick(ShellLayout::Layout layout);

signals:
    void layoutPicked(ShellLayout::Layout layout);

protected:
    // A QWidget subclass does not get its stylesheet background for free (see
    // shell/SideRail.cpp's paintEvent, same reason, same fix). This widget draws no chrome of its
    // own -- the three cards paint theirs -- but the primitive is still asked for so a future
    // stylesheet rule aimed at this class is not silently inert.
    void paintEvent(QPaintEvent *event) override;

private:
    CommitMode mode_ = CommitMode::Immediate;
    ShellLayout::Layout localSelection_;
};

} // namespace spellvision::shell
