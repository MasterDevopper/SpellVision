#pragma once

#include <QString>

class SecureCredentialStore
{
public:
    static QString storePath();
    static bool hasCredential(const QString &name);
    static bool setCredential(const QString &name, const QString &value);
    static bool clearCredential(const QString &name);
};
