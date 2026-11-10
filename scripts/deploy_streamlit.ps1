<#
.SYNOPSIS
    Deploy Inventory 360 to Streamlit in Snowflake.
.DESCRIPTION
    1. Pre-flight: every artifact in snowflake.yml must exist (a missing file uploads
       as an empty stage entry and breaks the app on first load).
    2. snow streamlit deploy --replace
    3. Grant app usage to the planner and viewer roles.
    4. Verify the STREAMLIT object exists.
.EXAMPLE
    .\scripts\deploy_streamlit.ps1 -Connection tbsljyv-rm91730
#>
param(
    [Parameter(Mandatory = $true)][string]$Connection,
    [string]$AppFqn = "INVENTORY_360_DB.APP.INVENTORY_360",
    [string[]]$GrantRoles = @("INV360_PLANNER", "INV360_VIEWER")
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$snow = Join-Path $root ".venv\Scripts\snow.exe"
if (-not (Test-Path $snow)) { $snow = "snow" }

Write-Host "== Pre-flight artifact check"
$missing = Get-Content snowflake.yml |
    Where-Object { $_ -match '^\s+-\s+(\S+\.\w+)\s*$' } |
    ForEach-Object { $Matches[1] } |
    Where-Object { -not (Test-Path $_) }
if ($missing) { throw "Missing artifacts:`n$($missing -join "`n")" }
Write-Host "OK"

Write-Host "== Deploying $AppFqn"
& $snow streamlit deploy inventory_360 --connection $Connection --replace
if ($LASTEXITCODE -ne 0) { throw "snow streamlit deploy failed" }

Write-Host "== Granting usage"
foreach ($role in $GrantRoles) {
    & $snow sql --connection $Connection -q "GRANT USAGE ON STREAMLIT $AppFqn TO ROLE $role"
}

Write-Host "== Verifying"
$name = $AppFqn.Split(".")[-1]
$rows = & $snow sql --connection $Connection --format json -q "SHOW STREAMLITS LIKE '$name' IN ACCOUNT" | ConvertFrom-Json
if (-not $rows -or $rows.Count -eq 0) { throw "Deploy reported success but $AppFqn was not found" }
Write-Host "Deployed: $AppFqn (owner $($rows[0].owner), warehouse $($rows[0].query_warehouse))"
