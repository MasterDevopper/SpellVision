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
    const QSize cap(fittedContent.width() + chromeW, fittedContent.height() + chromeH);
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
    // garbage. Treat it as no chrome; the content's own Resize refines the fit one pass later. 160
    // covers page margins plus a transport bar with room to spare.
    constexpr int kSaneChrome = 160;
    if (chrome.width() < 0 || chrome.height() < 0 || chrome.width() > kSaneChrome || chrome.height() > kSaneChrome)
        chrome = QSize(0, 0);
    return QSize(budget.width() - chrome.width(), budget.height() - chrome.height());
}

} // namespace spellvision::preview
