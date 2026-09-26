$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$scripts = Join-Path $root ".venv\Scripts"
$python = Join-Path $scripts "python.exe"
$translations = Join-Path $root "src\gf_ui_editor\translations"
$sources = @(
    (Join-Path $root "src\gf_ui_editor\app.py"),
    (Join-Path $root "src\gf_ui_editor\atlas_dialog.py"),
    (Join-Path $root "src\gf_ui_editor\editor_widgets.py"),
    (Join-Path $root "src\gf_ui_editor\i18n.py")
)

$languages = & $python -c "from gf_ui_editor.i18n import LANGUAGES; print(' '.join(language for language in LANGUAGES if language != 'pt_BR'))"
if ($LASTEXITCODE -ne 0) { throw "Falha ao ler os idiomas do aplicativo." }
foreach ($language in $languages.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)) {
    $catalog = Join-Path $translations "gf_ui_editor_$language.ts"
    $compiled = Join-Path $translations "gf_ui_editor_$language.qm"
    if (-not (Test-Path -LiteralPath $catalog)) { throw "Catálogo ausente: $catalog" }
    & (Join-Path $scripts "pyside6-lupdate.exe") -no-obsolete @sources -ts $catalog
    if ($LASTEXITCODE -ne 0) { throw "Falha ao atualizar $catalog." }
    $catalogXml = [xml](Get-Content -LiteralPath $catalog -Raw)
    if (($catalogXml.SelectNodes('//message[translation[@type="unfinished"] or not(translation) or normalize-space(translation)=""]')).Count -gt 0) {
        throw "Complete as traduções pendentes em $catalog antes de gerar o aplicativo."
    }
    & (Join-Path $scripts "pyside6-lrelease.exe") $catalog -qm $compiled
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar $catalog." }
}
