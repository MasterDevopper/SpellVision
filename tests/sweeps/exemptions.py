"""The third state: sites that are known, with a reason.

The old ratchets had two states -- compliant, or outside the file list they happened to name. A
violation in the second group was not compliant, not violating and not a documented exception; it
was merely *out of scope*, which is how a defect hides in plain sight. ``clothes_only.py`` rendered
seed 0 as 7 for months with a green seed ratchet three files away.

Two kinds live here, and the difference matters:

``EXEMPT``   a site that is legitimately different. The reason is the deliverable -- a boolean here
             would be indistinguishable from the out-of-scope state this module exists to abolish.

``BASELINE`` sites that are REAL violations, counted per file, awaiting the phase that fixes them.
             Two-way, like ``KNOWN_GAPS`` in test_family_capability: a count that goes UP fails
             because it is a regression, and a count that goes DOWN fails because the baseline must
             be lowered rather than left as a permanent allowance.

Per file rather than per line: line numbers shift under every edit above them, and a key that
invalidates itself would quietly re-report the thing it was meant to record.
"""
from __future__ import annotations

# --- legitimately different -------------------------------------------------------------------------

EXEMPT: dict[str, dict[str, str]] = {
    "comfy-output-path-through-one-resolver": {
        "qt_ui/WorkflowLibraryPage.cpp::shell-open:qt_ui/WorkflowLibraryPage.cpp": (
            "\"Open Workflow JSON\" opens <imported_workflows>/<slug>/workflow.json -- a file this "
            "app WROTE, under a root it owns, with a slug workflow_importer sanitised. Its suffix "
            "was never chosen by a remote. Routing it through openOutputAsset would reveal the "
            "folder instead of opening the file (JSON is not media), which is a worse answer for "
            "a user who asked to see the JSON. The rule's concern is a suffix authored elsewhere; "
            "this one is authored here."
        ),
    },
    # Zero, and it stays zero. All 80 sites route through `bounded_option`, which resolves the
    # field's aliases and its valid range from one table instead of from 80 hand-written `or`
    # chains. Two of those chains INVERTED a video denoise: 0.0 means "return the input unchanged",
    # and `or 1.0` turned it into "ignore the input entirely".
    #
    # The bounds table is what makes this more than a rename. It answers "is zero sayable here" once
    # per FIELD -- yes for cfg, denoise, limit, timeout, shift and lora_scale; no for steps, fps and
    # width -- and a stated value outside the range is clamped AND REPORTED. The old form silently
    # substituted a default, which is how a stated steps=0 came back as a normal-looking render with
    # nothing anywhere saying the number had been ignored.
    "no-machine-paths": {
        # These keys embed the literal, so a cutover that repoints the resolver WITHOUT editing
        # here does two bad things at once: the rule fires on the new literal, and the old
        # exemptions rot into entries that describe nothing. Both halves now name three trees --
        # one live and two superseded -- because the 2026-08-31 cutover made rollback two-deep and
        # `prefer_live` has to know every tree that was ever live, not just the oldest.
        "python/comfy_root.py::C:/sv_comfynext_v034/ComfyUI": (
            "THE resolver, and the live install after the 2026-08-31 cutover. A resolver has to "
            "name the things it resolves between -- the same way comfy_endpoint names "
            "127.0.0.1:8188. The rule's point is that this is the ONLY place they appear; before "
            "this they were spread across five modules, three naming only the rollback tree."
        ),
        "python/comfy_root.py::C:/sv_comfynext/ComfyUI": (
            "Superseded at the 2026-08-31 cutover and now the FIRST rollback. Listed in "
            "SUPERSEDED_COMFY so prefer_live redirects a stored path carrying it; without that "
            "entry a saved setting would silently run generation on the v0.27.0 core."
        ),
        "python/comfy_root.py::D:/AI_ASSETS/comfy_runtime/ComfyUI": (
            "The May build, superseded at the 2026-07-17 cutover -- the second rollback."
        ),
        "qt_ui/shell/RuntimeProfile.cpp::C:/sv_comfynext_v034/ComfyUI": (
            "The Qt half of the same resolver. resolvePreferredComfyRoot already existed and was "
            "already called from two of the four Qt sites -- it was a one-line "
            "`return normalized(configured)`, a resolver in name only. Filling it in beat adding a "
            "ninth, and these literals moved here out of ImageGenerationPage and "
            "ModelThumbnailCache."
        ),
        "qt_ui/shell/RuntimeProfile.cpp::C:/sv_comfynext/ComfyUI": (
            "Superseded, Qt side. Same reason as the Python half: kSupersededComfyRoots has to "
            "carry every tree that was ever live or a stale QSettings value walks past it."
        ),
        "qt_ui/shell/RuntimeProfile.cpp::D:/AI_ASSETS/comfy_runtime/ComfyUI": (
            "The May build, named once on the Qt side."
        ),
    },

    # Zero, and it stays zero. The one entry was a site inside `python/runtime_adapters/`, parked
    # with "Phase 4a deletes the package and this exemption goes with it". Phase 4a did, and it
    # has. An exemption that outlives its site is how a rule quietly stops being enforced.
    "zero-is-sayable": {},

    # The rule's own test file holds each broken shape as a FIXTURE -- it exists to prove the rule
    # fires on them. Exempted with a reason rather than spelled around, because a fixture that had
    # to disguise itself would no longer be the code the rule must catch, and the test would stop
    # testing the thing it claims to.
    "object-info-through-one-transport": {
        "tests/test_object_info_transport_is_one_rule.py": (
            "The rule's own test holds each broken shape as a FIXTURE -- it exists to watch the rule "
            "fire on them. Spelling around the pattern would leave the fixture no longer being the "
            "code the rule has to catch, so the test would stop testing what it claims to."
        ),
    },

    "request-keys-have-readers": {},

    # Zero, and it stays zero: the whole point is that there is one resolver per side.
    "one-comfy-root-resolver": {},

    "samplers-through-one-resolver": {
        "python/native_video_graphs.py::_build_native_hunyuan_wrapper_i2v_prompt::scheduler": (
            "Not a sampler choice. The kijai HunyuanVideoWrapper's `scheduler` input names a "
            "diffusers scheduler CLASS (FlowMatchDiscreteScheduler), which is the wrapper's "
            "sampling algorithm rather than a value from the KSampler scheduler combo. Routing it "
            "through sampling_for would offer the user ComfyUI scheduler names for an input that "
            "does not take them."
        ),
    },

    # Zero. The one entry was `runtime_adapters/comfy_workflow_adapter.py::_submit_prompt` -- the
    # sixth ComfyUI submitter, in a package nothing imported. Writing that exemption is what
    # identified the package as Phase 4a's work: the rule had found a real uncancellable
    # submission, and the honest answer was not to exempt it but to delete the copy it lived in.
    "cancellable-comfy-submission": {},

    # Zero, and a first exemption here deserves suspicion: an unreachable module is never
    # "legitimately different", it is either deleted or wired up.
    "every-module-is-reachable": {},

    "vram-numbers-name-their-source": {
        **{
            f"python/vram.py::worker_vram::{call}": (
                "THE reader. It has to make the torch calls it is the single point of, the same way "
                "comfy_root names the two install paths. The rule's point is that these five appear "
                "nowhere else -- before it, four routes read the worker's allocator to describe a "
                "render that happened in another process."
            )
            for call in ("mem_get_info", "memory_allocated", "memory_reserved",
                         "max_memory_allocated", "max_memory_reserved")
        },
        "tests/test_runtime_unload_on_exit.py::test_unload_all_runtimes_requests_comfy_free::allocated_gb": (
            "A monkeypatch stub standing in for the reader, not a claim about hardware. Tests stay "
            "in this rule's scope on purpose -- a test that asserts a fabricated VRAM number as if "
            "it were measured is the same defect -- so these two are exempted individually rather "
            "than by excluding the whole tree."
        ),
        "tests/test_runtime_unload_on_exit.py::test_unload_all_runtimes_fails_closed_when_comfy_free_fails::allocated_gb": (
            "The same stub in the failure-path test."
        ),
    },

    "latent-decode-through-one-resolver": {
        "python/comfy_graph_helpers.py::vae_decode_node::VAEDecode": (
            "THE resolver. It has to name the two classes it chooses between, the same way "
            "comfy_root names the live and rollback installs. The rule's point is that this is the "
            "only place either name appears: before it, eleven image sites named VAEDecode and "
            "could not see the tiling switch, while hunyuan and mochi named VAEDecodeTiled and "
            "would not let go of it."
        ),
        "python/comfy_graph_helpers.py::vae_decode_node::VAEDecodeTiled": (
            "Same: the tiled class, named once so no builder has to."
        ),
    },

    # Zero. The rule was scoped to node literals -- a dict that declares a `class_type` -- rather
    # than to any dict with a "device" key, which is why there is nothing to exempt: the looser form
    # reported three sites where two were real, the third being MODEL_CACHE's torch device. Tightening
    # the predicate beat writing a reason for a site that was never a violation.
    "text-encoder-placement-through-one-resolver": {},

    "wire-types-registered": {
        "python/worker_client.py::client_warning": (
            "Produced BY this client for a message it did not recognise, not by the worker. "
            "Registering it would be circular."
        ),
        "python/worker_client.py::client_error": (
            "Same: this client's own transport-failure envelope, never sent by the worker."
        ),
        "python/ltx_prompt_api_submission.py::spellvision_result_registration": (
            "A nested sub-record carried inside a larger payload's `result_registration` field, "
            "not a top-level wire message -- it never reaches normalize_worker_message."
        ),
        "python/ltx_queue_history_registry.py::spellvision_result_registration": (
            "The same nested sub-record, built in a second place. Exempting it site by site rather "
            "than by type name is deliberate: if this record ever DOES become a top-level message "
            "somewhere new, that third site must be looked at rather than inheriting a blanket pass."
        ),
    },

    "qss-draws-a-control": {
        "qt_ui/ThemeManager.cpp::QComboBox QAbstractItemView": (
            "The combo popup is a top-level window that escapes the MainWindow cascade and the "
            "proxy style's item-view paint does not reach a popup's selection colour on every "
            "platform; the qApp overlay sheet is the one place it can be themed."
        ),
        "qt_ui/ThemeManager.cpp::QPushButton, QInputDialog QPushButton": (
            "Message-box buttons are created by Qt inside a dialog that escapes the cascade; the "
            "overlay sheet is the only hook that reaches them before they show."
        ),
        "qt_ui/ThemeManager.cpp::QPushButton:hover, QInputDialog QPushButton:hover": (
            "Same: the hover state of those message-box/input-dialog buttons, painted by the same "
            "escaping dialog the overlay sheet is the only hook into."
        ),
    },

    "primary-button-defined-once": {
        "qt_ui/ThemeManager.cpp::PrimaryActionButton": (
            "The one definition, kept for spacing only after Task 4; the paint lives in SvStyle."
        ),
    },
}


