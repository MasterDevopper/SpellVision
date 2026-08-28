# 51 — Headless access for SpellBound Engine

**Status:** implemented 2026-08-28. Owner decision: **loopback bind + SSH tunnel** (option B of
three offered).

SpellBound Engine needs to drive SpellVision headlessly — feeding it character design and concept
work and collecting the results. This is how it reaches the worker without putting an
unauthenticated remote-code-execution surface on the network.

---

## 1. What the risk actually was

The worker protocol had **no authentication of any kind**, and its bind address is a single
environment variable (`SPELLVISION_WORKER_HOST`, default `127.0.0.1`). One setting away from
listening on every interface.

The command surface is not modest. Of 125 dispatched commands it includes:

| command | what it does |
|---|---|
| `install_custom_node` | fetches a GitHub zipball and runs pip |
| `import_model_url` | downloads to a caller-supplied path |
| `enqueue` | writes output to any path the request names |
| `comfy_workflow` | executes an arbitrary ComfyUI graph |
| `save_credential` | writes the credential store |

Exposed, that is remote code execution on the workstation. Loopback was the only control.

## 2. The model

Two levels, in `python/worker_auth.py`.

**`LOCAL_TRUSTED`** — a loopback connection presenting no token. Full surface. This is the
SpellVision UI, and it works with no configuration **whether or not a token is set**. An earlier
draft of this policy required a token from everyone once one existed, which would have broken the
UI silently, and only for the user who enabled the feature. `test_configuring_a_token_does_not_lock_the_local_ui_out` pins the corrected behaviour.

**`INTEGRATION`** — a caller presenting the configured token. Restricted to an explicit allowlist:

```
enqueue, queue_status, cancel_queue_item, cancel_active_queue_item, remove_queue_item,
t2i, i2i, ping, comfy_runtime_status, video_family_contracts, classify_models
```

Not node installation, model import, credential access, runtime mutation or dataset generation.
It is an **opt-in allowlist, not a denylist**, so a new worker command cannot widen the remote
surface merely by existing.

Everything else is `DENIED`, before dispatch.

## 3. Being precise about what the token buys

Over an SSH tunnel the real authentication is SSH's, and anything already able to reach loopback
can run code on this machine anyway. So the token is not what keeps an attacker out. Its value is:

1. **Bounding the integration** — a bug in SpellBound cannot install a node pack or overwrite a
   credential.
2. **Defence in depth** if the bind address is ever changed.

Stating that plainly matters more than overselling it.

## 4. Fail closed

Binding anywhere other than loopback with no token configured **refuses to start**:

```
RuntimeError: Refusing to bind the worker to '0.0.0.0' with no integration token configured.
```

Raised rather than warned, because the failure being prevented is an unauthenticated RCE surface
and a warning in a log nobody reads is not a control.

## 5. Setting it up

**On the SpellVision machine** — set a token. Either:

```powershell
# Environment (per-session or persistent), or...
$env:SPELLVISION_WORKER_TOKEN = "<a long random string>"
```

```powershell
# ...the DPAPI credential store, which binds it to this Windows user.
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'python'); import credential_store; credential_store.set_credential('worker_integration_token', '<token>')"
```

Leave `SPELLVISION_WORKER_HOST` at its default. **Do not bind to `0.0.0.0`.**

**On the SpellBound machine** — tunnel to the worker port and talk to it as if local:

```bash
ssh -N -L 8765:127.0.0.1:8765 user@spellvision-box
```

Then send newline-delimited JSON to `127.0.0.1:8765`, with the token on every request:

```json
{"command": "enqueue", "auth_token": "<token>", "task_command": "t2i",
 "prompt": "...", "model": "...", "output": "...", "metadata_output": "...",
 "width": 1024, "height": 1024, "steps": 28, "cfg": 7.0, "seed": 1}
```

A rejection comes back as `{"type": "auth_error", "ok": false, "error": "..."}` and nothing runs.

## 6. Handling of the token itself

- Compared with `hmac.compare_digest` — a naive `==` leaks it a character at a time under timing
  analysis.
- Listed in `worker_queue.SECRET_REQUEST_KEYS`, so it is redacted out of the persisted queue
  manifest (plain JSON on disk).
- Never logged, and never echoed in a denial message.
- In the DPAPI store it is bound to the Windows user, so a copied `credentials.json` is inert.

`worker_integration_token` was added to **both** credential stores — `python/credential_store.py`
and `qt_ui/shell/SecureCredentialStore.cpp`. They must stay in lockstep because their write
behaviour is asymmetric: the C++ side read-modify-writes and preserves keys it does not know, while
the Python side rebuilds the secrets object from its own `KNOWN_KEYS` and would **drop** a key only
C++ knew about. A test enforces the agreement.

## 7. Limits, stated

- **The protocol is plaintext.** Fine inside a tunnel or on a trusted wired LAN. Not something to
  expose to an untrusted network, token or no token.
- **No rate limiting or per-caller identity.** One shared secret, one integration. If a second
  consumer appears, that is when per-caller tokens become worth building.
- **No TLS.** Deliberate — the tunnel provides transport security, and adding a second encryption
  layer would be complexity without benefit for this deployment.

## 8. Related, and still open

The **ComfyUI endpoint is fragmented**: five environment variable names address it
(`COMFY_API_URL` ×11, `SPELLVISION_COMFY_URL`, `SPELLVISION_COMFY_HOST`/`_PORT`,
`SPELLVISION_COMFY_ENDPOINT`) plus 16 hardcoded `127.0.0.1:8188` fallbacks across 12 modules.

That blocks the separate idea of using a second machine (a 3090 Ti box) as a render lane: pointing
SpellVision at a remote ComfyUI today would work through some paths and silently fall back to
localhost in others — a health check reporting success while renders run on the wrong machine. The
fix is one resolver, and it is not done.
