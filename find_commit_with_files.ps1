Set-StrictMode -Version Latest
Set-Location 'C:\Users\holger.buchfeld\Documents\RobocopyGUI'
$commits = git rev-list --all
$commits = $commits -split "\n" | Where-Object {$_ -ne ""}
Write-Host "Total commits: $($commits.Count)"
foreach ($c in $commits) {
    $files = git ls-tree -r --name-only $c
    if ($files -and $files.Trim() -ne "") {
        Write-Host "Commit with files: $c"
        $files -split "\n" | Select-Object -First 30 | ForEach-Object { Write-Host " - $_" }
        break
    }
}
