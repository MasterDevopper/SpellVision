#pragma once

#include <QFrame>

class QStackedWidget;
class QButtonGroup;

// CockpitInspector — the studio-layout right column for a generation cockpit.
//
// Phase 2 (studio-layout migration): an EMPTY scaffold proving the inspector
// mechanics — fixed 340px wide, a tab bar (Model / Sampling / Output / Advanced)
// over a QStackedWidget that swaps IN PLACE (no scroll), and a readiness strip
// pinned to the bottom. The tab bodies hold placeholders for now; the real
// controls relocate here from the cockpit's left-scroll + model-stack in Phase 3.
//
// QFrame base: unlike a plain QWidget subclass, QFrame paints its stylesheet
// background natively (see the CustomTitleBar WA_StyledBackground gotcha) — we
// also set WA_StyledBackground belt-and-suspenders.
class CockpitInspector : public QFrame
{
    Q_OBJECT

public:
    explicit CockpitInspector(QWidget *parent = nullptr);

private:
    QStackedWidget *stack_ = nullptr;
    QButtonGroup *tabGroup_ = nullptr;
};
