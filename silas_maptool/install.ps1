$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { 'python' }
& $Python -m venv (Join-Path $Root '.venv')
$Py = Join-Path $Root '.venv\Scripts\python.exe'
$Wheelhouse = Join-Path $Root 'wheelhouse'
$Dist = Join-Path $Root 'dist'
$LinkDirs = @($Wheelhouse, $Dist) + @(Get-ChildItem -Path $Dist -Directory -Recurse -ErrorAction SilentlyContinue | ForEach-Object FullName)
$LinkDirs = @($LinkDirs | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -Unique)
if (-not $LinkDirs) { throw 'No wheelhouse/ or dist/ directory found. Download a release wheel; users do not need MSVC.' }
$PickDir = Join-Path $Root '.venv\wheel-select'
New-Item -ItemType Directory -Force -Path $PickDir | Out-Null
Get-ChildItem -LiteralPath $PickDir -Filter 'silas_maptool-*.whl' -ErrorAction SilentlyContinue | Remove-Item -Force
$FindArgs = @()
foreach ($Dir in $LinkDirs) { $FindArgs += @('--find-links', $Dir) }
& $Py -m pip download --no-deps --no-index @FindArgs --dest $PickDir silas-maptool
$Wheels = @(Get-ChildItem -LiteralPath $PickDir -Filter 'silas_maptool-*.whl')
if ($Wheels.Count -ne 1) { throw "Expected one compatible silas-maptool wheel, found $($Wheels.Count)." }
$Wheel = $Wheels[0]
$Original = Get-ChildItem -Path $Wheelhouse,$Dist -Filter $Wheel.Name -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($Original -and $Original.FullName.StartsWith($Wheelhouse, [System.StringComparison]::OrdinalIgnoreCase)) {
  & $Py -m pip install --no-index --find-links $Wheelhouse $Wheel.FullName
} else {
  & $Py -m pip install $Wheel.FullName
}
& $Py -m silas_maptool doctor --json
