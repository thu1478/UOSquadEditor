# Scripts

## Commit (`Scripts/`)

Product / rebuild tools used by the hub, editor, and release mods:

| Script | Role |
|--------|------|
| `gen_xp_scale.py` | Build `Release/xp_scale/*.zip` |
| `sync_mission_editor_data.ps1` | Rebuild editor JSON from Extraction |
| `run-editor.ps1` | Launch local mission editor |
| `build_mission_squads_json.py` | Editor document |
| `build_stage_levels.py` | Stage level table |
| `decode_fms.py` | FMS → CSV for editor tables |
| `export_*.py` | Table exporters |
| `export_mission_mod.py` | Editor → Ryujinx mod |
| `resolve_tactics_mods.py` | Tactics helpers |

## Do not commit (`Scripts/local/`)

Gitignored. Local dump / machine paths / RE scratch:

- `extract-*.ps1`, `fetch-reference-tables.ps1`, `decode-*.ps1` — need your `GameFiles/` / keys
- `scratch/_*.py` — one-off reverse-engineering notes
