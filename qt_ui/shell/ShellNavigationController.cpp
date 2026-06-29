#include "ShellNavigationController.h"

#include <QAbstractButton>

namespace spellvision::shell
{

QVector<ShellNavigationController::RailButtonSpec> ShellNavigationController::railButtonSpecs()
{
    const QString create = QStringLiteral("Create");
    const QString manage = QStringLiteral("Manage");
    const QString system = QStringLiteral("System");
    return {
        {QStringLiteral("home"), QStringLiteral("Home"), QStringLiteral("Home"), create},
        // --- CHAIN STUDIO PASS 7C-PRELUDE RAIL ENTRY ---
        {QStringLiteral("chain"), QStringLiteral("Chain"), QStringLiteral("Chain Studio (under construction)"), create},
        {QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("Text to Image"), create},
        {QStringLiteral("i2i"), QStringLiteral("I2I"), QStringLiteral("Image to Image"), create},
        {QStringLiteral("t2v"), QStringLiteral("T2V"), QStringLiteral("Text to Video"), create},
        {QStringLiteral("i2v"), QStringLiteral("I2V"), QStringLiteral("Image to Video"), create},
        {QStringLiteral("workflows"), QStringLiteral("Flows"), QStringLiteral("Workflows"), manage},
        {QStringLiteral("history"), QStringLiteral("History"), QStringLiteral("History"), manage},
        {QStringLiteral("inspiration"), QStringLiteral("Inspire"), QStringLiteral("Inspiration"), manage},
        {QStringLiteral("models"), QStringLiteral("Models"), QStringLiteral("Models"), manage},
        {QStringLiteral("settings"), QStringLiteral("Prefs"), QStringLiteral("Settings"), system},
    };
}

QString ShellNavigationController::pageContextForMode(const QString &modeId)
{
    const QString key = modeId.trimmed().toLower();

    if (key == QStringLiteral("home"))
        return QStringLiteral("Home");
    // --- CHAIN STUDIO PASS 7C-PRELUDE RAIL ENTRY ---
    if (key == QStringLiteral("chain"))
        return QStringLiteral("Chain Studio");
    if (key == QStringLiteral("t2i"))
        return QStringLiteral("Text to Image");
    if (key == QStringLiteral("i2i"))
        return QStringLiteral("Image to Image");
    if (key == QStringLiteral("t2v"))
        return QStringLiteral("Text to Video");
    if (key == QStringLiteral("i2v"))
        return QStringLiteral("Image to Video");
    if (key == QStringLiteral("workflows"))
        return QStringLiteral("Workflows");
    if (key == QStringLiteral("history"))
        return QStringLiteral("History");
    if (key == QStringLiteral("inspiration"))
        return QStringLiteral("Inspiration");
    if (key == QStringLiteral("models"))
        return QStringLiteral("Models");
    if (key == QStringLiteral("settings"))
        return QStringLiteral("Settings");

    return QStringLiteral("SpellVision");
}

void ShellNavigationController::updateModeButtonState(const QMap<QString, QAbstractButton *> &modeButtons,
                                                      const QString &activeModeId)
{
    for (auto it = modeButtons.cbegin(); it != modeButtons.cend(); ++it)
    {
        if (QAbstractButton *button = it.value())
            button->setChecked(it.key() == activeModeId);
    }
}

} // namespace spellvision::shell
