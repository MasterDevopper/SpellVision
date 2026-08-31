#include "SecureCredentialStore.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QIODevice>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStandardPaths>

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <wincrypt.h>
#endif

namespace
{
const QByteArray kEntropy = QByteArrayLiteral("SpellVision.credentials.v2");
// Must stay in lockstep with python/credential_store.py KNOWN_KEYS. The two stores write the
// same file, and their write behaviour is ASYMMETRIC: this one read-modify-writes and so
// preserves keys it does not know, while the Python side rebuilds the secrets object from
// its own KNOWN_KEYS and would therefore DROP a key only C++ knew about.
//
// worker_integration_token is the shared secret an external program (SpellBound Engine)
// presents to reach the worker over an SSH tunnel. There is no Settings field for it yet;
// it is listed so the two stores agree and a future field needs no migration.
const QStringList kKnownKeys = {QStringLiteral("hf_token"), QStringLiteral("civitai_api_key"),
                               QStringLiteral("worker_integration_token")};

#ifdef Q_OS_WIN
QByteArray protect(const QByteArray &plain)
{
    DATA_BLOB input{};
    input.cbData = static_cast<DWORD>(plain.size());
    input.pbData = reinterpret_cast<BYTE *>(const_cast<char *>(plain.constData()));
    DATA_BLOB entropy{};
    entropy.cbData = static_cast<DWORD>(kEntropy.size());
    entropy.pbData = reinterpret_cast<BYTE *>(const_cast<char *>(kEntropy.constData()));
    DATA_BLOB output{};
    if (!CryptProtectData(&input, L"SpellVision credential", &entropy, nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &output))
        return {};
    const QByteArray blob(reinterpret_cast<const char *>(output.pbData), static_cast<int>(output.cbData));
    LocalFree(output.pbData);
    return blob.toBase64();
}

QByteArray unprotect(const QByteArray &blobB64)
{
    const QByteArray raw = QByteArray::fromBase64(blobB64);
    if (raw.isEmpty())
        return {};
    DATA_BLOB input{};
    input.cbData = static_cast<DWORD>(raw.size());
    input.pbData = reinterpret_cast<BYTE *>(const_cast<char *>(raw.constData()));
    DATA_BLOB entropy{};
    entropy.cbData = static_cast<DWORD>(kEntropy.size());
    entropy.pbData = reinterpret_cast<BYTE *>(const_cast<char *>(kEntropy.constData()));
    DATA_BLOB output{};
    if (!CryptUnprotectData(&input, nullptr, &entropy, nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &output))
        return {};
    const QByteArray plain(reinterpret_cast<const char *>(output.pbData), static_cast<int>(output.cbData));
    LocalFree(output.pbData);
    return plain;
}
#endif

QJsonObject readPayload(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return {};
    return QJsonDocument::fromJson(file.readAll()).object();
}

bool writePayload(const QString &path, const QJsonObject &payload)
{
    QDir().mkpath(QFileInfo(path).absolutePath());
    const QString tmp = path + QStringLiteral(".tmp");
    QFile file(tmp);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return false;
    file.write(QJsonDocument(payload).toJson(QJsonDocument::Indented));
    file.close();
    QFile::remove(path);
    return QFile::rename(tmp, path);
}

QJsonObject secretsObject(QJsonObject payload)
{
    if (payload.value(QStringLiteral("version")).toInt(1) >= 2
        && payload.value(QStringLiteral("secrets")).isObject())
        return payload.value(QStringLiteral("secrets")).toObject();

#ifdef Q_OS_WIN
    QJsonObject migrated;
    for (const QString &key : kKnownKeys) {
        const QString plain = payload.value(key).toString().trimmed();
        if (plain.isEmpty())
            continue;
        const QByteArray blob = protect(plain.toUtf8());
        if (!blob.isEmpty())
            migrated.insert(key, QString::fromLatin1(blob));
    }
    QJsonObject next;
    next.insert(QStringLiteral("version"), 2);
    next.insert(QStringLiteral("backend"), QStringLiteral("dpapi"));
    next.insert(QStringLiteral("secrets"), migrated);
    writePayload(SecureCredentialStore::storePath(), next);
    return migrated;
#else
    return {};
#endif
}
}

QString SecureCredentialStore::storePath()
{
    const QByteArray override = qgetenv("SPELLVISION_CREDENTIAL_STORE");
    if (!override.trimmed().isEmpty())
        return QString::fromLocal8Bit(override);
    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation);
    return QDir(base).filePath(QStringLiteral("DarkDuck/SpellVision/credentials.json"));
}

bool SecureCredentialStore::hasCredential(const QString &name)
{
    const QJsonObject secrets = secretsObject(readPayload(storePath()));
    return !secrets.value(name).toString().trimmed().isEmpty();
}

QString SecureCredentialStore::credential(const QString &name)
{
    if (!kKnownKeys.contains(name))
        return {};
#ifdef Q_OS_WIN
    const QJsonObject secrets = secretsObject(readPayload(storePath()));
    const QString blob = secrets.value(name).toString().trimmed();
    if (blob.isEmpty())
        return {};
    // DPAPI decryption is bound to this user account, so a copied credentials.json is inert.
    return QString::fromUtf8(unprotect(blob.toLatin1())).trimmed();
#else
    return {};
#endif
}

bool SecureCredentialStore::setCredential(const QString &name, const QString &value)
{
    if (!kKnownKeys.contains(name))
        return false;
#ifdef Q_OS_WIN
    QJsonObject secrets = secretsObject(readPayload(storePath()));
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        secrets.remove(name);
    else {
        const QByteArray blob = protect(trimmed.toUtf8());
        if (blob.isEmpty())
            return false;
        secrets.insert(name, QString::fromLatin1(blob));
    }
    QJsonObject payload;
    payload.insert(QStringLiteral("version"), 2);
    payload.insert(QStringLiteral("backend"), QStringLiteral("dpapi"));
    payload.insert(QStringLiteral("secrets"), secrets);
    return writePayload(storePath(), payload);
#else
    Q_UNUSED(value);
    return false;
#endif
}

bool SecureCredentialStore::clearCredential(const QString &name)
{
    return setCredential(name, QString());
}
