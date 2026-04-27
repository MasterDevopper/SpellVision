from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
main_cpp = ROOT / "qt_ui" / "MainWindow.cpp"
cmake = ROOT / "CMakeLists.txt"


def fail(message: str) -> None:
    raise SystemExit(f"[pass7-fix] {message}")

if not main_cpp.exists():
    fail(f"Missing {main_cpp}")

cpp = main_cpp.read_text(encoding="utf-8")

if '#include "workers/WorkerSubmissionPolicy.h"' not in cpp:
    if '#include "workers/WorkerQueueController.h"\n' in cpp:
        cpp = cpp.replace(
            '#include "workers/WorkerQueueController.h"\n',
            '#include "workers/WorkerQueueController.h"\n#include "workers/WorkerSubmissionPolicy.h"\n',
            1,
        )
    elif '#include "workers/WorkerProcessController.h"\n' in cpp:
        cpp = cpp.replace(
            '#include "workers/WorkerProcessController.h"\n',
            '#include "workers/WorkerProcessController.h"\n#include "workers/WorkerSubmissionPolicy.h"\n',
            1,
        )
    else:
        fail("Could not find worker include anchor in MainWindow.cpp")

# Pass 7 extracted helpers but one or more call sites may remain unqualified.
# Qualify only unqualified MainWindow call sites; already-qualified calls are left unchanged.
replacements = {
    r'(?<!WorkerSubmissionPolicy::)\bresolvedModelValueFromPayload\(': 'spellvision::workers::WorkerSubmissionPolicy::resolvedModelValueFromPayload(',
    r'(?<!WorkerSubmissionPolicy::)\bhasNativeVideoStackPayload\(': 'spellvision::workers::WorkerSubmissionPolicy::hasNativeVideoStackPayload(',
    r'(?<!WorkerSubmissionPolicy::)\bhasWorkflowBinding\(': 'spellvision::workers::WorkerSubmissionPolicy::hasWorkflowBinding(',
    r'(?<!WorkerSubmissionPolicy::)\bvideoSubmitLogLine\(': 'spellvision::workers::WorkerSubmissionPolicy::videoSubmitLogLine(',
    r'(?<!WorkerSubmissionPolicy::)\bmissingModelMessage\(': 'spellvision::workers::WorkerSubmissionPolicy::missingModelMessage(',
    r'(?<!WorkerSubmissionPolicy::)\bacceptedRequestLogLine\(': 'spellvision::workers::WorkerSubmissionPolicy::acceptedRequestLogLine(',
}

change_count = 0
for pattern, replacement in replacements.items():
    cpp, count = re.subn(pattern, replacement, cpp)
    change_count += count

# Collapse accidental double qualifications if this script is run more than once after manual edits.
double = 'spellvision::workers::WorkerSubmissionPolicy::spellvision::workers::WorkerSubmissionPolicy::'
while double in cpp:
    cpp = cpp.replace(double, 'spellvision::workers::WorkerSubmissionPolicy::')

main_cpp.write_text(cpp, encoding="utf-8")

if cmake.exists():
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

print(f"[pass7-fix] Qualified {change_count} leftover WorkerSubmissionPolicy call site(s).")
