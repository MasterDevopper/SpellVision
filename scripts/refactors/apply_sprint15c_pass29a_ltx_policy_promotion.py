from pathlib import Path

policy_h_path = Path("qt_ui/generation/VideoGenerationPolicy.h")
policy_cpp_path = Path("qt_ui/generation/VideoGenerationPolicy.cpp")
builder_path = Path("qt_ui/generation/GenerationRequestBuilder.cpp")
doc_path = Path("docs/sprints/SPRINT15C_PASS29A_LTX_POLICY_PROMOTION_README.md")
script_path = Path("scripts/refactors/apply_sprint15c_pass29a_ltx_policy_promotion.py")

policy_h = policy_h_path.read_text(encoding="utf-8")
policy_cpp = policy_cpp_path.read_text(encoding="utf-8")
builder = builder_path.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# 1) Extend VideoGenerationPolicySnapshot with route/status fields.
# ----------------------------------------------------------------------

old_header_fields = '''    QString diagnosticSummary;
    QString resolvedFamily;

    bool isVideoMode = false;'''

new_header_fields = '''    QString diagnosticSummary;
    QString resolvedFamily;
    QString backendRoute;
    QString validationStatus;

    bool isVideoMode = false;'''

if "QString backendRoute;" not in policy_h:
    if old_header_fields not in policy_h:
        raise SystemExit("Could not find VideoGenerationPolicySnapshot string field marker.")
    policy_h = policy_h.replace(old_header_fields, new_header_fields, 1)

old_bool_fields = '''    bool fpsValid = false;
    bool ready = false;

    QStringList warnings;'''

new_bool_fields = '''    bool fpsValid = false;
    bool ready = false;
    bool usesPromptApiBackend = false;
    bool validatedPromptApiFamily = false;
    bool validatedVideoBackend = false;

    QStringList warnings;'''

if "bool usesPromptApiBackend" not in policy_h:
    if old_bool_fields not in policy_h:
        raise SystemExit("Could not find VideoGenerationPolicySnapshot bool field marker.")
    policy_h = policy_h.replace(old_bool_fields, new_bool_fields, 1)

old_public = '''    static bool requiresInputImageForMode(const QString &mode);
    static bool isValidatedNativeFamily(const QString &family);'''

new_public = '''    static bool requiresInputImageForMode(const QString &mode);
    static bool isValidatedNativeFamily(const QString &family);
    static bool isValidatedPromptApiFamily(const QString &family);'''

if "isValidatedPromptApiFamily" not in policy_h:
    if old_public not in policy_h:
        raise SystemExit("Could not find VideoGenerationPolicy public marker.")
    policy_h = policy_h.replace(old_public, new_public, 1)

policy_h_path.write_text(policy_h, encoding="utf-8")


# ----------------------------------------------------------------------
# 2) Promote LTX as a validated experimental Prompt API family.
# ----------------------------------------------------------------------

old_validated_native = '''bool VideoGenerationPolicy::isValidatedNativeFamily(const QString &family)
{
    const QString key = family.trimmed().toLower().replace(QStringLiteral("-"), QStringLiteral("_"));
    return key == QStringLiteral("wan") || key.startsWith(QStringLiteral("wan"));
}'''

new_validated_native = '''bool VideoGenerationPolicy::isValidatedNativeFamily(const QString &family)
{
    const QString key = family.trimmed().toLower().replace(QStringLiteral("-"), QStringLiteral("_"));

    // Sprint 15C Pass 29A:
    // Wan remains the production native video family.
    return key == QStringLiteral("wan") || key.startsWith(QStringLiteral("wan"));
}

bool VideoGenerationPolicy::isValidatedPromptApiFamily(const QString &family)
{
    const QString key = family.trimmed().toLower().replace(QStringLiteral("-"), QStringLiteral("_"));

    // Sprint 15C Pass 29A:
    // LTX is enabled through the existing Prompt API gated submission path.
    // This is intentionally separate from native Wan routing.
    return key == QStringLiteral("ltx") ||
           key == QStringLiteral("ltx_video") ||
           key == QStringLiteral("ltxv") ||
           key.startsWith(QStringLiteral("ltx_"));
}'''

if "VideoGenerationPolicy::isValidatedPromptApiFamily" not in policy_cpp:
    if old_validated_native not in policy_cpp:
        raise SystemExit("Could not find isValidatedNativeFamily block.")
    policy_cpp = policy_cpp.replace(old_validated_native, new_validated_native, 1)


old_stack_ready = '''    out.hasNativeVideoStack = hasNativeVideoStack(draft);
    out.resolvedFamily = resolvedVideoFamily(draft);
    out.stackReady = isStackReady(draft) || out.hasWorkflowBinding;'''

new_stack_ready = '''    out.hasNativeVideoStack = hasNativeVideoStack(draft);
    out.resolvedFamily = resolvedVideoFamily(draft);
    out.validatedPromptApiFamily = isValidatedPromptApiFamily(out.resolvedFamily);
    out.usesPromptApiBackend = out.validatedPromptApiFamily && !out.hasWorkflowBinding;
    out.validatedVideoBackend = isValidatedNativeFamily(out.resolvedFamily) ||
                                out.validatedPromptApiFamily ||
                                out.hasWorkflowBinding;
    out.backendRoute = out.hasWorkflowBinding
                           ? QStringLiteral("workflow")
                           : (out.usesPromptApiBackend
                                  ? QStringLiteral("prompt_api")
                                  : (out.hasNativeVideoStack ? QStringLiteral("native") : QStringLiteral("missing")));
    out.validationStatus = isValidatedNativeFamily(out.resolvedFamily)
                               ? QStringLiteral("production_native")
                               : (out.validatedPromptApiFamily
                                      ? QStringLiteral("experimental_prompt_api")
                                      : QStringLiteral("unvalidated"));

    // LTX Prompt API requests can be stack-ready with the selected model even
    // when they are not a Wan dual-noise native stack.
    out.stackReady = isStackReady(draft) ||
                     out.hasWorkflowBinding ||
                     (out.validatedPromptApiFamily && !draft.model.trimmed().isEmpty());'''

