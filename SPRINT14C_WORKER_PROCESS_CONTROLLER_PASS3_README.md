# Sprint 14C Pass 3 — Worker Process Controller scaffold

This pass introduces `WorkerProcessController` under `qt_ui/workers` as a reusable owner for future worker process lifecycle code.

It centralizes:

- `QProcess` startup
- JSON payload write-to-stdin
- stdout line handling
- stderr line handling
- stdout JSON object emission
- process finish/error reporting
- terminate/kill cleanup

This pass is intentionally behavior-neutral. The current Image Generation page already delegates worker command payload decoration through `WorkerCommandRunner`; the remaining raw `QProcess` ownership appears to live outside `ImageGenerationPage`. The next pass should wire this controller into the class that currently creates and reads the worker process.
