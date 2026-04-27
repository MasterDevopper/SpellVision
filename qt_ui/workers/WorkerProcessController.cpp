#include "WorkerProcessController.h"

#include <QJsonDocument>

namespace spellvision::workers
{

namespace
{
QString processErrorToString(QProcess::ProcessError error)
{
    switch (error)
    {
    case QProcess::FailedToStart:
        return QStringLiteral("Worker process failed to start.");
    case QProcess::Crashed:
        return QStringLiteral("Worker process crashed.");
    case QProcess::Timedout:
        return QStringLiteral("Worker process timed out.");
    case QProcess::WriteError:
        return QStringLiteral("Worker process write error.");
    case QProcess::ReadError:
        return QStringLiteral("Worker process read error.");
    case QProcess::UnknownError:
        return QStringLiteral("Worker process unknown error.");
    }
    return QStringLiteral("Worker process error.");
}

QString trimmedLineFromBytes(const QByteArray &line)
{
    return QString::fromUtf8(line).trimmed();
}
} // namespace

WorkerProcessController::WorkerProcessController(QObject *parent)
    : QObject(parent)
{
}

WorkerProcessController::~WorkerProcessController()
{
    terminate();
}

bool WorkerProcessController::isRunning() const
{
    return process_ && process_->state() != QProcess::NotRunning;
}

QString WorkerProcessController::activeProgram() const
{
    return activeProgram_;
}

QStringList WorkerProcessController::activeArguments() const
{
    return activeArguments_;
}

bool WorkerProcessController::start(const CommandRequest &request)
{
    const QString program = request.program.trimmed();
    if (program.isEmpty())
    {
        emit processError(QStringLiteral("Worker command program is empty."));
        return false;
    }

    if (isRunning())
    {
        emit processError(QStringLiteral("Worker process is already running."));
        return false;
    }

    resetProcess();

    process_ = new QProcess(this);
    activeProgram_ = program;
    activeArguments_ = request.arguments;
    stdoutBuffer_.clear();
    stderrBuffer_.clear();

    if (!request.workingDirectory.trimmed().isEmpty())
        process_->setWorkingDirectory(request.workingDirectory.trimmed());

    if (!request.environment.isEmpty())
        process_->setProcessEnvironment(request.environment);

    connect(process_, &QProcess::started, this, &WorkerProcessController::processStarted);
    connect(process_, &QProcess::readyReadStandardOutput, this, &WorkerProcessController::handleStdout);
    connect(process_, &QProcess::readyReadStandardError, this, &WorkerProcessController::handleStderr);
    connect(process_, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        emit processError(processErrorToString(error));
    });
    connect(process_,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this,
            [this](int exitCode, QProcess::ExitStatus exitStatus) {
                handleStdout();
                handleStderr();
                emit processFinished(exitCode, exitStatus);
                resetProcess();
            });

    process_->start(activeProgram_, activeArguments_);
    if (!process_->waitForStarted(5000))
    {
        emit processError(QStringLiteral("Worker process did not start: %1").arg(activeProgram_));
        resetProcess();
        return false;
    }

    return writePayload(request.payload, request.closeWriteChannelAfterPayload);
}

void WorkerProcessController::terminate()
{
    if (!process_)
        return;

    if (process_->state() == QProcess::NotRunning)
    {
        resetProcess();
        return;
    }

    process_->terminate();
    if (!process_->waitForFinished(1500))
        process_->kill();

    resetProcess();
}

void WorkerProcessController::kill()
{
    if (!process_)
        return;

    process_->kill();
    process_->waitForFinished(1000);
    resetProcess();
}

void WorkerProcessController::resetProcess()
{
    if (!process_)
        return;

    process_->disconnect(this);
    process_->deleteLater();
    process_ = nullptr;
    stdoutBuffer_.clear();
    stderrBuffer_.clear();
    activeProgram_.clear();
    activeArguments_.clear();
}

void WorkerProcessController::handleStdout()
{
    if (!process_)
        return;

    stdoutBuffer_.append(process_->readAllStandardOutput());
    drainLines(stdoutBuffer_, false);
}

void WorkerProcessController::handleStderr()
{
    if (!process_)
        return;

    stderrBuffer_.append(process_->readAllStandardError());
    drainLines(stderrBuffer_, true);
}

void WorkerProcessController::drainLines(QByteArray &buffer, bool stderrStream)
{
    while (true)
    {
        const qsizetype newlineIndex = buffer.indexOf('\n');
        if (newlineIndex < 0)
            return;

        const QByteArray rawLine = buffer.left(newlineIndex);
        buffer.remove(0, newlineIndex + 1);

        const QString line = trimmedLineFromBytes(rawLine);
        if (line.isEmpty())
            continue;

        if (stderrStream)
            emitStderrLine(line);
        else
            emitStdoutLine(line);
    }
}

void WorkerProcessController::emitStdoutLine(const QString &line)
{
    emit stdoutLineReceived(line);

    const QJsonDocument document = QJsonDocument::fromJson(line.toUtf8());
    if (!document.isObject())
        return;

    emit jsonMessageReceived(document.object());
}

void WorkerProcessController::emitStderrLine(const QString &line)
{
    emit stderrLineReceived(line);
}

bool WorkerProcessController::writePayload(const QJsonObject &payload, bool closeWriteChannelAfterPayload)
{
    if (!process_)
        return false;

    if (payload.isEmpty())
    {
        if (closeWriteChannelAfterPayload)
            process_->closeWriteChannel();
        return true;
    }

    const QByteArray bytes = QJsonDocument(payload).toJson(QJsonDocument::Compact) + '\n';
    if (process_->write(bytes) < 0)
    {
        emit processError(QStringLiteral("Failed to write worker command payload."));
        return false;
    }

    process_->waitForBytesWritten(1000);

    if (closeWriteChannelAfterPayload)
        process_->closeWriteChannel();

    return true;
}

} // namespace spellvision::workers
