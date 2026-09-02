#include "ErrorPillLabel.h"

#include "../shell/WorkerFailureDialog.h"
#include "../widgets/ElidingLabel.h"

#include <QFontMetrics>
#include <QMouseEvent>
#include <QResizeEvent>
#include <QSizePolicy>

#include <algorithm>

namespace spellvision::generation
{

namespace
{
// The pill's own style: 10px padding each side plus a 1px border.
constexpr int kHorizontalChrome = 24;
constexpr int kMaximumWidth = 420;
constexpr int kMinimumWidth = 60;
} // namespace

ErrorPillLabel::ErrorPillLabel(QWidget *parent)
    : QLabel(parent)
{
    setWordWrap(false);
    // Up to 420px when the row has it, down to 60px when it does not; refit() elides the message
    // to whatever width results, so no width ever cuts the text.
    setMaximumWidth(kMaximumWidth);
    setMinimumWidth(kMinimumWidth);
    setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);
}

void ErrorPillLabel::setMessage(const QString &oneLine, const QString &fullText)
{
    oneLine_ = oneLine.trimmed();
    fullText_ = fullText.trimmed();
    setToolTip(QStringLiteral("%1\n\nClick for the full message.").arg(fullText_));
    setCursor(Qt::PointingHandCursor);
    setText(QString::fromUtf8("⚠  ") + oneLine_);
    refit();
}

void ErrorPillLabel::clearMessage()
{
    oneLine_.clear();
    fullText_.clear();
    setCursor(Qt::ArrowCursor);
}

void ErrorPillLabel::refit()
{
    if (oneLine_.isEmpty())
        return;
    const QString prefix = QString::fromUtf8("⚠  ");
    const QFontMetrics metrics(font());
    // One elision helper for the whole UI (widgets/ElidingLabel.h). The pill's reserve is its own
    // padding plus the warning glyph; the arithmetic is the same everywhere else.
    const int reserved = kHorizontalChrome + metrics.horizontalAdvance(prefix);
    const QString shown = prefix + spellvision::widgets::elideForWidget(this, oneLine_, Qt::ElideRight, reserved);
    // Only write when it changes: setText re-lays out, which resizes, which re-enters here.
    if (text() != shown)
        setText(shown);
}

void ErrorPillLabel::resizeEvent(QResizeEvent *event)
{
    QLabel::resizeEvent(event);
    refit();
}

void ErrorPillLabel::mouseReleaseEvent(QMouseEvent *event)
{
    if (!fullText_.isEmpty() && event->button() == Qt::LeftButton)
    {
        spellvision::shell::showWorkerFailure(this, QStringLiteral("Generation failed"), fullText_, QString());
        event->accept();
        return;
    }
    QLabel::mouseReleaseEvent(event);
}

} // namespace spellvision::generation