# --- real violations, counted, awaiting their phase -------------------------------------------------

BASELINE: dict[str, dict[str, int]] = {
    # The Qt half of the remote-endpoint gap, held open deliberately.
    #
    # Verified on 2026-09-01 against a real second machine: the Python side drives a ComfyUI on
    # another host end to end -- endpoint resolution, a 904-class /object_info fetch, the graph
    # builder, and a 1.28 MB render fetched back over /view. Every one of those asks the endpoint.
    #
    # These seven ask the disk. `chooseComfyOutputPath()` resolves THIS machine's install whatever
    # the endpoint is, and the hazard is not that it comes back empty -- it is that it comes back
    # FULL, of the last local session's renders. Home's gallery, the output card model and the
    # catalog's salvage scan would each show a previous local image as though it were the render
    # that just finished elsewhere, with nothing logged.
    #
    # Not exempt, because they are wrong. Not fixed here for two reasons, and the second is the
    # larger one.
    #
    # First: the Qt layer cannot ASK the question. `RuntimeProfile::comfyHost` is a hardcoded
    # `127.0.0.1` -- it reads no environment and no setting, while `comfyPort` three lines later
    # reads SPELLVISION_COMFY_PORT. So the app can be pointed at another machine's PORT and never
    # at another machine. `COMFY_API_URL`, which the worker honours, appears zero times under
    # qt_ui/. Until that field is resolved rather than assumed, a C++ locality predicate would
    # have nothing to read.
    #
    # Second: what a gallery should SHOW when the renders live on another machine is a product
    # decision -- hide the section, label it local-only, or fetch the remote listing -- not a
    # mechanical edit. Inventing an answer inside a sweep would be the plausible-looking wrong
    # value this rule exists to stop.
    "local-output-only-for-a-local-endpoint": {
        "qt_ui/generation/OutputPathHelpers.cpp": 3,
        "qt_ui/HomeDashboardPage.cpp": 1,
        "qt_ui/ImageGenerationPage_catalog.cpp": 2,
        "qt_ui/OutputCardModel.cpp": 1,
    },

    # Not debt. The rule's own test file, which holds each broken shape as a fixture so the rule can
    # be watched firing on it -- see the reason in EXEMPT above. Counted here so the number is still
    # pinned in both directions: if this file ever grows a SECOND urllib fetch, or loses this one,
    # the baseline test says so.
    "object-info-through-one-transport": {
        "tests/test_object_info_transport_is_one_rule.py": 1,
    },

    # Doc 50 rule 8. Every one of these makes a value the UI offers unsayable. The fix is
    # `numeric_option` / `bounded_option`, which already exist and are used at three call sites --
    # that under-use is the whole finding. Phase 2 of the overhaul plan drives this to zero.
    #
    # native_video_graphs alone holds 45 of the 80, which is why the shared builder spine (Phase 4)
    # and this rule are the same piece of work approached from two directions.
    # Zero, and it stays zero. All 80 sites route through `bounded_option`, which resolves the
    # field's aliases and its valid range from one table instead of from 80 hand-written `or`
    # chains. Two of those chains INVERTED a video denoise: 0.0 means "return the input unchanged",
    # and `or 1.0` turned it into "ignore the input entirely".
    #
    # The bounds table is what makes this more than a rename. It answers "is zero sayable here" once
    # per FIELD -- yes for cfg, denoise, limit, timeout, shift and lora_scale; no for steps, fps and
    # width -- and a stated value outside the range is clamped AND REPORTED. The old form silently
    # substituted a default, which is how a stated steps=0 came back as a normal-looking render with
    # nothing anywhere saying the number had been ignored.
    "zero-is-sayable": {},

    # A hardcoded path is how a resolver stops being one. Three of these
    # (ltx_requeue_draft_submission, video_family_readiness, ltx_prompt_api_*) point at
    # D:/AI_ASSETS/comfy_runtime/ComfyUI -- the ROLLBACK build CLAUDE.md 9.2 forbids probing as
    # live -- and they take it because RuntimeProfile never exports the env name they read, so they
    # cannot see the configured root at all. Phase 3a.
    #
    # look_completion.py:319 reaches into C:/Users/xXste/Code_Projects/Master-Sculptor, a different
    # repository on the author's disk. That one is a dependency, not a default.
    # 26 -> 13. Every ComfyUI-install literal is gone: eight resolvers across four env names became
    # one, and the three modules that hardcoded the ROLLBACK tree (ltx_requeue_draft_submission,
    # ltx_prompt_api_*, and runtime_paths' own copy of the live/rollback pair) now derive from it.
    #
    # What is left is two different things. garment_shrinkwrap and look_completion reach into
    # C:/Users/xXste/Code_Projects/Master-Sculptor, a SEPARATE repository on the author's disk --
    # that is a dependency to be configured, not a default to be resolved. The qt_ui entries are
    # display and cache paths on the Qt side, which no Python resolver can help with; they need the
    # C++ equivalent of comfy_root and that does not exist yet.
    # 26 -> 11. Every ComfyUI-install literal outside the two resolvers is gone: eight resolvers
    # across four env names became one on each side of the wire. The Qt half mattered as much as the
    # Python half -- ImageGenerationPage carried the C++ twin of the LTX workflow literal, and
    # ModelThumbnailCache probed for ffmpeg inside the rollback tree.
    #
    # What is left is two different things. garment_shrinkwrap and look_completion reach into
    # C:/Users/xXste/Code_Projects/Master-Sculptor, a SEPARATE repository on the author's disk --
    # a dependency to be configured, not a default to be resolved. The rest are display, cache and
    # third-party tool paths (C:/ffmpeg) that no ComfyUI resolver can help with.
    "no-machine-paths": {
        "python/garment_shrinkwrap.py": 3,
        "qt_ui/HistoryPage.cpp": 3,
        "python/look_completion.py": 2,
        "python/runtime_paths.py": 1,
        "qt_ui/assets/ModelThumbnailCache.cpp": 1,
        "qt_ui/workers/WorkerQueueController.cpp": 1,
    },

    # Zero, and it stays zero. This rule shipped with a ratchet naming three files; sweeping all 92
    # modules found three more violations -- clothes_only (seed 0 -> 7), look_completion
    # (0 -> 4419) and ltx_smoke_test_route (0 -> a prompt hash, because _safe_int returns its
    # fallback for anything <= 0). All three are fixed.
    "seed-one-rule": {},

    # Zero, and it stays zero. Four terminalisers discarded transition_job's return; all four
    # happened to work, but silently -- which is exactly how fail_job hid the stranding bug for as
    # long as it did. Scoped to TERMINAL targets on purpose: 30 sites discard a STARTING/RUNNING
    # hop, which is a milder question, and flagging all of them would have buried these four.
    "terminalisers-check-their-hop": {},
    "wire-types-registered": {},

    # Zero, and it stays zero: every route that owns a job now hands its prompt id to the handle.
    # The only site left is exempted above as unreachable, so a NEW violation here means a new
    # route can start a render nobody can stop.
    "cancellable-comfy-submission": {},

    # 54 keys the UI sends that the worker never names. They are NOT one thing, and the split is
    # the useful part of the finding:
    #
    #   Provenance. Most of GenerationRequestBuilder's block -- video_dimensions_valid,
    #   video_readiness_warnings, client_video_mode, submit_origin, workflow_draft_source -- is
    #   diagnostic state the UI includes so it lands in the metadata sidecar, which
    #   clone_request_snapshot deep-copies whole. Nothing reads them individually and nothing
    #   should. They are not defects, but they are also not distinguishable from defects by
    #   inspection, which is why they sit at baseline rather than in EXEMPT: the honest label is
    #   "unclassified", and classifying 54 keys one at a time is its own pass.
    #
    #   Real, and named here so they are not lost: `positive_embeddings` / `negative_embeddings`
    #   (an embeddings picker whose values reach a worker with no textual-inversion loading).
    #   That is a FEATURE gap rather than hardening, so this pass records it instead of half-building it.
    #
    # What the rule already earned: wan_split, high_steps, low_steps, split_step, noise_split_step
    # and wan_noise_split_step were all in this list, and all six are now read.
    "request-keys-have-readers": {
        "qt_ui/generation/GenerationRequestBuilder.cpp": 24,
        # 8 -> 9 in Phase 4a, and the extra one is the most interesting result of that phase.
        #
        # `python_exe` had a reader: `runtime_adapters/diffusers_adapter.py` did
        # `request.get("python_exe")`. That package was unreachable -- nothing imported it -- so
        # the key was satisfied by code that could never run, and deleting the package is what
        # revealed the key had no live reader at all.
        #
        # An unreachable module does not only carry duplicate defects; it SATISFIES RATCHETS.
        # That is a second face of the meta-finding and the strongest argument for the
        # reachability rule: a dead copy makes a live rule report a pass.
        "qt_ui/MainWindow.cpp": 6,
        # 9 -> 6, and the missing three did not get readers: submit_origin,
        # client_readiness_block and workflow_backend moved with the 200-line generation builder
        # when it left MainWindow for its own translation unit. Recorded as a MOVE rather than
        # absorbed into the old count, because a baseline that quietly stayed at 9 would have hidden
        # three unread keys behind a number that looked unchanged -- and the sum across both files
        # is still 55, which is what makes the move checkable. (54 since ManagerPage's key gained
        # a reader on 2026-09-03.)
        "qt_ui/workers/WorkerRequestBuilder.cpp": 3,
        "qt_ui/Gen3DPage.cpp": 5,
        "qt_ui/workers/WorkerCommandRunner.cpp": 5,
        "qt_ui/DatasetGenerationPage.cpp": 1,
        # ManagerPage's key gained a reader when the Comfy-manager commands started streaming: the
        # runner takes an on_line callback, so what the page sends is now consumed rather than
        # merely accepted. Lowered rather than left at 1 -- a baseline that is not tightened when a
        # defect is genuinely fixed stops being a baseline and becomes a permission.
        "qt_ui/ManagerPage.cpp": 0,
        "qt_ui/WorkflowLibraryPage.cpp": 1,
        "qt_ui/studios/CharacterStudioPage.cpp": 1,
    },

    # The four Character-Studio graphs, each a hand-copy of the krea2 graph with its own literal
    # euler/simple. They are REAL violations, not exceptions: the same defect as Hunyuan's, in the
    # copies. Threading the resolver into each separately would entrench the duplication, so they
    # are held here until Phase 5 collapses the four into one builder -- at which point this drops
    # to zero in one edit rather than four.
    # Zero, and it is meant to stay there. Phase 4a removed `python/runtime_adapters/` (713 lines,
    # four modules) and `workflow_profile_registry.py` (a second workflow-profile store beside
    # `comfy_slot_mapper.save_profile`, which is the one `workflow_importer` actually calls).
    #
    # `workflow_profile_registry` was already recorded as having zero references in Doc 21, in
    # 2026-06. It survived because "no references" was a note in a document rather than a property
    # of the tree -- which is this audit's whole thesis in one file.
    "every-module-is-reachable": {},

    # Zero, and it stays zero: nine sites, two node vocabularies, one resolver that translates
    # between them from /object_info rather than from a remembered pair.
    "text-encoder-placement-through-one-resolver": {},

    # Zero. Both decode classes are named in the resolver and nowhere else; the two exemptions
    # there are the resolver naming its own subject.
    "latent-decode-through-one-resolver": {},

    # Zero. Every VRAM number now comes from `vram.py`, which records which PROCESS it measured --
    # the worker's torch allocator, the ComfyUI process holding the weights, or a hosted API where
    # no local GPU was involved at all. "Not measured" is None; it used to be 0.0.
    "vram-numbers-name-their-source": {},

    # 8 -> 0 in Phase 5. Four graphs hardcoded euler/simple, so the cockpit's sampler row -- sent on
    # every request -- was dropped on all four. For krea2 that was worse than inert: the family's
    # measured default is er_sde, settled by render comparison on 2026-08-28, so three studio routes
    # rendered with a sampler the family's own measurement had REJECTED while the cockpit route used
    # the winner. Same family, same model, different sampler by which page you started from.
    #
    # The one remaining violation is exempted above, not baselined: the kijai wrapper's `scheduler`
    # names a diffusers scheduler CLASS, not a KSampler choice.
    "samplers-through-one-resolver": {},

    # Task 3 baseline (2026-09-07), and it is spent. SvStyle draws every owned control; a
    # stylesheet rule that still painted background/border/color for one was debt the retreat
    # (Tasks 4-8) removed page by page: the shell and the cockpit took ThemeManager.cpp from 83 to
    # 16, the library pages and the studios took the tree from 144 to 101, and Task 8 takes 101 to
    # 0.
    #
    # The dict is EMPTY rather than a list of zeros, so a rule that comes back in any file fails as
    # a NEW file with the offending line printed, not as a number creeping up from nothing.
    #
    # What is still counted and exempted (see EXEMPT above) is the three selectors in
    # applicationOverlayStyleSheet(): the combo popup and the message-box/input-dialog button with
    # its :hover. Those are top-level widgets that escape the MainWindow cascade, and the qApp
    # sheet is the only hook that reaches them. Task 8 also removed the fourth site those three
    # keys used to match -- settingsStyleSheet() repeated the combo-popup selector verbatim.
    #
    # Task 8 took the last 101: the settings and home sheets, Dataset, Train, Gen3D, Inspiration,
    # ModePage, the model-card hover overlay, the cockpit's session-thumbnail strip, the two
    # workflow dialogs, the command palette and the four Chain Studio widgets. Chain is the one
    # nobody had counted honestly: three of its "violations" were `#include <QPushButton>` read as
    # a selector (see the guard in rules.py), so the number could never have reached zero by
    # fixing code.
    # NOT ZERO ANY MORE, and the rise is the point rather than a regression. `_OWNED_TYPES` omitted
    # QFrame while SvStyle draws PE_Frame, so the zero above was taken over a tree the rule was not
    # looking at. Adding QFrame surfaced 18 sites in 7 files -- none of them new code, all of them
    # stylesheets that have been painting a control the style owns since before the rule existed.
    #
    # Baselined rather than fixed, deliberately: the fix is a stylesheet retreat per surface with a
    # render to prove each one still looks right, which is the wave-4 surface work, and doing it
    # blind inside a review-fix pass would be changing what the app looks like without looking at it.
    # Two-way like every other entry here: a file that drops below its number fails until the number
    # is lowered.
    "qss-draws-a-control": {
        # The mode-page hero band: a QFrame painted as a glow gradient.
        "qt_ui/ModePage.cpp": 1,
        # The shell's own sheet: the telemetry container and its separator, the rail divider, the
        # readiness strip in its three states, and the timing row. Dividers and strips drawn as
        # QFrames with a background instead of through the style's frame paint.
        "qt_ui/ThemeManager.cpp": 7,
        # Chain Studio, five widgets. Nav-hidden (SPELLVISION_SHOW_ALL_MODES), which is why it was
        # last through the wave-1 retreat and is the bulk of what remains.
        "qt_ui/chain/ChainCanvasWidget.cpp": 1,
        "qt_ui/chain/ChainConfigPanelWidget.cpp": 3,
        "qt_ui/chain/ChainDialogBarWidget.cpp": 4,
        "qt_ui/chain/ChainRailWidget.cpp": 1,
        "qt_ui/chain/ChainStudioPage.cpp": 1,
    },

    # Task 3 baseline, spent. Three radius systems disagreed before this rule existed (10/6,
    # 26/20/16/13, and thirteen per-call literals); every literal `border-radius:Npx` in a
    # stylesheet string was one of them. 133 -> 88 -> 63 -> 0.
    #
    # Task 8 took the last 63, and NOT by deleting them all: a radius that is still drawn now reads
    # radiusCard() or radiusControl() at build time -- the settings chip and the mode-page hero
    # note, the dataset preview, Home's dependency banner, the cockpit's canvas metric chips and
    # error pill, the command palette's own frame, the video preview plate. The overlay sheet's
    # five radii went the same way rather than into an exemption: a popup that escapes the window
    # cascade is still made of the same material as the window behind it, which is what spec S2.4
    # says ("its radii move to radiusControl()"). An exemption there would also have been keyed on
    # the radius TEXT -- "border-radius:6px" -- and so would have pardoned every 6px in the file.
    "qss-literal-radius": {},

    # Task 3 baseline, spent. The ThemeManager.cpp definition is exempted above as the one kept
    # definition (spacing only; SvStyle paints it). Four pages redefined #PrimaryActionButton as a
    # flat borderless variant under the same object name -- Dataset, Gen3D and Inspiration as the
    # brief named, plus TrainPage.cpp, which measured the same way and was a fourth real instance.
    # All four are gone, and so are the spacing-only rules that briefly replaced them: the rule
    # counts the SELECTOR, and it is right to -- a second `#PrimaryActionButton {` is a second
    # place to look when the hero button is wrong, whatever it sets. Primary's 34px floor and its
    # 0 18 padding are sizeFromContents' now.
    "primary-button-defined-once": {},

    # Task 3 baseline, spent. Weights 700/800/900 (or QFont::Bold/ExtraBold/Black, or
    # setBold(true)) off the 400/500/600 Plex ramp. 36 -> 31 -> 29 -> 0.
    #
    # Task 8 took the last 29. Most went with the control they sat on (a button's label weight is
    # SvStyle's). The rest are labels, and a label keeps its type token -- what changed is the
    # number: the shell's dock title and two status-bar labels, Chain Studio's four uppercase
    # eyebrows, the queue table's active row and the model thumbnail monogram (both setBold(true)),
    # the command palette's category header, and the two rich-text classes in the cockpit's model
    # tooltip, which were CSS inside a QLabel rather than a Qt sheet and had never been looked at.
    # 600 is the top of the ramp and Plex ships it; 700 it does not, so a 700 was synthesised.
    "type-weight-on-ramp": {},

    # Task 3 baseline. 281 Spacing:: token reads coexist with literal setSpacing/setContentsMargins
    # calls; literal zero stays literal (the rule does not flag it), every other spacing decision is
    # debt until it reads theme.spacing(Spacing::X).
    "spacing-literal": {
        "qt_ui/CustomTitleBar.cpp": 3,
        "qt_ui/DashboardMetricChip.cpp": 2,
        "qt_ui/DatasetGenerationPage.cpp": 2,
        "qt_ui/Gen3DPage.cpp": 5,
        "qt_ui/HomeDashboardPage.cpp": 5,
        "qt_ui/HomeModuleFrame.cpp": 1,
        "qt_ui/ImageGenerationPage.cpp": 11,
        "qt_ui/InspirationPage.cpp": 5,
        "qt_ui/MainWindow.cpp": 3,
        "qt_ui/ManagerPage.cpp": 1,
        "qt_ui/ModePage.cpp": 1,
        "qt_ui/SettingsPage.cpp": 1,
        "qt_ui/HistoryPage.cpp": 1,
        "qt_ui/TrainPage.cpp": 4,
        "qt_ui/WorkflowImportDialog.cpp": 1,
        "qt_ui/assets/ModelCardView.cpp": 2,
        "qt_ui/chain/ChainDialogBarWidget.cpp": 1,
        "qt_ui/chain/ChainRailWidget.cpp": 1,
        "qt_ui/generation/CockpitInspector.cpp": 3,
        "qt_ui/shell/FirstRunDialog.cpp": 9,
        "qt_ui/studios/CharacterStudioPage.cpp": 18,
        "qt_ui/studios/ComicStudioPage.cpp": 15,
        "qt_ui/studios/ConceptReferencePage.cpp": 15,
    },

    # Wave 2 task 4, and it is zero because the ONE reader was fixed rather than recorded.
    # positionQueueOverlay started the drawer's X at sideRail_->width(); it now asks
    # contentOrigin(). The sweep found no second reader outside qt_ui/shell/ -- ThemeManager names
    # both rail tokens, but as the enum that declares them and the switch that gives them their
    # values, which the rule deliberately does not count as reads (see the rule's docstring).
    #
    # An entry here would have been worse than useless: this rule exists precisely because the
    # drawer's assumption was invisible for as long as the rail never moved, and the layout switch
    # that moves it lands in the NEXT task. A baselined reader would ship already defeated.
    "shell-geometry-through-the-layout": {},

    # Wave 2 task 5, and zero from the first commit rather than after a cleanup: applyShellLayout
    # was written to this rule. The whole switch is a QBoxLayout::setDirection and a
    # SideRail::setOrientation, neither of which re-parents a widget, so there was never a page to
    # construct or destroy.
    #
    # A baseline here would be a contradiction. The rule's entire subject is a function that is one
    # commit old; a "known" violation in it would mean the feature shipped already broken in the
    # exact way the ratchet was written to prevent.
    "layout-switch-is-not-a-rebuild": {},

    # Wave 3 task 10. Five waitFor* APIs. Not dataflow -- a new call is a regression even if it
    # happens to be off the GUI thread, because this rule cannot tell. sendWorkerRequestForRuntime
    # still waitForFinished (QProcess); tests/test_no_gui_sync_worker_rpc.py requires that and is
    # a different property (no QEventLoop). Chain/Character/T2V History remain until those pages
    # stream like ManagerPage.
    "no-blocking-wait-on-the-gui-thread": {
        "qt_ui/MainWindow.cpp": 5,
        "qt_ui/ManagerPage.cpp": 1,
        "qt_ui/HistoryPage.cpp": 3,
        "qt_ui/TrainPage.cpp": 1,
        "qt_ui/WorkflowLibraryPage.cpp": 7,
        "qt_ui/assets/ModelThumbnailCache.cpp": 2,
        "qt_ui/main.cpp": 2,
        "qt_ui/shell/RuntimeProfile.cpp": 10,
        "qt_ui/studios/CharacterStudioPage.cpp": 2,
        "qt_ui/workers/WorkerProcessController.cpp": 4,
    },

    # Wave 3 task 10. The invented 3/7/12 floor. Stays until Task 12 gives Comfy real step/total.
    "progress-is-not-invented": {
        "qt_ui/shell/TelemetryPresenter.cpp": 2,
        "qt_ui/shell/TelemetryPresenter.h": 1,
    },
}


def baseline_for(rule: str) -> dict[str, int]:
    return BASELINE.get(rule, {})


def is_exempt(rule: str, site: str) -> bool:
    return site in EXEMPT.get(rule, {})


def total_baseline() -> int:
    return sum(sum(files.values()) for files in BASELINE.values())
