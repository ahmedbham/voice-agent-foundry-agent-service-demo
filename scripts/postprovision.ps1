#!/usr/bin/env pwsh
# Post-provision hook: install Python deps and create the Foundry agent.

$ErrorActionPreference = 'Stop'

Write-Host "==> Installing Python dependencies..." -ForegroundColor Cyan
$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py -3" } else { "python" }

if (-not (Test-Path .venv)) {
    Write-Host "==> Creating virtual environment..." -ForegroundColor Cyan
    Invoke-Expression "$python -m venv .venv"
}

$venvPython = Join-Path '.venv' 'Scripts' 'python.exe'
& $venvPython -m pip install --upgrade pip | Out-Null
& $venvPython -m pip install -r requirements.txt

Write-Host "==> Creating Foundry agent..." -ForegroundColor Cyan
& $venvPython -m src.create_agent_with_voicelive
