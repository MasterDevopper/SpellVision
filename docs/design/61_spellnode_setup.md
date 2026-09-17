# Doc 61 — SpellNode setup (the second render machine)

**Status:** operational note, 2026-09-17. **Gate: PASSED** — see §5.

SpellVision routes **whole jobs** to a second machine. It does not split a model across two GPUs, it does not pool VRAM, and it never mounts anything on your behalf. This document is what the app deliberately does **not** automate.

---

## 1. What the app does and does not do

| The app does | The app does not |
|---|---|
| Ask an endpoint whether it can run a job, and refuse by name when it cannot | Install anything on the node |
| Send the whole job over HTTP and fetch the result back over `/view` | Mount, unmount or configure a file share |
| Remember which families have passed a gate render on that endpoint | Assume a model present on this machine is present on that one |
| Say plainly that VRAM does not add up | Claim 32 GB + 24 GB is 56 GB |

`install_custom_node` is **fail-closed for a remote endpoint by design** — the worker refuses to install into a ComfyUI it does not own. Node packs on SpellNode are your job, not the app's.

---

## 2. The node itself

Run ComfyUI so the LAN can reach it:

```
python main.py --listen 0.0.0.0 --port 8188 --enable-cors-header
```

Verified on this LAN, 2026-09-17:

| | |
|---|---|
| address | `192.168.1.127:8188` |
| ComfyUI | 0.34.0 |
| OS | Linux |
| torch | 2.13.0+cu130 |
| GPU | RTX 3090 Ti, 25.3 GB |
| checkpoints visible | 130 |

---

## 3. Models — out of band, and this is the part that bites

The node must be able to load the model the job names. There are two honest routes and they have different failure modes.

### 3a. A CIFS/SMB share of the master's model root

Convenient, and **it can hang ComfyUI's start**. ComfyUI walks its model directories when it builds a filename list, so a share whose host is down stalls the walk — this project has a recorded incident where a start blocked on `cifs_wait_for_server_reconnect` and ComfyUI only listened after the yaml was moved aside.

Mount so a dead share fails fast instead of blocking:

```
//192.168.1.182/AI_ASSETS_models  /mnt/ai_models  cifs
  credentials=/root/.smbcred,ro,soft,echo_interval=10,noserverino,
  _netdev,nofail,noauto,x-systemd.automount,x-systemd.mount-timeout=15,
  x-systemd.device-timeout=10,x-systemd.idle-timeout=300,vers=3.1.1  0 0
```

What each part is for:

- **`soft`** — return an error rather than blocking forever. `hard` is the default kind of hang you cannot `umount -f` your way out of.
- **`echo_interval=10`** — the reconnect wait is about three times this, so ~30 s instead of the default ~180 s.
- **`nofail` + `noauto` + `x-systemd.automount`** — boot does not wait on it, and the mount happens on first access.
- **`x-systemd.mount-timeout=15`** — that first access fails fast in userland instead of stalling the process that touched it.
- **`noserverino`** — avoids inode churn across reconnects.

**Be honest about the residual:** even tuned, an `ls` on a dead mount blocks for the timeout. A share can be made to fail *quickly*; it cannot be made transparent.

### 3b. Local copies (the route that actually makes "model present" true)

```
rsync -av --info=progress2 \
  /d/AI_ASSETS/models/checkpoints/sdxl/ spellnode:/opt/comfyui/models/checkpoints/sdxl/
```

Costs disk and a sync step, and in exchange **"the node has this model" becomes a property of the node** rather than of the network. If you care about a job not failing halfway because a switch blinked, this is the route.

Either way, point ComfyUI at the result with its own `extra_model_paths.yaml` **on the node**. The app will not write that file for you: a local file cannot prepare another machine, and pretending otherwise is how you get a job that passes its checks here and fails over there.

---

## 4. Which families to trust there

Ampere is not Blackwell, and the difference is not cosmetic.

- **No fp8 tensor cores.** An fp8 checkpoint loads and dequantises per layer — it works, it saves VRAM, it does not save time. Expect a 3090 Ti to be several times slower than the 5090 on the same fp8 graph.
- **NVFP4 is emulated.** Measured on this project's own hardware it was still the best memory cell, but it is emulation, not acceleration.
- **SageAttention runs** on sm_86 through its Triton kernels; the fp8 PV path is sm_89+.
- **24 GB is 24 GB.** LTX-2.3 22B and Wan 14B at high resolution are where it will run out, not where it will be slow.

So the Families checklist for an endpoint **starts empty and the app fills it from successes**. You can untick a family; you cannot tick one that has never rendered there. That is deliberate — a checkbox you can tick is a promise the machine has not made.

Recommended gate order: **SDXL and Krea2 first**, then Flux, then video one family at a time.

---

## 5. The gate, run for real

**2026-09-17, against `192.168.1.127:8188`.**

Capability check, through `endpoint_capability.check_endpoint`, on a real SDXL graph:

| graph | verdict | checks run |
|---|---|---|
| names `sdxl/LuxuriousPrisma_v30.safetensors` (the node reports it) | **ok** | health, models, nodes |
| names `no_such_model_xyz.safetensors` | **refused** | health, models |

The refusal read: *"http://192.168.1.127:8188 does not have no_such_model_xyz.safetensors."* Note it stopped after the models check — the checks run in cost order and the node contract was never fetched, because there was already a reason.

Then the render itself:

| | |
|---|---|
| checkpoint | `sdxl/LuxuriousPrisma_v30.safetensors` |
| graph | SDXL, 1024×1024, 20 steps, CFG 7.0, euler/normal |
| executed on | RTX 3090 Ti, via `POST /prompt` |
| wall time | **80.3 s** |
| fetched back | `GET /view` → 2,002,262 bytes |
| dest | `docs/design/55_t7_assets/t6_spellnode_sdxl_gate.png` |

**SDXL is gated on SpellNode.** Nothing else is. Krea2, Flux and every video family need their own gate render on that machine before the app will offer them.

---

## 6. Why not ComfyUI-Distributed

Doc 54 originally chose it. The 2026 research overturned that, and the reason is not a preference:

- With **no reachable worker it silently falls back to running the job on the master.** The requirement here is fail-closed. A router that quietly runs the job somewhere else is the opposite of one.
- It requires its **Collector and Seed nodes in every graph**, so SpellVision would have to inject them into every graph it builds.
- Its semantics are **parallel batch** — the same graph on N participants with different seeds — not "route this job there".
- **NetDist** substitutes a **black image** when a fetch fails, and last shipped in February 2024.

Native routing needed no ComfyUI extension at all, because the worker already resolved its endpoint per request and already fetched outputs over HTTP. What was missing was a producer, a capability gate and per-endpoint state.

---

## Related

Doc 54 §1 T6 · `docs/superpowers/plans/2026-09-17-w6-endpoint-routing.md` · `docs/superpowers/specs/2026-09-15-t2-t6-research/t6-research.md` · `python/endpoint_capability.py` · `qt_ui/shell/EndpointRegistry.*`
