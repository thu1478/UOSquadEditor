# Mission Squad Editor

Local Vite + React UI for editing Unicorn Overlord mission squads, EquipAiSet
**tactics presets**, and exporting a Ryujinx ExeFS mod.

## Setup

```powershell
# From repo root — refresh joined data for the GUI
.\Scripts\sync_mission_editor_data.ps1

cd Tools\mission_editor
npm install
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
npm run dev
```

Open the printed localhost URL. Dev APIs:

- `POST /api/export-mod` — write edits + run `export_mission_mod.py`
- `POST /api/resolve-tactics` — apply selected `.pchtxt` mods and return live class/IF maps

## Preset editor (detailed)

**[PRESET_EDITOR.md](PRESET_EDITOR.md)** — how presets work (id 0 vs named), finding
presets by mission, editing / removing skills, creating and assigning new
presets, shared forking, mods preview, export, and worked examples (including
removing Lifeshare from `C12_BOSS`).

## Workflow (short)

1. **Mission units** — pick mission → squad → unit; use the **Formation** grid
   (Back on top / Front on bottom; Left–Middle–Right as in-game) to select seats
   and click another seat to swap/move; **swap the unit** (any CharaSet / class
   template), edit gear; assign **Preset 0 (class defaults)**, an existing
   preset, or create a **new empty preset** (then fill slots before assigning —
   a non-zero empty preset skips class defaults).
   Use **Presets for mission** to jump to that map’s named presets.
2. **Class defaults** — edit class skill slots, learn levels, and per-skill default
   IF0/IF1. Global to all units of that class (and to marker resolution).
3. **EquipAiSet presets** — **Affects** / **(a) editable effects** / **(b) final
   results**. Drag effects to reorder them; contiguous slots `0–7` are assigned
   automatically. Filter by mission or search by unit / stage name.
4. **Load mods folder…** — apply `.pchtxt` under a folder (e.g. `Mods/class_editor`)
   for live Final results. Does **not** auto-bundle into the mission export.
5. Editing a **shared** preset (usage &gt; 1) or preset `0` from a unit forks a private
   EquipAiSet on export when appropriate.
6. **Export Ryujinx mod** → `Mods/<name>/exefs/main.pchtxt` (IPSwitch: `@enabled`
   + address lines, same pattern as `shop_editor`) plus `CHANGELOG.txt` and
   reusable `mission_editor_edits.json`. Restart Ryujinx after copying into
   `%AppData%\Ryujinx\mods\contents\010069401adb8000\`.
7. **Import editor mod…** — pick the exported **mod folder** (finds
   `mission_editor_edits.json` inside) or a JSON edits file directly to continue work.
8. **Reset changes** clears the in-editor edit log.

## Equipment vs presets

| EquipAiSet id | Tactics source |
|---------------|----------------|
| **0** | Class skills + **item-granted** skills from gear (runtime `0xDD610`) |
| **≠ 0** | **Only** the preset's `0x270AF48` slot list (`0xDDB90`). Gear skills appear **only** if hardcoded as an explicit skill id (e.g. C12 Lifeshare). |

Empty new presets change nothing until assigned. Assigning an empty non-zero id
wipes the unit's tactics list in-game — the UI warns before that.

## What patches in-game

| Field | ExeFS patch |
|-------|-------------|
| UnitSet composition / EquipAiSet **id** | Yes (`0x28120B8`) |
| CharaSet gear u16s | Yes (`0x276DD68`; shared templates duplicated) |
| Tactics **slots** | Yes — `0x270AF48` only; never patches id `0` as a body |
| Class skill slots / learn levels | Yes (`0xD36D94`, global by class) |
| Skill default IF0/IF1 | Yes (`EquipAiSet[skill_id] +0xAC/+0xB0`, global by skill) |

## Data sources

- `Extraction/editor/mission_squads.json` — joined document (`gear_policy: charaset_then_createdefault`)
- `Extraction/tables/equipaiset_*.csv` — from `Scripts/export_equipaiset.py`
- See `Docs/squad_tactics_equipment.md` for addresses and semantics
