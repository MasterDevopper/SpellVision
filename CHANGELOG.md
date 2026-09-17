# Changelog

SpellVision versions are **SemVer** (`MAJOR.MINOR.PATCH`). The running app reports
`project(VERSION)` from `CMakeLists.txt` — today **1.0.0**. Settings → About shows it.

A feature add is assigned a **named version** before it is built. That is how the
user tells 1.0 from 1.1 from 1.2. Do not dump new ideas into a flat “later” pile,
and do not bump `CMakeLists.txt` until that version actually ships.

Rule (Doc 56): patch = bugfix only; minor = user-visible features; major = breaking.

---

## [1.1.0] — planned (do not start until 1.0.0 ships)

Owner 2026-09-11. Focused minor, not a junk drawer.

### Added

- **Prompt blocks** — same model/stack/sampling; N positive cards; one shared
  negative **or** one negative per positive; each card is its own dest (Batch-N
  jobs). Not Dataset.
- **In-app trainer (T1)** — Train as a real trainer for the shipped families, with
  hardware-smart defaults, rather than a launcher for Sohya_kk. **Moved here from
  1.0 by owner directive 2026-09-14.** The Train page stays hidden from the v1 rail
  (`kV1HiddenModes`) until this ships; the external launcher still works behind
  `SPELLVISION_SHOW_ALL_MODES=1`.
- **Workflow houses** — SpellVision templates (LTX pattern), not dumped node
  graphs. Teachers: CivitAI **2877997** Krea 2 Character Forge (trait base +
  character sheet, two graphs) and **2726952** lonecat Pro Grade (edit / style /
  moodboard / ControlNet / multi-ref / SAM3 / low VRAM). 1.0 T2 drop is the on-ramp.

---

## [1.0.0] — unreleased (current ship)

T7 is **not** a ship certificate. Bug hunt lives on `night/s-t7-bug-hunt`.
Product requirements: Doc 54 §1, T2–T7 (T1 moved to 1.1.0). Do not merge to main until dests match
intent and T7 is honest.

Installer / first-run wizard is **separate**, not this version’s ship gate.

---

## Later minors (unscheduled)

Parked, not 1.1.0. Assign a real version when one of these is the next ship, not
before: LLM prompt cleaner / story; comic episodes; Character B; TRELLIS.2;
AirLLM; Chain unhide; History-as-library; ControlNet/IP-Adapter as Simple intent.
See Doc 54 §3.2.
