#pragma once

#include <QByteArray>
#include <QJsonObject>
#include <QList>
#include <QObject>
#include <QString>
#include <QtGlobal>

#include <functional>

namespace spellvision::workers
{

// Native transport for the worker's TCP/JSON protocol.
//
// The UI used to reach the worker by spawning `python worker_client.py` once per request. That
// script is a thin shim -- it normalizes an "action" key into a "command", opens a socket, writes
// one JSON line, and echoes the worker's newline-delimited replies -- but paying a CPython
// interpreter start for it costs ~78ms per call against ~1.4ms for the socket itself. The queue
// poll runs every 1800ms for the whole session, so that overhead alone is ~156s of CPU per idle
// hour, plus a process spawn every 1.8s.
//
// Nothing in the C++ sends an "action"-shaped request -- every call site already builds a
// "command" -- so the shim's normalization step is a no-op for real traffic and this class can
// speak the protocol directly.
//
// Protocol (see python/worker_tcp.py WorkerTCPHandler::handle): the server reads exactly ONE
// newline-terminated JSON line, dispatches it, writes newline-delimited JSON replies, then closes.
// No half-close is required on the client side.
class WorkerSocketClient final
{
public:
    // Mirrors the completion signature the QProcess path already hands its callers, so this is a
    // drop-in swap: `startedOk` means "the transport came up" (socket connected) exactly as it
    // previously meant "the process started".
    using Completion =
        std::function<void(const QJsonObject &response, const QString &diagnostics, bool startedOk)>;

    // Commands the worker streams multiple progress events for. They keep the subprocess path so
    // this change cannot alter generation behaviour; in practice the UI sends none of them except
    // `ping` (generation goes through `enqueue`, which is a one-shot ack).
    static bool isStreamingCommand(const QString &command);

    // Every complete newline-terminated JSON object a receive buffer holds, in the order the
    // worker wrote them, plus whatever trailing bytes have not yet seen a terminating newline.
    struct ParsedFrames
    {
        QList<QJsonObject> frames;
        QByteArray remainder;
    };

    // worker_tcp.py's EventEmitter writes one JSON object plus '\n' per event and flushes on every
    // write (python/worker_tcp.py), so a single response can legitimately carry several frames --
    // a run's progress events, not just its final result. This extracts all of them, in order,
    // leaving any not-yet-complete trailing line in `remainder` for the next call to extend rather
    // than discarding it. `docs/SPELLVISION_WORKER_PROTOCOL.md`'s client-behaviour rule is explicit
    // that a client "should not collapse multiline worker output into a single unreadable blob" --
    // this is the primitive that keeps the promise for the socket transport.
    static ParsedFrames parseJsonFrames(const QByteArray &buffer);

    // True when the request is a one-shot control command this transport can carry: it must have a
    // "command" (no "action" normalization needed) and must not be a streaming command.
    static bool canHandle(const QJsonObject &request);

    static QString host();
    static quint16 port();

    // This launch's worker session secret, read from the file the worker publishes under the
    // per-user app-data directory (or SPELLVISION_WORKER_SESSION_FILE). Empty when no worker has
    // published one; the worker then answers everything but `ping` with an auth_error, which is
    // the correct, loud outcome for a client that could not read the file.
    static QString sessionSecret();

    // `request` with the session secret added when one is available and the request does not
    // already carry one. Every send() goes through this; exposed so tests and the QProcess path
    // can build identical requests.
    static QJsonObject withSession(const QJsonObject &request);

    // Sends `request` and invokes `completion` exactly once. `context` owns the socket, so a
    // destroyed context cancels the call. Safe to invoke from the GUI thread; never blocks.
    static void send(QObject *context, const QJsonObject &request, int timeoutMs, Completion completion);
};

} // namespace spellvision::workers
