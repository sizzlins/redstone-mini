<#
    gate.ps1 - the authoritative build gate for redstone-mini.

    Runs compose -> maze -> verify (scratch/dense_status.py) for every recipe
    in recipes/, one bounded process per recipe, all in parallel. 20 cores
    means the wall time is the slowest recipe, not the sum; running the fleet
    sequentially stalled for 15+ minutes on andor8 alone.

    Every process is hard-bounded so nothing can hang:
      REDSTONE_MAX_SECS      - one attempt (layout/sim)
      REDSTONE_COMPOSE_SECS  - the whole compose() retry ladder

    Usage:
      pwsh -File tools/gate.ps1                     # whole fleet
      pwsh -File tools/gate.ps1 -Recipe recipes/x.txt   # one recipe
      pwsh -File tools/gate.ps1 -MaxSecs 2400 -TotalSecs 2400   # patient
#>
param(
  [string]$Recipe = "",
  [int]$MaxSecs = 300,
  [int]$TotalSecs = 600
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-Gate {
  param([string]$Target, [string]$Log)
  $env:PYTHONUNBUFFERED = "1"
  $env:REDSTONE_MAX_SECS = "$MaxSecs"
  $env:REDSTONE_COMPOSE_SECS = "$TotalSecs"
  Remove-Item Env:REDSTONE_FORCE -ErrorAction SilentlyContinue
  python scratch/dense_status.py $Target *> $Log
}

if ($Recipe) {
  $leaf = (Split-Path -Leaf $Recipe) -replace '\.txt$', ''
  Invoke-Gate $Recipe "scratch/gate_$leaf.log"
  Get-Content "scratch/gate_$leaf.log" |
    Select-String -Pattern '^\S+\s+(OK|RED)\s' | Select-Object -First 1
  exit 0
}

New-Item -ItemType Directory -Force -Path scratch | Out-Null
$procs = @()
foreach ($r in (Get-ChildItem recipes/*.txt | Sort-Object Name)) {
  $log = "scratch/gate_$($r.Name).log"
  $procs += Start-Process pwsh -PassThru -WindowStyle Hidden -ArgumentList `
    '-NoProfile', '-File', $PSCommandPath, '-Recipe', "recipes/$($r.Name)",
    '-MaxSecs', $MaxSecs, '-TotalSecs', $TotalSecs
}
foreach ($p in $procs) { $p.WaitForExit() }

$bad = 0
foreach ($r in (Get-ChildItem recipes/*.txt | Sort-Object Name)) {
  $res = Get-Content "scratch/gate_$($r.Name).log" -ErrorAction SilentlyContinue |
    Select-String -Pattern '^\S+\s+(OK|RED)\s' | Select-Object -First 1
  if ($res) {
    if ($res.Line -match '\bRED\b') { $bad++ }
    "{0,-18} {1}" -f $r.Name, $res.Line.Trim()
  }
  else {
    $bad++
    "{0,-18} NO RESULT" -f $r.Name
  }
}
if ($bad) { "FAIL: $bad red"; exit 1 }
"ALL OK"
