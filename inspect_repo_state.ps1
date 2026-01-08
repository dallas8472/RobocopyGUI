Set-StrictMode -Version Latest
$repo='C:\Users\holger.buchfeld\Documents\RobocopyGUI'
Set-Location $repo
Write-Host "PWD: $(Get-Location).Path"
Write-Host "\nGIT STATUS:"
git status --short --branch
Write-Host "\nLAST 5 COMMITS:"
git log -5 --oneline --decorate
Write-Host "\nWORKSPACE FILES (top-level):"
Get-ChildItem -Force -Name | Sort-Object | ForEach-Object { Write-Host ' - ' $_ }
Write-Host "\nHEAD TREE (tracked files):"
git ls-tree -r --name-only HEAD | ForEach-Object { Write-Host ' - ' $_ }
Write-Host "\nCHECK COMMON PATHS:"
$paths=@('dist','build','RobocopyGUI.spec','robocopygui_selfsigned_new.pfx','robocopygui_selfsigned.pfx')
foreach ($p in $paths) { Write-Host "$p -> " (Test-Path $p) }
Write-Host "\nREMOTE INFO:"
git remote -v
try { git rev-parse origin/master; } catch { Write-Host 'origin/master not found locally' }
Write-Host "\nGitHub root contents via gh API (if available):"
if (Get-Command gh -ErrorAction SilentlyContinue) {
    try {
        gh api repos/dallas8472/RobocopyGUI/contents -q '.[].name' | ForEach-Object { Write-Host ' - ' $_ }
    } catch {
        Write-Host 'gh API call failed or repo not accessible.'
    }
} else {
    Write-Host 'gh CLI not available'
}
