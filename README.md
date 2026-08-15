# UO Squad Editor

Unofficial fan tools for Unicorn Overlord (Ryujinx, US v1.0.5).

Not affiliated with Atlus, Sega, Vanillaware, or Nintendo. You need your own copy of the game. This repo does not include ROMs, keys, or firmware.

Original code is [MIT](LICENSE). Game names and data stay with their owners.

**Site:** https://thu1478.github.io/UOSquadEditor/

| Want | Get |
|------|-----|
| Browse all mods | [UO Tools hub](https://thu1478.github.io/UOSquadEditor/) |
| Enemy levels = your party average | Hub → **Enemy Level Scale**, or [Release/enemy_level_scale.zip](Release/enemy_level_scale.zip) |
| Combat EXP multiplier | Hub → **XP Scale** (slider), or [Release/xp_scale/](Release/xp_scale/) |
| Change mission squads / gear / tactics | [Mission Squad Editor](https://thu1478.github.io/UOSquadEditor/editor/) |

## Just the level scaler

1. Download [Release/enemy_level_scale.zip](Release/enemy_level_scale.zip) (or from the hub)
2. Unzip — you get a folder named `enemy_level_scale` that contains `exefs/`
3. In Ryujinx: right-click **Unicorn Overlord** → **Open Mods Directory** → paste that folder
4. Enable it under **Manage Mods**. Fully quit Ryujinx, then boot.

Details: [Release/enemy_level_scale/README.md](Release/enemy_level_scale/README.md) · how it works: [Docs/ELI5_enemy_levels.md](Docs/ELI5_enemy_levels.md)

## XP scale (combat)

1. On the hub, open **XP Scale**, drag the bar to a multiplier, download that zip (or pick a file under [Release/xp_scale/](Release/xp_scale/))
2. Unzip — you get a folder named `xp_scale` that contains `exefs/`
3. Copy into Ryujinx mods and enable it (only one XP scale zip at a time)
4. Fully quit Ryujinx, then boot

Details: [Release/xp_scale/README.md](Release/xp_scale/README.md)

## Squad editor

**Use the website:** https://thu1478.github.io/UOSquadEditor/editor/

1. Edit squads, gear, tactics, class defaults, or default-gear tables
2. Optionally name the mod in **Mod folder name**
3. **Export Ryujinx mod** — downloads a zip
4. Unzip, then in Ryujinx: right-click Unicorn Overlord → **Open Mods Directory** → paste the folder
5. Enable it under **Manage Mods**. Fully quit Ryujinx, then boot.

**Import editor mod…** reloads a zip/folder you exported earlier (`mission_editor_edits.json`).

**New to the data model?** Read [Docs/squad_tactics_equipment.md](Docs/squad_tactics_equipment.md) (examples first, hex later).

How-tos: [Tools/mission_editor/README.md](Tools/mission_editor/README.md) · [PRESET_EDITOR.md](Tools/mission_editor/PRESET_EDITOR.md) · [Docs/README.md](Docs/README.md)
