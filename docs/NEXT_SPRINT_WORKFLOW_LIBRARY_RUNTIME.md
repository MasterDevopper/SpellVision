# Next Sprint Kickoff — Workflow Library + Runtime Readiness

## Sprint theme
Now that Home can route people into real surfaces, the next sprint should make the workflow and execution path production-capable.

## Goal
Turn Workflow Library and launch flow into a dependable feature path so users can:
- browse workflows,
- understand what each workflow needs,
- open the correct mode directly,
- and launch with fewer dead ends.

## Why this is the right next sprint
The current sprint made Home usable. That means the next bottleneck is no longer the shell — it is the **workflow selection and execution pipeline** behind Home.

If Home sends users into weak workflow/library behavior, the dashboard gains are wasted. So the next sprint should harden the surfaces Home now depends on.

## Sprint objective
Build a production-ready first pass of the workflow selection path from library to mode launch, without reopening shell polish.

## In scope

### 1. Workflow Library production pass
- Real workflow list rendering.
- Clear workflow cards with name, type, media, backend, and readiness.
- Search / filter / sort foundation.
- Better distinction between recent, imported, starter, and favorite workflows.

### 2. Workflow readiness + dependency visibility
- Show whether a workflow is runnable.
- Surface missing nodes / missing models / missing assets clearly.
- Provide actionable readiness messaging instead of vague failure states.
- Keep this visible both in library and when launching from Home.

### 3. Correct mode launch routing
- Opening a workflow should route to the right mode reliably:
  - T2I
  - I2I
  - T2V
  - I2V
- Launch actions from Home and Workflow Library should use the same contract.

### 4. Initial workflow metadata contract hardening
- Normalize workflow metadata used by Home, library, and mode surfaces.
- Avoid one-off mapping logic scattered across pages.
- Create one stable source of truth for workflow descriptors.

### 5. Runtime handoff sanity pass
- Ensure selected workflow information arrives cleanly in the destination mode.
- Preserve model/workflow selection where appropriate.
- Improve launch-state messaging for idle, ready, blocked, and dependency-missing states.

## Out of scope
- Shell redesign.
- Queue / Details / Logs redesign.
- Final polish of Home visual issues.
- Full cinematic refinement passes.
- Large model-management overhaul.
- Final telemetry redesign.

## Engineering guardrails
- Do not change MainWindow shell layout unless there is a hard functional blocker.
- Prefer shared contracts over page-specific hacks.
- Keep new data flow centralized and inspectable.
- Favor feature-complete behavior over cosmetic work.

## Deliverables
- Workflow Library usable as a real workflow browser.
- Workflow readiness shown clearly.
- Home launcher and library launcher aligned.
- Mode routing reliable.
- Workflow metadata contract documented in code and used consistently.

## Acceptance criteria
- A user can choose a workflow from Home or Workflow Library and land in the correct mode.
- The app shows whether the workflow is ready or blocked.
- Missing dependencies are surfaced clearly.
- Library actions no longer feel placeholder-level.
- No regression to the accepted Queue / Details / Logs shell baseline.

## Suggested branch / sprint label
Use whatever numbering matches your branch plan, but the theme should be:

**Workflow Library + Runtime Readiness**

## After this sprint
Once this sprint lands, the next natural follow-on would be either:
- **Models / Downloads production pass**, or
- **History / Results / rerun pipeline pass**

That choice should depend on which feature path feels weaker after workflow launch becomes stable.
