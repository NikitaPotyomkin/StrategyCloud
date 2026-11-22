$output = @()

# Check common Python locations
$locations = @(
    "C:\Users\UseR\AppData\Local\Programs\Python",
    "C:\Python39",
    "C:\Python38",
    "C:\Python311",
    "C:\Python310",
    "C:\Program Files\Python39",
    "C:\Program Files\Python38",
    "C:\Program Files\Python311",
    "C:\Program Files\Python310",
    "C:\Program Files (x86)\Python39",
    "C:\Program Files (x86)\Python38",
    "C:\Program Files (x86)\Python311",
    "C:\Program Files (x86)\Python310"
)

foreach ($loc in $locations) {
    if (Test-Path $loc) {
        $output += "FOUND: $loc"
    } else {
        $output += "NOT FOUND: $loc"
    }
}

# Check registry
try {
    $regKey = "HKCU:\Software\Python\PythonCore"
    if (Test-Path $regKey) {
        $output += "Registry key exists: $regKey"
        Get-ChildItem $regKey -ErrorAction SilentlyContinue | ForEach-Object {
            $output += "  Version: $($_.Name)"
        }
    } else {
        $output += "Registry key NOT found: HKCU:\Software\Python\PythonCore"
    }
} catch {
    $output += "Registry check error: $_"
}

# Check PATH
$pathEnv = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($pathEnv -and $pathEnv -match "python") {
    $output += "PATH contains python"
} else {
    $output += "PATH does NOT contain python"
}

# Write to file
$output | Out-File -FilePath "python_locations.txt" -Encoding UTF8
