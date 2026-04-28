# Sprint 14C Pass 8 Notes

This pass extracts the persistent dock construction entry point from MainWindow into `spellvision::shell::MainWindowTrayController`.

`MainWindow` still owns the detailed bottom utility tab contents for this first tray pass. The next tray pass can move bottom utility widget/page construction into the shell layer after this safer dock-level extraction is stable.
