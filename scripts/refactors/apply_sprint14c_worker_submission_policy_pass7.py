from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
main_cpp = ROOT / "qt_ui" / "MainWindow.cpp"
cmake = ROOT / "CMakeLists.txt"


def fail(message: str) -> None:
    raise SystemExit(f"[pass7] {message}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"Expected one occurrence for {label}, found {count}.")
    return text.replace(old, new, 1)


cpp = main_cpp.read_text(encoding="utf-8")

if '#include "workers/WorkerSubmissionPolicy.h"' not in cpp:
    cpp = replace_once(
        cpp,
        '#include "workers/WorkerQueueController.h"\n',
        '#include "workers/WorkerQueueController.h"\n#include "workers/WorkerSubmissionPolicy.h"\n',
        "WorkerSubmissionPolicy include anchor",
    )

old_helpers = '''
    QString firstStackString(const QJsonObject &stack, const QStringList &keys)
    {
        for (const QString &key : keys)
        {
            const QString value = stack.value(key).toString().trimmed();
            if (!value.isEmpty())
                return value;
        }
        return QString();
    }

    QJsonObject videoStackFromPayload(const QJsonObject &payload)
    {
        const QJsonValue videoStackValue = payload.value(QStringLiteral("video_model_stack"));
        if (videoStackValue.isObject())
            return videoStackValue.toObject();

        const QJsonValue modelStackValue = payload.value(QStringLiteral("model_stack"));
        if (modelStackValue.isObject())
            return modelStackValue.toObject();

        return {};
    }

    QString resolvedModelValueFromPayload(const QJsonObject &payload)
    {
        const QString modelValue = payload.value(QStringLiteral("model")).toString().trimmed();
        if (!modelValue.isEmpty())
            return modelValue;

        const QJsonObject stack = videoStackFromPayload(payload);
        if (stack.isEmpty())
            return QString();

        return firstStackString(stack,
                                {QStringLiteral("diffusers_path"),
                                 QStringLiteral("model_dir"),
                                 QStringLiteral("model_directory"),
                                 QStringLiteral("primary_path"),
                                 QStringLiteral("transformer_path"),
                                 QStringLiteral("unet_path"),
                                 QStringLiteral("model_path")});
    }

    bool hasNativeVideoStackPayload(const QJsonObject &payload)
    {
        const QJsonObject stack = videoStackFromPayload(payload);
        if (!stack.isEmpty())
            return true;

        return !payload.value(QStringLiteral("native_video_stack_kind")).toString().trimmed().isEmpty();
    }

'''
if old_helpers in cpp:
    cpp = cpp.replace(old_helpers, "\n", 1)
elif "resolvedModelValueFromPayload" in cpp or "hasNativeVideoStackPayload" in cpp or "videoStackFromPayload" in cpp:
    fail("Submission helper names still exist, but the exact helper block did not match. Inspect MainWindow.cpp before continuing.")

old_binding = '''
    const bool hasWorkflowBinding =
        !payload.value(QStringLiteral("workflow_profile_path")).toString().trimmed().isEmpty() ||
        !payload.value(QStringLiteral("workflow_path")).toString().trimmed().isEmpty() ||
        !payload.value(QStringLiteral("compiled_prompt_path")).toString().trimmed().isEmpty();

    const bool hasNativeVideoStack = videoMode && hasNativeVideoStackPayload(payload);
    const QString modelValue = resolvedModelValueFromPayload(payload);

    if (videoMode)
    {
        const QString origin = payload.value(QStringLiteral("submit_origin")).toString().trimmed();
        appendLogLine(QStringLiteral("%1 submit received%2 • model=%3 • stack=%4 • workflow=%5")
                          .arg(modeId.toUpper(),
                               origin.isEmpty() ? QString() : QStringLiteral(" from %1").arg(origin),
                               modelValue.isEmpty() ? QStringLiteral("none") : QFileInfo(modelValue).fileName(),
                               hasNativeVideoStack ? QStringLiteral("yes") : QStringLiteral("no"),
                               hasWorkflowBinding ? QStringLiteral("yes") : QStringLiteral("no")));
    }

    if (modelValue.isEmpty() && !(videoMode && (hasWorkflowBinding || hasNativeVideoStack)))
    {
        const QString message = videoMode
                                    ? QStringLiteral("%1 request blocked: choose a native video model stack or open an imported workflow draft.").arg(modeId.toUpper())
                                    : QStringLiteral("%1 request blocked: choose a model first.").arg(modeId.toUpper());
        appendLogLine(message);
        page->setBusy(false, message);
        return;
    }
'''
new_binding = '''
    const bool hasWorkflowBinding = spellvision::workers::WorkerSubmissionPolicy::hasWorkflowBinding(payload);
    const bool hasNativeVideoStack = videoMode && spellvision::workers::WorkerSubmissionPolicy::hasNativeVideoStackPayload(payload);
    const QString modelValue = spellvision::workers::WorkerSubmissionPolicy::resolvedModelValueFromPayload(payload);

    if (videoMode)
    {
        appendLogLine(spellvision::workers::WorkerSubmissionPolicy::videoSubmitLogLine(
            modeId,
            payload,
            modelValue,
            hasNativeVideoStack,
            hasWorkflowBinding));
    }

    if (modelValue.isEmpty() && !(videoMode && (hasWorkflowBinding || hasNativeVideoStack)))
    {
        const QString message = spellvision::workers::WorkerSubmissionPolicy::missingModelMessage(modeId, videoMode);
        appendLogLine(message);
        page->setBusy(false, message);
        return;
    }
'''
cpp = replace_once(cpp, old_binding, new_binding, "submission policy block")

old_accept = '''
    const QString backendSummary = videoMode
                                       ? (hasWorkflowBinding ? QStringLiteral("workflow video") : QStringLiteral("native video"))
                                       : QStringLiteral("native image");
    appendLogLine(QStringLiteral("%1 request accepted: %2 • model=%3")
                      .arg(modeId.toUpper(),
                           backendSummary,
                           modelValue.isEmpty() ? QStringLiteral("workflow-bound") : QFileInfo(modelValue).fileName()));
'''
new_accept = '''
    appendLogLine(spellvision::workers::WorkerSubmissionPolicy::acceptedRequestLogLine(
        modeId,
        videoMode,
        hasWorkflowBinding,
        modelValue));
'''
cpp = replace_once(cpp, old_accept, new_accept, "accepted request log block")

main_cpp.write_text(cpp, encoding="utf-8")

cmake_text = cmake.read_text(encoding="utf-8")
if "qt_ui/workers/WorkerSubmissionPolicy.cpp" not in cmake_text:
    insert = "    qt_ui/workers/WorkerSubmissionPolicy.cpp\n    qt_ui/workers/WorkerSubmissionPolicy.h\n"
    anchor = "    qt_ui/workers/WorkerQueueController.h\n"
    if anchor not in cmake_text:
        anchor = "    qt_ui/workers/WorkerProcessController.h\n"
    if anchor not in cmake_text:
        fail("Could not find CMake worker anchor. Add WorkerSubmissionPolicy manually.")
    cmake_text = cmake_text.replace(anchor, anchor + insert, 1)
    cmake.write_text(cmake_text, encoding="utf-8")

print("[pass7] WorkerSubmissionPolicy wiring applied successfully.")