if "out.validatedPromptApiFamily = isValidatedPromptApiFamily" not in policy_cpp:
    if old_stack_ready not in policy_cpp:
        raise SystemExit("Could not find evaluate() stack readiness block.")
    policy_cpp = policy_cpp.replace(old_stack_ready, new_stack_ready, 1)


old_warnings = '''    if (out.hasNativeVideoStack && !out.stackReady && !out.hasWorkflowBinding)
        out.warnings << QStringLiteral("Selected native video stack is partial or unresolved.");
    if (out.hasNativeVideoStack && !out.hasWorkflowBinding && !isValidatedNativeFamily(out.resolvedFamily))
        out.warnings << QStringLiteral("Only Wan native T2V is production-enabled in Sprint 15B Pass 1. Other video families are recognized but experimental until validated.");'''

new_warnings = '''    if (out.hasNativeVideoStack && !out.stackReady && !out.hasWorkflowBinding && !out.validatedPromptApiFamily)
        out.warnings << QStringLiteral("Selected native video stack is partial or unresolved.");
    if (out.hasNativeVideoStack &&
        !out.hasWorkflowBinding &&
        !isValidatedNativeFamily(out.resolvedFamily) &&
        !out.validatedPromptApiFamily)
    {
        out.warnings << QStringLiteral("Only Wan native video and LTX Prompt API video are enabled. Other video families are recognized but experimental until validated.");
    }'''

if old_warnings in policy_cpp:
    policy_cpp = policy_cpp.replace(old_warnings, new_warnings, 1)


old_backend = '''    const QString backend = out.hasWorkflowBinding
                                ? QStringLiteral("workflow")
                                : (out.hasNativeVideoStack ? QStringLiteral("native") : QStringLiteral("missing"));'''

new_backend = '''    const QString backend = out.backendRoute.trimmed().isEmpty()
                                ? (out.hasWorkflowBinding
                                       ? QStringLiteral("workflow")
                                       : (out.hasNativeVideoStack ? QStringLiteral("native") : QStringLiteral("missing")))
                                : out.backendRoute;'''

if old_backend in policy_cpp:
    policy_cpp = policy_cpp.replace(old_backend, new_backend, 1)


old_summary = '''    out.diagnosticSummary = QStringLiteral("%1 video • %2 • %3 • %4 • %5 • %6")
                                .arg(out.requestKind.toUpper(), backend, input, stack, family, out.durationLabel);'''

new_summary = '''    out.diagnosticSummary = QStringLiteral("%1 video • %2 • %3 • %4 • %5 • %6 • %7")
                                .arg(out.requestKind.toUpper(),
                                     backend,
                                     input,
                                     stack,
                                     family,
                                     out.durationLabel,
                                     out.validationStatus);'''

if old_summary in policy_cpp:
    policy_cpp = policy_cpp.replace(old_summary, new_summary, 1)

policy_cpp_path.write_text(policy_cpp, encoding="utf-8")


# ----------------------------------------------------------------------
# 3) Emit LTX route/status metadata in generation payloads.
# ----------------------------------------------------------------------

old_builder_validation = '''        payload.insert(QStringLiteral("video_validated_backend"), VideoGenerationPolicy::isValidatedNativeFamily(videoPolicy.resolvedFamily));'''

new_builder_validation = '''        payload.insert(QStringLiteral("video_validated_backend"), videoPolicy.validatedVideoBackend);
        payload.insert(QStringLiteral("video_backend_route"), videoPolicy.backendRoute);
        payload.insert(QStringLiteral("video_validation_status"), videoPolicy.validationStatus);
        payload.insert(QStringLiteral("video_uses_prompt_api_backend"), videoPolicy.usesPromptApiBackend);
        payload.insert(QStringLiteral("video_validated_prompt_api_family"), videoPolicy.validatedPromptApiFamily);'''

if "video_backend_route" not in builder:
    if old_builder_validation not in builder:
        raise SystemExit("Could not find GenerationRequestBuilder video_validated_backend line.")
    builder = builder.replace(old_builder_validation, new_builder_validation, 1)

builder_path.write_text(builder, encoding="utf-8")


# ----------------------------------------------------------------------
# 4) Sprint doc.
# ----------------------------------------------------------------------

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text("""# Sprint 15C Pass 29A — LTX Policy Promotion

## Goal

Promote LTX from a recognized-but-blocked video family into an enabled experimental Prompt API family.

## What changed

- Wan remains the production native video family.
- LTX is now validated through the Prompt API gated submission path.
- LTX readiness can pass when a selected LTX model is present, even without Wan dual-noise native stack metadata.
- Video payloads now include route/status metadata:
  - `video_backend_route`
  - `video_validation_status`
  - `video_uses_prompt_api_backend`
  - `video_validated_prompt_api_family`
  - `video_validated_backend`

## Why this matters

This removes the policy-level block before Qt Generate routing is connected to the existing LTX Prompt API submission path.

## Expected status after this pass

- LTX T2V/I2V can be marked ready by the video readiness policy.
- Generate routing is not changed yet.
- Wan behavior is unchanged.

## Next pass

Sprint 15C Pass 29B — route Qt Generate for LTX T2V/I2V into `ltx_prompt_api_gated_submission`.
""", encoding="utf-8")

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 29A: LTX policy promotion.")
