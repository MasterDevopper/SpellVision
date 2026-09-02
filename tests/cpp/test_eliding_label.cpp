// A value the UI did not choose the length of must elide, and must not demand its own width.
//
// Both halves are load-bearing, and each was a live defect on 2026-09-02:
//
//   * the LoRA name was cut mid-glyph in a ~215px card. It had `setWordWrap(true)`, which is not
//     elision -- and for a name like "Realistic_Anime_Illustrious_v2" it is not even wrapping,
//     because U+005F is not a UAX-14 break opportunity. The existing row test passed because every
//     fixture name happened to contain a hyphen (class HY), which IS a break opportunity.
//   * the video caption wrapped a four-line block, including the full absolute path, inside the
//     video preview's own height budget.
//
// So the fixture text here has NO break opportunity anywhere in it. That is the whole point: a rig
// whose fixture can wrap cannot tell wrapping apart from eliding.

#include <QtTest>

#include <QFontMetrics>
#include <QHBoxLayout>
#include <QLabel>
#include <QWidget>

#include "widgets/ElidingLabel.h"

using spellvision::widgets::ElidingLabel;
using spellvision::widgets::elideForWidget;

namespace
{
// One token, no spaces, no hyphens: nothing a layout may break.
const QString kUnbreakable = QStringLiteral("Realistic_Anime_Illustrious_v2_fp16_e12_final_000008");
} // namespace

class ElidingLabelTest : public QObject
{
    Q_OBJECT

private slots:
    void theTextFitsTheWidthItIsGiven();
    void whatDoesNotFitGetsAnEllipsisAndAToolTip();
    void itDoesNotDemandItsNaturalWidth();
    void aWidthlessLabelKeepsItsTextRatherThanBecomingAnEllipsis();
    void middleElisionKeepsTheHeadAndTheTail();
    void theHelperReservesWhatTheCallerAlreadySpent();
};

void ElidingLabelTest::theTextFitsTheWidthItIsGiven()
{
    QWidget host;
    auto *label = new ElidingLabel(&host);
    label->setFullText(kUnbreakable);
    label->resize(140, 20);
    QCoreApplication::processEvents();

    const QFontMetrics metrics(label->fontMetrics());
    QVERIFY2(metrics.horizontalAdvance(label->text()) <= label->width(),
             qPrintable(QStringLiteral("shown text is %1px wide in a %2px label")
                            .arg(metrics.horizontalAdvance(label->text()))
                            .arg(label->width())));
}

void ElidingLabelTest::whatDoesNotFitGetsAnEllipsisAndAToolTip()
{
    QWidget host;
    auto *label = new ElidingLabel(&host);
    label->setFullText(kUnbreakable);
    label->resize(120, 20);
    QCoreApplication::processEvents();

    QVERIFY2(label->text() != kUnbreakable, "the text was not elided at all -- it is being clipped");
    QVERIFY2(label->text().contains(QChar(0x2026)), "elided text carries no ellipsis, so the cut is invisible");
    // The value is never lost: the full text is one hover away.
    QCOMPARE(label->toolTip(), kUnbreakable);
    QCOMPARE(label->fullText(), kUnbreakable);
}

void ElidingLabelTest::itDoesNotDemandItsNaturalWidth()
{
    // Eliding alone would not have fixed the LoRA card: a wrapped QLabel's minimumSizeHint is its
    // widest unbreakable word, so the card still overflowed its scroll viewport.
    //
    // Asserted through a LAYOUT, which is what the defect was about. QLabel::minimumSizeHint() is
    // the label's own opinion (97px here for the long value, 48px for a short one), but a layout
    // asks qSmartMinSize, which ignores that opinion for a horizontally-Ignored policy -- so the
    // opinion is not the property. The first version of this case compared the two hints and
    // failed while the widget was behaving correctly.
    QWidget shortHost;
    auto *shortLayout = new QHBoxLayout(&shortHost);
    shortLayout->setContentsMargins(0, 0, 0, 0);
    auto *shortLabel = new ElidingLabel(&shortHost);
    shortLabel->setFullText(QStringLiteral("v1"));
    shortLayout->addWidget(shortLabel);

    QWidget longHost;
    auto *longLayout = new QHBoxLayout(&longHost);
    longLayout->setContentsMargins(0, 0, 0, 0);
    auto *longLabel = new ElidingLabel(&longHost);
    longLabel->setFullText(kUnbreakable);
    longLayout->addWidget(longLabel);

    const QFontMetrics metrics(longLabel->fontMetrics());
    QVERIFY2(longLayout->minimumSize().width() == shortLayout->minimumSize().width(),
             qPrintable(QStringLiteral("a long value raises the layout minimum to %1px where a short one asks %2px")
                            .arg(longLayout->minimumSize().width())
                            .arg(shortLayout->minimumSize().width())));
    // 215px is the width the LoRA card actually gets at a half-screen window.
    QVERIFY2(longLayout->minimumSize().width() <= 215,
             qPrintable(QStringLiteral("layout minimum %1px exceeds the card it lives in (the value itself is %2px)")
                            .arg(longLayout->minimumSize().width())
                            .arg(metrics.horizontalAdvance(kUnbreakable))));
    QVERIFY(!longLabel->wordWrap());
}

void ElidingLabelTest::aWidthlessLabelKeepsItsTextRatherThanBecomingAnEllipsis()
{
    // Eliding against a zero width returns a lone ellipsis and the value is simply gone -- the
    // cold-widget failure mode that made the canvas cap converge on 48x86 in the first place.
    //
    // Asserted on the helper, because an ElidingLabel cannot reach zero width: its own 48px floor
    // holds it up (a resize(0, ...) is clamped, which is how the first version of this case
    // "failed"). Other callers pass widgets with no such floor.
    QWidget cold;
    cold.resize(0, 20);
    QCOMPARE(elideForWidget(&cold, kUnbreakable, Qt::ElideRight), kUnbreakable);
}

void ElidingLabelTest::middleElisionKeepsTheHeadAndTheTail()
{
    QWidget host;
    auto *label = new ElidingLabel(&host, Qt::ElideMiddle);
    label->setFullText(kUnbreakable);
    label->resize(120, 20);
    QCoreApplication::processEvents();

    // A LoRA is told apart by its model (head) and its version (tail); the middle is what repeats.
    QVERIFY(label->text().startsWith(QStringLiteral("Real")));
    QVERIFY(label->text().endsWith(QStringLiteral("8")));
}

void ElidingLabelTest::theHelperReservesWhatTheCallerAlreadySpent()
{
    // ErrorPillLabel reserves its padding plus a warning glyph; the telemetry bar reserves 6px.
    // Same helper, so the reserve is the only thing that differs.
    QWidget widget;
    widget.resize(200, 20);
    const QString wide = elideForWidget(&widget, kUnbreakable, Qt::ElideRight, 0);
    const QString narrow = elideForWidget(&widget, kUnbreakable, Qt::ElideRight, 120);
    const QFontMetrics metrics(widget.fontMetrics());
    QVERIFY(metrics.horizontalAdvance(narrow) < metrics.horizontalAdvance(wide));
    // A reserve larger than the widget must not produce an ellipsis-only string.
    QCOMPARE(elideForWidget(&widget, kUnbreakable, Qt::ElideRight, 500), kUnbreakable);
}

QTEST_MAIN(ElidingLabelTest)
#include "test_eliding_label.moc"
