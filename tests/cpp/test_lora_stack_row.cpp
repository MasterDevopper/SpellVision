// The LoRA stack row fits the card it actually gets.
//
// The Model tab's LoRA cards are ~215px wide at a half-screen window and ~300px at 1600px. Four
// full-word buttons (Change / Up / Down / Remove) in one row clipped to "hang" / "low" / "mo" at
// both -- visible in the 2026-09-02 screenshot pass at every window narrower than 1600px. The
// responsive matrix could not see it: the cards live inside the inspector's scroll area, and the
// matrix skips scroll-area children on purpose (a scroll area is allowed to be smaller than its
// contents). So the row gets its own test, at the width it really gets, and it asks the question
// the matrix asks everywhere else: is any button narrower than it says it needs?
//
// The fix moved the reorder arrows beside the weight spinner as fixed-width glyph buttons. This
// test also pins the affordance that came with it: the first row cannot move up and the last row
// cannot move down, which the old always-enabled Up/Down never said.

#include <QtTest>

#include <QApplication>
#include <QCheckBox>
#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>
#include <QVector>
#include <QWidget>

#include "assets/LoraStackController.h"
#include "widgets/ElidingLabel.h"

using spellvision::assets::LoraStackBindings;
using spellvision::assets::LoraStackController;
using spellvision::assets::LoraStackEntry;

namespace
{

struct Rig
{
    QWidget host;
    QVector<LoraStackEntry> stack;
    LoraStackController controller;
};

void build(Rig &rig, int cardWidth)
{
    // The host stands in for the inspector column: the card's OWN margins are the only ones the
    // real thing has, so the host adds none (a default 11px margin would take 22px the product
    // never loses).
    rig.host.setFixedWidth(cardWidth);
    auto *layout = new QVBoxLayout(&rig.host);
    layout->setContentsMargins(0, 0, 0, 0);
    auto *summary = new QLabel(&rig.host);
    auto *clear = new QPushButton(QStringLiteral("Clear Stack"), &rig.host);
    clear->hide();

    LoraStackBindings bindings;
    bindings.container = &rig.host;
    bindings.layout = layout;
    bindings.summaryLabel = summary;
    bindings.clearButton = clear;
    rig.controller.bind(&rig.stack, bindings);
    rig.controller.addOrUpdate(QStringLiteral("D:/loras/a.safetensors"), QStringLiteral("DetailerILv2-000008"), 2.0, false);
    rig.controller.addOrUpdate(QStringLiteral("D:/loras/b.safetensors"), QStringLiteral("Realistic_Anime_-_Illustrious"), 0.5, true);
    rig.controller.addOrUpdate(QStringLiteral("D:/loras/c.safetensors"), QStringLiteral("Curvier"), 1.0, false);
    // A name with NO break opportunity anywhere in it. Every other fixture here contains a hyphen
    // (UAX-14 class HY), which is why the wrapped label passed this test while cutting real names
    // mid-glyph on screen: underscores are not break opportunities, so wrap had nothing to do.
    rig.controller.addOrUpdate(QStringLiteral("D:/loras/d.safetensors"),
                               QStringLiteral("Realistic_Anime_Illustrious_v2_fp16_e12_final_000008"), 0.8, true);

    rig.host.show();
    QVERIFY(QTest::qWaitForWindowExposed(&rig.host));
    // rebuild() retires the previous cards with deleteLater(); processEvents() alone never runs
    // deferred deletes, so without this the rig measures three stale, never-laid-out cards.
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    QApplication::processEvents();
}

// The width a button must have: its explicit minimum when one was set (the 32px glyph arrows),
// else what the style says it needs.
int requiredWidth(const QPushButton *button)
{
    return button->minimumWidth() > 0 ? button->minimumWidth() : button->minimumSizeHint().width();
}

} // namespace

