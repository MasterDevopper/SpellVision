# Doc 38 — Missing models should not be a hard blocker (research)

**Status:** research + design. Nothing auto-substitutes yet, deliberately — see §6.
**Measured:** 2026-08-26, against the 81-entry imported-workflow library and a live `/object_info`.

---

## 1. The problem

Of 81 imported workflows, **56 fail to launch for one reason only: they name a model file that is
not on this box.** Not a missing node, not a bad graph — the workflow is fine and the machine simply
has a different checkpoint.

That is at odds with the product premise. SpellVision exists to resolve dependencies for the user;
"you must own exactly `juggernautXL_ragnarokBy.safetensors`" is the kind of friction it is supposed
to remove. A user with 130 checkpoints should not be told no because none of them is *that* one.

Today `_sv_choose_comfy_choice` (`comfy_graph_helpers.py`) matches exact name, then basename. If
the file is absent entirely it returns the requested name unchanged and `/prompt` rejects it with
`value_not_in_list`.

## 2. First hypothesis — substitute within the same family — mostly FAILS

Measured per missing model reference, asking "does the catalog hold another model of the same
family?":

| family of requested model | missing refs | have a same-family stand-in |
|---|---|---|
| unknown | 33 | 0 |
| wan | 14 | 13 |
| illustrious | 11 | 0 |
| anima | 5 | 5 |
| pony | 5 | 3 |
| stable_diffusion | 1 | 1 |

**Only 10 of 56 workflows would be fully rescued.** Two distinct causes, and they point the same way:

- **33 references classify as `unknown`.** `model_classification` reads the FILENAME, and the
  filename of a model you do not have is weak evidence. Community checkpoint names carry no reliable
  architecture signal.
- **11 classify as `illustrious` with no stand-in**, on a box full of SDXL checkpoints. Illustrious
  *is* an SDXL derivative. The taxonomy conflates **architecture** (what the graph can actually
  load) with **lineage** (a stylistic finetune).

## 3. Second hypothesis — infer architecture from the GRAPH — WORKS

The filename of an absent model is the weakest signal available. The nodes *around* the loader are
present, unambiguous, and describe exactly what the model must satisfy.

Measured over the 55 workflows with a missing checkpoint/unet:

| | count |
|---|---|
| architecture inferable from graph markers | **53** |
| no marker at all | 2 |

Signals found:

| marker | workflows | implies |
|---|---|---|
| `EmptyLatentImage` | 43 | sd15 or sdxl |
| `EmptySD3LatentImage` | 5 | sd3 / flux / krea2 |
| `ModelSamplingSD3` | 5 | sd3 / flux |
| `WanImageToVideo`, `CLIPLoader(type=wan)` | 4 | wan |
| `ModelSamplingAuraFlow` | 2 | lumina / krea2 |
| `EmptyHunyuanLatentVideo` | 1 | hunyuan_video |

The 43 `sd15_or_sdxl` cases are disambiguated by latent size: 1080/1024/896/832 px → SDXL,
512 px → SD15. Only 2 workflows in the library use 512.

`CLIPLoader.type` is the strongest signal where present — it names the architecture outright.

**So architecture is recoverable for ~53 of 55, against 10 by family-name matching.**

## 4. The taxonomy fix this implies

Two separate axes, currently collapsed into one:

- **architecture** — what the graph requires and the loader can bind: `sdxl`, `sd15`, `flux`,
  `wan`, `ltx`, `hunyuan_video`, `krea2`, …
- **lineage** — a stylistic finetune of that architecture: `pony`, `illustrious`, `anima`,
  `noobai`, …

Substitution is legal **within an architecture**. Lineage is a *preference*, not a gate: prefer the
same lineage, fall back to any model of the right architecture.

That single change is what turns "11 illustrious requests, 0 candidates" into "11 illustrious
requests, ~100 SDXL candidates, prefer any illustrious-lineage ones present".

## 5. Proposed resolution order

For a loader input whose value is not in the live catalog:

1. exact match, then basename match (today's behaviour, unchanged)
2. **infer required architecture from the graph** — CLIPLoader.type > latent node > sampler/guidance
   markers > latent dimensions
3. classify the AVAILABLE catalog by architecture — these files are on disk, so use the real
   signal (safetensors header / metadata), not the filename
4. filter candidates to that architecture; rank by: same lineage > same base resolution >
   filename similarity
5. **report the substitution in the job record and the UI**

Step 3 matters: we classify what we HAVE from its header, and only guess about what we LACK.

## 6. Why this is not shipped as a silent auto-substitution

A wrong substitution does not fail loudly — it renders. This codebase's most expensive failures have
all been of that shape: the LTX prefix bug, the Wan VAE version mismatch, the
`ltx-2.3-22b-dev` hardlink that silently served FP8 weights. Swapping a checkpoint changes the
output completely while every status line still reads success.

So the intended shape is:

- **auto-substitute only within an architecture we positively inferred**, never on a guess
- **never silently** — the substitution is surfaced ("wanted X, ran Y") in the job record and the
  launch UI
- **user-overridable**, and remembered per workflow
- a workflow with no inferable architecture keeps failing loudly, as it does now

## 7. Also worth fixing, found alongside

- **`GetNode` / `SetNode` (KJNodes) are frontend-only wireless links.** Unlike rgthree's labels they
  carry real data flow, so they cannot simply be dropped — they need rewiring to the source the
  matching `SetNode` feeds. Currently blocks 1 workflow; the same machinery covers Reroute
  pass-through, a documented converter limitation.
- **`MagCache` is incompatible with both cores** — it imports a module-level `precompute_freqs_cis`
  that neither the Jul core nor v0.34.0 defines (both expose only `_precompute_freqs_cis`, a
  method). Not a bump regression; upstream lag.
- **54 missing-model failures are library content, not code.** Worth surfacing in Flows as
  "needs N models" with the Registry resolver offering to fetch them.

## 8. Reproducing

Both measurement scripts are self-contained and read a live `/object_info`:

- `substitution_research.py` — family-match opportunity sizing (§2)
- `arch_inference.py` — graph-marker architecture inference (§3)

Run against any instance with `--api`. They only measure; neither mutates a graph.
