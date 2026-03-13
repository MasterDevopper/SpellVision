# Job Lifecycle Contract — Sprint 7

## Purpose
This contract defines the canonical job lifecycle for SpellVision generation requests so the Python backend and Qt UI always agree on state, progress, errors, and result handling.

## Canonical States
Every generation job must use one of these states:

- `queued`
- `starting`
- `running`
- `completed`
- `failed`
- `cancelled`

These values are the single source of truth for both backend and UI.

## Valid State Transitions

```text
queued -> starting
starting -> running
running -> completed
running -> failed
running -> cancelled
starting -> failed
queued -> cancelled
```

Disallowed transitions should be ignored or logged as invalid.

Examples:
- `completed -> running` is invalid
- `failed -> running` is invalid
- `cancelled -> completed` is invalid

## Required Event Payload
Every progress/status event sent from Python to Qt should follow this structure:

```json
{
  "type": "job_update",
  "job_id": "job_20260312_0001",
  "state": "running",
  "progress": {
    "current": 3,
    "total": 10,
    "percent": 30.0,
    "message": "Generating preview"
  },
  "result": null,
  "error": null,
  "timestamps": {
    "created_at": "2026-03-12T07:15:00Z",
    "started_at": "2026-03-12T07:15:03Z",
    "finished_at": null,
    "updated_at": "2026-03-12T07:15:10Z"
  }
}
```

## Required Fields

### Top-level
- `type`: must be `job_update`
- `job_id`: stable identifier for the job
- `state`: canonical lifecycle state
- `progress`: progress object
- `result`: result object or `null`
- `error`: error object or `null`
- `timestamps`: timestamp object

### Progress Object
- `current`: integer step index
- `total`: integer total step count
- `percent`: float between `0.0` and `100.0`
- `message`: user-facing status message

### Error Object
Used only when `state == failed`.

```json
{
  "code": "MODEL_LOAD_ERROR",
  "message": "Failed to load generation model",
  "details": {
    "model_name": "spellvision-base-v1"
  }
}
```

Fields:
- `code`: stable machine-readable error code
- `message`: concise human-readable failure message
- `details`: optional structured debugging payload

### Result Object
Used only when `state == completed`.

```json
{
  "artifact_type": "image",
  "output_path": "outputs/job_20260312_0001/final.png",
  "metadata": {
    "width": 1024,
    "height": 1024
  }
}
```

## Cancel Contract
Cancel requests should use:

```json
{
  "action": "cancel_job",
  "job_id": "job_20260312_0001"
}
```

Successful cancel should emit a normal `job_update` event with:

```json
{
  "type": "job_update",
  "job_id": "job_20260312_0001",
  "state": "cancelled"
}
```

## Retry Contract
Retry requests should use:

```json
{
  "action": "retry_job",
  "job_id": "job_20260312_0001"
}
```

Recommended behavior:
- create a new `job_id`
- preserve a reference to the original job in internal metadata
- emit a new `queued` event for the retried job

## UI Rules

### Button State
- `queued`: cancel enabled, retry disabled, start disabled
- `starting`: cancel enabled, retry disabled, start disabled
- `running`: cancel enabled, retry disabled, start disabled
- `completed`: cancel disabled, retry enabled, start enabled
- `failed`: cancel disabled, retry enabled, start enabled
- `cancelled`: cancel disabled, retry enabled, start enabled

### Status Text
Suggested UI text:
- `queued`: "Queued"
- `starting`: "Starting generation"
- `running`: use `progress.message`
- `completed`: "Generation complete"
- `failed`: use `error.message`
- `cancelled`: "Generation cancelled"

## Backend Guard Rails
- always include `job_id`
- never emit a state outside the canonical list
- do not emit duplicate terminal transitions
- terminal states are `completed`, `failed`, and `cancelled`
- once terminal, ignore further progress updates
- missing payload fields should be filled with safe defaults before emission

## Safe Defaults

```json
{
  "progress": {
    "current": 0,
    "total": 0,
    "percent": 0.0,
    "message": "Waiting"
  },
  "result": null,
  "error": null
}
```

## Recommended Internal Python Model

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from datetime import datetime, timezone


class JobState(str, Enum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobProgress:
    current: int = 0
    total: int = 0
    percent: float = 0.0
    message: str = "Waiting"


@dataclass
class JobError:
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


@dataclass
class JobResult:
    artifact_type: str
    output_path: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobTimestamps:
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class JobRecord:
    job_id: str
    state: JobState
    progress: JobProgress = field(default_factory=JobProgress)
    result: Optional[JobResult] = None
    error: Optional[JobError] = None
    timestamps: JobTimestamps = field(
        default_factory=lambda: JobTimestamps(
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    )
```

## Recommended Next Implementation Order
1. Add `JobState` and `JobRecord` models in Python.
2. Normalize all backend emissions into the payload contract.
3. Add cancel and retry handling to the worker client.
4. Parse canonical states in Qt.
5. Update button enable/disable rules in `MainWindow`.
6. Prevent invalid UI transitions after terminal states.
