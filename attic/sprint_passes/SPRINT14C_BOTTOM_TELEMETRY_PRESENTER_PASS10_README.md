# Sprint 14C Pass 10 - Bottom Telemetry Presenter

Adds `qt_ui/shell/BottomTelemetryPresenter.*` and wires MainWindow bottom telemetry construction/sync through the presenter.

This pass moves the first bottom-bar responsibility slice out of MainWindow:

- status-bar label construction
- bottom progress bar construction
- model/LoRA short-name formatting
- queue count / active queue state formatting
- telemetry sync presentation policy

MainWindow still owns the actual widgets and shell lifecycle.
