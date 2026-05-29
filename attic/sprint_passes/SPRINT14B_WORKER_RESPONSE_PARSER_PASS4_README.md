# Sprint 14B Pass 4 — Worker Response Parser Scaffold

This pass introduces a focused parser for raw worker JSON messages without changing runtime behavior yet.

## Added

- `qt_ui/workers/WorkerResponseParser.h`
- `qt_ui/workers/WorkerResponseParser.cpp`

## Purpose

`WorkerResponseParser` normalizes worker/client messages into a small typed structure before page-level or shell-level code decides what to do with them.

It recognizes:

- `job_update`
- `status`
- `progress`
- `result`
- `error`
- `queue_snapshot`
- `queue_ack`
- workflow import/profile messages
- Comfy runtime status/ack messages
- client error messages

## Why this is a scaffold pass

The current `ImageGenerationPage` refactor chain already moved preview routing and request assembly out of the page. The remaining raw worker JSON parsing is expected to live around the shell/worker integration path. This pass adds the parser as a build-safe dependency first, then the next pass can wire it into the worker/message handling code without mixing parser creation and behavior migration.

## Guardrails preserved

- No `Q_OBJECT` macro in the new worker helper.
- No `QMediaPlayer::MediaStatus` dependency.
- No preview lifecycle changes.
- No request payload changes.
- No generation behavior changes.
