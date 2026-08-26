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

// The root of the ComfyUI instance that is ACTUALLY serving `host:port`, or an empty string when
// that cannot be established.
//
// This exists because the configured root and the running one can disagree. scripts/dev/
// start_comfy.ps1 records the real install it launched -- taken from the process command line --
// in <projectRoot>/build/.comfy_runtime.session.json. When SpellVision adopts an already-running
// ComfyUI it has no such knowledge, and writing the *configured* root in its place quietly
// mislabels the live runtime: after the 2026-07-17 cutover the stored QSettings root still pointed
// at the D:\ rollback build while :8188 was served from C:\sv_comfynext, so the Runtime page
// reported the wrong install and aimed its install/restart actions at it.
//
// Only trusts the launcher's record when it matches the host/port being asked about and its
// recorded main.py still exists, so a stale file cannot win over a live probe.
QString resolveLiveComfyRoot(const QString &projectRoot, const QString &host, quint16 port);

} // namespace spellvision::shell
