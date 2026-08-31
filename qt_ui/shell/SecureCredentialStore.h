#pragma once

#include <QString>

class SecureCredentialStore
{
public:
    static QString storePath();
    static bool hasCredential(const QString &name);
    // Decrypt and return a stored secret, empty when absent or undecryptable. Restricted to the
    // known key names, same as setCredential. Call it only at the point of use and do not hold the
    // value: the store existed with no way to read it back, so the key a user saved in Settings
    // could never reach the code that needed it.
    static QString credential(const QString &name);
    static bool setCredential(const QString &name, const QString &value);
    static bool clearCredential(const QString &name);
};
