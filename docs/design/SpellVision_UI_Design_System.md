# SpellVision UI Design System
## Layout, Buttons, Style, and Visual Rules

# ⚠️ SOURCE OF TRUTH

This document defines ALL UI rules for SpellVision.

If code or UI conflicts with this document:
→ THIS DOCUMENT WINS

Do not replace, truncate, or regenerate this file without review.

## Purpose
This document defines the visual and interaction system for SpellVision. It is the source of truth for layout behavior, button hierarchy, spacing, styling, components, and overall product feel.

---

# 1. Design Intent

SpellVision should feel like a premium cinematic creative workstation:
- professional
- dense but breathable
- fast
- desktop-native
- premium without gaudiness
- futuristic without losing clarity

It should borrow the structural confidence of tools like VSCode, Resolve, Unreal, and high-end DCC software, while keeping a distinct SpellVision identity.

It should not feel like:
- a loose web dashboard
- a toy AI prompt box
- a flat settings-heavy admin panel
- a Comfy graph wrapper

It should feel like:
- an intentional production studio

---

# 2. Global Visual Principles

## 2.1 Core Principles
- One primary surface at a time
- Strong hierarchy before decoration
- High information density without clutter
- Soft separation instead of heavy borders
- Stable shell, adaptive pages
- Motion is subtle, not flashy
- Important controls are obvious
- Destructive actions are never visually ambiguous

## 2.2 Product Character
SpellVision visual language should communicate:
- precision
- mysticism-tech fusion
- premium craftsmanship
- confidence
- power without chaos

---

# 3. Shell Layout Rules

## 3.1 Main Application Shell
The shell should remain stable across all pages.

### Structure
- Custom title bar at top
- Slim status/message strip below title/menu area if used
- Left navigation rail
- Main content workspace
- Optional right dock
- Bottom telemetry bar

### Behavior
- The shell must not jump around between pages
- Docks can change content, not identity
- Telemetry stays authoritative and singular
- Navigation rail width remains fixed unless in compact mode
- Main content owns the most space
- The right dock is contextual, not always dominant

---

## 3.2 Left Navigation Rail
### Rules
- icon-first
- narrow by default
- expanded labels on hover or optional wide mode
- enough reserved capacity for future modes
- active page gets a strong accent indicator
- inactive items remain readable but quiet

### Visual behavior
- subtle hover lift or glow
- active item gets:
  - accent line
  - higher contrast background
  - icon emphasis
- avoid oversized pill buttons unless in expanded mode

---

## 3.3 Bottom Telemetry Bar
### Rules
- this is the only always-on telemetry area
- must show dynamic runtime state, not static hardware facts
- should stay horizontally efficient
- no oversized widgets
- progress must be readable at a glance

### Contents
- runtime state
- queue depth
- active model / LoRA summary
- VRAM usage
- generation progress
- warnings/errors when relevant

---

# 4. Page Layout Rules

## 4.1 Home Page
### Priorities
- start creating hero
- recent workflows
- favorites/inspiration
- current stack summary

### Layout rules
- hero is dominant
- remove unnecessary decorative headers
- mode selection must be immediate
- do not bury quick-start actions below fold
- cards should feel large and editorial, not cramped

---

## 4.2 Generation Pages
### Standard structure
- left inspector
- center preview/canvas
- right details dock
- bottom telemetry

### Inspector section order
1. Prompt
2. Negative Prompt
3. Model Stack
4. Output / Queue
5. Resolution / Sampling
6. Advanced

### Rules
- prompt areas are large and visually important
- model stack must be readable as a system, not scattered controls
- queue/output must appear earlier than most AI apps place it
- defaults should be visible, not hidden behind mystery state
- collapsible sections should reduce clutter without hiding essentials

---

## 4.3 History Page
### Layout rules
- browser on left
- review panel on right
- preview is large
- metadata starts simple, then expands
- action row stays visible

### Must support
- single review
- compare review
- quick rerun/send-to-page actions

---

## 4.4 Queue Page
### Layout rules
- active job strip at top
- controls grouped, not scattered
- table-first default
- card mode optional
- selection state very clear
- queued vs running vs failed visually distinct

---

