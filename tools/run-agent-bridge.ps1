param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("abt", "babp", "sca", "btd")]
  [string]$Mod,

  [Parameter(Mandatory = $true)]
  [string]$FactorioExe,

  [Parameter(Mandatory = $true)]
  [string]$TargetModRoot,

  [Parameter(Mandatory = $true)]
  [string]$Scenario,

  [int]$MaxTicks = 720,

  [int]$SampleInterval = 30,

  [int]$CaptureRadius = 48,

  [string]$SetupOptionsJson = "{}",

  [string]$AssertionOptionsJson = "{}"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

python -m factorio_agent_bridge run `
  --mod $Mod `
  --factorio-exe $FactorioExe `
  --target-mod-root $TargetModRoot `
  --scenario $Scenario `
  --max-ticks $MaxTicks `
  --sample-interval $SampleInterval `
  --capture-radius $CaptureRadius `
  --setup-options-json $SetupOptionsJson `
  --assertion-options-json $AssertionOptionsJson
