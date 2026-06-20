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

$redisHost = Require-EnvValue -Values $dotenv -Name "REDIS_HOST"
$redisPort = Require-EnvValue -Values $dotenv -Name "REDIS_PORT"
$redisDatabase = if ($dotenv.ContainsKey("REDIS_DB") -and -not [string]::IsNullOrWhiteSpace($dotenv["REDIS_DB"])) {
    $dotenv["REDIS_DB"]
} else {
    "0"
}

$argsList = @(
    "universal-db-mcp",
    "--type", "redis",
    "--host", $redisHost,
    "--port", $redisPort,
    "--database", $redisDatabase,
    "--permission-mode", "full"
)

if ($dotenv.ContainsKey("REDIS_PASSWORD") -and -not [string]::IsNullOrWhiteSpace($dotenv["REDIS_PASSWORD"])) {
    $argsList += @("--password", $dotenv["REDIS_PASSWORD"])
}

Set-Location -LiteralPath $repoRoot

& npx @argsList
