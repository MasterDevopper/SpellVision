#pragma once

#include <QString>

namespace spellvision::shell
{

// The sentinel that marks the project root. Every copy of this search already agreed on it, which
// is the only reason they could be merged without a behaviour decision.
QString projectRootSentinel();

// Walk up from the application directory, then from the current working directory, looking for the
// sentinel. Falls back to the current working directory when neither start finds it.
//
// There were FOUR hand-written copies of this walk -- MainWindow, HomePage, ManagerPage and main.cpp's
// self-test -- and they disagreed on two axes:
//
//     MainWindow      depth 7   appDir + cwd
//     HomePage        depth 8   appDir + cwd
//     ManagerPage     depth 8   appDir only
//     main.cpp        depth 8   appDir only
//
// MainWindow searched one level SHALLOWER than every other copy, so a build laid out exactly eight
// levels below the root would have three components find the project and the fourth silently fall
// back to the working directory -- resolving python/worker_client.py, the runtime profile and every
// worker request against the wrong tree. Not reachable in the default build layout (the exe sits
// three levels down), which is why it never showed up: a latent divergence, not a live bug.
//
// The merged behaviour is the majority one: depth 8, both starts. It is a superset of all four --
// no copy searched deeper, and no copy searched a start this one does not.
QString resolveProjectRoot();

// The same walk from an explicit starting directory. Split out so tests can exercise the search on
// a fixture tree rather than on wherever the test binary happens to live.
QString resolveProjectRootFrom(const QString &startDirectory, int maxDepth = 8);

}  // namespace spellvision::shell
