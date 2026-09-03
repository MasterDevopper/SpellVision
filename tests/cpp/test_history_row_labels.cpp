// A history row's mode-dependent columns, which used to be two implementations of one rule.
//
// History v1 flattened image results onto a video-shaped row, so the UI put an image's step count
// in the Duration column and a T2I render read as "35 frames". Schema v2 fixed the record; the rule
// for what each column then SAYS existed twice -- `history_schema.detail_label`, which had no
// production caller and only its own test, and a hand-rolled copy inline in T2VHistoryPage. The
// tested one was unused and the used one was untested, and they agreed by coincidence.
//
// These two assertions came across from that Python test, so the coverage moved with the rule
// instead of being deleted with it.

#include <QtTest>

#include "history/HistoryRowLabels.h"

using spellvision::history::detailLabel;
using spellvision::history::stackLabel;

class HistoryRowLabelsTest : public QObject
{
    Q_OBJECT

private slots:
    void animageRowSaysStepsNotDuration();
    void aVideoRowSaysDurationNotSteps();
    void aRowWithNothingToSayNamesItsModeRatherThanGoingBlank();
    void theStackColumnFollowsTheSameSplit();
};

void HistoryRowLabelsTest::animageRowSaysStepsNotDuration()
{
    QCOMPARE(detailLabel(true, QStringLiteral("t2i"), QStringLiteral("35"), QString()),
             QStringLiteral("T2I • 35 steps"));
    // Even when a duration is present on the record -- an image row must never borrow it, which is
    // the defect the whole v2 schema exists to end.
    QCOMPARE(detailLabel(true, QStringLiteral("t2i"), QStringLiteral("35"),
                         QStringLiteral("81 frames @ 16 fps (5.1s)")),
             QStringLiteral("T2I • 35 steps"));
}

void HistoryRowLabelsTest::aVideoRowSaysDurationNotSteps()
{
    QCOMPARE(detailLabel(false, QStringLiteral("t2v"), QStringLiteral("35"),
                         QStringLiteral("81 frames @ 16 fps (5.1s)")),
             QStringLiteral("81 frames @ 16 fps (5.1s)"));
}

void HistoryRowLabelsTest::aRowWithNothingToSayNamesItsModeRatherThanGoingBlank()
{
    QCOMPARE(detailLabel(true, QStringLiteral("i2i"), QString(), QString()), QStringLiteral("I2I"));
    QCOMPARE(detailLabel(false, QStringLiteral("i2v"), QString(), QString()), QStringLiteral("I2V"));
    // A row whose mode never made it onto the record still has to say which KIND it is: a blank
    // cell reads as a broken row, and the media type is always known.
    QCOMPARE(detailLabel(true, QString(), QString(), QString()), QStringLiteral("IMAGE"));
    QCOMPARE(detailLabel(false, QString(), QString(), QString()), QStringLiteral("VIDEO"));
}

void HistoryRowLabelsTest::theStackColumnFollowsTheSameSplit()
{
    QCOMPARE(stackLabel(true, QStringLiteral("anima-base-v1.0"), QStringLiteral("Wan high/low")),
             QStringLiteral("anima-base-v1.0"));
    QCOMPARE(stackLabel(false, QStringLiteral("anima-base-v1.0"), QStringLiteral("Wan high/low")),
             QStringLiteral("Wan high/low"));
    QCOMPARE(stackLabel(true, QString(), QString()), QStringLiteral("image"));
    QCOMPARE(stackLabel(false, QString(), QString()), QStringLiteral("Wan stack"));
}

QTEST_MAIN(HistoryRowLabelsTest)
#include "test_history_row_labels.moc"
