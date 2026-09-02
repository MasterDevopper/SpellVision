#include "ShellNavigationController.h"

#include <QAbstractButton>
#include <QSet>

namespace spellvision::shell
{

bool ShellNavigationController::devToolsVisible()
{
    return !qEnvironmentVariableIsEmpty("SPELLVISION_SHOW_ALL_MODES");
}

bool ShellNavigationController::isModeHidden(const QString &modeId)
{
    // v1.0 NAV GATE (reversible). Chain Studio is hidden from the rail until recipe UX
    // is finished enough. Inspiration is now owner-approved to ship (2026-07-25) and stays visible.
    // RE-ENABLE Chain: launch with env SPELLVISION_SHOW_ALL_MODES=1; or remove from kV1HiddenModes.
    if (devToolsVisible())
        return false;
    static const QSet<QString> kV1HiddenModes = {
        QStringLiteral("chain"),
        QStringLiteral("gen3d"),
    };
    return kV1HiddenModes.contains(modeId.trimmed().toLower());
}

QVector<ShellNavigationController::RailButtonSpec> ShellNavigationController::railButtonSpecs()
{
    const QString create = QStringLiteral("Create");
    const QString manage = QStringLiteral("Manage");
    const QString system = QStringLiteral("System");
    const QVector<RailButtonSpec> all = {
        {QStringLiteral("home"), QStringLiteral("Home"), QStringLiteral("Home"), create, QStringLiteral("Ctrl+1")},
        // --- CHAIN STUDIO PASS 7C-PRELUDE RAIL ENTRY ---
        {QStringLiteral("chain"), QStringLiteral("Chain"), QStringLiteral("Chain Studio (under construction)"), create, QStringLiteral("Ctrl+2")},
        {QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("Text to Image"), create, QStringLiteral("Ctrl+3")},
        {QStringLiteral("i2i"), QStringLiteral("I2I"), QStringLiteral("Image to Image"), create, QStringLiteral("Ctrl+4")},
        {QStringLiteral("t2v"), QStringLiteral("T2V"), QStringLiteral("Text to Video"), create, QStringLiteral("Ctrl+5")},
        {QStringLiteral("i2v"), QStringLiteral("I2V"), QStringLiteral("Image to Video"), create, QStringLiteral("Ctrl+6")},
        {QStringLiteral("character"), QStringLiteral("Char"), QStringLiteral("Character Studio"), create, QStringLiteral("Ctrl+Shift+C")},
        {QStringLiteral("concept"), QStringLiteral("Concept"), QStringLiteral("Concept Reference Lab (multi-view packs)"), create, QStringLiteral("Ctrl+Shift+R")},
        {QStringLiteral("comic"), QStringLiteral("Comic"), QStringLiteral("Comic Studio"), create, QStringLiteral("Ctrl+Shift+M")},
        {QStringLiteral("gen3d"), QStringLiteral("3D"), QStringLiteral("Image to 3D (Pixal3D / TRELLIS.2)"), create, QStringLiteral("Ctrl+Shift+3")},
        {QStringLiteral("dataset"), QStringLiteral("Dataset"), QStringLiteral("Dataset Generator (prompt batch → T2I queue)"), manage, QStringLiteral("Ctrl+Shift+D")},
        {QStringLiteral("workflows"), QStringLiteral("Flows"), QStringLiteral("Workflows"), manage, QStringLiteral("Ctrl+7")},
        {QStringLiteral("history"), QStringLiteral("History"), QStringLiteral("History"), manage, QStringLiteral("Ctrl+8")},
        {QStringLiteral("inspiration"), QStringLiteral("Inspire"), QStringLiteral("Inspiration"), manage, QStringLiteral("Ctrl+9")},
        {QStringLiteral("models"), QStringLiteral("Models"), QStringLiteral("Models"), manage, QStringLiteral("Ctrl+0")},
        {QStringLiteral("runtime"), QStringLiteral("Runtime"), QStringLiteral("Comfy Manager / custom nodes / restart"), system, QStringLiteral("Ctrl+Shift+U")},
        {QStringLiteral("train"), QStringLiteral("Train"), QStringLiteral("House LoRA trainer launcher (Sohya_kk)"), system, QStringLiteral("Ctrl+Shift+T")},
        {QStringLiteral("settings"), QStringLiteral("Prefs"), QStringLiteral("Settings"), system, QStringLiteral("Ctrl+,")},
    };
    // v1.0 nav gate: drop hidden modes (Chain, Inspire) from the rail. Reversible -- see isModeHidden.
    QVector<RailButtonSpec> visible;
    visible.reserve(all.size());
    for (const auto &spec : all)
        if (!isModeHidden(spec.modeId))
            visible.push_back(spec);
    return visible;
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
    if (key == QStringLiteral("character"))
        return QStringLiteral("Character Studio");
    if (key == QStringLiteral("concept"))
        return QStringLiteral("Concept Reference");
    if (key == QStringLiteral("comic"))
        return QStringLiteral("Comic Studio");
    if (key == QStringLiteral("gen3d"))
        return QStringLiteral("3D Generation");
    if (key == QStringLiteral("dataset"))
        return QStringLiteral("Dataset");
    if (key == QStringLiteral("workflows"))
        return QStringLiteral("Workflows");
    if (key == QStringLiteral("history"))
        return QStringLiteral("History");
    if (key == QStringLiteral("inspiration"))
        return QStringLiteral("Inspiration");
    if (key == QStringLiteral("models"))
        return QStringLiteral("Models");
    if (key == QStringLiteral("runtime"))
        return QStringLiteral("Runtime / Comfy Manager");
    if (key == QStringLiteral("train"))
        return QStringLiteral("Train");
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
