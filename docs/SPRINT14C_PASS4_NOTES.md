# Sprint 14C Pass 4 Notes

`WorkerProcessController` now owns worker process startup, stdin payload writing, stdout/stderr line routing, JSON message capture, and finish/error signaling for `MainWindow::sendWorkerRequest()`.

This is still a synchronous call path from `submitGenerationRequest()` so queue submission behavior remains unchanged. A later pass can make worker command submission fully async if desired.
