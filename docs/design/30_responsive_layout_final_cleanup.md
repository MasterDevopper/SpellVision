# 30 — Responsive layout final cleanup

**Status:** A- polish pass (2026-07-25 late) — owner eyes still gate S  
**Grade context:** Owner **A-**; residual is live matrix + any remaining owner nits  
**Owner surface:** generation cockpits, Comic/Character studios, History, title bar, Home, telemetry

## Code landed (B+ → S track)

### P0 cockpit / resize
- Combo `minimumContentsLength` + elide; stacked video Components (cell-wrapped visibility)
- `CockpitInspector::setWidthBudget` + content max-width
- `showEvent` + deferred reflow on generation pages
- No T2I/T2V IMG stub; readiness footer sync; stale input path clear

### P1 studios / chrome
- Comic + Character `reflowForWidth` / scroll rails
- Character: **QFormLayout removed** → stacked label-above-field
- History: **@token@ QSS** (fixed `%10` disabled-button corruption), 14px density, details pane reflow
- Title bar: search pill compresses; shortcut + layout icons hide at narrow widths
- Telemetry: adaptive chip widths; LoRA/ETA + **their separators** hide together
- Home glass radii tightened to instrument scale (hero 18 / standard 14)
- ModePage (Inspire stub): honest “Coming soon”, @token@ sheet, denser cards

### Explicitly out of scope
- Bundled Space Grotesk / Inter / JetBrains Mono (Segoe UI interim)
- True OS acrylic (painted glass only)

## Matrix — AUTOMATED and RUN (2026-08-30; nine surfaces since 2026-09-01)

No longer owner-eyes. Every clause of the pass predicate below is a geometry, visibility or
message-handler assertion, so the matrix is now `tests/cpp/test_responsive_matrix.cpp`, wired into
ctest and CI. It became possible once `SpellVisionCore` existed — before that nothing could
construct a page outside the running app.

**First run (2026-08-30): 26 of 28 cells pass. Re-run 2026-09-01 with two added surfaces: 34 of 36.
Re-run 2026-09-02 with a viewport-overflow clause: 36 of 38 (the two known cells below).
Re-run 2026-09-02, later the same day: 36 of 36 — the baseline is EMPTY.**

Both known cells were fixed once the clip report started printing the ANCESTRY of a squeezed control
instead of only its size. `QWidget(-) 120x32 < min 364x32` says a row is squeezed and nothing about
which container lost the width; with the chain it read `CanvasEmptyState 1390w/min364`, which names
the defect outright — the parent had the room and the row was not being given it.

* **T2I / Full** — the canvas empty-state chips row was added as
  `addWidget(chipsRow, 0, Qt::AlignHCenter)`. An aligned item is given its size *hint*, not the space
  available, so the row sat at 120px inside a 1390px empty state and the four metric chips were
  squeezed to 24px against minimums of 94/67/59/120. It centres itself now (`setAlignment` on its own
  layout), which is the same remedy the preview stack already uses and for the same reason.
* **History details / Half W** — "Open Output", "Reveal Folder", "KEEP (K)" and "NO (N)" in one
  `QHBoxLayout` gave the details card a 367px minimum, while `reflowForWidth` deliberately shrinks
  that card to ~300px at a half-screen window so the table is not crushed. The card obeyed the reflow
  and the row clipped. They are a 2×2 grid now, like the copy actions right below them — the same
  shape, and the same fix, as the LoRA stack row a day earlier.

The `kKnownFailures` baseline stays in the test, empty and two-way: a new failure fails the suite, and
a cell that starts passing must be deleted rather than left standing as an excuse.

The 2026-09-02 clause exists because a live screenshot pass found Comic Studio's left column
clipping at 1776px and at half width while its matrix cells read PASS. The matrix skips everything
inside a scroll area on purpose (a scroll area may be smaller than its contents), which also hid a
scroll area whose CONTENT was wider than its viewport — with the horizontal bar off everywhere in
this app, that is clipping, not scrolling. The clause asks the area itself: `widgetResizable`, bar
off, `widget()->width() > viewport()->width()` is an offender. It flagged Comic at Restore and Half W
(260px of content in a 228px viewport: two combos sized to their widest items), and nothing else.

| Surface | Full | Restore | Half W | Half H |
|---|---|---|---|---|
| T2I | **FAIL** | PASS | PASS | PASS |
| T2V | PASS | PASS | PASS | PASS |
| I2V | PASS | PASS | PASS | PASS |
| Comic Advanced ON | PASS | PASS | PASS | PASS |
| Character concept | PASS | PASS | PASS | PASS |
| History details | PASS | PASS | **FAIL** | PASS |
| Title bar + telemetry | PASS | PASS | PASS | PASS |
| Workflows library *(added 2026-09-01)* | PASS | PASS | PASS | PASS |
| Runtime page *(added 2026-09-01)* | PASS | PASS | PASS | PASS |

The two added rows are the pages the per-page UI audit graded weakest, and both were absent from
the matrix — which is how a nine-button non-wrapping row (Workflows) and a page with no scroll
region at all (Runtime) shipped past a discipline enforced everywhere else. Both pass now: the row
became two rows, the page gained its one `QScrollArea`, and neither can regress silently again. A
surface now also declares whether it has a Generate button, so that clause is asserted where it
applies rather than faked against the first `PrimaryActionButton` a library page happens to hold.

Pass = no clipped controls, no missing Advanced, Generate always reachable, status bar readable, no QSS parse spam.

The two failures are real and are recorded as a baseline in `kKnownFailures`, which can only shrink —
a cell that starts passing must be deleted from the list, so a fixed bug leaves no permanent excuse:

- **T2I / Full** — the canvas EMPTY-STATE chips row lays out at 120×32 against a 364×32 minimum, so
  its four metric chips are squeezed to 24px. Visible before the first render of a session.
- **History details / Half W** — `HistoryDetailsCard` gets 340px against a 367px minimum at the
  960px half-screen width. Precisely the half-screen clipping this matrix was written to catch.

**The check was narrowed before it shipped**, because the first version reported 6 failures and 4 of
them were its own fault (Doc 50 rule 1). It now skips widgets that are not layout-managed — the
prompt-chip close button is 18×18 by explicit `setGeometry` against a 28×40 hint, which is deliberate
and says nothing about responsiveness — and empty `QLabel`s, whose `minimumSizeHint` is stylesheet
padding rather than content. `Title bar + telemetry` currently instantiates the T2I page as a stand-in;
that row is a placeholder until the chrome is separately constructible.

## Skills / authority
- `spellvision` + `spellvision-qt-studio-surfaces`
- `references/responsive-half-screen.md`, `owner-visual-qa-checklist.md`
