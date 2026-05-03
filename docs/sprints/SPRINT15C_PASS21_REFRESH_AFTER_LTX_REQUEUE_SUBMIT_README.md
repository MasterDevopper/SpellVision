# Sprint 15C Pass 21 — Refresh History/Queue After LTX Requeue Submit

Adds a post-submit refresh hook after successful LTX requeue submission from T2V History.

Behavior:

- Emits `ltxRequeueSubmitted(promptId, primaryOutputPath)`.
- Automatically clicks the History page Refresh button shortly after submit.
- Repeats the refresh after a short delay so registry writes have time to settle.
- Updates the success modal to tell the user that history and queue views are refreshing.

This keeps Pass 20's guarded confirmation flow while reducing the need to manually refresh after requeue submission.
