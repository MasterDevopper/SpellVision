---
title: Worker Protocol
type: contract
status: accepted
sources:
  - docs/SPELLVISION_WORKER_PROTOCOL.md
  - ARCHITECTURE.md
updated: 2026-07-25
---

# Worker Protocol

## Transport

- Local TCP loopback `127.0.0.1:8765`
- UTF-8 JSON, **one logical event per line** (NDJSON)
- UI → `worker_client.py` → `worker_service.py` → Comfy/pipeline → events back

## Roles

| Actor | Responsibility |
|-------|----------------|
| Qt UI | Build requests, consume stream, progress/result UI |
| worker_client | Connect, forward, relay stdout lines |
| worker_service | Validate, route, execute, emit progress/result/error |

Frontend **never** talks to ComfyUI directly.

## Related

[[Job Lifecycle Contract]] · [[Worker Service]] · [[Generation Cockpit]]
