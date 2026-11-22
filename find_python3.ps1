$output = @()

# Get Python install paths from registry
$versions = @("3.11", "3.12", "3.14")

foreach ($ver in $versions) {
    try {
        $regPath = "HKCU:\Software\Python\PythonCore\$ver\InstallPath"
        if (Test-Path $regPath) {
            $installPath = Get-ItemProperty $regPath -ErrorAction SilentlyContinue
            if ($installPath) {
                $exePath = Join-Path $installPath.InstallPath "python.exe"
                if (Test-Path $exePath) {
                    $output += "FOUND: $exePath"
                } else {
                    $output += "NOT FOUND: $exePath"
                }
            }
        }
    } catch {
        $msg = "Error checking " + $ver + ": " + $_.Exception.Message
        $output += $msg
    }
}

# Also check the Programs directory
$programsDir = "C:\Users\UseR\AppData\Local\Programs\Python"
if (Test-Path $programsDir) {
    Get-ChildItem $programsDir -Directory | ForEach-Object {
        $exePath = Join-Path $_.FullName "python.exe"
        if (Test-Path $exePath) {
            $output += "FOUND: $exePath"
        } else {
            $output += "NOT FOUND: $exePath"
        }
    }
}

# Write to file
$output | Out-File -FilePath "python_paths.txt" -Encoding UTF8
