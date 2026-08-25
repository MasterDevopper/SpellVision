#include "RuntimeProfile.h"

#include <QDir>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QElapsedTimer>
#include <QProcessEnvironment>
#include <QSettings>
#include <QStandardPaths>
#include <QTcpSocket>

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

QString resolvePreferredComfyRoot(const QString &configured)
{
    return normalized(configured);
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

    bool comfyPortOk = false;
    const int configuredComfyPort = QString::fromLocal8Bit(qgetenv("SPELLVISION_COMFY_PORT")).toInt(&comfyPortOk);
    if (comfyPortOk && configuredComfyPort > 0 && configuredComfyPort <= 65535)
        profile.comfyPort = static_cast<quint16>(configuredComfyPort);

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
