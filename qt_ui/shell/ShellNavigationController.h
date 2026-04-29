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
    };

    ShellNavigationController() = delete;

    static QVector<RailButtonSpec> railButtonSpecs();
    static QString pageContextForMode(const QString &modeId);
    static void updateModeButtonState(const QMap<QString, QAbstractButton *> &modeButtons,
                                      const QString &activeModeId);
};

} // namespace spellvision::shell
