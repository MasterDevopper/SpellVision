#pragma once

#include <QProcessEnvironment>
#include <QString>
#include <QtGlobal>

class QJsonObject;

namespace spellvision::shell
{

struct RuntimeProfile
{
    QString projectRoot;
    QString workerPython;
    QString workerScript;
    QString workerHost = QStringLiteral("127.0.0.1");
    quint16 workerPort = 8765;
    QString comfyRoot;
    QString comfyPython;
    QString comfyHost = QStringLiteral("127.0.0.1");
    quint16 comfyPort = 8188;
    QString modelsRoot;
    QString stateRoot;

    static RuntimeProfile load(const QString &projectRoot);
    void save() const;

    [[nodiscard]] bool workerPythonReady() const;
    [[nodiscard]] bool workerScriptReady() const;
    [[nodiscard]] bool comfyRootReady() const;
    [[nodiscard]] bool comfyMainReady() const;
    [[nodiscard]] bool comfyPythonReady() const;
    [[nodiscard]] bool modelsRootReady() const;
    [[nodiscard]] QString comfyMainPath() const;

    void applyToProcessEnvironment(QProcessEnvironment &environment) const;
    void applyToWorkerRequest(QJsonObject &request) const;
};

enum class ComfyQueueState
{
    Unknown,
    Idle,
    Busy,
};

bool isRegularExecutableFile(const QString &path);
bool probeWorkerProtocol(const QString &host, quint16 port, int timeoutMs = 350);
bool probeTcpPort(const QString &host, quint16 port, int timeoutMs = 350);
bool probeComfyProtocol(const QString &host, quint16 port, int timeoutMs = 350);
ComfyQueueState probeComfyQueueState(const QString &host, quint16 port, int timeoutMs = 500);
QString resolvePreferredComfyRoot(const QString &configured);

} // namespace spellvision::shell
