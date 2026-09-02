// The Qt client presents the worker's session secret, read from the file the worker wrote.
//
// Loopback is not a per-user boundary: every account on a Windows machine shares 127.0.0.1, so a
// worker that trusted the peer address handed its full command surface -- node-pack install, model
// download with the stored keys, credential writes -- to any other user on a shared PC. The worker
// now publishes a per-launch secret to a user-only file and refuses everything but `ping` without
// it. This client is the app's proof that it is the same user.
//
// The Python suite proves the worker enforces this over the wire, and that worker_client.py and the
// test fixture present the secret. Nothing there exercises THIS transport, which carries every
// one-shot command the UI sends. A compiled-but-untested reader that returned "" would leave the
// app answering every queue poll with an auth_error -- loudly, at least, but broken.
//
// Environment-driven: SPELLVISION_WORKER_SESSION_FILE relocates the file exactly as it does for the
// worker and the harness, so the test never touches the real per-user location.

#include <QtTest>

#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTemporaryDir>

#include "workers/WorkerSocketClient.h"

using spellvision::workers::WorkerSocketClient;

namespace
{

void clearSessionEnvironment()
{
    qunsetenv("SPELLVISION_WORKER_SESSION_FILE");
    qunsetenv("SPELLVISION_WORKER_SESSION_SECRET");
}

QString writeSessionFile(const QTemporaryDir &dir, const QString &secret)
{
    const QString path = QDir(dir.path()).filePath(QStringLiteral("worker_session.json"));
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return QString();
    file.write(QJsonDocument(QJsonObject{{QStringLiteral("secret"), secret},
                                         {QStringLiteral("port"), 8765}})
                   .toJson(QJsonDocument::Compact));
    return path;
}

}  // namespace

class WorkerSessionSecretTest : public QObject
{
    Q_OBJECT

private slots:
    void cleanup() { clearSessionEnvironment(); }

    void readsTheSecretFromTheFile()
    {
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const QString path = writeSessionFile(dir, QStringLiteral("abc123"));
        QVERIFY(!path.isEmpty());
        clearSessionEnvironment();
        qputenv("SPELLVISION_WORKER_SESSION_FILE", path.toUtf8());
        QCOMPARE(WorkerSocketClient::sessionSecret(), QStringLiteral("abc123"));
    }

    void theEnvironmentValueWinsOverTheFile()
    {
        // A launcher that hands the secret down directly need not publish a file. Same precedence
        // as python/worker_auth.read_session_secret.
        QTemporaryDir dir;
        const QString path = writeSessionFile(dir, QStringLiteral("from-file"));
        clearSessionEnvironment();
        qputenv("SPELLVISION_WORKER_SESSION_FILE", path.toUtf8());
        qputenv("SPELLVISION_WORKER_SESSION_SECRET", "from-env");
        QCOMPARE(WorkerSocketClient::sessionSecret(), QStringLiteral("from-env"));
    }

    void aMissingFileYieldsAnEmptySecretNotACrash()
    {
        clearSessionEnvironment();
        qputenv("SPELLVISION_WORKER_SESSION_FILE", "Z:/definitely/not/here.json");
        QVERIFY(WorkerSocketClient::sessionSecret().isEmpty());
    }

    void aMalformedFileYieldsAnEmptySecret()
    {
        QTemporaryDir dir;
        const QString path = QDir(dir.path()).filePath(QStringLiteral("bad.json"));
        QFile file(path);
        QVERIFY(file.open(QIODevice::WriteOnly));
        file.write("this is not json");
        file.close();
        clearSessionEnvironment();
        qputenv("SPELLVISION_WORKER_SESSION_FILE", path.toUtf8());
        QVERIFY(WorkerSocketClient::sessionSecret().isEmpty());
    }

    void withSessionAddsTheFieldToEveryRequest()
    {
        QTemporaryDir dir;
        const QString path = writeSessionFile(dir, QStringLiteral("s3cret"));
        clearSessionEnvironment();
        qputenv("SPELLVISION_WORKER_SESSION_FILE", path.toUtf8());

        const QJsonObject request{{QStringLiteral("command"), QStringLiteral("queue_status")}};
        const QJsonObject sent = WorkerSocketClient::withSession(request);
        QCOMPARE(sent.value(QStringLiteral("session_secret")).toString(), QStringLiteral("s3cret"));
        QCOMPARE(sent.value(QStringLiteral("command")).toString(), QStringLiteral("queue_status"));
        // The input is not mutated.
        QVERIFY(!request.contains(QStringLiteral("session_secret")));
    }

    void withSessionDoesNotOverwriteAnExplicitField()
    {
        // A caller that deliberately presents a different secret (a test, an integration probe) is
        // not second-guessed.
        QTemporaryDir dir;
        const QString path = writeSessionFile(dir, QStringLiteral("file-secret"));
        clearSessionEnvironment();
        qputenv("SPELLVISION_WORKER_SESSION_FILE", path.toUtf8());

        const QJsonObject request{{QStringLiteral("command"), QStringLiteral("ping")},
                                  {QStringLiteral("session_secret"), QStringLiteral("mine")}};
        QCOMPARE(WorkerSocketClient::withSession(request).value(QStringLiteral("session_secret")).toString(),
                 QStringLiteral("mine"));
    }

    void withSessionLeavesTheRequestAloneWhenThereIsNoSecret()
    {
        // No secret available: send the request unchanged and let the worker refuse it with a
        // message that names the file. Inventing an empty field would be a different, worse error.
        clearSessionEnvironment();
        qputenv("SPELLVISION_WORKER_SESSION_FILE", "Z:/nope.json");
        const QJsonObject request{{QStringLiteral("command"), QStringLiteral("queue_status")}};
        QVERIFY(!WorkerSocketClient::withSession(request).contains(QStringLiteral("session_secret")));
    }
};

QTEST_MAIN(WorkerSessionSecretTest)
#include "test_worker_session_secret.moc"
