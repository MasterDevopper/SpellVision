# Point git at the repo's versioned hooks.
#
# .git/hooks is not versioned, so a hook written there exists on one machine and nowhere else.
# core.hooksPath makes .githooks/ the source of truth, so the hook is reviewed, diffed and shared
# like any other file in the repo.
#
# Usage:  .\scripts\dev\install_hooks.ps1
#         .\scripts\dev\install_hooks.ps1 -Uninstall

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$repoRoot = (git rev-parse --show-toplevel)
if (-not $repoRoot) { throw "Not inside a git repository." }
Set-Location $repoRoot

if ($Uninstall) {
    git config --unset core.hooksPath
    Write-Host "==> Hooks uninstalled (core.hooksPath cleared)."
    exit 0
}

git config core.hooksPath .githooks
Write-Host "==> core.hooksPath = .githooks"

# Git for Windows runs hooks through its bundled bash and does not require the executable bit, but
# setting it keeps the file usable on a Linux checkout too.
git update-index --chmod=+x .githooks/pre-commit 2>$null

Write-Host ""
Write-Host "The pre-commit hook runs the tree-wide ratchets (~5s). It does NOT run the full suite --"
Write-Host "CI does that. Bypass a single commit with:  git commit --no-verify"
