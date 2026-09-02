#pragma once

#include <QLabel>
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

protected:
    void resizeEvent(QResizeEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;

private:
    void refit();

    QString oneLine_;
    QString fullText_;
};

} // namespace spellvision::generation
