# Sprint 13 Pass 8 — Models / Workflows / Downloads warm cache and nonblocking activation

This pass extends the manager cache pattern to two other heavy surfaces:

- Workflows
- Models / Downloads

## What this pass does

### Workflows
- Stops auto-scanning imported workflows on page construction
- Loads the last cached workflow library snapshot instead
- Uses the cache path immediately when the page is opened
- Keeps the expensive library scan behind **Refresh Library**
- Persists workflow library snapshots to disk after refresh

### Models / Downloads
- Replaces the placeholder Models page with a real `ModelManagerPage`
- Loads cached model inventory immediately
- Shows a downloads / asset-cache summary on the same page
- Persists model inventory to disk after refresh
- Keeps model scanning behind **Refresh Models**

### Main shell
- Uses `ModelManagerPage` instead of the placeholder `ModePage`
- Warms the workflows/models caches during page setup so clicking those pages is nonblocking

## Notes

This pass prioritizes **responsiveness and cache-first activation**.

It does **not** yet make the manual refresh buttons asynchronous. That can be the next pass if you want full background scanning for workflows and model inventory too.
