# =============================================================================
# SpellVision repo cleanup
# =============================================================================
# One-shot migration. Run ONCE from the repo root, with a clean working tree.
#
# What this does (in order):
#   1. Verifies preconditions (right directory, clean working tree).
#   2. Creates attic/ subdirectories for archived material.
#   3. Moves the apply_*/repair_*/promote_* scripts from repo root to attic/.
#   4. Moves the SPRINT*/Sprint*/Manager*/README_* sprint-pass docs to attic/.
#   5. Moves CMakeLists.txt.pre_*.bak backups to attic/.
#   6. Moves rust/ to attic/rust_original_intent/ (preserves history).
#   7. Moves debug dumps (panel_dump.txt, pass*_*.json, etc.) to attic/.
#   8. Moves zip archives at repo root to attic/.
#   9. Moves applied patch files (already in git history) to attic/.
#  10. Moves stray .bak files in python/ and qt_ui/ to attic/.
#  11. Untracks files that should be ignored going forward (Screenshots/,
#      output/, hf_cache/, models/) without deleting them from disk.
#
# All moves use `git mv` so blame and history are preserved. Files moved to
# attic/ stay in the repo (for searchability) but are clearly out of the way.
#
# Safe to inspect before running: every step prints what it does, and the
# preflight refuses to run if the working tree isn't clean.
# =============================================================================

$ErrorActionPreference = 'Stop'

# --- Preflight ---------------------------------------------------------------

if (-not (Test-Path 'CMakeLists.txt') -or -not (Test-Path 'python/worker_service.py')) {
    Write-Error 'Must be run from the SpellVision repo root (CMakeLists.txt and python/worker_service.py not found here).'
    exit 1
}

$dirty = git status --porcelain
if ($dirty) {
    Write-Error 'Working tree is not clean. Commit or stash before running cleanup.ps1.'
    Write-Host $dirty
    exit 1
}

Write-Host 'Preflight OK. Beginning cleanup.' -ForegroundColor Green
Write-Host ''

# --- Helpers -----------------------------------------------------------------

function New-AtticDir {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
        Write-Host "  created: $Path"
    }
}

function Move-WithGit {
    param([string]$From, [string]$ToDir)
    if (-not (Test-Path $From)) { return }
    & git mv -- $From "$ToDir/" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "  git mv failed: $From -> $ToDir/ (skipped)"
    } else {
        Write-Host "  moved: $From"
    }
}

# --- Create attic structure --------------------------------------------------

Write-Host 'Creating attic/ subdirectories...' -ForegroundColor Cyan
$atticDirs = @(
    'attic',
    'attic/apply_scripts',
    'attic/sprint_passes',
    'attic/cmake_backups',
    'attic/debug_dumps',
    'attic/old_archives',
    'attic/applied_patches',
    'attic/code_backups'
)
foreach ($d in $atticDirs) { New-AtticDir $d }
Write-Host ''

# --- 1. apply_/repair_/promote_ scripts at repo root --------------------------

Write-Host 'Moving apply_*/repair_*/promote_* scripts (root only) to attic/apply_scripts/...' -ForegroundColor Cyan
Get-ChildItem -File -Path . -Filter '*.py' | Where-Object {
    $_.Name -match '^(apply_|repair_|promote_)'
} | ForEach-Object {
    Move-WithGit $_.Name 'attic/apply_scripts'
}
Get-ChildItem -File -Path . -Filter '*.ps1' | Where-Object {
    $_.Name -match '^(apply_|repair_)'
} | ForEach-Object {
    Move-WithGit $_.Name 'attic/apply_scripts'
}
Write-Host ''

# --- 2. Sprint pass README files at root --------------------------------------

Write-Host 'Moving sprint pass READMEs to attic/sprint_passes/...' -ForegroundColor Cyan
Get-ChildItem -File -Path . -Filter '*.md' | Where-Object {
    $_.Name -match '^(SPRINT|Sprint|Manager_Cache|README_APPLY|README_T2V)'
} | ForEach-Object {
    Move-WithGit $_.Name 'attic/sprint_passes'
}
Write-Host ''

