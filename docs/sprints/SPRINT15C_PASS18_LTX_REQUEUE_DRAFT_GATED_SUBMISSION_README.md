# Sprint 15C Pass 18 — Execute LTX Requeue Draft Through Gated Submission

Adds `ltx_requeue_draft_gated_submission`.

The command reads the newest Pass 17 `.requeue.json` draft and routes it through the existing safe LTX Prompt API gated submission path.

Default behavior is dry-run. Actual submission requires `submit_to_comfy=true` and `dry_run=false`.
