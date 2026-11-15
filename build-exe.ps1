[CmdletBinding()]
param([string]$Python, [string]$Wheelhouse)
$ErrorActionPreference = 'Stop'

function Invoke-Checked($Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Build command failed: $Executable (exit $LASTEXITCODE)" }
}

Push-Location $PSScriptRoot
$previousBuildMode = $env:DIDBAN_STATIC_BUILD
$previousBrowsersPath = $env:PLAYWRIGHT_BROWSERS_PATH
try {
    if (-not $Python) {
        $venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
        $Python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { 'python' }
    }
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    $work = Join-Path $PSScriptRoot 'build\windows'
    $dist = Join-Path $PSScriptRoot 'dist'
    $frontendBuild = Join-Path $work ('frontend-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $work, $dist -Force | Out-Null

    $pipArgs = @('-m', 'pip', 'install', '--timeout', '15', '--retries', '1', '-r', 'requirements.txt', 'pyinstaller')
    if ($Wheelhouse) { $pipArgs += @('--no-index', '--find-links', $Wheelhouse) }
    Invoke-Checked $Python $pipArgs
    New-Item -ItemType Directory -Path $frontendBuild | Out-Null
    foreach ($item in @('app', 'public', 'package.json', 'package-lock.json', 'next.config.ts', 'tsconfig.json')) {
        $source = Join-Path 'frontend' $item
        if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $frontendBuild -Recurse }
    }
    Invoke-Checked $npm @('--prefix', $frontendBuild, 'ci')
    $env:DIDBAN_STATIC_BUILD = '1'
    Invoke-Checked $npm @('--prefix', $frontendBuild, 'run', 'build')

    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $work 'chromium'
    Invoke-Checked $Python @('-m', 'playwright', 'install', '--no-shell', 'chromium')
    Invoke-Checked $Python @(
        '-m', 'PyInstaller', '--noconfirm', '--onefile', '--name', 'Didban',
        '--workpath', $work, '--specpath', $work, '--distpath', $dist,
        '--add-data', "$(Join-Path $frontendBuild 'out');dashboard",
        '--add-data', "$env:PLAYWRIGHT_BROWSERS_PATH;chromium",
        '--collect-all', 'tzdata',
        '--hidden-import', 'uvicorn.loops.asyncio',
        '--hidden-import', 'uvicorn.protocols.http.h11_impl',
        'desktop.py'
    )
    Write-Host "Built: $(Join-Path $dist 'Didban.exe')"
} finally {
    $env:DIDBAN_STATIC_BUILD = $previousBuildMode
    $env:PLAYWRIGHT_BROWSERS_PATH = $previousBrowsersPath
    Pop-Location
    if ($frontendBuild -and (Test-Path -LiteralPath $frontendBuild)) {
        $stagedPath = (Resolve-Path -LiteralPath $frontendBuild).Path
        $workPath = (Resolve-Path -LiteralPath $work).Path
        if ([IO.Path]::GetDirectoryName($stagedPath) -eq $workPath) {
            Remove-Item -LiteralPath $stagedPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
