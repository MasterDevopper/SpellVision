#pragma once

#include <QString>

namespace spellvision::shell
{

// The running app's version, as declared once in CMakeLists.txt project(VERSION).
QString appVersion();

// Numeric dotted comparison: negative when a < b, zero when equal, positive when a > b.
// Tolerates a leading "v"/"V", missing components ("1.2" == "1.2.0"), and a trailing
// pre-release suffix after "-" or "+", which is ignored. Non-numeric input compares as 0.
int compareVersions(const QString &a, const QString &b);

// Where the update check asks. GitHub Releases for this repository.
QString latestReleaseApiUrl();
QString releasesPageUrl();

} // namespace spellvision::shell
