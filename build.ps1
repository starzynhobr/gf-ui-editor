$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Crie o ambiente virtual antes: py -m venv .venv"
}

Push-Location $projectRoot
$originalPath = $env:PATH
try {
    # Evita que DLLs de outras ferramentas no PATH entrem no pacote Qt.
    $env:PATH = "$(Split-Path -Parent $python);$env:SystemRoot\System32;$env:SystemRoot"
    & $python -m PyInstaller --noconfirm --clean --onedir --windowed --name GF-UI-Editor --distpath dist --workpath build --specpath build packaging\launcher.py
    if ($LASTEXITCODE -ne 0) { throw "Falha ao empacotar o aplicativo." }

    $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (-not (Test-Path -LiteralPath $iscc)) {
        throw "Inno Setup não encontrado em $iscc. O aplicativo está pronto em dist\GF-UI-Editor."
    }
    & $iscc packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o instalador." }
} finally {
    $env:PATH = $originalPath
    Pop-Location
}
