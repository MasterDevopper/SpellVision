#pragma once

#include <QJsonObject>
#include <QObject>
#include <QProcess>
#include <QProcessEnvironment>
#include <QString>
#include <QStringList>

namespace spellvision::workers
{

class WorkerProcessController final : public QObject
{
    Q_OBJECT

public:
    struct CommandRequest
    {
        QString program;
        QStringList arguments;
        QString workingDirectory;
        QProcessEnvironment environment;
        QJsonObject payload;
        bool closeWriteChannelAfterPayload = true;
    };

    explicit WorkerProcessController(QObject *parent = nullptr);
    ~WorkerProcessController() override;

    [[nodiscard]] bool isRunning() const;
    [[nodiscard]] QString activeProgram() const;
    [[nodiscard]] QStringList activeArguments() const;

    bool start(const CommandRequest &request);
    void terminate();
    void kill();

signals:
    void processStarted();
    void stdoutLineReceived(const QString &line);
    void stderrLineReceived(const QString &line);
    void jsonMessageReceived(const QJsonObject &message);
    void processFinished(int exitCode, QProcess::ExitStatus exitStatus);
    void processError(const QString &message);

private:
    void resetProcess();
    void handleStdout();
    void handleStderr();
    void drainLines(QByteArray &buffer, bool stderrStream);
    void emitStdoutLine(const QString &line);
    void emitStderrLine(const QString &line);
    bool writePayload(const QJsonObject &payload, bool closeWriteChannelAfterPayload);

    QProcess *process_ = nullptr;
    QByteArray stdoutBuffer_;
    QByteArray stderrBuffer_;
    QString activeProgram_;
    QStringList activeArguments_;
};

} // namespace spellvision::workers
