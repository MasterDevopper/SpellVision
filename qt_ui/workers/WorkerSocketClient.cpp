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
#include <QAbstractSocket>
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

} // namespace

WorkerSocketClient::ParsedFrames WorkerSocketClient::parseJsonFrames(const QByteArray &buffer)
{
    ParsedFrames result;
    qsizetype start = 0;
    const qsizetype size = buffer.size();
    for (qsizetype i = 0; i < size; ++i)
    {
        if (buffer.at(i) != '\n')
            continue;

        const QByteArray line = buffer.mid(start, i - start).trimmed();
        start = i + 1;
        if (line.isEmpty())
            continue;

        QJsonParseError parseError{};
        const QJsonDocument doc = QJsonDocument::fromJson(line, &parseError);
        if (parseError.error == QJsonParseError::NoError && doc.isObject())
            result.frames.append(doc.object());
    }
    // Whatever follows the last '\n' has not been terminated yet -- it is not a discarded frame,
    // it is an incomplete one the next batch of bytes will finish.
    result.remainder = buffer.mid(start);
    return result;
}

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
        // Bytes received but not yet resolved into a complete line -- the tail parseJsonFrames
        // handed back as `remainder`, extended by whatever readyRead delivers next.
        QByteArray response;
        // Every frame parsed so far, in the order the worker wrote them. Completion below still
        // reports only the last one (that contract is unchanged in this task), but the ordered set
        // is what a future subscriber over this transport needs, and it is what proves the reader
        // no longer discards every frame but the last.
        QList<QJsonObject> frames;
        QStringList diagnostics;
        bool connected = false;
        bool done = false;
        // Every byte received across the CONNECTION'S LIFETIME, independent of `response`.
        // `response` is drained down to the unparsed remainder after every readyRead so frame
        // delivery works; a cap read off its size alone would see only one batch's new bytes plus
        // a small leftover; and an endless stream of well-formed lines would never trip it.
        qsizetype totalBytesReceived = 0;
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

        const QByteArray finalBytes = socket->readAll();
        state->totalBytesReceived += finalBytes.size();
        state->response.append(finalBytes);
        const ParsedFrames finalParsed = parseJsonFrames(state->response);
        state->frames.append(finalParsed.frames);

        // The public contract here is unchanged: one response object per completion. It is now the
        // LAST of every frame actually parsed, in arrival order, rather than a backwards scan of
        // the raw buffer -- so it agrees with `frames` instead of being a second, independent guess
        // at the same thing.
        QJsonObject response;
        QStringList diagnostics = state->diagnostics;
        if (!state->frames.isEmpty())
        {
            response = state->frames.last();
        }
        else if (!finalParsed.remainder.trimmed().isEmpty())
        {
            diagnostics << QStringLiteral("Worker returned invalid JSON: %1")
                               .arg(QString::fromUtf8(finalParsed.remainder.trimmed()));
        }
        else
        {
            diagnostics << QStringLiteral("Worker returned no JSON payload.");
        }
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
        const QByteArray incoming = socket->readAll();
        state->totalBytesReceived += incoming.size();
        state->response.append(incoming);
        // Bounds total lifetime traffic on the connection, not what happens to be sitting in
        // `response` right now -- that buffer is drained to its unparsed remainder below on every
        // call, so checking its size here would let an unbounded stream of well-formed lines
        // through a batch at a time without ever tripping this.
        if (state->totalBytesReceived > kMaxResponseBytes)
        {
            state->diagnostics << QStringLiteral("Worker response exceeded 8 MiB safety limit.");
            (*finish)();
            return;
        }

        // Parse every complete line as it lands rather than waiting for the socket to close.
        // worker_tcp.py flushes one JSON object per event (EventEmitter.emit), so a multi-frame
        // response -- a run's progress events, not just its terminal result -- has frames sitting
        // in the buffer well before the connection ends. Only the trailing, not-yet-terminated line
        // stays buffered for the next readyRead.
        const ParsedFrames parsed = parseJsonFrames(state->response);
        state->frames.append(parsed.frames);
        state->response = parsed.remainder;
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

void WorkerSocketClient::listen(QObject *context,
                                const QJsonObject &request,
                                FrameCallback onFrame,
                                ClosedCallback onClosed)
{
    auto *socket = new QTcpSocket(context);
    const auto state = std::make_shared<QByteArray>();
    const auto done = std::make_shared<bool>(false);
    const QPointer<QObject> contextGuard(context);

    const auto finish = std::make_shared<std::function<void()>>();
    *finish = [socket, done, contextGuard, onClosed]() {
        if (*done)
            return;
        *done = true;
        if (contextGuard && onClosed)
            onClosed();
        socket->abort();
        socket->deleteLater();
    };

    QObject::connect(socket, &QTcpSocket::connected, socket, [socket, request]() {
        const QByteArray payload =
            QJsonDocument(withSession(request)).toJson(QJsonDocument::Compact) + '\n';
        socket->write(payload);
    });

    QObject::connect(socket, &QTcpSocket::readyRead, socket, [socket, state, onFrame, contextGuard]() {
        state->append(socket->readAll());
        const ParsedFrames parsed = parseJsonFrames(*state);
        *state = parsed.remainder;
        if (!contextGuard || !onFrame)
            return;
        for (const QJsonObject &frame : parsed.frames)
            onFrame(frame);
    });

    QObject::connect(socket, &QTcpSocket::disconnected, socket, [finish]() { (*finish)(); });
    QObject::connect(socket, &QTcpSocket::errorOccurred, socket,
                     [finish](QAbstractSocket::SocketError error) {
                         Q_UNUSED(error);
                         (*finish)();
                     });

    socket->connectToHost(host(), port());
}

} // namespace spellvision::workers
