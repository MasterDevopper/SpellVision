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
// The environment value overriding the saved ComfyUI root, and (optionally) which name carried it.
// Empty when nothing in the environment overrides it.
QString comfyRootEnvOverride(QString *name = nullptr);

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

// The ComfyUI launch policy, shared with python/comfy_launch_policy.py.
//
// Three sites started ComfyUI with three different command lines. Only scripts/dev/start_comfy.ps1
// passed --use-sage-attention, which was measured on this box at -25.1% per iteration on Wan 2.2
// dual-noise and -22.8% end to end -- so starting SpellVision the way a USER starts it gave up
// roughly a quarter of the speed on the heaviest path in the product.
//
// The flag cannot be hardcoded. ComfyUI does exit(-1) when it is passed without the sageattention
// package installed, so this probes the interpreter that will run ComfyUI, exactly as the Python
// policy does. An explicit SPELLVISION_COMFY_ATTENTION=sage with the package missing is refused
// rather than downgraded: silently giving someone SDPA when they asked for sage is the same class
// of substitution as swapping a model.
QStringList comfyLaunchArguments(const QString &comfyPython, QString *refusalReason = nullptr);

// PYTHONUTF8 / PYTHONIOENCODING, which every ComfyUI launch needs. Not tuning: CLAUDE.md 9.2 -- the
// Jul-10 RES4LYF pack ships a non-ASCII character that crashes ComfyUI's stderr logging under
// Windows cp1252 and takes the process down with it.
void applyComfyLaunchEnvironment(QProcessEnvironment &environment);

} // namespace spellvision::shell
