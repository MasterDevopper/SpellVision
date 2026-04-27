#pragma once

#include <QVector>
#include <QString>

namespace spellvision::assets
{

struct LoraStackEntry
{
    QString display;
    QString value;
    double weight = 1.0;
    bool enabled = true;
};

class ModelStackState final
{
public:
    ModelStackState() = delete;

    static QString normalizedPath(const QString &value);
    static QString firstEnabledLoraValue(const QVector<LoraStackEntry> &stack);
    static int enabledLoraCount(const QVector<LoraStackEntry> &stack);
    static bool containsLora(const QVector<LoraStackEntry> &stack, const QString &value);
    static void upsertLora(QVector<LoraStackEntry> &stack, const LoraStackEntry &entry);
    static QString summaryText(const QVector<LoraStackEntry> &stack);
};

} // namespace spellvision::assets
