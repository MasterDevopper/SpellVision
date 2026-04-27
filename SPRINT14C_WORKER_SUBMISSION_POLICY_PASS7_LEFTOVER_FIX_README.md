# Sprint 14C Pass 7 Leftover WorkerSubmissionPolicy Call Fix

This fix qualifies any remaining MainWindow call sites that still reference extracted WorkerSubmissionPolicy helpers by their old unqualified names.

It specifically resolves unresolved `resolvedModelValueFromPayload(...)` call sites that can remain outside the main generation-submit path after the Pass 7 extraction.
