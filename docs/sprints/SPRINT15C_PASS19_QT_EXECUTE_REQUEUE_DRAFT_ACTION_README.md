# Sprint 15C Pass 19 — Qt Execute Requeue Draft Action

Adds a T2V History `Validate Requeue` button for LTX rows.

The button resolves the Pass 17 `.requeue.json` draft and calls the Pass 18 `ltx_requeue_draft_gated_submission` backend command in dry-run mode.

This pass does not submit a new LTX job. It validates that the selected draft is ready for gated submission.
