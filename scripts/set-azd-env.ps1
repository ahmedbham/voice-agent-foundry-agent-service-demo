#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Sets all azd environment variables required by this demo.

.DESCRIPTION
    Wraps `azd env set` calls for every variable consumed by infra/main.parameters.json
    and the post-provision hook. Values can be supplied via parameters; any omitted
    parameter is prompted for interactively (existing azd env value shown as default).

    Run AFTER `azd env new <name>` (or select an existing env with `azd env select`).
    All azd calls pass `-e <envName>` explicitly to avoid azd's interactive env
    picker (which would hang non-interactively).

.EXAMPLE
    ./scripts/set-azd-env.ps1 `
        -FoundryProjectEndpoint "https://my-foundry.services.ai.azure.com/api/projects/my-project" `
        -FoundryResourceGroup   "rg-my-foundry" `
        -FoundryResourceName    "my-foundry" `
        -FoundryProjectName     "my-project"

.EXAMPLE
    ./scripts/set-azd-env.ps1   # fully interactive
#>
[CmdletBinding()]
param(
    [string]$EnvName,
    [string]$FoundryProjectEndpoint,
    [string]$FoundryResourceGroup,
    [string]$FoundryResourceName,
    [string]$FoundryProjectName,
    [string]$ModelDeploymentName = 'gpt-4.1-mini',
    [string]$AgentName           = 'MyVoiceAgent',
    [string]$AzureLocation       = 'eastus2',
    [string]$VoiceName           = 'en-US-Ava:DragonHDLatestNeural'
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command azd -ErrorAction SilentlyContinue)) {
    throw "azd CLI not found on PATH. Install: https://aka.ms/azd-install"
}

# --- Resolve the azd environment to operate on ---
function Get-AzdEnvList {
    $raw = azd env list --output json 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) { return @() }
    try { return @($raw | ConvertFrom-Json) } catch { return @() }
}

if (-not $EnvName) {
    $envs = Get-AzdEnvList
    if ($envs.Count -eq 0) {
        $EnvName = Read-Host "No azd environment found. Enter a name to create one"
        if ([string]::IsNullOrWhiteSpace($EnvName)) { throw "Environment name is required." }
        azd env new $EnvName
        if ($LASTEXITCODE -ne 0) { throw "azd env new failed." }
    } else {
        $default = $envs | Where-Object { $_.IsDefault -eq $true } | Select-Object -First 1
        if ($default) {
            $EnvName = $default.Name
        } elseif ($envs.Count -eq 1) {
            $EnvName = $envs[0].Name
        } else {
            Write-Host "Available azd environments:" -ForegroundColor Cyan
            $envs | Format-Table Name, IsDefault | Out-Host
            $EnvName = Read-Host "Enter environment name to use"
        }
    }
}

if ([string]::IsNullOrWhiteSpace($EnvName)) {
    throw "Could not determine azd environment name. Pass -EnvName or run 'azd env select <name>'."
}
Write-Host "Using azd environment: $EnvName" -ForegroundColor Cyan

# --- Helpers (always pass -e $EnvName) ---
function Get-AzdValue([string]$Key) {
    $all = azd env get-values -e $EnvName --output json 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($all)) { return $null }
    try {
        $obj = $all | ConvertFrom-Json
        if ($obj.PSObject.Properties.Name -contains $Key) {
            return [string]$obj.$Key
        }
    } catch { return $null }
    return $null
}

function Read-WithDefault([string]$Prompt, [string]$Default) {
    if ([string]::IsNullOrWhiteSpace($Default)) {
        return Read-Host $Prompt
    }
    $v = Read-Host "$Prompt [$Default]"
    if ([string]::IsNullOrWhiteSpace($v)) { return $Default }
    return $v
}

function Resolve-Value([string]$Key, [string]$Provided, [string]$Fallback) {
    if (-not [string]::IsNullOrWhiteSpace($Provided)) { return $Provided }
    $existing = Get-AzdValue $Key
    $default = if ([string]::IsNullOrWhiteSpace($existing)) { $Fallback } else { $existing }
    return Read-WithDefault $Key $default
}

# --- Collect values ---
$values = [ordered]@{
    FOUNDRY_PROJECT_ENDPOINT = Resolve-Value 'FOUNDRY_PROJECT_ENDPOINT' $FoundryProjectEndpoint $null
    FOUNDRY_RESOURCE_GROUP   = Resolve-Value 'FOUNDRY_RESOURCE_GROUP'   $FoundryResourceGroup   $null
    FOUNDRY_RESOURCE_NAME    = Resolve-Value 'FOUNDRY_RESOURCE_NAME'    $FoundryResourceName    $null
    FOUNDRY_PROJECT_NAME     = Resolve-Value 'FOUNDRY_PROJECT_NAME'     $FoundryProjectName     $null
    MODEL_DEPLOYMENT_NAME    = Resolve-Value 'MODEL_DEPLOYMENT_NAME'    $ModelDeploymentName    'gpt-4.1-mini'
    AGENT_NAME               = Resolve-Value 'AGENT_NAME'               $AgentName              'MyVoiceAgent'
    AZURE_LOCATION           = Resolve-Value 'AZURE_LOCATION'           $AzureLocation          'eastus2'
    VOICE_NAME               = Resolve-Value 'VOICE_NAME'               $VoiceName              'en-US-Ava:DragonHDLatestNeural'
}

# Auto-derive FOUNDRY_PROJECT_NAME from endpoint if still empty
if ([string]::IsNullOrWhiteSpace($values.FOUNDRY_PROJECT_NAME) -and $values.FOUNDRY_PROJECT_ENDPOINT) {
    $derived = ($values.FOUNDRY_PROJECT_ENDPOINT.TrimEnd('/').Split('/'))[-1]
    Write-Host "Derived FOUNDRY_PROJECT_NAME from endpoint: $derived" -ForegroundColor Yellow
    $values.FOUNDRY_PROJECT_NAME = $derived
}

# Validate required values
$required = @('FOUNDRY_PROJECT_ENDPOINT', 'FOUNDRY_RESOURCE_GROUP', 'FOUNDRY_RESOURCE_NAME', 'FOUNDRY_PROJECT_NAME')
foreach ($k in $required) {
    if ([string]::IsNullOrWhiteSpace($values[$k])) {
        throw "$k is required."
    }
}

# --- Write values ---
Write-Host "`nSetting azd environment variables on '$EnvName'..." -ForegroundColor Cyan
foreach ($k in $values.Keys) {
    $v = $values[$k]
    Write-Host ("  {0,-26} = {1}" -f $k, $v)
    # Pass -e to avoid azd's interactive env picker; --no-prompt fails fast on any prompt.
    azd env set $k $v -e $EnvName --no-prompt
    if ($LASTEXITCODE -ne 0) { throw "azd env set $k failed." }
}

Write-Host "`nDone. Current azd environment values for '$EnvName':" -ForegroundColor Green
azd env get-values -e $EnvName
