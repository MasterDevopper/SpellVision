# Sprint 15C Pass 22 — Surface Latest Requeue Output in Preview/Queue After Refresh

Adds post-submit tracking for the latest LTX requeue prompt/output.

After a successful Submit Requeue action, the T2V History page now stores the returned prompt id and primary output path, refreshes the page, and attempts to select the matching row after registry updates settle.

This keeps the current guarded submit flow while making the newest requeue result easier to find in History and details/preview surfaces.
