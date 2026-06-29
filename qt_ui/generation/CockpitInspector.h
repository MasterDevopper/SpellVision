#pragma once

#include <QFrame>

class QStackedWidget;
class QButtonGroup;
class QVBoxLayout;
class QLabel;

// CockpitInspector — the studio-layout right column for a generation cockpit.
//
// Fixed 340px; a tab bar (Model / Sampling / Output / Advanced) over a
// QStackedWidget that swaps IN PLACE, plus a readiness strip pinned to the
// bottom. Each tab body is a scroll area (relocated control sets can be tall),
// exposed via tabContentLayout() so the cockpit can reparent its real controls
// into the tabs (phase 3a).
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

private:
    QStackedWidget *stack_ = nullptr;
    QButtonGroup *tabGroup_ = nullptr;
    QVBoxLayout *tabLayouts_[4] = {nullptr, nullptr, nullptr, nullptr};
    QLabel *readinessText_ = nullptr;
};
