$base = "C:\Users\UseR\AppData\Roaming\MetaQuotes\Terminal\FA97EA291D4188820508F9D2B5AAD50F\MQL5\Files\PythonProjects\StrategyCloud"
$scriptPath = Join-Path $base "syntax_check.py"
$outputFile = Join-Path $base "check_output.txt"

$pythonExe = $null

$locations = @(
    "C:\Users\UseR\AppData\Local\Programs\Python\Python311\python.exe",
    "C:\Users\UseR\AppData\Local\Programs\Python\Python310\python.exe",
    "C:\Users\UseR\AppData\Local\Programs\Python\Python39\python.exe",
    "C:\Users\UseR\AppData\Local\Programs\Python\Python38\python.exe",
    "C:\Python39\python.exe",
    "C:\Python38\python.exe",
    "C:\Python311\python.exe",
    "C:\Python310\python.exe"
)

foreach ($loc in $locations) {
    if (Test-Path $loc) {
        $pythonExe = $loc
        Write-Host "Found Python at: $loc"
        break
    }
}

if (-not $pythonExe) {
    if (Test-Path "C:\Windows\py.exe") {
        $pythonExe = "C:\Windows\py.exe"
        Write-Host "Using py launcher"
    }
}

if (-not $pythonExe) {
    Write-Host "ERROR: Python not found"
    exit 1
}

& $pythonExe $scriptPath 2>&1 | Tee-Object -FilePath $outputFile
