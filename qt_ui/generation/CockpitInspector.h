#pragma once

#include <QFrame>
#include <QStringList>

class QStackedWidget;
class QBoxLayout;
class QButtonGroup;
class QVBoxLayout;
class QLabel;
class QWidget;

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

    // Empty hides the strip. A ready state is not a sentence. applyExpandedForm does not
    // bring an empty strip back.
    void setReadinessSentence(const QString &text);

    // Phase 7: show/hide a whole tab (its tab-bar button). Hiding the currently-selected tab moves
    // selection to the first visible tab so the body never goes blank.
    void setTabVisible(Tab tab, bool visible);

    // Adaptive width budget for half-screen / restore. Clamped internally to a safe range so
    // Model Stack + 4-tab bar never clip, and the canvas still gets room at narrow widths.
    //
    // Called from the page's adaptive pass on EVERY resize, which means it keeps arriving while the
    // inspector is collapsed. It records the budget then and applies it on the way back out, which
    // is what makes setCollapsed(false) restore the budget the inspector HAD rather than a default.
    void setWidthBudget(int preferredWidth);
    int widthBudget() const { return budget_; }

    // The Canvas layout's inspector: a narrow strip of tab glyphs with its content area hidden
    // (spec section 2.1). HIDDEN, never destroyed -- every control in every tab keeps its value,
    // its connections and its place in the layout, so expanding is a setVisible and not a rebuild.
    //
    // EXPAND-ON-DEMAND IS A PUSH, NOT AN OVERLAY. Clicking a glyph while collapsed expands the
    // column in the layout it already sits in, so the canvas narrows beside it; clicking the same
    // glyph again puts it back. An overlay would have to be positioned imperatively -- the one
    // mechanism in this shell that has already produced a silent geometry bug -- and, tall enough to
    // hold the Model tab, it would cover the action row that lives at the canvas card's bottom.
    void setCollapsed(bool collapsed);
    bool isCollapsed() const { return collapsed_; }

signals:
    void collapsedChanged(bool collapsed);

private:
    // The two forms, each stated in full. Neither reads what the other left behind, so a form can be
    // re-applied to an inspector that has drifted and put it right.
    void applyCollapsedForm();
    void applyExpandedForm();
    void applyWidthBudget();

    QStackedWidget *stack_ = nullptr;
    QButtonGroup *tabGroup_ = nullptr;
    QVBoxLayout *tabLayouts_[4] = {nullptr, nullptr, nullptr, nullptr};
    QLabel *readinessText_ = nullptr;
    QWidget *tabBar_ = nullptr;
    QBoxLayout *tabRow_ = nullptr;
    // The tail of the tab strip. Hiding the content area empties the column of everything that could
    // take its height, and a QBoxLayout hands the leftover to whatever CAN grow -- which was the tab
    // bar, so four glyphs ended up spread evenly down 900 px instead of grouped at the top. This is
    // the one item allowed to grow while collapsed; it is 0x0 and inert while expanded.
    QWidget *tabTail_ = nullptr;
    QFrame *readinessStrip_ = nullptr;
    // Kept because the tab bar is REBUILT between two forms and each needs both halves: the labelled
    // form needs the name, the glyph form needs the name for its tooltip. Reading either back off a
    // button would mean reading back whatever the last form wrote.
    QStringList tabNames_;
    bool collapsed_ = false;
    // Expanded by a click on a glyph rather than by the layout. Only such an expansion re-collapses
    // on a second click; an inspector the layout expanded is not a peek and does not toggle shut.
    bool peeking_ = false;
    int budget_ = 0;
};
