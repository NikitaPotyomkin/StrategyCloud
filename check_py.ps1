$py = Get-Item 'C:\Windows\py.exe' -ErrorAction SilentlyContinue
if ($py) {
    Write-Host "py.exe exists"
    Write-Host "FullName: $($py.FullName)"
    $ver = $py.VersionInfo
    Write-Host "Version: $($ver.FileVersion)"
} else {
    Write-Host "py.exe not found"
}
