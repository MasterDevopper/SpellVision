// The probe that decides whether exit may kill ComfyUI.
//
// `MainWindow::tearDownComfyOnExit` used to answer "is ComfyUI busy?" by walking SpellVision's OWN
// QueueManager -- the jobs this app submitted and still remembers -- and the line after that check
// was terminate(). Work ComfyUI is genuinely doing is invisible to that walk whenever this app did
// not submit it: a render started from ComfyUI's own web UI, one from a second SpellVision, one
// from before a queue reset. All of them read as idle, and all of them died on quit.
//
// `probeComfyQueueState` -- specified, built, and for its whole life called by nothing -- is now
// that decision's engine, so the property this file holds is the one the guard rests on:
//
//     NO failure resolves to Idle.
//
// Idle is the single state that permits a kill, and it may only ever come from ComfyUI answering
// the question. A closed port, a server that never replies, an error status, a body that is not
// JSON, a body without the queue arrays -- each is "we could not check", which is not "we checked
// and it is idle" (223e466 settled the same distinction for the workflow drop path). Every one of
// them must come back Unknown, and must do so inside the timeout it was given, because this runs
// on aboutToQuit where a probe that hangs is a quit that hangs.
//
// A source-level test cannot hold this: the Python checks beside it assert that the teardown WIRES
// the probe, and would pass just as happily against a probe that answered Idle on a refused
// connection -- which is the one answer that destroys a render.
//
// The probe is deliberately blocking (waitForConnected / waitForReadyRead), so the fake ComfyUI
// cannot live on the calling thread: those waits service their own socket and would never give a
// QTcpServer on the same thread a turn to accept. The probe therefore runs on a worker thread
// while this thread stays free to serve it -- a real loopback socket and the real transport, no
// monkeypatch anywhere.

#include <QtTest>

#include <QByteArray>
#include <QCoreApplication>
#include <QElapsedTimer>
#include <QHostAddress>
#include <QScopedPointer>
#include <QTcpServer>
#include <QTcpSocket>
#include <QThread>

#include "shell/RuntimeProfile.h"

using spellvision::shell::ComfyQueueState;

namespace
{

QByteArray httpResponse(const QByteArray &status, const QByteArray &body)
{
    return "HTTP/1.1 " + status + "\r\nContent-Type: application/json\r\nContent-Length: "
           + QByteArray::number(body.size()) + "\r\nConnection: close\r\n\r\n" + body;
}

// A ComfyUI that answers /queue with one canned response -- or, with `answer` false, accepts the
// connection and then says nothing at all, which is the shape a wedged backend takes.
class FakeComfy
{
public:
    explicit FakeComfy(const QByteArray &response, bool answer = true)
    {
        QObject::connect(&server_, &QTcpServer::newConnection, &server_, [this, response, answer]() {
            while (QTcpSocket *socket = server_.nextPendingConnection())
            {
                if (!answer)
                    continue;
                QObject::connect(socket, &QTcpSocket::readyRead, socket, [socket, response]() {
                    socket->readAll();
                    socket->write(response);
                    socket->flush();
                    socket->disconnectFromHost();
                });
            }
        });
        listening_ = server_.listen(QHostAddress::LocalHost);
    }

    bool listening() const { return listening_; }
    quint16 port() const { return server_.serverPort(); }

private:
    QTcpServer server_;
    bool listening_ = false;
};

// A port nothing is listening on: bound, read back, then closed, so it cannot collide with a real
// service the way a hardcoded number can.
quint16 closedPort()
{
    QTcpServer scratch;
    if (!scratch.listen(QHostAddress::LocalHost))
        return 0;
    const quint16 port = scratch.serverPort();
    scratch.close();
    return port;
}

// Seeded with Idle, never with Unknown: every failure case here asserts Unknown, and seeding the
// expected answer would let a probe that never ran at all pass all of them.
ComfyQueueState probeWhileServing(quint16 port, int timeoutMs, qint64 *elapsedMs = nullptr)
{
    ComfyQueueState observed = ComfyQueueState::Idle;
    QElapsedTimer timer;
    timer.start();
    QScopedPointer<QThread> worker(QThread::create([&observed, port, timeoutMs]() {
        observed = spellvision::shell::probeComfyQueueState(QStringLiteral("127.0.0.1"), port,
                                                            timeoutMs);
    }));
    worker->start();
    while (!worker->wait(5))
        QCoreApplication::processEvents(QEventLoop::AllEvents, 5);
    if (elapsedMs)
        *elapsedMs = timer.elapsed();
    return observed;
}

constexpr int kProbeBudgetMs = 500;   // the teardown's own budget, kComfyExitQueueProbeTimeoutMs
constexpr int kBoundedMs = 3000;      // generous, but far below "stalls the quit"

}  // namespace

class ComfyExitGuardTest : public QObject
{
    Q_OBJECT

private slots:
    void anEmptyQueueIsTheOnlyIdleAnswer();
    void aRunningJobIsBusy();
    void aPendingJobIsBusyToo();
    void aChunkedBusyAnswerIsStillBusy();
    void aClosedPortIsUnknownNotIdle();
    void aServerThatNeverAnswersIsUnknownInsideItsBudget();
    void anErrorStatusIsUnknownEvenWhenItsBodyLooksIdle();
    void aBodyWithoutTheQueueArraysIsUnknown();
    void aBodyThatIsNotJsonIsUnknown();
};

