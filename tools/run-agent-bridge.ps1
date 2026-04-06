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

  [string]$CapabilitiesJson = "[\"world\", \"entities\", \"players\", \"forces\", \"combat\", \"events\"]",

  [string]$CapabilityOptionsJson = "{}",

  [string]$SetupOptionsJson = "{}",

  [string]$ActionPlanJson = "[]",

  [string]$AssertionOptionsJson = "{}",

  [string]$WaitsJson = "[]",

  [string]$EventFiltersJson = "{}",

  [string]$FrameFiltersJson = "{}",

  [string]$PlanJson = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

if ($PlanJson -ne "") {
  python -m factorio_agent_bridge run-plan `
    --mod $Mod `
    --factorio-exe $FactorioExe `
    --target-mod-root $TargetModRoot `
    --plan-json $PlanJson
}
else {
  python -m factorio_agent_bridge run `
    --mod $Mod `
    --factorio-exe $FactorioExe `
    --target-mod-root $TargetModRoot `
    --scenario $Scenario `
    --max-ticks $MaxTicks `
    --sample-interval $SampleInterval `
    --capture-radius $CaptureRadius `
    --capabilities-json $CapabilitiesJson `
    --capability-options-json $CapabilityOptionsJson `
    --setup-options-json $SetupOptionsJson `
    --action-plan-json $ActionPlanJson `
    --assertion-options-json $AssertionOptionsJson `
    --waits-json $WaitsJson `
    --event-filters-json $EventFiltersJson `
    --frame-filters-json $FrameFiltersJson
}
