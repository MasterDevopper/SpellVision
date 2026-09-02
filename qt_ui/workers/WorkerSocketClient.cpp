#include "WorkerSocketClient.h"

#include <QByteArray>
#include <QDir>
#include <QFile>
#include <QStandardPaths>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QPointer>
#include <QProcessEnvironment>
#include <QStringList>
#include <QTcpSocket>
#include <QTimer>

#include <memory>
#include <utility>

namespace spellvision::workers
{

namespace
{

// Matches worker_client.py's STREAMING_COMMANDS.
const QStringList &streamingCommands()
{
    static const QStringList commands{
        QStringLiteral("t2i"),
        QStringLiteral("i2i"),
        QStringLiteral("ping"),
        QStringLiteral("comfy_workflow"),
    };
    return commands;
}

// Same 8 MiB ceiling the QProcess path applies to worker stdout.
constexpr qsizetype kMaxResponseBytes = 8 * 1024 * 1024;

QString commandOf(const QJsonObject &request)
{
    return request.value(QStringLiteral("command")).toString().trimmed();
}

// Byte-for-byte the selection rule parseLastJsonObjectFromStdout applies to the subprocess's
// stdout: walk backwards for the last line that both starts with '{' and ends with '}', then
// parse it. Keeping the rule identical is what makes this transport a drop-in.
QJsonObject parseLastJsonObject(const QByteArray &payload, QString *errorText)
{
    QString lastJsonLine;
    const QStringList lines = QString::fromUtf8(payload).split('\n', Qt::SkipEmptyParts);
    for (auto it = lines.crbegin(); it != lines.crend(); ++it)
    {
        const QString candidate = it->trimmed();
        if (candidate.startsWith('{') && candidate.endsWith('}'))
        {
            lastJsonLine = candidate;
            break;
        }
    }

    if (lastJsonLine.isEmpty())
    {
        if (errorText)
            *errorText = QStringLiteral("Worker returned no JSON payload.");
        return {};
    }

    QJsonParseError parseError{};
    const QJsonDocument doc = QJsonDocument::fromJson(lastJsonLine.toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
    {
        if (errorText)
            *errorText = QStringLiteral("Worker returned invalid JSON: %1").arg(lastJsonLine);
        return {};
    }

    return doc.object();
}

} // namespace

bool WorkerSocketClient::isStreamingCommand(const QString &command)
{
    return streamingCommands().contains(command);
}

bool WorkerSocketClient::canHandle(const QJsonObject &request)
{
    // An "action"-shaped request would need worker_client.py's normalize_outbound_request to turn
    // it into a command. No C++ call site builds one, but guard rather than assume.
    if (request.contains(QStringLiteral("action")))
        return false;

    const QString command = commandOf(request);
    if (command.isEmpty())
        return false;

    return !isStreamingCommand(command);
}

QString WorkerSocketClient::host()
{
    const QString value =
        QProcessEnvironment::systemEnvironment().value(QStringLiteral("SPELLVISION_WORKER_HOST")).trimmed();
    return value.isEmpty() ? QStringLiteral("127.0.0.1") : value;
}

quint16 WorkerSocketClient::port()
{
    const QString value =
        QProcessEnvironment::systemEnvironment().value(QStringLiteral("SPELLVISION_WORKER_PORT")).trimmed();
    bool ok = false;
    const uint parsed = value.toUInt(&ok);
    if (!ok || parsed == 0 || parsed > 65535)
        return 8765;
    return static_cast<quint16>(parsed);
}

QString WorkerSocketClient::sessionSecret()
{
    // Same resolution as python/worker_auth.read_session_secret: environment value first, then the
    // file. A launcher that hands the secret down through the environment does not need the file;
    // an adopting UI that shares no environment with the worker does.
    const QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    const QString fromEnv = env.value(QStringLiteral("SPELLVISION_WORKER_SESSION_SECRET")).trimmed();
    if (!fromEnv.isEmpty())
        return fromEnv;

    QString path = env.value(QStringLiteral("SPELLVISION_WORKER_SESSION_FILE")).trimmed();
    if (path.isEmpty())
    {
        // Must equal python/app_paths.app_data_dir(): %LOCALAPPDATA%/DarkDuck/SpellVision. Qt
        // derives the same directory from the organisation and application names set in main().
        const QString base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
        if (base.isEmpty())
            return QString();
        path = QDir(base).filePath(QStringLiteral("worker_session_%1.json").arg(port()));
    }

    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return QString();
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    return doc.object().value(QStringLiteral("secret")).toString().trimmed();
}

QJsonObject WorkerSocketClient::withSession(const QJsonObject &request)
{
    if (request.contains(QStringLiteral("session_secret")))
        return request;
    const QString secret = sessionSecret();
    if (secret.isEmpty())
        return request;
    QJsonObject out = request;
    out.insert(QStringLiteral("session_secret"), secret);
    return out;
}

void WorkerSocketClient::send(QObject *context,
                              const QJsonObject &request,
                              int timeoutMs,
                              Completion completion)
{
    struct CallState
    {
        QByteArray response;
        QStringList diagnostics;
        bool connected = false;
        bool done = false;
    };

    auto *socket = new QTcpSocket(context);
    auto *timeout = new QTimer(socket);
    timeout->setSingleShot(true);

    const auto state = std::make_shared<CallState>();
    const QPointer<QObject> contextGuard(context);

    // One shared finisher so every exit path -- clean close, socket error, timeout -- reports
    // exactly once and tears the socket down the same way.
    const auto finish = std::make_shared<std::function<void()>>();
    *finish = [socket, timeout, state, contextGuard, completion = std::move(completion)]() mutable {
        if (state->done)
            return;
        state->done = true;
        timeout->stop();

        state->response.append(socket->readAll());

        QString parseError;
        const QJsonObject response = parseLastJsonObject(state->response, &parseError);
        QStringList diagnostics = state->diagnostics;
        if (response.isEmpty() && !parseError.trimmed().isEmpty())
            diagnostics << parseError.trimmed();
        diagnostics.removeAll(QString());

        if (contextGuard && completion)
            completion(response, diagnostics.join(QChar('\n')), state->connected);

        socket->abort();
        socket->deleteLater();
    };

    // Read at connect time rather than at call time: a worker restarted between the two publishes
    // a new secret, and the file is small enough that re-reading per request costs nothing.
    QObject::connect(socket, &QTcpSocket::connected, socket, [socket, request, state]() {
        state->connected = true;
        const QByteArray payload =
            QJsonDocument(withSession(request)).toJson(QJsonDocument::Compact) + '\n';
        socket->write(payload);
    });

    QObject::connect(socket, &QTcpSocket::readyRead, socket, [socket, state, finish]() {
        state->response.append(socket->readAll());
        if (state->response.size() > kMaxResponseBytes)
        {
            state->diagnostics << QStringLiteral("Worker response exceeded 8 MiB safety limit.");
            (*finish)();
        }
    });

    // The server closes the connection when the handler returns, so disconnect is the normal
    // end-of-response signal -- not an error.
    QObject::connect(socket, &QTcpSocket::disconnected, socket, [finish]() { (*finish)(); });

    QObject::connect(socket, &QTcpSocket::errorOccurred, socket,
                     [socket, state, finish](QAbstractSocket::SocketError error) {
                         // RemoteHostClosedError is how a clean server-side close surfaces when it
                         // races readyRead; the buffered response is still complete.
                         if (error != QAbstractSocket::RemoteHostClosedError)
                             state->diagnostics << QStringLiteral("Worker socket error: %1")
                                                       .arg(socket->errorString());
                         (*finish)();
                     });

    QObject::connect(timeout, &QTimer::timeout, socket, [state, finish]() {
        state->diagnostics << QStringLiteral("Worker request timed out.");
        (*finish)();
    });

    timeout->start(qMax(1, timeoutMs));
    socket->connectToHost(host(), port());
}

} // namespace spellvision::workers
