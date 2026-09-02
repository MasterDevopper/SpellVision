#include "ElidingLabel.h"

#include <QFontMetrics>
#include <QResizeEvent>
#include <QWidget>

namespace spellvision::widgets
{

QString elideForWidget(const QWidget *widget, const QString &text, Qt::TextElideMode mode, int reserved)
{
    if (!widget || text.isEmpty())
        return text;
    const int available = widget->width() - reserved;
    // A widget that has not been laid out yet has width 0 (or the reserve exceeds it). Eliding
    // against that returns a lone ellipsis and the value is gone; the resize that follows refits.
    if (available <= 0)
        return text;
    const QFontMetrics metrics(widget->fontMetrics());
    if (metrics.horizontalAdvance(text) <= available)
        return text;
    return metrics.elidedText(text, mode, available);
}

ElidingLabel::ElidingLabel(QWidget *parent, Qt::TextElideMode mode)
    : QLabel(parent)
    , mode_(mode)
{
    // Both halves of the fix, stated in the constructor so no call site can take one without the
    // other: never wrap (wrapping is what clipped instead of eliding), and never demand the value's
    // natural width from the layout (which is what pushed the LoRA card past its viewport).
    setWordWrap(false);
    setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred);
    setMinimumWidth(48);
    setTextInteractionFlags(Qt::NoTextInteraction);
}

void ElidingLabel::setFullText(const QString &text, const QString &toolTip)
{
    full_ = text;
    const QString tip = toolTip.isEmpty() ? text : toolTip;
    if (this->toolTip() != tip)
        setToolTip(tip);
    refit();
}

void ElidingLabel::clearFullText()
{
    full_.clear();
    setToolTip(QString());
    clear();
}

void ElidingLabel::setElideMode(Qt::TextElideMode mode)
{
    if (mode_ == mode)
        return;
    mode_ = mode;
    refit();
}

void ElidingLabel::resizeEvent(QResizeEvent *event)
{
    QLabel::resizeEvent(event);
    refit();
}

void ElidingLabel::refit()
{
    const QString shown = elideForWidget(this, full_, mode_);
    if (text() != shown)
        setText(shown);
}

} // namespace spellvision::widgets
