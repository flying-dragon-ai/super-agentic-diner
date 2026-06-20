$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$envPath = Join-Path $repoRoot ".env"

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Missing .env at $envPath"
}

function Read-DotEnv {
    param([string]$Path)

    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) {
            continue
        }

        $parts = $trimmed -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        $values[$name] = $value
    }

    return $values
}

function Require-EnvValue {
    param(
        [hashtable]$Values,
        [string]$Name
    )

    if (-not $Values.ContainsKey($Name) -or [string]::IsNullOrWhiteSpace($Values[$Name])) {
        throw "Missing $Name in $envPath"
    }

    return $Values[$Name]
}

$dotenv = Read-DotEnv -Path $envPath

$mysqlHost = Require-EnvValue -Values $dotenv -Name "MYSQL_HOST"
$mysqlPort = Require-EnvValue -Values $dotenv -Name "MYSQL_PORT"
$mysqlUser = Require-EnvValue -Values $dotenv -Name "MYSQL_USER"
$mysqlPassword = Require-EnvValue -Values $dotenv -Name "MYSQL_PASSWORD"
$mysqlDatabase = Require-EnvValue -Values $dotenv -Name "MYSQL_DATABASE"

Set-Location -LiteralPath $repoRoot

& npx universal-db-mcp `
    --type mysql `
    --host $mysqlHost `
    --port $mysqlPort `
    --user $mysqlUser `
    --password $mysqlPassword `
    --database $mysqlDatabase `
    --permission-mode full
