"""Five copies of one search, and a name-keyed grep could only ever have found four.

"Find the project root" -- climb from a starting directory until ``python/worker_client.py``
appears -- was written by hand five times:

    MainWindow::resolveProjectRoot            depth 7   appDir, then cwd
    HomePage::resolveProjectRoot (free)       depth 8   appDir, then cwd
    ManagerPage::resolveProjectRoot           depth 8   appDir only
    main.cpp resolveProjectRootForSelfTest    depth 8   appDir only
    T2VHistoryPage spellVisionRepoRootForWorkerClient   cwd exact, then appDir, depth 8

All five agreed on the sentinel, which is the only reason they could be merged without a behaviour
decision. They agreed on nothing else. **MainWindow searched one level shallower than every other
copy**, so a build laid out exactly eight levels below the root would have had four components find
the project and MainWindow fall back to ``QDir::currentPath()`` -- then resolve the worker script,
the runtime profile, the Python executable and every generation request against whatever directory
the app started in, with no error, because the fallback is a valid path. Not reachable in the
default build layout, which is precisely why it survived: the reason it never fired is a property of
the build directory, not of the code.

The fifth copy is the point of this file. Grepping for ``resolveProjectRoot`` finds four. The fifth
is called ``spellVisionRepoRootForWorkerClient`` and shares no substring with the others, so no
name-keyed search could reach it. The sweep found it by what it DOES.

The rule's own first version reported three sites where one was real -- MainWindow also climbs
looking for ``qt_ui/icons`` during a Debug run, and WorkflowLibraryPage climbs three levels to derive
the Comfy root from its workflows directory. Neither is a project-root search; both merely share a
file with one. Both numbers are recorded here, the way Doc 53 records R7's 30-against-10.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from sweeps import rules, sources  # noqa: E402

RULE = [r for r in rules.ALL_RULES if r.name == "one-project-root-resolver"][0]
FAKE = sources.ROOT / "qt_ui" / "Fake.cpp"

# The body as MainWindow carried it, verbatim, including the 7 that made it the outlier.
OLD_MAINWINDOW = """    const QStringList starts = {QCoreApplication::applicationDirPath(), QDir::currentPath()};
    for (const QString &start : starts)
    {
        QDir dir(start);
        for (int depth = 0; depth < 7; ++depth)
        {
            if (QFileInfo::exists(dir.filePath(QStringLiteral("python/worker_client.py"))))
                return dir.absolutePath();
            if (!dir.cdUp())
                break;
        }
    }
    return QDir::currentPath();"""

# The one a name-keyed grep could not find.
OLD_T2V_HISTORY = """    const QString current = QDir::currentPath();
    if (QFileInfo::exists(QDir(current).filePath(QStringLiteral("python/worker_client.py"))))
        return current;

    QDir appDir(QCoreApplication::applicationDirPath());
    for (int i = 0; i < 8; ++i)
    {
        if (QFileInfo::exists(appDir.filePath(QStringLiteral("python/worker_client.py"))))
            return appDir.absolutePath();

        if (!appDir.cdUp())
            break;
    }
    return current;"""


# --- the tree is clean -------------------------------------------------------------------------

def test_no_file_re_implements_the_search() -> None:
    violations = RULE.run()
    assert not violations, [str(v) for v in violations]


def test_the_resolver_is_recognised_by_what_it_declares_not_by_its_path() -> None:
    """Keyed on the two names that make up its contract, so moving or renaming the file does not
    silently switch the rule off -- the failure mode of every ratchet this audit re-scoped."""
    resolver = sources.ROOT / "qt_ui/shell/ProjectRoot.cpp"
    assert not rules._check_project_root_resolver(resolver, resolver.read_text(encoding="utf-8"))
    disguised = resolver.read_text(encoding="utf-8")
    assert not rules._check_project_root_resolver(sources.ROOT / "qt_ui/Elsewhere.cpp", disguised)


# --- the rule fires on what it was written for ---------------------------------------------------

@pytest.mark.parametrize("name,body", [
    ("MainWindow (the depth-7 outlier)", OLD_MAINWINDOW),
    ("T2VHistoryPage (the one grep missed)", OLD_T2V_HISTORY),
])
def test_the_rule_fires_on_each_copy_it_replaced(name: str, body: str) -> None:
    """A guard nobody has watched fail is a guess about what it does. This rule's first version was
    silently broken -- a mangled word-boundary escape left a literal backspace in the pattern, so it
    matched nothing and reported a clean tree. It looked exactly like success."""
    assert rules._check_project_root_resolver(FAKE, body), name


def test_a_pattern_that_matches_nothing_is_not_a_clean_tree() -> None:
    """The specific failure above, pinned: the compiled pattern must still match an ordinary call."""
    assert rules._ROOT_WALK.search("if (!dir.cdUp())")
    assert rules._ROOT_SENTINEL.search('QStringLiteral("python/worker_client.py")')


# --- and stays quiet on what it is not for -------------------------------------------------------

def test_naming_the_worker_script_is_not_re_implementing_the_search() -> None:
    """Every caller that runs the worker names this file. Flagging them would make the rule noise."""
    assert not rules._check_project_root_resolver(
        FAKE, 'const QString c = QDir(root).filePath(QStringLiteral("python/worker_client.py"));')


def test_climbing_for_something_else_is_not_this_search() -> None:
    assert not rules._check_project_root_resolver(
        FAKE, 'while (d.cdUp()) { if (QDir(d.filePath("qt_ui/icons")).exists()) return d; }')


def test_the_over_count_the_proximity_scope_removed() -> None:
    """The rule's first version asked whether a file mentioned the sentinel ANYWHERE and climbed
    ANYWHERE. Three sites, one real. MainWindow's icons walk and WorkflowLibraryPage's three-level
    climb to the Comfy root are the two it wrongly claimed -- kept here as the shape, because a rule
    with two false positives per true one gets bypassed and then protects nothing."""
    icons_walk_far_from_a_sentinel = (
        'QStringLiteral("python/worker_client.py");\n' + "\n" * 30
        + 'QDir climb(appDir);\n while (climb.cdUp()) {}'
    )
    assert not rules._check_project_root_resolver(FAKE, icons_walk_far_from_a_sentinel)


def test_the_proximity_window_is_wide_enough_for_a_real_copy() -> None:
    """Set against the copies, not chosen round: all five tested the sentinel inside the loop that
    climbs, so they span a handful of lines. Too tight and the rule misses a copy written with more
    whitespace, which is the same silent under-report as the broken pattern."""
    assert rules._ROOT_PROXIMITY_LINES >= 8
    spread = OLD_MAINWINDOW.replace("            if (!dir.cdUp())", "\n\n            if (!dir.cdUp())")
    assert rules._check_project_root_resolver(FAKE, spread)
