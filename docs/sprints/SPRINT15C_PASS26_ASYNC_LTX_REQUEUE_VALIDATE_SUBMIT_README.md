# Sprint 15C Pass 26 — Async LTX Requeue Validate/Submit Worker Calls

Moves LTX requeue validation and submission off the UI thread.

Changes:

- `Validate Requeue` now starts an owned `QProcess` and returns immediately.
- `Submit Requeue` now starts an owned `QProcess` and returns immediately after confirmation.
- Buttons are disabled while validation/submission is running.
- Buttons show `Validating...` and `Submitting...` state text.
- Nested `blocked_submit_reasons`, `adapter_blocked_submit_reasons`, `submit_error`, stdout, and stderr are surfaced in failure dialogs.
- The existing guarded `Prepare → Validate → Submit` flow remains intact.

This pass removes the short UI freeze caused by synchronous `waitForFinished()` calls while preserving the backend gated submission contract.
