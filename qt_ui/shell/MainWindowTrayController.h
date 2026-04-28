#pragma once

#include <functional>

class QDockWidget;
class QMainWindow;
class QWidget;

namespace spellvision::shell
{

class MainWindowTrayController final
{
public:
    struct Bindings
    {
        QMainWindow *owner = nullptr;
        std::function<QWidget *()> createBottomUtilityWidget;
        std::function<void(QDockWidget *)> hideNativeDockTitleBar;
        std::function<void()> updateDockChrome;

        QDockWidget **queueDock = nullptr;
        QDockWidget **detailsDock = nullptr;
        QDockWidget **logsDock = nullptr;
    };

    static void buildPersistentDocks(const Bindings &bindings);
};

} // namespace spellvision::shell