class LoraStackRowTest : public QObject
{
    Q_OBJECT

private slots:
    void every_button_fits_at_half_screen_width()
    {
        Rig rig;
        build(rig, 215);

        const QList<QPushButton *> buttons = rig.host.findChildren<QPushButton *>();
        // Geometry dump first: a bare "34 < 81" says nothing about which container lost the width.
        qWarning() << "host" << rig.host.width() << "layout margins" << rig.host.layout()->contentsMargins();
        for (QWidget *child : rig.host.findChildren<QWidget *>())
        {
            if (child->parentWidget() == &rig.host && child->isVisible())
                qWarning() << "  card" << child->metaObject()->className() << child->objectName() << child->geometry();
        }
        for (QPushButton *button : buttons)
        {
            if (button->isVisible())
                qWarning() << "    button" << button->text() << "geom" << button->geometry() << "needs" << requiredWidth(button)
                           << "parent" << button->parentWidget()->width();
        }
        int checked = 0;
        for (QPushButton *button : buttons)
        {
            if (!button->isVisible())
                continue;
            ++checked;
            const int textWidth = button->fontMetrics().horizontalAdvance(button->text());
            QVERIFY2(button->width() >= requiredWidth(button),
                     qPrintable(QStringLiteral("'%1' is %2px wide against a %3px minimum")
                                    .arg(button->text()).arg(button->width()).arg(requiredWidth(button))));
            QVERIFY2(button->width() >= textWidth + 6,
                     qPrintable(QStringLiteral("'%1' text needs %2px, button is %3px")
                                    .arg(button->text()).arg(textWidth).arg(button->width())));
        }
        // Four rows x (Change, Remove, up, down).
        QCOMPARE(checked, 16);

        // The name row: the enabled box says "Enabled" to a screen reader without spending the
        // width on the word, and the name keeps enough room to be read.
        const QList<QCheckBox *> boxes = rig.host.findChildren<QCheckBox *>();
        QCOMPARE(boxes.size(), 4);
        for (const QCheckBox *box : boxes)
        {
            QVERIFY(box->text().isEmpty());
            QCOMPARE(box->accessibleName(), QStringLiteral("Enabled"));
            QVERIFY(!box->toolTip().isEmpty());
        }
        int namesChecked = 0;
        for (const QLabel *label : rig.host.findChildren<QLabel *>())
        {
            if (label->objectName() != QStringLiteral("SectionBody"))
                continue;
            ++namesChecked;
            // 79px measured at 215: enough room for a name to read. Below ~70 nothing useful of it
            // is left.
            QVERIFY2(label->width() >= 70,
                     qPrintable(QStringLiteral("name '%1' has only %2px").arg(label->text()).arg(label->width())));
            // The question that matters, and the one this test did not ask before: does the text
            // the user SEES fit the label? "label is wide" and "the name is readable" are different
            // facts, and a hard-clipped name satisfies the first.
            const int shownWidth = label->fontMetrics().horizontalAdvance(label->text());
            QVERIFY2(shownWidth <= label->width(),
                     qPrintable(QStringLiteral("name '%1' needs %2px in a %3px label -- it is being clipped, not elided")
                                    .arg(label->text()).arg(shownWidth).arg(label->width())));
            // Anything that did not fit says so, and the full value stays in the tooltip.
            const auto *eliding = qobject_cast<const spellvision::widgets::ElidingLabel *>(label);
            QVERIFY2(eliding != nullptr, "the name is a plain QLabel again -- it will clip, not elide");
            if (eliding->fullText() != label->text())
                QVERIFY2(label->text().contains(QChar(0x2026)),
                         qPrintable(QStringLiteral("'%1' was shortened with no ellipsis").arg(label->text())));
            QVERIFY(!eliding->toolTip().isEmpty());
        }
        QCOMPARE(namesChecked, 4);
    }

    void the_arrows_know_the_ends_of_the_stack()
    {
        Rig rig;
        build(rig, 300);

        QList<QPushButton *> ups;
        QList<QPushButton *> downs;
        for (QPushButton *button : rig.host.findChildren<QPushButton *>())
        {
            if (button->text() == QStringLiteral("▲"))
                ups << button;
            else if (button->text() == QStringLiteral("▼"))
                downs << button;
        }
        QCOMPARE(ups.size(), 4);
        QCOMPARE(downs.size(), 4);
        QVERIFY(!ups.first()->isEnabled());
        QVERIFY(ups.at(1)->isEnabled());
        QVERIFY(ups.at(2)->isEnabled());
        QVERIFY(ups.last()->isEnabled());
        QVERIFY(downs.first()->isEnabled());
        QVERIFY(downs.at(1)->isEnabled());
        QVERIFY(downs.at(2)->isEnabled());
        QVERIFY(!downs.last()->isEnabled());
        QVERIFY(!ups.first()->toolTip().isEmpty());
    }
};

QTEST_MAIN(LoraStackRowTest)
#include "test_lora_stack_row.moc"
