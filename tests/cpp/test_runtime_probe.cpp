// probeWorkerProtocol used to spend timeoutMs on connect, again on write, and again
// on read, because the deadline timer started after the write. A port that accepts
// and never answers must return within one timeout plus a small margin.

#include <QtTest>

#include <QElapsedTimer>
#include <QHostAddress>
#include <QTcpServer>
#include <QTcpSocket>

#include "shell/RuntimeProfile.h"

using spellvision::shell::probeWorkerProtocol;

class RuntimeProbeTest : public QObject
{
    Q_OBJECT

private slots:
    void a_silent_listener_returns_within_one_timeout();
};

void RuntimeProbeTest::a_silent_listener_returns_within_one_timeout()
{
    QTcpServer server;
    QVERIFY(server.listen(QHostAddress::LocalHost, 0));
    const quint16 port = server.serverPort();

    QList<QTcpSocket *> clients;
    QObject::connect(&server, &QTcpServer::newConnection, &server, [&]() {
        while (server.hasPendingConnections())
            clients.append(server.nextPendingConnection());
    });

    constexpr int timeoutMs = 200;
    QElapsedTimer timer;
    timer.start();
    const bool reached = probeWorkerProtocol(QStringLiteral("127.0.0.1"), port, timeoutMs);
    const qint64 elapsed = timer.elapsed();

    QVERIFY2(!reached, "a silent listener is not the worker protocol");
    QVERIFY2(elapsed < timeoutMs + 150,
             qPrintable(QStringLiteral("probe took %1 ms against a %2 ms deadline")
                            .arg(elapsed)
                            .arg(timeoutMs)));

    qDeleteAll(clients);
}

QTEST_MAIN(RuntimeProbeTest)
#include "test_runtime_probe.moc"
