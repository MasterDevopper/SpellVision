from pathlib import Path
import re

path = Path("qt_ui/workers/WorkerSubmissionPolicy.cpp")
text = path.read_text(encoding="utf-8")

pattern = re.compile(
    r'\s*const QString route = payload\.value\(QStringLiteral\("video_backend_route"\)\).*?'
    r'const QString backendSummary = videoMode\s*'
    r'\? \(promptApiVideo.*?QStringLiteral\("native image"\);',
    re.DOTALL,
)

replacement = '''
    // Sprint 15C Pass 29F repair:
    // acceptedRequestLogLine() does not receive the full payload, so it cannot
    // inspect video_backend_route here. Keep the route enforcement in
    // GenerationRequestBuilder and make this display helper payload-free.
    const QString normalizedModel = modelValue.trimmed().toLower();
    const bool likelyLtxPromptApiVideo =
        videoMode && normalizedModel.contains(QStringLiteral("ltx"));

    const QString backendSummary = videoMode
                                       ? (likelyLtxPromptApiVideo
                                              ? QStringLiteral("Prompt API video")
                                              : (hasWorkflowBinding ? QStringLiteral("workflow video") : QStringLiteral("native video")))
                                       : QStringLiteral("native image");'''

text, count = pattern.subn(replacement, text, count=1)

if count != 1:
    raise SystemExit("Could not repair WorkerSubmissionPolicy.cpp payload logging block.")

path.write_text(text, encoding="utf-8")

print("Repaired Pass 29F WorkerSubmissionPolicy payload compile issue.")
