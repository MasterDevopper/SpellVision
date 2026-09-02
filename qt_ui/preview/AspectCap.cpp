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

} // namespace spellvision::preview
