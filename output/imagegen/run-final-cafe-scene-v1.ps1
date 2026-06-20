$ErrorActionPreference = 'Stop'

$Cli = Join-Path $env:USERPROFILE '.codex\skills\.system\imagegen\scripts\image_gen.py'
$Prompt = Join-Path $PSScriptRoot 'coffee-characters-final-cafe-scene-v1.prompt.txt'
$ConceptSheet = Join-Path $PSScriptRoot 'coffee-characters-concept-sheet-v1.png'
$CompositionPreview = Join-Path $PSScriptRoot 'coffee-characters-cafe-composite-preview-v1.png'
$Out = Join-Path $PSScriptRoot 'coffee-characters-final-cafe-scene-v1.png'
$Validator = Join-Path $PSScriptRoot 'validate-imagegen-workflow.py'

if (-not $env:OPENAI_API_KEY) {
  throw 'OPENAI_API_KEY is not configured in this shell. Set it locally, then rerun this script.'
}

if (-not (Test-Path -LiteralPath $Cli)) {
  throw "Image generation CLI not found: $Cli"
}

if (-not (Test-Path -LiteralPath $Prompt)) {
  throw "Prompt file not found: $Prompt"
}

if (-not (Test-Path -LiteralPath $ConceptSheet)) {
  throw "Approved concept sheet not found: $ConceptSheet. Generate and approve coffee-characters-concept-sheet-v1.png first."
}

if (-not (Test-Path -LiteralPath $CompositionPreview)) {
  throw "Composition preview not found: $CompositionPreview"
}

python $Cli edit `
  --model gpt-image-2 `
  --quality high `
  --size 2048x1152 `
  --output-format png `
  --prompt-file $Prompt `
  --image $ConceptSheet `
  --image $CompositionPreview `
  --out $Out `
  --force `
  --no-augment

Write-Host "Generated: $Out"

python $Validator --require-generated
