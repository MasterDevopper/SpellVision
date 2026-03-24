# SpellVision First-Pass UI Shell

This bundle gives you the **first-pass persistent application shell** for SpellVision.

## Included
- VSCode-style top menu bar
- Thin status strip under the menu
- Persistent left mode rail across the full app
- Balanced Production Home page
- Placeholder pages for:
  - Text to Image
  - Image to Image
  - Text to Video
  - Image to Video
  - Workflows
  - Models
  - Inspiration
  - History
  - System
  - Managers
  - Settings
- Persistent docks for:
  - Telemetry
  - Queue
  - Logs
  - Details

## Add these sources to your CMake target
```cmake
qt_ui/MainWindow.h
qt_ui/MainWindow.cpp
qt_ui/HomePage.h
qt_ui/HomePage.cpp
qt_ui/ModePage.h
qt_ui/ModePage.cpp
```

## Notes
- This pass is **layout-first**, not feature-complete.
- The left rail stays persistent while the center page changes.
- Telemetry remains singular and global rather than duplicated in multiple pages.
- Home is the chosen **Balanced Production Home** direction.
