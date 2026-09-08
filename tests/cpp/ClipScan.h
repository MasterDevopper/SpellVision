#pragma once
//
// THE CLIPPING SCANNER -- one copy, for every C++ test that asks whether a control has been squeezed
// below what it needs.
//
// It lived twice, under one name, asking two different questions. `test_shell_layout.cpp` built the
// better copy on this wave (a layout walk that sees nested layouts, and a font-metric predicate for
// labels that is immune to the minimumSizeHint cache); `test_responsive_matrix.cpp` -- the surface
// Doc 28 lists as a RELEASE GATE -- kept the shallow one, so 36 of its 38 cells asked the weaker
// question. Two functions with one name in one directory is the shape that produced that, so there
// is now one function.
//
// Everything below is the shell copy verbatim; nothing was softened to make the gate green.
//
#include <QAbstractScrollArea>
#include <QFontMetrics>
#include <QLabel>
#include <QLayout>
#include <QList>
#include <QRect>
#include <QSize>
#include <QString>
#include <QStringList>
#include <QTextDocumentFragment>
#include <QVector>
#include <QWidget>

namespace spellvision::testscan
{
// What a single-line QLabel's TEXT actually needs, against the box it has to draw it in.
//
// Four diagnoses of the same number were wrong before this one, so the reason is written out.
// `width() < minimumSizeHint().width()` IS a valid clip predicate -- sizeForWidth ends with
// `.expandedTo(q->minimumSize())`, which clamps UPWARD only and so cannot hide a clip, and the
// `qMax(w, q->minimumWidth())` line it opens with is inert here (minimumSizeHint asks
// sizeForWidth(0), and without word wrap that w only reaches fm.boundingRect, which ignores it).
// The defect is the CACHE: the hint sits behind valid_hints, cleared by setText/setFont/
// setAlignment and NOT by setFixedWidth. So a scan that resizes first reads the PREVIOUS rung --
// which is why five "shortfalls" came out as pick()'s mid rungs to the pixel (99/90/73/118/68),
// and why an earlier font A/B "proving" a Plex regression was really measuring cache invalidation,
// setFont being one of the calls that clears the flag.
//
// horizontalAdvance() against contentsRect() asks the real question, is independent of the widget's
// width, and stays put when the ladder moves. Rich text is flattened first -- the backend health
// label is two coloured dots in HTML, whose markup would otherwise be measured as characters.
// A label's text as CHARACTERS. The backend health chip is two coloured dots in HTML, whose markup
// would otherwise be measured, printed and keyed as if it were text.
inline QString plainTextOf(const QLabel *label)
{
    return label->textFormat() == Qt::RichText
               ? QTextDocumentFragment::fromHtml(label->text()).toPlainText()
               : label->text();
}

inline int textOverflowPx(const QLabel *label)
{
    if (label->wordWrap() || label->text().trimmed().isEmpty())
        return 0;
    const int advance = QFontMetrics(label->font()).horizontalAdvance(plainTextOf(label));
    return advance - label->contentsRect().width();
}

inline bool insideScrollArea(const QWidget *widget)
{
    for (const QWidget *w = widget; w != nullptr; w = w->parentWidget())
        if (qobject_cast<const QAbstractScrollArea *>(w) != nullptr)
            return true;
    return false;
}

inline bool layoutHolds(const QLayout *layout, const QWidget *widget)
{
    if (layout == nullptr)
        return false;
    for (int index = 0; index < layout->count(); ++index)
    {
        QLayoutItem *item = layout->itemAt(index);
        if (item == nullptr)
            continue;
        if (item->widget() == widget)
            return true;
        if (layoutHolds(item->layout(), widget))
            return true;
    }
    return false;
}

// Whether this widget's size is its parent layout's responsibility -- and the RECORDED BLIND SPOT of
// the version test_responsive_matrix.cpp used to carry, closed. That one asked
// parent->layout()->indexOf(w), and QLayout::indexOf sees only a layout's OWN direct items: a widget
// inside a nested QHBoxLayout that was addLayout()ed into its parent's column answers "not layout
// managed" and is silently skipped. Walking the parent's whole layout tree is the same question
// asked of the structure that actually exists. The matrix asks THIS one now.
inline bool layoutManagedDeep(const QWidget *widget)
{
    const QWidget *parent = widget->parentWidget();
    if (parent == nullptr || parent->layout() == nullptr)
        return false;
    return layoutHolds(parent->layout(), widget);
}

// A control squeezed below the size it says it needs. minimumSizeHint, not sizeHint: being smaller
// than a preference is normal, being smaller than a MINIMUM is what a user sees as a cut-off label.
//
// The WIDGET comes back with its key, not only a string, so an offender keyed by a class and an
// EMPTY object name can still be checked against the specific widget it is claimed to be. "QWidget(-)"
// as a bare allowance entry would pardon every unnamed QWidget in the shell.
struct Offender
{
    QWidget *widget = nullptr;
    QString key;      // Class(objectName) -- the identity an allowance is keyed on
    QString detail;   // the measurement plus the ancestry that lost the space
};

inline QVector<Offender> clippedControls(QWidget *root)
{
    QVector<Offender> offenders;
    for (QWidget *w : root->findChildren<QWidget *>())
    {
        if (!w->isVisible() || w->size().isEmpty())
            continue;
        if (insideScrollArea(w))
            continue;
        if (!layoutManagedDeep(w))
            continue;
        // A LABEL is asked about its text, not about its size hint -- see textOverflowPx. Everything
        // else keeps minimumSizeHint, which for a container IS composed from its children and means
        // what it says.
        if (const auto *label = qobject_cast<const QLabel *>(w))
        {
            const int overflow = textOverflowPx(label);
            if (overflow <= 0)
                continue;
            Offender offender;
            offender.widget = w;
            offender.key = QStringLiteral("QLabel(%1)")
                               .arg(w->objectName().isEmpty() ? QStringLiteral("-") : w->objectName());
            // The STRING is part of the diagnosis and part of the identity a baseline is keyed on:
            // "QLabel(X) needs 117 px more" names a widget, and the same widget showing a different
            // string is a different finding.
            offender.detail = QStringLiteral("%1 text \"%2\" needs %3 px more than its %4 px contents box")
                                  .arg(offender.key, plainTextOf(label))
                                  .arg(overflow).arg(label->contentsRect().width());
            offenders.append(offender);
            continue;
        }
        const QSize need = w->minimumSizeHint();
        if (!need.isValid())
            continue;
        if (w->width() >= need.width() && w->height() >= need.height())
            continue;

        // The ancestry, not just the victim: "48x24 < min 50x24" says a label is squeezed and
        // nothing about WHICH container lost the width.
        QStringList chain;
        for (QWidget *up = w->parentWidget(); up && up != root; up = up->parentWidget())
            chain << QStringLiteral("%1(%2) %3x%4")
                         .arg(QString::fromLatin1(up->metaObject()->className()),
                              up->objectName().isEmpty() ? QStringLiteral("-") : up->objectName())
                         .arg(up->width()).arg(up->height());

        Offender offender;
        offender.widget = w;
        offender.key = QStringLiteral("%1(%2)")
                           .arg(QString::fromLatin1(w->metaObject()->className()),
                                w->objectName().isEmpty() ? QStringLiteral("-") : w->objectName());
        offender.detail = QStringLiteral("%1 %2x%3 < min %4x%5  [up: %6]")
                              .arg(offender.key)
                              .arg(w->width()).arg(w->height()).arg(need.width()).arg(need.height())
                              .arg(chain.mid(0, 4).join(QStringLiteral(" < ")));
        offenders.append(offender);
    }
    return offenders;
}

} // namespace spellvision::testscan
