$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$iconPng = Join-Path $projectRoot "src\gf_ui_editor\assets\app-icon.png"
$translations = Join-Path $projectRoot "src\gf_ui_editor\translations"
$iconIco = Join-Path $projectRoot "packaging\app-icon.ico"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Crie o ambiente virtual antes: py -m venv .venv"
}

Push-Location $projectRoot
$originalPath = $env:PATH
try {
    # Evita que DLLs de outras ferramentas no PATH entrem no pacote Qt.
    $env:PATH = "$(Split-Path -Parent $python);$env:SystemRoot\System32;$env:SystemRoot"
    $appVersion = & $python -c "from gf_ui_editor import __version__; print(__version__)"
    if ($LASTEXITCODE -ne 0 -or -not $appVersion) { throw "Falha ao ler a versão do aplicativo." }
    & (Join-Path $projectRoot "translations.ps1")
    & $python -m PyInstaller --noconfirm --clean --onedir --windowed --name GF-UI-Editor --icon $iconIco --add-data "$iconPng;gf_ui_editor\assets" --add-data "$translations;gf_ui_editor\translations" --distpath dist --workpath build --specpath build packaging\launcher.py
    if ($LASTEXITCODE -ne 0) { throw "Falha ao empacotar o aplicativo." }

    $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (-not (Test-Path -LiteralPath $iscc)) {
        throw "Inno Setup não encontrado em $iscc. O aplicativo está pronto em dist\GF-UI-Editor."
    }
    & $iscc "-dAppVersion=$appVersion" packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o instalador." }
} finally {
    $env:PATH = $originalPath
    Pop-Location
}
