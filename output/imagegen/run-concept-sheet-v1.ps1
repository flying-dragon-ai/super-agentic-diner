$ErrorActionPreference = 'Stop'

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$Cli = Join-Path $env:USERPROFILE '.codex\skills\.system\imagegen\scripts\image_gen.py'
$Prompt = Join-Path $PSScriptRoot 'coffee-characters-concept-sheet-v1.prompt.txt'
$Out = Join-Path $PSScriptRoot 'coffee-characters-concept-sheet-v1.png'
$Validator = Join-Path $PSScriptRoot 'validate-imagegen-workflow.py'
$Refs = @(
  (Join-Path $PSScriptRoot 'references\character-ref-01.png'),
  (Join-Path $PSScriptRoot 'references\character-ref-02.png'),
  (Join-Path $PSScriptRoot 'references\character-ref-03.png'),
  (Join-Path $PSScriptRoot 'references\character-ref-04.png')
)

if (-not $env:OPENAI_API_KEY) {
  throw 'OPENAI_API_KEY is not configured in this shell. Set it locally, then rerun this script.'
}

if (-not (Test-Path -LiteralPath $Cli)) {
  throw "Image generation CLI not found: $Cli"
}

if (-not (Test-Path -LiteralPath $Prompt)) {
  throw "Prompt file not found: $Prompt"
}

foreach ($Ref in $Refs) {
  if (-not (Test-Path -LiteralPath $Ref)) {
    throw "Reference image not found: $Ref"
  }
}

python $Cli edit `
  --model gpt-image-2 `
  --quality high `
  --size 2048x2048 `
  --output-format png `
  --prompt-file $Prompt `
  --image $($Refs[0]) `
  --image $($Refs[1]) `
  --image $($Refs[2]) `
  --image $($Refs[3]) `
  --out $Out `
  --force `
  --no-augment

Write-Host "Generated: $Out"

python $Validator
