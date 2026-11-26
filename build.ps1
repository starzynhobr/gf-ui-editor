$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$iconPng = Join-Path $projectRoot "src\gf_ui_editor\assets\app-icon.png"
$translations = Join-Path $projectRoot "src\gf_ui_editor\translations"
$releaseNotes = Join-Path $projectRoot "src\gf_ui_editor\assets\release-notes.json"
$contributors = Join-Path $projectRoot "src\gf_ui_editor\assets\contributors.json"
$stzLogo = Join-Path $projectRoot "src\gf_ui_editor\assets\stz-labs.svg"
$stzMark = Join-Path $projectRoot "src\gf_ui_editor\assets\stz-mark.svg"
$fonts = Join-Path $projectRoot "src\gf_ui_editor\assets\fonts"
$backgrounds = Join-Path $projectRoot "src\gf_ui_editor\assets\backgrounds"
$iconIco =Join-Path $projectRoot "packaging\app-icon.ico"
$webDir = Join-Path $projectRoot "web"
$webDist = Join-Path $projectRoot "src\gf_ui_editor\web_dist"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Crie o ambiente virtual antes: py -m venv .venv"
}

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) { throw "Node.js/npm não encontrado: necessário para compilar a interface nova (web\)." }
Push-Location $projectRoot
$originalPath = $env:PATH
try {
    # Evita que DLLs de outras ferramentas no PATH entrem no pacote Qt.
    $env:PATH = "$(Split-Path -Parent $python);$env:SystemRoot\System32;$env:SystemRoot"
    # Worktrees reuse the main venv, whose editable install points at another checkout: this one wins.
    $env:PYTHONPATH = Join-Path $projectRoot "src"
    $appVersion = & $python -c "from gf_ui_editor import __version__; print(__version__)"
    if ($LASTEXITCODE -ne 0 -or -not $appVersion) { throw "Falha ao ler a versão do aplicativo." }
    & (Join-Path $projectRoot "translations.ps1")
    # Interface nova: o build do front vai dentro do pacote (src\gf_ui_editor\web_dist).
    Push-Location $webDir
    try {
        $env:PATH = "$(Split-Path -Parent $npm.Source);$env:PATH"
        if (-not (Test-Path -LiteralPath (Join-Path $webDir "node_modules"))) {
            & $npm.Source ci
            if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependências da interface nova (npm ci)." }
        }
        & $npm.Source run build
        if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar a interface nova (npm run build)." }
    } finally {
        Pop-Location
        $env:PATH = "$(Split-Path -Parent $python);$env:SystemRoot\System32;$env:SystemRoot"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $webDist "index.html"))) { throw "Build da interface nova não encontrado em $webDist." }
    & $python -m PyInstaller --noconfirm --clean --onedir --windowed --name GF-UI-Editor --icon $iconIco --add-data "$iconPng;gf_ui_editor\assets" --add-data "$iconIco;gf_ui_editor\assets" --add-data "$releaseNotes;gf_ui_editor\assets" --add-data "$contributors;gf_ui_editor\assets" --add-data "$stzLogo;gf_ui_editor\assets" --add-data "$stzMark;gf_ui_editor\assets" --add-data "$translations;gf_ui_editor\translations" --add-data "$fonts;gf_ui_editor\assets\fonts" --add-data "$backgrounds;gf_ui_editor\assets\backgrounds" --add-data "$webDist;gf_ui_editor\web_dist" --collect-all webview --collect-all clr_loader --collect-all pythonnet --hidden-import clr --distpath dist --workpath build --specpath build packaging\launcher.py
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
