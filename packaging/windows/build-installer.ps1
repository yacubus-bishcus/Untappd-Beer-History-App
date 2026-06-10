param(
    [string]$Python = "py",
    [string]$PythonVersion = "",
    [string]$InnoCompiler = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvDir = Join-Path $RepoRoot ".windows-build-venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$SpecPath = Join-Path $PSScriptRoot "UntappdBeerHistory.spec"
$InnoScript = Join-Path $PSScriptRoot "UntappdBeerHistory.iss"

function Resolve-InnoCompiler {
    param([string]$RequestedPath)

    if ($RequestedPath) {
        if (-not (Test-Path $RequestedPath)) {
            throw "Inno Setup compiler not found at '$RequestedPath'."
        }
        return (Resolve-Path $RequestedPath).Path
    }

    $Command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }

    $Candidates = @()
    foreach ($Root in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
        if ($Root) {
            $Candidates += Join-Path $Root "Inno Setup 6\ISCC.exe"
        }
    }

    foreach ($Candidate in $Candidates) {
        if (Test-Path $Candidate) {
            return (Resolve-Path $Candidate).Path
        }
    }

    throw "Inno Setup 6 compiler was not found. Install Inno Setup or pass -InnoCompiler C:\Path\To\ISCC.exe."
}

Push-Location $RepoRoot
try {
    $PythonArgs = @()
    if ($PythonVersion.Trim()) {
        $PythonArgs += $PythonVersion
    }

    $PythonVersionInfo = (& $Python @PythonArgs -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Could not run the requested Python interpreter."
    }
    $PythonVersionParts = $PythonVersionInfo.Split(".")
    if (
        [int]$PythonVersionParts[0] -lt 3 -or
        ([int]$PythonVersionParts[0] -eq 3 -and [int]$PythonVersionParts[1] -lt 12)
    ) {
        throw "Windows packaging requires Python 3.12 or newer; found Python $PythonVersionInfo."
    }
    Write-Host "Using Python $PythonVersionInfo for the Windows build."

    if (-not (Test-Path $VenvPython)) {
        & $Python @PythonArgs -m venv $VenvDir
    }

    $VenvVersionInfo = (& $VenvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    $VenvVersionParts = $VenvVersionInfo.Split(".")
    if (
        [int]$VenvVersionParts[0] -lt 3 -or
        ([int]$VenvVersionParts[0] -eq 3 -and [int]$VenvVersionParts[1] -lt 12)
    ) {
        throw "The existing build environment uses Python $VenvVersionInfo. Delete '$VenvDir' and rerun with Python 3.12 or newer."
    }

    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r (Join-Path $RepoRoot "src\requirements.txt") -r (Join-Path $PSScriptRoot "requirements-build.txt")

    $AppVersion = (& $VenvPython -c "import pathlib, tomllib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])").Trim()

    & $VenvPython -m PyInstaller --clean --noconfirm $SpecPath

    $Iscc = Resolve-InnoCompiler $InnoCompiler
    Push-Location $PSScriptRoot
    try {
        & $Iscc "/DAppVersion=$AppVersion" $InnoScript
    }
    finally {
        Pop-Location
    }

    Write-Host ""
    Write-Host "Built installer:" -ForegroundColor Green
    Write-Host "  $(Join-Path $RepoRoot "dist\installer\Untappd-Beer-History-Setup-$AppVersion.exe")"
}
finally {
    Pop-Location
}
