# Sprint 15C Pass 25 — Disable Startup Video Restore and Prefer LTX Distilled Output

Fixes two UX regressions discovered after Pass 24:

1. T2V no longer auto-loads the last generated video preview on startup. `restoreSnapshot()` still restores controls and prompts, but video preview state is cleared for video modes.
2. LTX history/preview paths now prefer `role=distilled` outputs over `role=full` outputs when available.

This prevents Home/T2V startup from probing the previous MP4 and ensures LTX uses the better distilled render for preview/history surfaces.
