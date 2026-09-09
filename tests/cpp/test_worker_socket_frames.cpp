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
//
// manyWellFormedFramesTripTheLifetimeCap below is different in kind: it drives WorkerSocketClient
// ::send() over a REAL loopback socket, not the pure parsing primitive. Frame delivery works by
// draining `response` down to its unparsed remainder after every readyRead; making that drain
// correct silently changed what the 8 MiB cap bounds. Before, `response` accumulated every byte
// ever received on the connection, so the cap bounded total lifetime traffic. Naively reusing
// `response.size()` after the drain bounds only one batch's new bytes plus a small leftover instead
// -- an endless stream of well-formed lines never trips it. Nothing else in this suite opens a real
// socket against WorkerSocketClient::send() at all, which is the only reason that would have
// shipped unnoticed.

#include <QtTest>

#include <QByteArray>
#include <QCoreApplication>
#include <QElapsedTimer>
#include <QHostAddress>
#include <QJsonObject>
#include <QTcpServer>
#include <QTcpSocket>

#include "workers/WorkerSocketClient.h"

using spellvision::workers::WorkerSocketClient;
using ParsedFrames = WorkerSocketClient::ParsedFrames;

class WorkerSocketFramesTest : public QObject
{
    Q_OBJECT

private slots:
    void cleanup();

    void threeFramesArriveInOrderAndThePartialIsRetained();
    void theRetainedPartialCompletesOnTheNextCall();
    void aBufferEndingExactlyOnANewlineLeavesNoRemainder();
    void blankLinesBetweenFramesAreIgnored();
    void manyWellFormedFramesTripTheLifetimeCap();
};

void WorkerSocketFramesTest::cleanup()
{
    // Only manyWellFormedFramesTripTheLifetimeCap sets these; harmless to clear unconditionally
    // after every case so a failure partway through never leaks environment into the next test.
    qunsetenv("SPELLVISION_WORKER_HOST");
    qunsetenv("SPELLVISION_WORKER_PORT");
}

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

void WorkerSocketFramesTest::manyWellFormedFramesTripTheLifetimeCap()
{
    QTcpServer server;
    QVERIFY(server.listen(QHostAddress::LocalHost));

    qputenv("SPELLVISION_WORKER_HOST", "127.0.0.1");
    qputenv("SPELLVISION_WORKER_PORT", QByteArray::number(server.serverPort()));

    QObject context;
    QJsonObject response;
    QString diagnostics;
    bool startedOk = false;
    bool completed = false;

    // A buggy build never trips the cap and falls through to this timeout instead -- the test's
    // own wait bound below must stay comfortably LONGER than this, or a not-yet-timed-out buggy
    // run reads as "never completed" for the wrong reason (observed directly: a 3000ms wait
    // against this same 5000ms value reported completed=false, startedOk=false, diagnostics='' --
    // true, but only because nothing had happened yet, not because nothing ever would).
    constexpr int kSendTimeoutMs = 3000;
    WorkerSocketClient::send(
        &context, QJsonObject{{QStringLiteral("command"), QStringLiteral("ping")}}, kSendTimeoutMs,
        [&](const QJsonObject &r, const QString &d, bool ok) {
            response = r;
            diagnostics = d;
            startedOk = ok;
            completed = true;
        });

    // Accept and drain the client's one-line request by spinning the event loop rather than
    // QTcpServer/QTcpSocket's blocking waitFor* calls: those wait on their OWN socket becoming
    // ready and do not reliably also dispatch the CLIENT socket's queued `connected` signal (the
    // thing that makes WorkerSocketClient actually write its request) on this thread in between --
    // observed directly, not assumed: waitForNewConnection alone returned true (the OS-level
    // loopback handshake completes independently of Qt's signal dispatch) while the client had not
    // yet been given a turn to write anything, so the subsequent waitForReadyRead reliably timed
    // out. processEvents() drives both sockets uniformly.
    QTcpSocket *serverSide = nullptr;
    {
        QElapsedTimer acceptTimer;
        acceptTimer.start();
        while (!serverSide && acceptTimer.elapsed() < 5000)
        {
            QCoreApplication::processEvents(QEventLoop::AllEvents, 20);
            serverSide = server.nextPendingConnection();
        }
    }
    QVERIFY(serverSide);

    {
        QElapsedTimer readTimer;
        readTimer.start();
        while (serverSide->bytesAvailable() == 0 && readTimer.elapsed() < 5000)
            QCoreApplication::processEvents(QEventLoop::AllEvents, 20);
    }
    QVERIFY2(serverSide->bytesAvailable() > 0, "the client never wrote its request line");
    serverSide->readAll();

    // Far past the 8 MiB cap, entirely in small, individually well-formed JSON lines, written in
    // chunks well under the cap with the event loop spun between them -- so every single readyRead
    // batch on the client side is tiny. This is exactly the shape the per-batch regression let
    // through: no one batch would ever trip a per-batch check, even though the connection's
    // lifetime total does.
    constexpr qint64 kCapBytes = 8 * 1024 * 1024;
    const QByteArray line = "{\"type\":\"progress\",\"step\":0}\n";
    const qint64 totalNeeded = kCapBytes + (1000 * line.size());
    const QByteArray fullPayload = line.repeated(static_cast<int>(totalNeeded / line.size()));

    // 512 KiB per write (still 16x under the 8 MiB cap -- ample margin even if a couple of writes
    // land in the same read) with a real (wall-clock, not merely "no more queued events") pause
    // between writes: QCoreApplication::processEvents(..., N) returns as soon as its queue is
    // empty, which can be well under N ms, so pacing needs an elapsed-time loop or Qt/the OS is
    // free to coalesce the whole payload into arbitrarily few, large reads on the client side --
    // which would trip even the buggy per-batch check and defeat the point of this case. Kept
    // short overall (a handful of chunks, single-digit-ms pacing, a few-second ceiling below) so a
    // buggy build that never trips the cap reaches its own bounded failure quickly rather than
    // sitting on an open, actively-receiving socket for an extended stretch.
    constexpr qint64 kChunkSize = 512 * 1024;
    qint64 offset = 0;
    while (offset < fullPayload.size() && !completed)
    {
        const qint64 chunk = qMin(kChunkSize, qint64(fullPayload.size()) - offset);
        serverSide->write(fullPayload.constData() + offset, chunk);
        offset += chunk;

        QElapsedTimer pump;
        pump.start();
        while (pump.elapsed() < 10)
            QCoreApplication::processEvents(QEventLoop::AllEvents, 5);
    }

    QElapsedTimer timer;
    timer.start();
    while (!completed && timer.elapsed() < (kSendTimeoutMs + 2000))
        QCoreApplication::processEvents(QEventLoop::AllEvents, 50);

    // Always visible, pass or fail: whatever WorkerSocketClient actually reported, so a failure
    // that isn't the expected cap diagnostic still says what happened instead of just not-that.
    qWarning("manyWellFormedFramesTripTheLifetimeCap: completed=%d startedOk=%d diagnostics='%s'",
             int(completed), int(startedOk), qPrintable(diagnostics));

    QVERIFY2(completed,
             "send() never completed for a well-formed stream that must exceed the 8 MiB cap");
    QVERIFY2(startedOk, "the fake server accepted the connection; the transport must report it up");
    QVERIFY2(diagnostics.contains(QStringLiteral("8 MiB")),
             qPrintable(QStringLiteral(
                            "expected the 8 MiB cap diagnostic; got diagnostics: '%1'")
                            .arg(diagnostics)));
}

QTEST_MAIN(WorkerSocketFramesTest)
#include "test_worker_socket_frames.moc"