void ComfyExitGuardTest::anEmptyQueueIsTheOnlyIdleAnswer()
{
    FakeComfy comfy(httpResponse("200 OK", R"({"queue_running":[],"queue_pending":[]})"));
    QVERIFY(comfy.listening());
    QCOMPARE(probeWhileServing(comfy.port(), kProbeBudgetMs), ComfyQueueState::Idle);
}

void ComfyExitGuardTest::aRunningJobIsBusy()
{
    FakeComfy comfy(
        httpResponse("200 OK", R"({"queue_running":[[0,"7f1c",{},{}]],"queue_pending":[]})"));
    QVERIFY(comfy.listening());
    QCOMPARE(probeWhileServing(comfy.port(), kProbeBudgetMs), ComfyQueueState::Busy);
}

void ComfyExitGuardTest::aPendingJobIsBusyToo()
{
    // Nothing is sampling yet, but a queued job is work this app would destroy by killing the
    // process it is queued on.
    FakeComfy comfy(
        httpResponse("200 OK", R"({"queue_running":[],"queue_pending":[[1,"a9d2",{},{}]]})"));
    QVERIFY(comfy.listening());
    QCOMPARE(probeWhileServing(comfy.port(), kProbeBudgetMs), ComfyQueueState::Busy);
}

void ComfyExitGuardTest::aChunkedBusyAnswerIsStillBusy()
{
    // ComfyUI can answer /queue chunked. A decoder that failed here would return Unknown -- safe,
    // but it would detach every time and the Idle path would be dead code, so the one state that
    // permits a kill would never be reachable against the real server.
    const QByteArray body = R"({"queue_running":[[0,"7f1c",{},{}]],"queue_pending":[]})";
    const QByteArray chunked = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                               "Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
                               + QByteArray::number(body.size(), 16) + "\r\n" + body
                               + "\r\n0\r\n\r\n";
    FakeComfy comfy(chunked);
    QVERIFY(comfy.listening());
    QCOMPARE(probeWhileServing(comfy.port(), kProbeBudgetMs), ComfyQueueState::Busy);
}

void ComfyExitGuardTest::aClosedPortIsUnknownNotIdle()
{
    // The whole defect in one case: ComfyUI unreachable must NOT read as "nothing is running".
    const quint16 port = closedPort();
    QVERIFY(port != 0);
    qint64 elapsed = -1;
    const ComfyQueueState state = probeWhileServing(port, kProbeBudgetMs, &elapsed);
    QCOMPARE(state, ComfyQueueState::Unknown);
    QVERIFY2(elapsed < kBoundedMs,
             qPrintable(QStringLiteral("a refused connection took %1 ms").arg(elapsed)));
}

void ComfyExitGuardTest::aServerThatNeverAnswersIsUnknownInsideItsBudget()
{
    // Accepts, then silence. This is the case that could stall a quit, so the budget is asserted
    // as well as the verdict.
    FakeComfy comfy(QByteArray(), /*answer=*/false);
    QVERIFY(comfy.listening());
    qint64 elapsed = -1;
    const ComfyQueueState state = probeWhileServing(comfy.port(), 300, &elapsed);
    QCOMPARE(state, ComfyQueueState::Unknown);
    QVERIFY2(elapsed < kBoundedMs,
             qPrintable(QStringLiteral("a silent server held the probe for %1 ms").arg(elapsed)));
}

void ComfyExitGuardTest::anErrorStatusIsUnknownEvenWhenItsBodyLooksIdle()
{
    // The body is a perfectly well-formed idle queue. The status says the server did not answer
    // the question, and the status wins -- otherwise an error page would be a licence to kill.
    FakeComfy comfy(
        httpResponse("500 Internal Server Error", R"({"queue_running":[],"queue_pending":[]})"));
    QVERIFY(comfy.listening());
    QCOMPARE(probeWhileServing(comfy.port(), kProbeBudgetMs), ComfyQueueState::Unknown);
}

void ComfyExitGuardTest::aBodyWithoutTheQueueArraysIsUnknown()
{
    // A different service on the port, or a core that renamed the keys: absence of the arrays is
    // not emptiness of them.
    FakeComfy comfy(httpResponse("200 OK", R"({"error":"no such endpoint"})"));
    QVERIFY(comfy.listening());
    QCOMPARE(probeWhileServing(comfy.port(), kProbeBudgetMs), ComfyQueueState::Unknown);
}

void ComfyExitGuardTest::aBodyThatIsNotJsonIsUnknown()
{
    FakeComfy comfy(httpResponse("200 OK", "<html>ComfyUI</html>"));
    QVERIFY(comfy.listening());
    qint64 elapsed = -1;
    QCOMPARE(probeWhileServing(comfy.port(), 300, &elapsed), ComfyQueueState::Unknown);
    QVERIFY2(elapsed < kBoundedMs,
             qPrintable(QStringLiteral("an unparseable body took %1 ms").arg(elapsed)));
}

QTEST_MAIN(ComfyExitGuardTest)
#include "test_comfy_exit_guard.moc"
