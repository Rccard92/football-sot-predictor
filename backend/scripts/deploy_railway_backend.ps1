# Deploy backend Railway (railway up) con provenance GIT_COMMIT_SHA esplicita.
# Uso: da backend/  ->  .\scripts\deploy_railway_backend.ps1
# Richiede: git, railway CLI, working tree clean.

$ErrorActionPreference = "Stop"

$BackendRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $BackendRoot

$porcelain = git status --porcelain
if ($porcelain) {
    Write-Error "Working tree non clean. Commit o stash prima del deploy:`n$porcelain"
}

$DeploySha = (git rev-parse HEAD).Trim()
if (-not $DeploySha) {
    Write-Error "git rev-parse HEAD non ha restituito uno SHA."
}

Write-Host "DEPLOY_SHA=$DeploySha"

Write-Host "Imposto GIT_COMMIT_SHA e SOURCE_VERSION sul servizio backend..."
railway variables set "GIT_COMMIT_SHA=$DeploySha" --service backend
railway variables set "SOURCE_VERSION=$DeploySha" --service backend

Write-Host "Avvio railway up..."
railway up --service backend

Write-Host ""
Write-Host "Post-deploy: verifica provenance con:"
Write-Host "  railway run --service backend python -c `"from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision; import json; print(json.dumps(resolve_code_revision()))`""
Write-Host "Atteso: revision_status=resolved, git_commit=$DeploySha"