# --- 3. CMakeLists backups at root --------------------------------------------

Write-Host 'Moving CMakeLists.txt.pre_*.bak files to attic/cmake_backups/...' -ForegroundColor Cyan
Get-ChildItem -File -Path . -Filter 'CMakeLists.txt.*.bak' | ForEach-Object {
    Move-WithGit $_.Name 'attic/cmake_backups'
}
Write-Host ''

# --- 4. rust/ directory -------------------------------------------------------

if (Test-Path 'rust') {
    Write-Host 'Moving rust/ to attic/rust_original_intent/...' -ForegroundColor Cyan
    & git mv -- 'rust' 'attic/rust_original_intent' 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning '  git mv rust failed'
    } else {
        Write-Host '  moved: rust/'
    }
    Write-Host ''
}

# --- 5. Debug dumps at root ---------------------------------------------------

Write-Host 'Moving debug dumps to attic/debug_dumps/...' -ForegroundColor Cyan
$debugFiles = @('panel_dump.txt', 'wan_node_object_info.json')
Get-ChildItem -File -Path . -Filter 'pass*_*.json' | ForEach-Object {
    $debugFiles += $_.Name
}
foreach ($f in ($debugFiles | Sort-Object -Unique)) {
    Move-WithGit $f 'attic/debug_dumps'
}
Write-Host ''

# --- 6. ZIP archives at root --------------------------------------------------

Write-Host 'Moving .zip archives to attic/old_archives/...' -ForegroundColor Cyan
Get-ChildItem -File -Path . -Filter '*.zip' | ForEach-Object {
    Move-WithGit $_.Name 'attic/old_archives'
}
Write-Host ''

# --- 7. Applied patches at root -----------------------------------------------

Write-Host 'Moving .patch files (already applied) to attic/applied_patches/...' -ForegroundColor Cyan
Get-ChildItem -File -Path . -Filter '*.patch' | ForEach-Object {
    Move-WithGit $_.Name 'attic/applied_patches'
}
Write-Host ''

# --- 8. Stray .bak files inside python/ and qt_ui/ ----------------------------

Write-Host 'Moving stray .bak files from python/ and qt_ui/ to attic/code_backups/...' -ForegroundColor Cyan
foreach ($scope in @('python', 'qt_ui')) {
    if (Test-Path $scope) {
        Get-ChildItem -File -Path $scope -Recurse -Filter '*.bak' | ForEach-Object {
            # Use the file's path relative to repo root.
            $rel = Resolve-Path -Relative $_.FullName
            $rel = $rel -replace '\\', '/' -replace '^\./', ''
            Move-WithGit $rel 'attic/code_backups'
        }
    }
}
Write-Host ''

# --- 9. Untrack tracked-but-should-be-ignored content -------------------------

Write-Host 'Untracking files now covered by .gitignore (files remain on disk)...' -ForegroundColor Cyan
foreach ($pattern in @('Screenshots', 'output', 'hf_cache', 'models', '_sv_patch', '.local_wip', '.venv_old', 'build-vscode')) {
    if (Test-Path $pattern) {
        # Check if anything is actually tracked at this path before running rm.
        $tracked = git ls-files $pattern 2>$null
        if ($tracked) {
            & git rm -r --cached -- $pattern 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  untracked: $pattern (kept on disk)"
            } else {
                Write-Warning "  git rm --cached failed for $pattern"
            }
        }
    }
}
Write-Host ''

# --- Summary ------------------------------------------------------------------

Write-Host 'Cleanup complete.' -ForegroundColor Green
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. Inspect the staged changes:    git status'
Write-Host '  2. Diff a few moves if you want:  git diff --cached --stat'
Write-Host '  3. Run the test suite to confirm: pytest tests/'
Write-Host '  4. Commit when satisfied:'
Write-Host '       git commit -m "Archive historical scripts, sprint docs, and code backups to attic/"'
Write-Host ''
Write-Host 'To undo before committing:  git reset --hard HEAD'
