#include "AspectCap.h"

#include <QWidget>

#include <cstdlib>

namespace spellvision::preview
{

void applyAspectCap(QWidget *capWidget, const QWidget *content, const QSize &fittedContent)
{
    if (!capWidget || !content || fittedContent.isEmpty())
        return;
    // The chrome is whatever surrounds the content inside the cap widget: page margins, the
    // stacked layout's contents rect. Measured, not assumed, so a theme margin change needs no
    // edit here. Clamped at zero for the one frame where the content is not laid out yet.
    const int chromeW = std::max(0, capWidget->width() - content->width());
    const int chromeH = std::max(0, capWidget->height() - content->height());
    QSize cap(fittedContent.width() + chromeW, fittedContent.height() + chromeH);
    // A cap is a limit on the PICTURE, never on the controls beside it. The capped widget holds a
    // transport bar too, and a small clip (301px wide at half height) squeezed seven buttons, a
    // speed combo and the time readout into that width -- the buttons became slivers and the time
    // read ":05 / 00:". Seen live on 2026-09-02 once the chrome fix made the cap tight enough to
    // matter. minimumSizeHint is what the widget's own contents say they need, so this asks the
    // layout rather than guessing a floor.
    cap = cap.expandedTo(capWidget->minimumSizeHint());
    const QSize current = capWidget->maximumSize();
    if (std::abs(cap.width() - current.width()) <= 1 && std::abs(cap.height() - current.height()) <= 1)
        return;
    capWidget->setMaximumSize(cap);
}

void releaseAspectCap(QWidget *capWidget)
{
    if (!capWidget)
        return;
    if (capWidget->maximumWidth() == QWIDGETSIZE_MAX && capWidget->maximumHeight() == QWIDGETSIZE_MAX)
        return;
    capWidget->setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX);
}

QSize fitBudget(const QWidget *budgetWidget, const QWidget *capWidget, const QWidget *content)
{
    if (!budgetWidget || !capWidget || !content)
        return {};
    const QSize budget = budgetWidget->contentsRect().size();
    QSize chrome(capWidget->width() - content->width(), capWidget->height() - content->height());
    // Before the page's first layout pass the content's geometry is stale and the difference is
    // garbage (typically the whole widget, because the content is still 0x0). Treat that as no
    // chrome; the content's own Resize refines the fit one pass later.
    //
    // The test is DIMENSIONAL, not a constant. It was `> 160`, which is a guess about how much
    // chrome is plausible -- and a four-line video caption plus a transport bar crosses it, at
    // which point real chrome was silently dropped and the cap came out ~160px too tall. Chrome
    // that equals or exceeds the whole budget is impossible; chrome smaller than the budget is
    // just chrome, however much of it there is.
    if (chrome.width() < 0 || chrome.width() >= budget.width())
        chrome.setWidth(0);
    if (chrome.height() < 0 || chrome.height() >= budget.height())
        chrome.setHeight(0);
    return QSize(budget.width() - chrome.width(), budget.height() - chrome.height());
}

} // namespace spellvision::preview
