#pragma once

#include <QFrame>

class QStackedWidget;
class QButtonGroup;
class QVBoxLayout;
class QLabel;

// CockpitInspector — the studio-layout right column for a generation cockpit.
//
// Width is adaptive: callers call setWidthBudget() from the page's adaptive layout
// pass so half-screen / restore sizes keep tabs + Model Stack fully readable without
// clipping. Each tab body is a scroll area (controls can be tall); exposed via
// tabContentLayout() so the cockpit can reparent its real controls into the tabs.
//
// QFrame base paints its stylesheet background natively (see the CustomTitleBar
// WA_StyledBackground gotcha); we also set WA_StyledBackground belt-and-suspenders.
class CockpitInspector : public QFrame
{
    Q_OBJECT

public:
    enum Tab
    {
        Model = 0,
        Sampling = 1,
        Output = 2,
        Advanced = 3
    };

    explicit CockpitInspector(QWidget *parent = nullptr);

    // Content layout of a tab body — callers reparent relocated controls here.
    QVBoxLayout *tabContentLayout(Tab tab) const;
    QLabel *readinessLabel() const { return readinessText_; }

    // Phase 7: show/hide a whole tab (its tab-bar button). Hiding the currently-selected tab moves
    // selection to the first visible tab so the body never goes blank.
    void setTabVisible(Tab tab, bool visible);

    // Adaptive width budget for half-screen / restore. Clamped internally to a safe range so
    // Model Stack + 4-tab bar never clip, and the canvas still gets room at narrow widths.
    void setWidthBudget(int preferredWidth);

private:
    QStackedWidget *stack_ = nullptr;
    QButtonGroup *tabGroup_ = nullptr;
    QVBoxLayout *tabLayouts_[4] = {nullptr, nullptr, nullptr, nullptr};
    QLabel *readinessText_ = nullptr;
};
