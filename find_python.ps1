$found = Get-ChildItem C:\ -Filter python.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 5 FullName
foreach ($f in $found) {
    Write-Host $f
}
if (-not $found) {
    Write-Host "No python.exe found"
}
