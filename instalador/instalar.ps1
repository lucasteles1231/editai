# O instalador do Editai para Windows.
#
#   powershell -ExecutionPolicy ByPass -c "irm https://lucasteles1231.github.io/editai/instalar.ps1 | iex"
#
# Faz os tres passos da instalacao manual: instala o uv (se faltar), que cuida do Python sem
# mexer no do sistema; instala o Editai na versao abaixo; e cria o atalho "Editai" no menu
# Iniciar e na Area de Trabalho. Rodar de novo atualiza (feche o Editai antes).
# So ASCII aqui: o PowerShell 5.1 le o que o irm baixa sem saber que e UTF-8.
$ErrorActionPreference = 'Stop'

$versao = if ($env:EDITAI_VERSAO) { $env:EDITAI_VERSAO } else { '__VERSAO__' }
$pacote = if ($env:EDITAI_PACOTE) { $env:EDITAI_PACOTE } else {
  "https://github.com/lucasteles1231/editai/releases/download/v$versao/editai-$versao-py3-none-any.whl"
}

Write-Host "Instalando o Editai $versao"

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv -and (Test-Path "$env:USERPROFILE\.local\bin\uv.exe")) {
  $uv = "$env:USERPROFILE\.local\bin\uv.exe"
}
if (-not $uv) {
  Write-Host '-> instalando o uv (uns 45 MB)...'
  powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $uv = "$env:USERPROFILE\.local\bin\uv.exe"
}

Write-Host '-> instalando o Editai (uns 220 MB na primeira vez)...'
& $uv tool install --force --python 3.12 $pacote
if ($LASTEXITCODE -ne 0) { throw 'O uv nao conseguiu instalar o Editai.' }

$bin = (& $uv tool dir --bin).Trim()
& "$bin\editai.exe" --criar-atalho
if ($LASTEXITCODE -ne 0) { Write-Host '(o atalho nao foi criado; abra pelo PowerShell, com: editai)' }

Write-Host ''
Write-Host 'Pronto! Para abrir, use o atalho Editai no menu Iniciar, ou digite editai num PowerShell novo.'
