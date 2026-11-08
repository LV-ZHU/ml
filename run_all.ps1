param([string]$OutputDir = 'new_experiment')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw '请先按 README 建立 .venv 并安装 requirements.txt。'
}
$env:MPLCONFIGDIR = Join-Path $PSScriptRoot (Join-Path $OutputDir 'matplotlib_cache')
& $projectPython -m src.run --stage all --config config.json --output $OutputDir
if ($LASTEXITCODE -ne 0) { throw '运行失败，详细证据已保存到输出目录 runs 和 run.log。' }
