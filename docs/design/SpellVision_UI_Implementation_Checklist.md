# SpellVision UI Implementation Checklist
## Component-Level Build Guide

This document converts the UI design system into implementation-ready tasks.

---

# 1. GLOBAL SHELL (MainWindow.cpp)

## Components
- CustomTitleBar
- NavigationRail
- CentralStack (QStackedWidget)
- RightDock (QDockWidget)
- BottomTelemetryBar

## Tasks
- [ ] Implement fixed shell layout
- [ ] Remove page headers
- [ ] Add command palette trigger (Ctrl+Shift+P)
- [ ] Ensure docks are resizable + persist state

---

# 2. NAVIGATION RAIL

## Tasks
- [ ] Icon-only default mode
- [ ] Active highlight
- [ ] Tooltip support

---

# 3. HOME PAGE

## Tasks
- [ ] Adaptive hero
- [ ] Workflow cards
- [ ] Favorites carousel

---

# 4. GENERATION PAGE

## Tasks
- [ ] Prompt + Negative Prompt editors
- [ ] LoRA stack UI
- [ ] Trigger word chips
- [ ] Generate + Queue actions
- [ ] Preview canvas

---

# 5. HISTORY PAGE

## Tasks
- [ ] Grid + preview
- [ ] Metadata panel
- [ ] Compare mode

---

# 6. QUEUE PAGE

## Tasks
- [ ] Reorder
- [ ] Multi-select
- [ ] Status indicators

---

# 7. SETTINGS PAGE

## Tasks
- [ ] Tree navigation
- [ ] Search
- [ ] Family defaults UI

---

# 8. BUTTON SYSTEM

## Tasks
- [ ] Primary / Secondary / Ghost / Destructive styles

---

# 9. TELEMETRY

## Tasks
- [ ] Bind runtime data
- [ ] Show progress + VRAM

---

# FINAL GOAL

Professional, fast, production UI.
