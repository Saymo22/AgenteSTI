# deploy.ps1 - AgenteSTI Deploy Automatizado
param (
    [string]$CommitMessage = "Deploy automatico: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
)

$ErrorActionPreference = "Stop"

Write-Host "=== AgenteSTI - Iniciando Deploy ===" -ForegroundColor Cyan

# 1. Verifica se está no repositório
git rev-parse --is-inside-work-tree | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Erro: Execute este script dentro do repositório AgenteSTI." }
$currentBranch = git branch --show-current
if ($LASTEXITCODE -ne 0 -or $currentBranch -ne "main") {
    throw "Faça o merge na branch main antes de executar o deploy."
}

# 2. Prepara e commita alterações locais
$status = git status --porcelain
if ($status) {
    Write-Host "Adicionando e commitando alterações..." -ForegroundColor Yellow
    git add .
    if ($LASTEXITCODE -ne 0) { throw "Falha ao preparar os arquivos para commit." }
    git commit -m $CommitMessage
    if ($LASTEXITCODE -ne 0) { throw "Falha no commit. Deploy interrompido." }
} else {
    Write-Host "Nenhuma alteração local para commitar." -ForegroundColor DarkGray
}

# 3. Push para Produção (Intranet)
Write-Host "Enviando para Produção (Intranet)..." -ForegroundColor Yellow
git push production main
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO CRÍTICO: Falha ao enviar para Produção." -ForegroundColor Red
    exit 1
}

# 4. Push para o GitHub (Backup)
Write-Host "Enviando backup para GitHub..." -ForegroundColor Yellow
git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "AVISO: Sem internet ou falha no GitHub. O deploy na intranet foi concluído." -ForegroundColor DarkYellow
}

# 5. Verificação do Deploy no Servidor
Write-Host "Buscando logs do servidor..." -ForegroundColor Cyan
ssh agente-sti "tail -n 20 /var/log/agenteSTI/deploy.log"

Write-Host "Status do serviço:" -ForegroundColor Cyan
ssh agente-sti "systemctl status agente-sti.service --no-pager"

Write-Host "=== Deploy Finalizado! ===" -ForegroundColor Green
