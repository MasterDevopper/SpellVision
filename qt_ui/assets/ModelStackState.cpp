#include "ModelStackState.h"

namespace spellvision::assets
{

QString ModelStackState::normalizedPath(const QString &value)
{
    return value.trimmed();
}

QString ModelStackState::firstEnabledLoraValue(const QVector<LoraStackEntry> &stack)
{
    for (const LoraStackEntry &entry : stack)
    {
        const QString value = normalizedPath(entry.value);
        if (entry.enabled && !value.isEmpty())
            return value;
    }
    return QString();
}

int ModelStackState::enabledLoraCount(const QVector<LoraStackEntry> &stack)
{
    int count = 0;
    for (const LoraStackEntry &entry : stack)
    {
        if (entry.enabled)
            ++count;
    }
    return count;
}

bool ModelStackState::containsLora(const QVector<LoraStackEntry> &stack, const QString &value)
{
    const QString needle = normalizedPath(value);
    if (needle.isEmpty())
        return false;

    for (const LoraStackEntry &entry : stack)
    {
        if (entry.value.compare(needle, Qt::CaseInsensitive) == 0)
            return true;
    }
    return false;
}

void ModelStackState::upsertLora(QVector<LoraStackEntry> &stack, const LoraStackEntry &entry)
{
    const QString value = normalizedPath(entry.value);
    if (value.isEmpty())
        return;

    for (LoraStackEntry &existing : stack)
    {
        if (existing.value.compare(value, Qt::CaseInsensitive) != 0)
            continue;

        existing.weight = entry.weight;
        existing.enabled = entry.enabled;
        if (existing.display.trimmed().isEmpty())
            existing.display = entry.display.trimmed();
        return;
    }

    LoraStackEntry copy = entry;
    copy.value = value;
    copy.display = copy.display.trimmed();
    stack.push_back(copy);
}

QString ModelStackState::summaryText(const QVector<LoraStackEntry> &stack)
{
    if (stack.isEmpty())
        return QStringLiteral("No LoRAs in stack");

    const int enabledCount = enabledLoraCount(stack);
    const LoraStackEntry &first = stack.first();
    return QStringLiteral("%1 in stack • %2 enabled • first: %3 @ %4")
        .arg(stack.size())
        .arg(enabledCount)
        .arg(first.display)
        .arg(QString::number(first.weight, 'f', 2));
}

} // namespace spellvision::assets
