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
    // dialog carry. Both are kept until clearMessage().
    void setMessage(const QString &oneLine, const QString &fullText);
    void clearMessage();
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

    QString oneLine_;
    QString fullText_;
};

} // namespace spellvision::generation
