#include "ClickOnlyComboBox.h"

#include <QAbstractItemView>
#include <QWheelEvent>

namespace spellvision::widgets
{

ClickOnlyComboBox::ClickOnlyComboBox(QWidget *parent)
    : QComboBox(parent)
{
    setFocusPolicy(Qt::StrongFocus);
}

void ClickOnlyComboBox::wheelEvent(QWheelEvent *event)
{
    if (view() && view()->isVisible())
    {
        QComboBox::wheelEvent(event);
        return;
    }

    if (event)
        event->ignore();
}

} // namespace spellvision::widgets
