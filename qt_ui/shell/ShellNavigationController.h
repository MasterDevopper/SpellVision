#pragma once

#include <QMap>
#include <QString>
#include <QVector>

class QAbstractButton;

namespace spellvision::shell
{

class ShellNavigationController final
{
public:
    struct RailButtonSpec
    {
        QString modeId;
        QString text;
        QString toolTip;
        QString section;  // rail group header: "Create" / "Manage" / "System"
        QString shortcut; // window-wide nav shortcut (e.g. "Ctrl+1"); navigates + shown in the tooltip
    };

    ShellNavigationController() = delete;

    static QVector<RailButtonSpec> railButtonSpecs();
    // v1.0 nav gate: true if `modeId` is hidden from the rail / command palette / navigation for
    // v1.0 (Chain Studio, Inspire -- not finished enough to offer user value). Reversible at launch
    // via env SPELLVISION_SHOW_ALL_MODES=1, or permanently by editing kV1HiddenModes in the .cpp.
    static bool isModeHidden(const QString &modeId);
    // Developer-only surfaces: the hidden modes AND any control that exists for batch testing
    // rather than for a user. One env read, SPELLVISION_SHOW_ALL_MODES, named once.
    static bool devToolsVisible();
    static QString pageContextForMode(const QString &modeId);
    static void updateModeButtonState(const QMap<QString, QAbstractButton *> &modeButtons,
                                      const QString &activeModeId);
};

} // namespace spellvision::shell
