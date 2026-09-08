// Task 1 of wave 3: the socket client used to walk its receive buffer BACKWARDS and keep exactly
// one JSON line, discarding every frame but the last. Nothing failed because of it -- every
// existing call site only ever wanted a single one-shot response -- but worker_tcp.py's
// EventEmitter writes one JSON object plus '\n' PER EVENT and flushes on every write
// (python/worker_tcp.py:58-66), so a real reply can already carry several frames on the wire
// whenever more than one event fires before the connection closes: a `ping` alone comes back as 3
// frames in 1.83ms. docs/SPELLVISION_WORKER_PROTOCOL.md's client-behaviour rule (line 475) is
// explicit: "The client should not collapse multiline worker output into a single unreadable
// blob." The backwards walk did exactly that, silently, because nothing was asking for more than
// one frame yet.
//
// This is the reader every later wave-3 task depends on, so it is proven directly against the
// buffer-parsing primitive rather than a live socket: feed it three complete frames and a trailing
// partial, and check the COUNT and the ORDER, not only the last frame's content. A regression back
// to last-only behaviour still produces a correct-LOOKING last frame -- its content equals the
// true last object either way -- so a content-only assertion would not catch it. The count is what
// catches it, and it is asserted first for that reason.

#include <QtTest>

#include <QByteArray>
#include <QJsonObject>

#include "workers/WorkerSocketClient.h"

using spellvision::workers::WorkerSocketClient;
using ParsedFrames = WorkerSocketClient::ParsedFrames;

class WorkerSocketFramesTest : public QObject
{
    Q_OBJECT

private slots:
    void threeFramesArriveInOrderAndThePartialIsRetained();
    void theRetainedPartialCompletesOnTheNextCall();
    void aBufferEndingExactlyOnANewlineLeavesNoRemainder();
    void blankLinesBetweenFramesAreIgnored();
};

void WorkerSocketFramesTest::threeFramesArriveInOrderAndThePartialIsRetained()
{
    // Three complete frames -- the shape a real run's progress stream takes -- plus a fourth
    // object the worker has started writing but not finished.
    const QByteArray buffer =
        "{\"type\":\"progress\",\"step\":1}\n"
        "{\"type\":\"progress\",\"step\":2}\n"
        "{\"type\":\"result\",\"step\":3}\n"
        "{\"type\":\"result\",\"step\":4,\"note\":\"still comi";

    const ParsedFrames parsed = WorkerSocketClient::parseJsonFrames(buffer);

    // The count first, and named explicitly: the old backwards walk produced exactly one frame
    // from this buffer, and that one frame's content (step 3, genuinely the last COMPLETE object)
    // is indistinguishable from frames.last() below. A test that checked only the last frame's
    // content would pass against that regression. This is the line that fails it instead.
    QCOMPARE(parsed.frames.size(), 3);

    // Order, checked independently of the count, using values written into the test literal above
    // rather than anything derived from the parser itself.
    QCOMPARE(parsed.frames.at(0).value(QStringLiteral("step")).toInt(), 1);
    QCOMPARE(parsed.frames.at(1).value(QStringLiteral("step")).toInt(), 2);
    QCOMPARE(parsed.frames.at(2).value(QStringLiteral("step")).toInt(), 3);

    // The third parsed frame's content matches the LAST complete object in the buffer -- so this
    // assertion alone would also pass under the old last-only behaviour, which is exactly why the
    // count above has to be the anchor, not this.
    QCOMPARE(parsed.frames.at(2).value(QStringLiteral("type")).toString(), QStringLiteral("result"));

    // The fourth object never closed, so it must not have been force-parsed into a frame...
    for (const QJsonObject &frame : parsed.frames)
        QVERIFY(frame.value(QStringLiteral("step")).toInt() != 4);

    // ...and it must not have been thrown away either: it sits in `remainder`, byte-for-byte,
    // waiting for the read that finishes it.
    QVERIFY2(!parsed.remainder.isEmpty(), "the trailing partial object must be retained");
    QVERIFY(parsed.remainder.contains("\"step\":4"));
    QVERIFY2(!parsed.remainder.contains('\n'),
             "the remainder is exactly the unterminated tail, not a whole extra line");
}

void WorkerSocketFramesTest::theRetainedPartialCompletesOnTheNextCall()
{
    // What readyRead actually does: parse what has arrived, keep the tail, append more bytes when
    // they land, parse again. Proven here as two calls to the same pure function.
    const QByteArray firstRead =
        "{\"type\":\"progress\",\"step\":1}\n"
        "{\"type\":\"result\",\"step\":2,\"tail\":\"unfinis";
    const ParsedFrames firstParsed = WorkerSocketClient::parseJsonFrames(firstRead);
    QCOMPARE(firstParsed.frames.size(), 1);
    QVERIFY(!firstParsed.remainder.isEmpty());

    const QByteArray secondRead = firstParsed.remainder + "hed\"}\n";
    const ParsedFrames secondParsed = WorkerSocketClient::parseJsonFrames(secondRead);

    QCOMPARE(secondParsed.frames.size(), 1);
    QCOMPARE(secondParsed.frames.at(0).value(QStringLiteral("step")).toInt(), 2);
    QCOMPARE(secondParsed.frames.at(0).value(QStringLiteral("tail")).toString(),
             QStringLiteral("unfinished"));
    QVERIFY(secondParsed.remainder.isEmpty());
}

void WorkerSocketFramesTest::aBufferEndingExactlyOnANewlineLeavesNoRemainder()
{
    const QByteArray buffer = "{\"type\":\"ping\"}\n{\"type\":\"pong\"}\n";
    const ParsedFrames parsed = WorkerSocketClient::parseJsonFrames(buffer);
    QCOMPARE(parsed.frames.size(), 2);
    QVERIFY(parsed.remainder.isEmpty());
}

void WorkerSocketFramesTest::blankLinesBetweenFramesAreIgnored()
{
    const QByteArray buffer = "{\"type\":\"a\"}\n\n{\"type\":\"b\"}\n";
    const ParsedFrames parsed = WorkerSocketClient::parseJsonFrames(buffer);
    QCOMPARE(parsed.frames.size(), 2);
    QCOMPARE(parsed.frames.at(0).value(QStringLiteral("type")).toString(), QStringLiteral("a"));
    QCOMPARE(parsed.frames.at(1).value(QStringLiteral("type")).toString(), QStringLiteral("b"));
}

QTEST_MAIN(WorkerSocketFramesTest)
#include "test_worker_socket_frames.moc"
