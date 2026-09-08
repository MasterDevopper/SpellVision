#include "CockpitLayout.h"

#include "CockpitInspector.h"
#include "../ThemeManager.h"

#include <QBoxLayout>
#include <QEvent>
#include <QFontMetrics>
#include <QFrame>
#include <QTextDocument>
#include <QTextEdit>
#include <QTimer>

#include <utility>

namespace spellvision::generation
{
namespace
{
// The slack the cockpit has always added on top of the type metrics so a three-line envelope does
// not clip its own descenders. Carried across with the formula rather than left behind in the page.
constexpr int kEnvelopeSlack = 6;
} // namespace

CockpitLayout::CockpitLayout(QFrame *promptCard,
                             QTextEdit *promptEdit,
                             QTextEdit *negativeEdit,
                             CockpitInspector *inspector,
                             QObject *parent)
    : QObject(parent)
    , promptCard_(promptCard)
    , inspector_(inspector)
{
    if (promptEdit)
        edits_.append(promptEdit);
    if (negativeEdit)
        edits_.append(negativeEdit);
    for (QTextEdit *edit : std::as_const(edits_))
        edit->installEventFilter(this);
}

void CockpitLayout::applyPromptEnvelope(QTextEdit *edit, int lines)
{
    if (!edit || lines < 1)
        return;
    edit->ensurePolished();
    const QFontMetrics metrics = edit->fontMetrics();
    const int height = metrics.lineSpacing() * lines
        + 2 * static_cast<int>(edit->document()->documentMargin())
        + 2 * edit->frameWidth()
        + kEnvelopeSlack;
    edit->setMinimumHeight(height);
    edit->setMaximumHeight(height);
    edit->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    edit->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    edit->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
}

// IDEMPOTENT BY ASKING, like the shell's own switch. Both halves re-assert their shape every time
// rather than returning early on a remembered flag: a page that is built while the app is already
// in Canvas gets this call from its own constructor AND from MainWindow's tail, and the second must
// be free rather than confusing.
void CockpitLayout::applyShellLayout(spellvision::shell::ShellLayout::Layout layout)
{
    canvas_ = layout == spellvision::shell::ShellLayout::Layout::Canvas;
    if (inspector_)
        inspector_->setCollapsed(canvas_);
    // A switch made while the user is mid-sentence does not fold the sentence away under them; the
    // fold arrives when the prompt loses the focus, which is the same rule the focus filter follows.
    setFolded(canvas_ && !aPromptHasFocus());
}

// The whole fold, and every line of it is reversible. The heights come back out of
// applyPromptEnvelope, so unfolding restores the height construction gave rather than a height
// something remembered; the card's padding comes back to the Snug it was built with. The negative
// field folds WITH the prompt when it is open, or a "single line" would be a line plus a paragraph.
void CockpitLayout::setFolded(bool folded)
{
    folded_ = folded;
    for (QTextEdit *edit : std::as_const(edits_))
        applyPromptEnvelope(edit, folded ? kFoldedLines : kPromptLines);

    if (auto *cardLayout = promptCard_ ? qobject_cast<QBoxLayout *>(promptCard_->layout()) : nullptr)
    {
        auto &theme = ThemeManager::instance();
        const int side = theme.spacing(ThemeManager::Spacing::Snug);
        const int ends = theme.spacing(folded ? ThemeManager::Spacing::Tight
                                              : ThemeManager::Spacing::Snug);
        cardLayout->setContentsMargins(side, ends, side, ends);
    }
    if (promptCard_)
        promptCard_->updateGeometry();
}

bool CockpitLayout::aPromptHasFocus() const
{
    for (const QTextEdit *edit : std::as_const(edits_))
        if (edit->hasFocus())
            return true;
    return false;
}

bool CockpitLayout::eventFilter(QObject *watched, QEvent *event)
{
    if (canvas_)
    {
        if (event->type() == QEvent::FocusIn)
        {
            setFolded(false);
        }
        else if (event->type() == QEvent::FocusOut)
        {
            // Deferred by one turn on purpose -- see the header. Tabbing from the prompt to the
            // negative field is two events, and the fold must not happen between them.
            QTimer::singleShot(0, this, [this]() {
                if (canvas_ && !aPromptHasFocus())
                    setFolded(true);
            });
        }
    }
    return QObject::eventFilter(watched, event);
}

} // namespace spellvision::generation
