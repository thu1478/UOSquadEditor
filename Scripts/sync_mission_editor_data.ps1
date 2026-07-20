$ErrorActionPreference = "Stop"
$ROOT = Split-Path $PSScriptRoot -Parent
python "$ROOT\Scripts\build_stage_levels.py"
python "$ROOT\Scripts\export_charasets.py"
python "$ROOT\Scripts\decode_fms.py"
python "$ROOT\Scripts\export_equipaiset.py"
python "$ROOT\Scripts\export_equiptype_defaults.py"
python "$ROOT\Scripts\export_stage_unitsets.py"
python "$ROOT\Scripts\build_mission_squads_json.py"
New-Item -ItemType Directory -Force -Path "$ROOT\Tools\mission_editor\public\data" | Out-Null
Copy-Item "$ROOT\Extraction\editor\mission_squads.json" "$ROOT\Tools\mission_editor\public\data\mission_squads.json" -Force
Write-Host "Synced mission_squads.json. Run: cd Tools\mission_editor; npm.cmd run dev"