## 4.5 Settings Page
### Layout rules
- hierarchical tree navigation
- searchable
- expandable categories
- center/right content panel
- sections grouped into premium cards/modules

### Categories should feel like
- product settings
not
- raw form rows

---

# 5. Spacing and Density System

## 5.1 Token-Based Density
SpellVision should use a constrained density system rather than arbitrary manual spacing.

### Density presets
- Compact
- Standard
- Comfortable

### Apply density to
- panel padding
- row height
- card padding
- button height
- input field height
- section spacing
- dock padding
- toolbar spacing

### Rules
- density changes must not break layout
- controls must remain window-aware
- the app should adapt intelligently to screen size and density together

---

## 5.2 Base Spacing Tokens
Recommended conceptual tokens:
- `space-1`: micro gap
- `space-2`: tight control gap
- `space-3`: standard internal gap
- `space-4`: section gap
- `space-5`: panel gap
- `space-6`: page block gap

### Usage
- never stack arbitrary margins repeatedly
- use consistent section rhythm
- card interior spacing must feel deliberate
- empty space should support hierarchy, not expose layout weakness

---

# 6. Button System

## 6.1 Button Hierarchy
SpellVision should use four main button tiers.

### Primary
Used for the main forward action.
Examples:
- Generate
- Queue
- Start Runtime
- Install
- Apply

### Secondary
Used for important but non-primary actions.
Examples:
- Save Snapshot
- Reset
- Compare
- Open Folder

### Tertiary / Ghost
Used for lighter actions.
Examples:
- Reveal
- Copy
- More
- View All

### Destructive
Used for:
- Delete
- Remove
- Clear
- Stop
- Cancel all

---

## 6.2 Primary Button Rules
- highest contrast button on the page
- only one true primary in a local action group
- should read instantly as the main action
- must be large enough for fast recognition
- should not be duplicated unnecessarily

---

## 6.3 Secondary Button Rules
- clear border or softer filled variant
- visually subordinate to primary
- still obviously clickable
- grouped with primary when relevant

---

## 6.4 Ghost Button Rules
- minimal chrome
- used for utility and low-emphasis actions
- must still have strong hover/focus states

---

## 6.5 Destructive Button Rules
- never styled like primary generate actions
- require clear contrast
- if action is high-risk, use confirm dialog or undo path
- should not sit too close to positive actions without visual separation

---

## 6.6 Button Shape and Feel
- medium-to-large hit targets
- rounded corners, but not cartoonish
- premium surface feel
- subtle elevation or glow on hover
- no excessive gradients
- focus state must be obvious for keyboard usage

---

# 7. Inputs and Editors

## 7.1 Text Inputs
### Rules
- strong readability
- sufficient height
- clear focus ring
- placeholder text visible but subdued
- no heavy borders if surface contrast is already clear

## 7.2 Prompt Editors
### Rules
- larger than standard fields
- support chips/tokens
- support insertions from trigger words/defaults
- prompt and negative prompt should feel like core creative surfaces

## 7.3 Dropdowns / Pickers
### Rules
- avoid tiny combo boxes
- show selected state clearly
- searchable where option count is large
- use compatibility badges when relevant

## 7.4 Sliders
### Rules
- used for continuous values only
- numeric field should exist beside important sliders
- value must always be visible

## 7.5 Toggles
### Rules
- use for true binary settings
- label must explain effect clearly
- avoid hidden side effects

---

# 8. Cards, Panels, and Sections

## 8.1 Cards
Used for:
- workflow previews
- model assets
- history items
- inspiration items
- settings modules

### Rules
- soft rounded corners
- layered surface, not flat white-box style
- hover state should clarify interactivity
- content alignment must be disciplined
- titles should not compete with preview media

## 8.2 Panels
Used for:
- inspector groups
- metadata areas
- settings sections
- dock content

### Rules
- premium, restrained surface treatment
- use panel headers only when needed
- do not waste vertical space with giant decorative titles
- panels should scale across density modes

## 8.3 Collapsible Sections
### Rules
- smooth expansion
- remember state when appropriate
- collapsed state should still reveal critical summary info
- expansion arrows must be obvious

---

# 9. Color and Surface Rules

