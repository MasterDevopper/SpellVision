# Sprint 15C Pass 20 — Qt Submit Requeue Draft With Confirmation

Adds a guarded `Submit Requeue` button to T2V History LTX rows.

The button remains disabled until `Validate Requeue` succeeds for the selected draft.

Submission asks for confirmation, then calls `ltx_requeue_draft_gated_submission` with `submit_to_comfy=true` and `dry_run=false`.

The UI does not wait for the full video result in this pass; it only confirms that the job was submitted.
