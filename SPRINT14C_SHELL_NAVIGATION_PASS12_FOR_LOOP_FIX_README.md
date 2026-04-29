# Sprint 14C Pass 12 For-Loop Type Fix

Fixes the MainWindow side-rail loop after ShellNavigationController extraction.

The original transform left a typed loop variable using `RailButtonSpec`, but that type now lives inside the shell controller layer. The safest call-site form is:

```cpp
for (const auto &spec : spellvision::shell::ShellNavigationController::railButtonSpecs())
```

This patch updates only the affected loop in `qt_ui/MainWindow.cpp`.
