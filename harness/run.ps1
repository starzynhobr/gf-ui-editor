# Harness "mesma entrada, mesma saída": roda os fluxos reais do editor na versão de
# referência (um ref do git) e na árvore atual, cada uma na sua caixa de areia, e compara.
#
#   .\harness\run.ps1                    # referência = main
#   .\harness\run.ps1 -Reference v0.7.0
#
# Na primeira vez copia UI, data\Translate e as listas do jogo para -Work\pristine (~1 GB).
# O jogo real só é lido. Saídas em -Work\reference e -Work\candidate.
param(
    [string]$Reference = "main",
    [string]$Game = "C:\Violet Games\Grand Fantasia Violet",
    [string]$Work = "$env:TEMP\gf-ui-harness"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$python = $null
foreach ($candidate in @("$repo\.venv\Scripts\python.exe", "$(git -C $repo rev-parse --path-format=absolute --git-common-dir)\..\.venv\Scripts\python.exe")) {
    if (Test-Path $candidate) { $python = (Resolve-Path $candidate).Path; break }
}
if (-not $python) { throw "Não achei a .venv (nem nesta árvore nem no checkout principal)." }

$pristine = Join-Path $Work "pristine"
if (-not (Test-Path (Join-Path $pristine "UI"))) {
    Write-Host "Copiando a UI e os textos do jogo para $pristine…"
    New-Item -ItemType Directory -Force $pristine | Out-Null
    robocopy "$Game\UI" "$pristine\UI" /E /NFL /NDL /NJH /NJS /MT:16 | Out-Null
    robocopy "$Game\data\Translate" "$pristine\data\Translate" /E /NFL /NDL /NJH /NJS /MT:16 | Out-Null
    foreach ($file in "GameDataFileList.txt", "GameDataFileListT.txt", "Launcher.ini", "GrandFantasia.exe") {
        if (Test-Path "$Game\$file") { Copy-Item "$Game\$file" $pristine }
    }
    New-Item -ItemType Directory -Force "$pristine\UICustom" | Out-Null
}

$refTree = Join-Path $Work "reference-src"
if (Test-Path $refTree) { git -C $repo worktree remove --force $refTree 2>$null; Remove-Item -Recurse -Force $refTree -ErrorAction SilentlyContinue }
git -C $repo worktree add --detach $refTree $Reference | Out-Null
try {
    $flows = Join-Path $PSScriptRoot "run_flows.py"  # o roteiro da árvore atual roda nas duas versões
    $runs = @(
        @{ Name = "reference"; Src = "$refTree\src" },
        @{ Name = "candidate"; Src = "$repo\src" }
    ) | ForEach-Object {
        $out = Join-Path $Work $_.Name
        Start-Process $python -ArgumentList "`"$flows`" `"$out`" `"$pristine`"" -Environment @{ PYTHONPATH = $_.Src } `
            -RedirectStandardOutput "$out.log" -RedirectStandardError "$out.err" -NoNewWindow -PassThru
    }
    $runs | ForEach-Object { $_.WaitForExit() }
    foreach ($name in "reference", "candidate") {
        if (-not (Test-Path (Join-Path $Work "$name\log.json"))) {
            Get-Content (Join-Path $Work "$name.err") -Tail 30
            throw "A execução '$name' não terminou (veja $Work\$name.err e $Work\$name\stacks.txt)."
        }
    }
    & $python (Join-Path $PSScriptRoot "compare.py") (Join-Path $Work "reference") (Join-Path $Work "candidate")
    exit $LASTEXITCODE
}
finally {
    git -C $repo worktree remove --force $refTree 2>$null
}