## 9.1 Palette Direction
Default palette should lean:
- dark obsidian / charcoal base
- indigo/violet/blue accents
- subtle silver/neutral support
- restrained highlights

### Avoid
- rainbow UI
- oversaturated neon everywhere
- flat gray monotony
- excessive glass blur that destroys readability

---

## 9.2 Surface Hierarchy
Use 4 conceptual levels:
- background
- shell surface
- panel/card surface
- elevated interactive surface

Each level should be visibly distinct but close enough to feel cohesive.

---

## 9.3 Accent Usage
Accent color is for:
- active state
- primary action
- selected tab/item
- key graphs or emphasis
- focus highlights

Accent should not be sprayed across every component.

---

## 9.4 Text Contrast
### Text tiers
- Primary text
- Secondary text
- Muted/help text
- Status text
- Error/warning text

Rules:
- body text must stay readable on dark surfaces
- avoid ultra-low contrast minimalist failures
- muted text should still be legible, not invisible

---

# 10. Typography Rules

## 10.1 Hierarchy
- Page titles
- Section titles
- Card titles
- Body text
- Caption / metadata text

### Rules
- fewer size jumps, stronger weight discipline
- avoid oversized headers that waste space
- body text should support scanning
- metadata text should be compact but readable

## 10.2 Tone
Typography should feel:
- technical
- premium
- calm
- authoritative

Not:
- playful
- noisy
- overly decorative

---

# 11. Motion and Interaction

## 11.1 Motion Rules
- quick
- subtle
- functional
- never laggy
- never theatrical

### Good motion uses
- hover state changes
- dock transitions
- collapsible sections
- button feedback
- preview swaps
- selection emphasis

### Bad motion uses
- long fades
- bouncy panels
- flashy animated gradients
- dramatic sliding on routine actions

---

## 11.2 Hover / Focus / Active States
Every interactive control must clearly support:
- hover
- pressed
- keyboard focus
- disabled

No control should rely only on color shifts too subtle to notice.

---

# 12. Iconography

## 12.1 Icon Rules
- clean
- readable at small sizes
- consistent stroke/weight
- support rail + toolbar + buttons
- no random icon style mixing

## 12.2 Usage
- rail icons should be iconic and stable
- buttons may use leading icons when helpful
- do not overload every label with icons

---

# 13. Design Rules by Component

## 13.1 Generate Action Bar
Must contain:
- Generate
- Queue
- Save Snapshot
- Reset

Rules:
- Generate is primary
- Queue is high-importance secondary or co-primary depending on page
- actions grouped tightly
- no noisy extra buttons in same band

## 13.2 LoRA Stack UI
Must support:
- stack rows
- enable/disable
- reorder
- weight
- trigger words
- remove
- compatibility state

Rules:
- each row compact but readable
- trigger chips should be easy to add
- active state obvious
- stacking should look like composition, not clutter

## 13.3 Family Defaults UI
Must support:
- positive defaults
- negative defaults
- per family grouping
- visible enable/disable
- optional profile variants later

Rules:
- token-friendly design
- easy to scan by family
- no giant text areas when token chip model is better

## 13.4 Settings Tree
Rules:
- categories collapse/expand
- search jumps to exact section
- selected node clearly highlighted
- content panel should feel modular and premium

---

# 14. What to Avoid

Do not:
- waste vertical space on repeated page headers
- hide critical generation state
- duplicate telemetry in multiple places
- overload the user with giant bordered boxes
- create tiny controls that feel web-admin-like
- make every panel look equally important
- use heavy black boxes behind text unnecessarily
- make settings feel like a plain form dump
- let style outrun readability
- let layout depend on arbitrary per-page hacks

---

# 15. Layout and Design Ownership

## Qt/C++
Owns:
- implementation of all visual layout behavior
- widgets
- interaction states
- docking presentation
- adaptive density behavior in UI

## Rust
Owns:
- persistent design settings values
- layout preset persistence
- saved workspace state

## Python
Owns:
- none of the visual system directly

---

# 16. Final Design Summary

SpellVision should look and feel like:
- a premium desktop production tool
- built for serious creative work
- fast, dense, cinematic, and clear

The design target is not “pretty AI app.”
The design target is:

a high-end creative workstation with a distinct SpellVision identity
