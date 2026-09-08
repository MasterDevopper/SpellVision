#pragma once

#include <QLabel>
#include <QSize>
#include <QString>

class QMouseEvent;
class QResizeEvent;

namespace spellvision::generation
{

// The pill beside Generate.
//
// A QLabel with a 280px cap and no elision showed "module 'worker_service' has no attribute 'res"
// and nothing else (2026-09-02) -- a user could neither read the error nor reach the rest of it.
// This label elides its one-line message to the width the action row actually gives it, keeps the
// full text in the tooltip, and opens it in the shared failure dialog on click. It is still a
// QLabel, so the readiness hints that share the widget keep working unchanged.
class ErrorPillLabel final : public QLabel
{
    Q_OBJECT

public:
    explicit ErrorPillLabel(QWidget *parent = nullptr);

    // oneLine is what the pill shows (elided as needed); fullText is what the tooltip and the
    // dialog carry. Both are kept until clearMessage(). An ERROR: it wears the warning glyph, its
    // tooltip offers the full text, its cursor is a pointing hand and a click opens the failure
    // dialog.
    void setMessage(const QString &oneLine, const QString &fullText);

    // A READINESS HINT -- "Choose an output folder to generate." -- which is not an error and must
    // not be dressed as one, but must still be elided to the width the row gives it.
    //
    // This exists because the pill only ever elided what arrived through setMessage(): refit()
    // early-returned on an empty oneLine_, and NINE call sites wrote the pill with a raw
    // QLabel::setText(), so every readiness hint bypassed elision entirely. Measured at the
    // half-screen width Doc 30 gates on: 183 px of text hard-cut in a 66 px box, on I2V. One of
    // those nine was updatePrimaryActionAvailability(), which is the site the responsive matrix
    // measures, and three were ~95-character "defaults applied" notices cut at EVERY width.
    //
    // Routing those callers at setMessage() would have been the wrong fix -- it would have given
    // every hint a warning glyph, a "Click for the full message." tooltip, a pointing-hand cursor
    // and a click that opens a failure dialog about nothing. So the hint keeps its own affordances
    // (plain text, plain tooltip, arrow cursor, inert click) and borrows only the elision.
    void setHint(const QString &text);

    void clearMessage();
    // "Is an ERROR showing", and it stays that: a hint leaves oneLine_ and fullText_ empty, so
    // neither this nor fullText() starts answering for one.
    bool hasMessage() const { return !oneLine_.isEmpty(); }
    QString fullText() const { return fullText_; }

    // QLabel's default answer, for a non-wrapped single line, is the full un-elided text extent --
    // right for a plain label, wrong for this one: refit() elides to whatever width the row gives
    // it, and the constructor's setMinimumWidth(60)/setMaximumWidth(420) are the real, enforced
    // contract. Reporting the un-elided extent as our own minimum makes a normal in-contract
    // squeeze (down to 60px) read as a clipped control to anything that compares minimumSizeHint()
    // against actual size, the way Doc 30's responsive-matrix gate does.
    QSize minimumSizeHint() const override;

protected:
    void resizeEvent(QResizeEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;

private:
    void refit();

    QString oneLine_;   // the ERROR's one-line form, empty for a hint
    QString fullText_;  // the ERROR's full form, empty for a hint
    QString text_;      // what refit() elides -- set by BOTH paths, and the reason refit works now
    QString prefix_;    // the warning glyph for an error, empty for a hint
};

} // namespace spellvision::generation
