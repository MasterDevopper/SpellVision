# Sprint 15C Pass 16 — LTX History Metadata Polish and Requeue Prep

## Goal

Polish LTX records in the T2V History page and prepare the row metadata for future requeue/rerun actions.

## What changed

- LTX History rows now map registry metadata into visible labels:
  - `width` + `height` → resolution label
  - `frames` + `fps` → duration label
  - `registered_at` / `created_at` → finished label when supported by the current `VideoHistoryItem` shape
- LTX runtime summary now includes:
  - `LTX registry`
  - `comfy_prompt_api`
  - `requeue-ready`
  - registry prompt id when available

## Why this pass exists

Pass 15 proved LTX records can appear in History, but the first version still showed some generic `unknown` values. Pass 16 uses the durable registry metadata already written by Pass 12.

## Expected UI behavior

The LTX row should no longer show generic `LTX` / `unknown` where metadata exists. It should display the registry resolution, frame count/fps duration, and a local finished timestamp where the current UI item structure supports it.

## Requeue prep

This pass does not add the final Requeue button yet. It makes the LTX History item carry enough stable context for the next pass to create a requeue command from the selected history row.
