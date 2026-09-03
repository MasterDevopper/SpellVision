#include "RuntimeProfile.h"

#include <QDir>
#include <QHash>
#include <QProcess>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QElapsedTimer>
#include <QProcessEnvironment>
#include <QSettings>
#include <QStandardPaths>
#include <QTcpSocket>
#include <QHostAddress>
#include <QUrl>

namespace spellvision::shell
{
namespace
{
constexpr int kWorkerProtocolVersion = 1;

QString normalized(const QString &path)
{
    const QString trimmed = path.trimmed();
    if (trimmed.isEmpty())
        return {};
    return QDir::fromNativeSeparators(QFileInfo(trimmed).absoluteFilePath());
}

QString envOrSettings(const char *environmentName, const QString &settingsKey)
{
    const QString fromEnv = QString::fromLocal8Bit(qgetenv(environmentName)).trimmed();
    if (!fromEnv.isEmpty())
        return normalized(fromEnv);

    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    return settings.value(settingsKey).toString().trimmed();
}

QString firstRegularExecutable(const QStringList &candidates)
{
    for (const QString &candidate : candidates)
    {
        if (isRegularExecutableFile(candidate))
            return normalized(candidate);
    }
    return {};
}

bool decodeChunkedBody(const QByteArray &encoded, QByteArray *decoded)
{
    if (!decoded)
        return false;
    decoded->clear();
    qsizetype offset = 0;
    while (true)
    {
        const qsizetype lineEnd = encoded.indexOf("\r\n", offset);
        if (lineEnd < 0)
            return false;
        QByteArray sizeText = encoded.mid(offset, lineEnd - offset).trimmed();
        const qsizetype extension = sizeText.indexOf(';');
        if (extension >= 0)
            sizeText.truncate(extension);
        bool sizeOk = false;
        const qulonglong chunkSize = sizeText.toULongLong(&sizeOk, 16);
        if (!sizeOk)
            return false;
        offset = lineEnd + 2;
        if (chunkSize == 0)
            return true;
        if (chunkSize > static_cast<qulonglong>(encoded.size() - offset))
            return false;
        decoded->append(encoded.mid(offset, static_cast<qsizetype>(chunkSize)));
        offset += static_cast<qsizetype>(chunkSize);
        if (encoded.mid(offset, 2) != QByteArrayLiteral("\r\n"))
            return false;
        offset += 2;
    }
}

} // namespace

bool probeTcpPort(const QString &host, quint16 port, int timeoutMs)
{
    QTcpSocket socket;
    socket.connectToHost(host, port);
    return socket.waitForConnected(timeoutMs);
}

bool probeComfyProtocol(const QString &host, quint16 port, int timeoutMs)
{
    QTcpSocket socket;
    QElapsedTimer timer;
    timer.start();
    socket.connectToHost(host, port);
    if (!socket.waitForConnected(timeoutMs))
        return false;

    const QByteArray request = QByteArrayLiteral("GET /system_stats HTTP/1.1\r\nHost: ")
                               + host.toUtf8() + ':' + QByteArray::number(port)
                               + QByteArrayLiteral("\r\nAccept: application/json\r\nConnection: close\r\n\r\n");
    socket.write(request);
    const int writeRemaining = qMax(1, timeoutMs - static_cast<int>(timer.elapsed()));
    if (!socket.waitForBytesWritten(writeRemaining))
        return false;

    QByteArray response;
    while (timer.elapsed() < timeoutMs)
    {
        const int remaining = qMax(1, timeoutMs - static_cast<int>(timer.elapsed()));
        if (!socket.waitForReadyRead(remaining))
            break;
        response.append(socket.readAll());
        if (response.size() > 1024 * 1024)
            return false;

        const qsizetype headerEnd = response.indexOf("\r\n\r\n");
        if (headerEnd < 0)
            continue;
        const QByteArray headers = response.left(headerEnd);
        const QString statusLine = QString::fromLatin1(headers.left(headers.indexOf("\r\n")));
        if (!statusLine.contains(QStringLiteral(" 200 ")))
            return false;

        QByteArray body = response.mid(headerEnd + 4);
        if (headers.toLower().contains("transfer-encoding: chunked"))
        {
            QByteArray decoded;
            if (!decodeChunkedBody(body, &decoded))
                continue;
            body = decoded;
        }
        QJsonParseError parseError{};
        const QJsonDocument document = QJsonDocument::fromJson(body, &parseError);
        if (parseError.error != QJsonParseError::NoError || !document.isObject())
            continue;
        const QJsonObject object = document.object();
        return object.value(QStringLiteral("system")).isObject()
               && object.value(QStringLiteral("devices")).isArray();
    }
    return false;
}

ComfyQueueState probeComfyQueueState(const QString &host, quint16 port, int timeoutMs)
{
    QTcpSocket socket;
    QElapsedTimer timer;
    timer.start();
    socket.connectToHost(host, port);
    if (!socket.waitForConnected(timeoutMs))
        return ComfyQueueState::Unknown;

    const QByteArray request = QByteArrayLiteral("GET /queue HTTP/1.1\r\nHost: ")
                               + host.toUtf8() + ':' + QByteArray::number(port)
                               + QByteArrayLiteral("\r\nAccept: application/json\r\nConnection: close\r\n\r\n");
    socket.write(request);
    const int writeRemaining = qMax(1, timeoutMs - static_cast<int>(timer.elapsed()));
    if (!socket.waitForBytesWritten(writeRemaining))
        return ComfyQueueState::Unknown;

    QByteArray response;
    while (timer.elapsed() < timeoutMs)
    {
        const int remaining = qMax(1, timeoutMs - static_cast<int>(timer.elapsed()));
        if (!socket.waitForReadyRead(remaining))
            break;
        response.append(socket.readAll());
        if (response.size() > 1024 * 1024)
            return ComfyQueueState::Unknown;

        const qsizetype headerEnd = response.indexOf("\r\n\r\n");
        if (headerEnd < 0)
            continue;
        const QByteArray headers = response.left(headerEnd);
        const QString statusLine = QString::fromLatin1(headers.left(headers.indexOf("\r\n")));
        if (!statusLine.contains(QStringLiteral(" 200 ")))
            return ComfyQueueState::Unknown;

        QByteArray body = response.mid(headerEnd + 4);
        if (headers.toLower().contains("transfer-encoding: chunked"))
        {
            QByteArray decoded;
            if (!decodeChunkedBody(body, &decoded))
                continue;
            body = decoded;
        }
        QJsonParseError parseError{};
        const QJsonDocument document = QJsonDocument::fromJson(body, &parseError);
        if (parseError.error != QJsonParseError::NoError || !document.isObject())
            continue;
        const QJsonObject object = document.object();
        if (!object.value(QStringLiteral("queue_running")).isArray()
            || !object.value(QStringLiteral("queue_pending")).isArray())
            return ComfyQueueState::Unknown;
        const bool busy = !object.value(QStringLiteral("queue_running")).toArray().isEmpty()
                          || !object.value(QStringLiteral("queue_pending")).toArray().isEmpty();
        return busy ? ComfyQueueState::Busy : ComfyQueueState::Idle;
    }
    return ComfyQueueState::Unknown;
}

// The four names the ComfyUI install root has been read under, in precedence order. This side
// only ever exported and read SPELLVISION_COMFY, while the worker's readiness check read
// SPELLVISION_COMFY_ROOT and COMFYUI_ROOT -- an empty intersection, so the two halves could not
// agree about which ComfyUI they were discussing. Mirrors python/comfy_root.py exactly.
static const char *const kComfyRootEnvNames[] = {
    "SPELLVISION_COMFY",
    "SPELLVISION_COMFY_ROOT",
    "COMFYUI_ROOT",
    "COMFY_ROOT",
};

// The 2026-08-31 cutover (Doc 25 S7). LIVE is the v0.34.0 core in its own isolated venv.
static const char *const kLiveComfyRoot = "C:/sv_comfynext_v034/ComfyUI";

// Every tree that USED to be live, newest first. A list rather than one constant because the
// previous version redirected exactly one suffix, "comfy_runtime/ComfyUI", and would therefore have
// let a stale "C:/sv_comfynext/ComfyUI" -- the root that had been live for six weeks, so the one
// most likely to be sitting in QSettings or in saved metadata -- pass straight through to the
// superseded core. Nothing errors in that case: the old tree and its venv are still on disk, so
// every existence check succeeds and the only symptom is the wrong core.
static const char *const kSupersededComfyRoots[] = {
    "C:/sv_comfynext/ComfyUI",              // v0.27.0, Jul-10 core -- the 2026-07-17 cutover
    "D:/AI_ASSETS/comfy_runtime/ComfyUI",   // cf9cbec5, May build
};

// Where to fall back when LIVE is gone: the most recent superseded build, not the oldest.
static const char *const kRollbackComfyRoot = kSupersededComfyRoots[0];

QString comfyRootEnvOverride(QString *name)
{
    for (const char *const envName : kComfyRootEnvNames)
    {
        const QString value = QString::fromLocal8Bit(qgetenv(envName)).trimmed();
        if (value.isEmpty())
            continue;
        if (name)
            *name = QString::fromLatin1(envName);
        return value;
    }
    return {};
}

namespace
{
// Kept identical to python/comfy_launch_policy.py. tests/test_comfy_launch_policy.py asserts the
// two sides name the same flag, the same variable and the same env, which is what stops them
// drifting apart again -- the same shape as the comfy-root resolver's cross-language check.
constexpr const char *kAttentionEnvVar = "SPELLVISION_COMFY_ATTENTION";
constexpr const char *kSageFlag = "--use-sage-attention";

// VRAM headroom. The ONE memory lever that works on this core: DynamicVRAM (comfy-aimdo) is on by
// default and hooks CUDA allocation directly, so --lowvram is documented by ComfyUI itself as a
// no-op, and --novram/--highvram/--gpu-only turn the offload engine OFF -- reaching for one to
// "make it fit" disables the thing that was making it fit. Measured numbers are in
// python/comfy_launch_policy.py, which this mirrors.
constexpr const char *kVramHeadroomEnvVar = "SPELLVISION_COMFY_VRAM_HEADROOM";
constexpr const char *kReserveVramFlag = "--reserve-vram";

bool sageAttentionAvailable(const QString &comfyPython)
{
    // Cached per interpreter: a probe costs a process, and readiness asks far more often than a
    // launch happens.
    static QHash<QString, bool> cache;
    if (comfyPython.trimmed().isEmpty())
        return false;
    const auto hit = cache.constFind(comfyPython);
    if (hit != cache.constEnd())
        return hit.value();

    QProcess probe;
    probe.setProcessChannelMode(QProcess::MergedChannels);
    probe.start(comfyPython, {QStringLiteral("-c"), QStringLiteral("import sageattention")});
    const bool available = probe.waitForStarted(5000) && probe.waitForFinished(30000)
                           && probe.exitStatus() == QProcess::NormalExit && probe.exitCode() == 0;
    cache.insert(comfyPython, available);
    return available;
}
} // namespace

QStringList comfyLaunchArguments(const QString &comfyPython, QString *refusalReason)
{
    if (refusalReason)
        refusalReason->clear();

    const QString requested =
        QString::fromLocal8Bit(qgetenv(kAttentionEnvVar)).trimmed().toLower();
    const bool asksForSdpa = requested == QStringLiteral("sdpa") || requested == QStringLiteral("pytorch")
                             || requested == QStringLiteral("torch") || requested == QStringLiteral("none")
                             || requested == QStringLiteral("off") || requested == QStringLiteral("default");
    if (asksForSdpa)
        return {};

    const bool asksForSage = requested == QStringLiteral("sage")
                             || requested == QStringLiteral("sageattention")
                             || requested == QStringLiteral("sage_attention");
    QStringList arguments;
    if (!sageAttentionAvailable(comfyPython))
    {
        if (asksForSage && refusalReason)
        {
            // Asked for by name and missing. ComfyUI would exit(-1) into a log file; say it here
            // instead, where someone is watching.
            *refusalReason = QStringLiteral(
                "%1=sage, but `import sageattention` fails in %2. ComfyUI exits when %3 is passed "
                "without the package. Install it, or set %1=sdpa.")
                .arg(QString::fromLatin1(kAttentionEnvVar), comfyPython, QString::fromLatin1(kSageFlag));
        }
    }
    else
    {
        arguments << QString::fromLatin1(kSageFlag);
    }

    arguments << comfyVramHeadroomArguments(refusalReason);
    return arguments;
}

QStringList comfyVramHeadroomArguments(QString *refusalReason)
{
    const QString requested =
        QString::fromLocal8Bit(qgetenv(kVramHeadroomEnvVar)).trimmed().toLower();
    if (requested.isEmpty())
        return {};  // ComfyUI's own OS-dependent reservation. Nothing has shown it to be wrong.

    static const QStringList inert = {
        QStringLiteral("--lowvram"), QStringLiteral("--novram"), QStringLiteral("--highvram"),
        QStringLiteral("--gpu-only"), QStringLiteral("--cpu"),
    };
    if (inert.contains(requested))
    {
        if (refusalReason && refusalReason->isEmpty())
            *refusalReason = QStringLiteral(
                "%1=%2 names a flag that is inert or harmful under DynamicVRAM. It takes a number "
                "of GB to reserve for the OS.")
                .arg(QString::fromLatin1(kVramHeadroomEnvVar), requested);
        return {};
    }

    bool ok = false;
    const double gb = requested.toDouble(&ok);
    if (!ok || gb < 0.0)
    {
        if (refusalReason && refusalReason->isEmpty())
            *refusalReason = QStringLiteral("%1=%2 is not a number of GB.")
                                 .arg(QString::fromLatin1(kVramHeadroomEnvVar), requested);
        return {};
    }
    return {QString::fromLatin1(kReserveVramFlag), QString::number(gb, 'g', 6)};
}

void applyComfyLaunchEnvironment(QProcessEnvironment &environment)
{
    environment.insert(QStringLiteral("PYTHONUTF8"), QStringLiteral("1"));
    environment.insert(QStringLiteral("PYTHONIOENCODING"), QStringLiteral("utf-8"));
}

QString resolvePreferredComfyRoot(const QString &configured)
{
    // An environment override outranks the saved setting, which is the behaviour every call site
    // already had -- they just each read one name.
    const QString overridden = comfyRootEnvOverride(nullptr);
    const QString candidate = overridden.isEmpty() ? configured.trimmed() : overridden;

    const QString live = QDir::fromNativeSeparators(QString::fromLatin1(kLiveComfyRoot));
    if (!candidate.isEmpty())
    {
        // A path into the pre-cutover tree becomes the live one when the live one is there. Saved
        // settings and old metadata still carry it, and following it would run generation against
        // the May core while everything else talks to the July one.
        QString key = QDir::fromNativeSeparators(candidate).toLower();
        while (key.endsWith(QLatin1Char('/')))
            key.chop(1);
        if (QDir(live).exists())
        {
            for (const char *const superseded : kSupersededComfyRoots)
            {
                const QString old = QString::fromLatin1(superseded).toLower();
                // Exact, or a path INSIDE it. Compared with the separator attached on purpose:
                // "c:/sv_comfynext_v034/comfyui" starts with "c:/sv_comfynext/comfyui" as a bare
                // substring, so a looser test would redirect the live root onto itself today and
                // onto the wrong tree the moment the names stop overlapping.
                if (key == old || key.startsWith(old + QLatin1Char('/')))
                    return normalized(live);
            }
        }
        return normalized(candidate);
    }

    if (QDir(live).exists())
        return normalized(live);

    const QString rollback = QDir::fromNativeSeparators(QString::fromLatin1(kRollbackComfyRoot));
    if (QDir(rollback).exists())
    {
        qWarning("falling back to the ROLLBACK ComfyUI at %s -- the live install at %s is not "
                 "present. Set SPELLVISION_COMFY if this is not what you want.",
                 qPrintable(rollback), qPrintable(live));
        return normalized(rollback);
    }

    return {};
}

QString resolveLiveComfyRoot(const QString &projectRoot, const QString &host, quint16 port)
{
    const QString root = normalized(projectRoot);
    if (root.isEmpty())
        return {};

    QFile sessionFile(QDir(root).filePath(QStringLiteral("build/.comfy_runtime.session.json")));
    if (!sessionFile.open(QIODevice::ReadOnly))
        return {};

    QJsonParseError parseError{};
    const QJsonDocument doc = QJsonDocument::fromJson(sessionFile.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
        return {};

    const QJsonObject session = doc.object();

    // The record only describes the instance it launched. If it is about a different endpoint than
    // the caller is asking about, it says nothing useful.
    const QString sessionHost = session.value(QStringLiteral("host")).toString().trimmed();
    const int sessionPort = session.value(QStringLiteral("port")).toInt();
    if (sessionPort != static_cast<int>(port))
        return {};
    if (!sessionHost.isEmpty() && sessionHost != host)
        return {};

    const QString comfyRoot = normalized(session.value(QStringLiteral("comfy_root")).toString());
    if (comfyRoot.isEmpty())
        return {};

    // Guard against a stale file naming an install that has since been moved or deleted.
    const QString comfyMain = session.value(QStringLiteral("comfy_main")).toString().trimmed();
    const QString mainPath = comfyMain.isEmpty() ? QDir(comfyRoot).filePath(QStringLiteral("main.py"))
                                                 : normalized(comfyMain);
    if (!QFileInfo(mainPath).isFile())
        return {};

    return comfyRoot;
}

bool isRegularExecutableFile(const QString &path)
{
    if (path.trimmed().isEmpty())
        return false;
    const QFileInfo info(path);
    return info.isFile() && !info.isDir();
}

bool probeWorkerProtocol(const QString &host, quint16 port, int timeoutMs)
{
    QTcpSocket socket;
    socket.connectToHost(host, port);
    if (!socket.waitForConnected(timeoutMs))
        return false;

    socket.write(QJsonDocument(QJsonObject{{QStringLiteral("command"), QStringLiteral("ping")}})
                     .toJson(QJsonDocument::Compact)
                 + '\n');
    if (!socket.waitForBytesWritten(timeoutMs))
        return false;

    QByteArray response;
    QElapsedTimer timer;
    timer.start();
    while (timer.elapsed() < timeoutMs)
    {
        const int remaining = qMax(1, timeoutMs - static_cast<int>(timer.elapsed()));
        if (!socket.waitForReadyRead(remaining))
            break;
        response.append(socket.readAll());
        while (true)
        {
            const qsizetype newline = response.indexOf('\n');
            if (newline < 0)
                break;
            const QByteArray line = response.left(newline).trimmed();
            response.remove(0, newline + 1);
            if (line.isEmpty())
                continue;
            const QJsonObject object = QJsonDocument::fromJson(line).object();
            if (object.value(QStringLiteral("type")).toString() == QStringLiteral("result")
                && object.value(QStringLiteral("ok")).toBool()
                && object.value(QStringLiteral("pong")).toBool()
                && object.value(QStringLiteral("service")).toString() == QStringLiteral("spellvision_worker")
                && object.value(QStringLiteral("protocol_version")).toInt(-1) == kWorkerProtocolVersion)
                return true;
        }
    }
    return false;
}

bool RuntimeProfile::comfyEndpointIsLocal() const
{
    // Mirrors comfy_endpoint.is_local_endpoint. Load-bearing for anything that manages the ComfyUI
    // process or reads its FILES: starting it, stopping it, installing node packs, or scanning its
    // output directory are all meaningless against a ComfyUI on another machine -- and the output
    // scan is the dangerous one, because the local directory is not empty, it holds the previous
    // local session's renders.
    const QString host = comfyHost.trimmed().toLower();
    if (host.isEmpty() || host == QStringLiteral("localhost") || host == QStringLiteral("0.0.0.0")
        || host == QStringLiteral("::1"))
        return true;
    return QHostAddress(host).isLoopback();
}

RuntimeProfile RuntimeProfile::load(const QString &projectRoot)
{
    RuntimeProfile profile;
    profile.projectRoot = normalized(projectRoot);
    profile.workerScript = QDir(profile.projectRoot).filePath(QStringLiteral("python/worker_service.py"));

    const QString virtualEnv = QString::fromLocal8Bit(qgetenv("VIRTUAL_ENV")).trimmed();
    profile.workerPython = firstRegularExecutable({
        envOrSettings("SPELLVISION_WORKER_PYTHON", QStringLiteral("runtime/workerPython")),
        virtualEnv.isEmpty() ? QString() : QDir(virtualEnv).filePath(QStringLiteral("Scripts/python.exe")),
        QDir(profile.projectRoot).filePath(QStringLiteral(".venv/Scripts/python.exe")),
    });

    const QString configuredComfy = envOrSettings("SPELLVISION_COMFY", QStringLiteral("runtime/comfyRoot"));
    profile.comfyRoot = resolvePreferredComfyRoot(configuredComfy);

    QStringList comfyPythonCandidates{
        envOrSettings("SPELLVISION_COMFY_PYTHON", QStringLiteral("runtime/comfyPython")),
    };
    if (!profile.comfyRoot.isEmpty())
    {
        comfyPythonCandidates << QDir(profile.comfyRoot).filePath(QStringLiteral("../.venv/Scripts/python.exe"))
                              << QDir(profile.comfyRoot).filePath(QStringLiteral("venv/Scripts/python.exe"));
    }
    profile.comfyPython = firstRegularExecutable(comfyPythonCandidates);

    const QString configuredModels = envOrSettings("SPELLVISION_MODELS", QStringLiteral("runtime/modelsRoot"));
    profile.modelsRoot = configuredModels.isEmpty() ? QString() : normalized(configuredModels);

    const QString configuredHost = QString::fromLocal8Bit(qgetenv("SPELLVISION_WORKER_HOST")).trimmed();
    if (!configuredHost.isEmpty())
        profile.workerHost = configuredHost;
    bool portOk = false;
    const int configuredPort = QString::fromLocal8Bit(qgetenv("SPELLVISION_WORKER_PORT")).toInt(&portOk);
    if (portOk && configuredPort > 0 && configuredPort <= 65535)
        profile.workerPort = static_cast<quint16>(configuredPort);

    // The ComfyUI ENDPOINT, resolved rather than assumed. `comfyHost` used to be a hardcoded
    // 127.0.0.1 that read nothing, while `comfyPort` right here read its environment -- so the app
    // could be pointed at another machine's PORT and never at another machine. Meanwhile the worker
    // honoured COMFY_API_URL and would happily generate on a remote ComfyUI, leaving every Qt probe
    // reporting on localhost: the Runtime page could show a healthy local install while generation
    // ran somewhere else entirely.
    //
    // Precedence is COPIED FROM python/comfy_endpoint.py, deliberately and in the same order. Two
    // resolvers that disagree are worse than one that is wrong, and this is the ninth root/endpoint
    // resolver only if it answers differently from the eighth.
    bool comfyEndpointFromUrl = false;
    for (const char *name : {"COMFY_API_URL", "SPELLVISION_COMFY_URL", "SPELLVISION_COMFY_ENDPOINT"}) {
        QString raw = QString::fromLocal8Bit(qgetenv(name)).trimmed();
        if (raw.isEmpty())
            continue;
        while (raw.endsWith(QLatin1Char('/')))
            raw.chop(1);
        // `COMFY_API_URL=otherbox:8188` is the obvious thing to type, and QUrl reads a bare
        // host:port as scheme "otherbox" with no host. Same accommodation the Python side makes.
        if (!raw.contains(QStringLiteral("://")))
            raw.prepend(QStringLiteral("http://"));
        const QUrl url(raw);
        if (!url.isValid() || url.host().isEmpty())
            continue;
        profile.comfyHost = url.host();
        if (url.port() > 0)
            profile.comfyPort = static_cast<quint16>(url.port());
        comfyEndpointFromUrl = true;
        break;
    }
    if (!comfyEndpointFromUrl) {
        const QString configuredComfyHost = QString::fromLocal8Bit(qgetenv("SPELLVISION_COMFY_HOST")).trimmed();
        if (!configuredComfyHost.isEmpty())
            profile.comfyHost = configuredComfyHost;
        bool comfyPortOk = false;
        const int configuredComfyPort = QString::fromLocal8Bit(qgetenv("SPELLVISION_COMFY_PORT")).toInt(&comfyPortOk);
        if (comfyPortOk && configuredComfyPort > 0 && configuredComfyPort <= 65535)
            profile.comfyPort = static_cast<quint16>(configuredComfyPort);
    }

    const QString configuredStateRoot = QString::fromLocal8Bit(qgetenv("SPELLVISION_STATE_ROOT")).trimmed();
    if (!configuredStateRoot.isEmpty())
        profile.stateRoot = normalized(configuredStateRoot);
    else
        profile.stateRoot = normalized(QDir(QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation))
                                           .filePath(QStringLiteral("runtime")));
    return profile;
}

void RuntimeProfile::save() const
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    if (!comfyRoot.trimmed().isEmpty())
        settings.setValue(QStringLiteral("runtime/comfyRoot"), comfyRoot);
    if (!modelsRoot.trimmed().isEmpty())
        settings.setValue(QStringLiteral("runtime/modelsRoot"), modelsRoot);
    if (!comfyPython.trimmed().isEmpty())
        settings.setValue(QStringLiteral("runtime/comfyPython"), comfyPython);
    if (!workerPython.trimmed().isEmpty())
        settings.setValue(QStringLiteral("runtime/workerPython"), workerPython);
}

