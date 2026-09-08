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
// The error's own mark. A hint carries no prefix at all, which is the whole difference between
// the two paths below as far as layout is concerned.
const QString &warningPrefix()
{
    static const QString prefix = QString::fromUtf8("⚠  ");
    return prefix;
}
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
    text_ = oneLine_;
    prefix_ = warningPrefix();
    setToolTip(QStringLiteral("%1\n\nClick for the full message.").arg(fullText_));
    setCursor(Qt::PointingHandCursor);
    setText(prefix_ + oneLine_);
    refit();
}

QSize ErrorPillLabel::minimumSizeHint() const
{
    return QSize(minimumWidth(), QLabel::minimumSizeHint().height());
}

void ErrorPillLabel::setHint(const QString &text)
{
    // Everything setMessage does about ELISION, and nothing it does about being an error.
    //
    // oneLine_ and fullText_ stay empty, so hasMessage() is still answering "is an error showing"
    // and mouseReleaseEvent still falls through to QLabel instead of opening a failure dialog about
    // nothing. The cursor stays an arrow. The tooltip is the plain string rather than an invitation
    // to click -- and it is set HERE rather than by each caller, so that the full text is reachable
    // on hover by construction the moment the visible text is elided. Three callers used to set it
    // themselves and one did not.
    oneLine_.clear();
    fullText_.clear();
    text_ = text.trimmed();
    prefix_.clear();
    setToolTip(text_);
    setCursor(Qt::ArrowCursor);
    setText(text_);
    refit();
}

void ErrorPillLabel::clearMessage()
{
    oneLine_.clear();
    fullText_.clear();
    text_.clear();
    prefix_.clear();
    setCursor(Qt::ArrowCursor);
}

void ErrorPillLabel::refit()
{
    // text_, not oneLine_. Gated on oneLine_ this returned early for every readiness hint, so the
    // one widget in the app whose job is to stop a message being cut mid-word cut every hint
    // mid-word instead -- 183 px of text in a 66 px box on I2V at the half-screen width Doc 30
    // gates on, found by the responsive matrix the day it was pointed at the deeper clip scanner.
    if (text_.isEmpty())
        return;
    const QFontMetrics metrics(font());
    // One elision helper for the whole UI (widgets/ElidingLabel.h). The pill's reserve is its own
    // padding plus whatever prefix this message carries -- the warning glyph for an error, nothing
    // at all for a hint; the arithmetic is the same everywhere else.
    const int reserved = kHorizontalChrome + metrics.horizontalAdvance(prefix_);
    const QString shown = prefix_ + spellvision::widgets::elideForWidget(this, text_, Qt::ElideRight, reserved);
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
