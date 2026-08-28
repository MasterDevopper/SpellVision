# 50 — The feature build standard

**Status:** active. Apply to every feature from v0.1.0 onward.

The owner asked for two things alongside the Krea 2 work: a repeatable way to build each feature
*sophisticatedly*, and a critique of what was already built so v0.1.0 does not ship bugs we already
had the evidence to prevent.

This is the first. Every rule below is here because it caught a real defect — the citation is the
defect, not a principle. Nothing is aspirational.

---

## The governing observation

> **The dangerous failures report success.**

Every serious bug found across this work had the same shape. Not a crash, not a traceback — a green
result over a wrong or absent one:

| what it looked like | what it was |
|---|---|
| `ok: true` + empty payload | an unregistered worker command returning a `client_warning` envelope |
| `ready: true`, green badge | a scanner that skipped subgraph internals it could not read |
| "nothing missing" | a `scan_report.json` written before the check existed |
| a clean conversion | a bypassed `LoraLoader` leaving the sampler's `model` unset |
| a cancel that returned success | `snapshot_payload()` overriding the handler's `ok` |
| 764 tests passing | the download progress bar wired to a signal that never fired |
| `exact_download` | the first same-named file from an unrelated uploader |

A rule that only prevents crashes is not worth writing down. These are the rules that prevent
confident wrongness.

---

## The eight rules

### 1. Measure before building

Every heuristic gets a number on the real corpus *before* it ships.

- Name-similarity substitution ranking: **0 of 16**. Deleted before it shipped.
- Tier-3 name search "resolved" **9 of 10** missing checkpoints — and 4 of those were a *style
  LoRA*, not the checkpoint. Constrained to exact-filename + type filter: **5 of 10, all correct.**
  An answer for 9 that is wrong about 4 is worse than an answer for 5 that knows it.
- "We have 2 substitution candidates" was actually **112**.

A heuristic without a number is a guess with formatting.

### 2. Ground from live artifacts, never from memory

`/object_info` dumps, real API payloads, the actual workflow JSON.

- Live `CLIPLoader.type` returned `"Wan-2.2 T2V"`, matching no hardcoded table anywhere.
- `CLIPLoader.device` was confirmed as an *optional* input accepting exactly `{default, cpu}` by
  reading the live schema — not by copying the value out of the reference workflow.
- Two Cloudflare R2 delivery hostnames were guessed for the Civitai allowlist. **Both wrong**; the
  live redirect goes to `b2.civitai.com`.

Corollary, learned twice while writing this document's own commit: **a filename and a public API
listing are not the file.** Two module docstrings written from those alone were both wrong —
`comfy_graph_helpers` is schema introspection, not graph rewiring; `gpu_info` is an uncalled
standalone script, not the NVML fast path.

### 3. Three states, never two

`resolved` / `ambiguous` / `unknown`. **Ambiguity is an answer**, and collapsing it into either
neighbour is how a guess gets laundered into a fact.

- `AmbiguousDownload` when several genuinely different files share a filename.
- `AmbiguousCivitaiModel` when a link names no version.
- Architecture inference reports `ambiguous` rather than picking the likelier family.
- A ZIP holding two workflows refuses and names them.

The test of a two-state design: ask what it returns when it does not know. If that is the same
value it returns for one of the real answers, it will lie.

### 4. A component must be unable to look correct while being wrong

Not "should not" — *unable*. Design so the failure mode is loud.

- No `ok: true` around an empty payload.
- No "nothing missing" derived from an artifact that could not be read.
- Readiness fails on an unresolved subgraph, because a green badge was the last route to a launch
  that would then refuse with a raw UUID.

### 5. One resolver, not two

A checker that decides differently from the doer is a bug generator.

- The model picker offered 112 substitutes for a model the launcher could already resolve, because
  the picker required an exact match and the launcher resolved bare basenames.
- The subgraph expander is **pure topology, no `/object_info`** specifically so the scanner (which
  runs with ComfyUI unreachable, by contract) and the converter share one code path and agree on
  node ids.
- The Qt import dialog had a file-dialog filter *and* a separate hard-coded validator list. Adding
  ZIP to the backend would have left the Import button disabled with a message naming the old set.
- Where a second copy is genuinely unavoidable (layering), **pin them together with a test** —
  `test_the_zip_predicate_agrees_with_the_url_importer`.

### 6. Gate on the artifact, not the build

Pixels on the surface. Bytes on disk. A render in `/history`. Never a green suite alone.

- 764 tests passed while the download progress bar was dead — it polled off a signal that only
  fired on *change*.
- An MP4 decoded perfectly and never displayed: `QVideoWidget` failed silently.
- A byte-identical resubmit hit ComfyUI's node cache and returned a *fake* 12.1 s / 23.62 GB
  measurement. Vary the seed to force real sampling.

A green build says the code compiles, not that the feature exists.

### 7. Register the seam

Every new worker response type goes into `worker_client`'s message types **in the same commit** as
its command, with a test. An unregistered type is wrapped in a `client_warning` envelope whose own
`ok` is `true` — the UI sees success and shows nothing.

Generalised: when a feature crosses a boundary, the boundary's registry is part of the feature.

### 8. State the cause you verified, not the one you assume

Three separate messages this session named a cause that was never checked. Text-scanning source
produced a confidently wrong conclusion **five times** — including "lumina and pixart are
unreachable by any user", reported as fact, when the detection simply lived in C++ where the scan
was not looking.

Before asserting a cause: check it a second way. Call sites, not just string literals. The menu,
not just the handler. The bytes, not just the return value.

---

## Applying it

A feature is done when:

1. Its heuristics have numbers from the real corpus (rule 1).
2. Its schema assumptions came from a live dump (rule 2).
3. It has a name for "I don't know" (rule 3).
4. Its failure is louder than its success is quiet (rule 4).
5. Nothing else in the tree decides the same question differently (rule 5).
6. It was verified on the artifact, not the build (rule 6).
7. Every boundary it crosses is registered, with a test (rule 7).
8. Every causal claim in its commit message was checked twice (rule 8).

## Where the ratchets live

Rules are advice; tests are enforcement. The ones that hold this standard in place:

| ratchet | holds |
|---|---|
| `tests/test_family_capability.py` | a family cannot be "supported" while missing a layer |
| `tests/test_queue_commands_live.py` | every menu command + its payload key, over the real protocol |
| `tests/test_comfy_subgraph_expansion.py` | 268/268 identity on non-subgraph templates |
| `tests/test_worker_client_message_types.py` | rule 7, mechanically |
| `tests/test_comfy_object_info_transport.py` | the transport fix stays fixed |
| `tests/test_credential_store.py` | the plaintext secret never reaches disk |
| the god-file drift sweeps | split modules keep their imports (`py_compile` passes either way) |

The gap this table makes visible: nothing yet distinguishes a command that is *deliberately*
CLI-only from one someone forgot to wire. Tagging each worker command `user_facing` / `diagnostic`
/ `internal`, with a test asserting every `user_facing` one has a route, is the next ratchet worth
building — it would turn Doc 49's one-off sweep into a standing guarantee.