bool RuntimeProfile::workerPythonReady() const
{
    return isRegularExecutableFile(workerPython);
}

bool RuntimeProfile::workerScriptReady() const
{
    return QFileInfo(workerScript).isFile();
}

bool RuntimeProfile::comfyRootReady() const
{
    return QDir(comfyRoot).exists();
}

QString RuntimeProfile::comfyMainPath() const
{
    return QDir(comfyRoot).filePath(QStringLiteral("main.py"));
}

bool RuntimeProfile::comfyMainReady() const
{
    return QFileInfo(comfyMainPath()).isFile();
}

bool RuntimeProfile::comfyPythonReady() const
{
    return isRegularExecutableFile(comfyPython);
}

bool RuntimeProfile::modelsRootReady() const
{
    return QDir(modelsRoot).exists();
}

void RuntimeProfile::applyToProcessEnvironment(QProcessEnvironment &environment) const
{
    environment.insert(QStringLiteral("SPELLVISION_ROOT"), projectRoot);
    if (!comfyRoot.trimmed().isEmpty())
        environment.insert(QStringLiteral("SPELLVISION_COMFY"), comfyRoot);
    if (!modelsRoot.trimmed().isEmpty())
        environment.insert(QStringLiteral("SPELLVISION_MODELS"), modelsRoot);
    if (!comfyPython.trimmed().isEmpty())
        environment.insert(QStringLiteral("SPELLVISION_COMFY_PYTHON"), comfyPython);
    if (!workerPython.trimmed().isEmpty())
        environment.insert(QStringLiteral("SPELLVISION_WORKER_PYTHON"), workerPython);
    if (!stateRoot.trimmed().isEmpty())
        environment.insert(QStringLiteral("SPELLVISION_STATE_ROOT"), stateRoot);
    if (environment.value(QStringLiteral("SPELLVISION_WORKER_HOST")).trimmed().isEmpty())
        environment.insert(QStringLiteral("SPELLVISION_WORKER_HOST"), workerHost);
    if (environment.value(QStringLiteral("SPELLVISION_WORKER_PORT")).trimmed().isEmpty())
        environment.insert(QStringLiteral("SPELLVISION_WORKER_PORT"), QString::number(workerPort));
    if (environment.value(QStringLiteral("SPELLVISION_COMFY_PORT")).trimmed().isEmpty())
        environment.insert(QStringLiteral("SPELLVISION_COMFY_PORT"), QString::number(comfyPort));
}

void RuntimeProfile::applyToWorkerRequest(QJsonObject &request) const
{
    if (!comfyRoot.trimmed().isEmpty())
        request.insert(QStringLiteral("comfy_root"), comfyRoot);
    if (!comfyPython.trimmed().isEmpty())
        request.insert(QStringLiteral("comfy_python_executable"), comfyPython);
    if (!modelsRoot.trimmed().isEmpty())
        request.insert(QStringLiteral("models_root"), modelsRoot);
    if (!workerPython.trimmed().isEmpty())
        request.insert(QStringLiteral("python_executable"), workerPython);
}

} // namespace spellvision::shell
