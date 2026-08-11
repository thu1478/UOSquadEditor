# Documentation

Start here if you have never opened this repo. You do **not** need to know
reverse engineering. You need the game (US v1.0.5) and Ryujinx.

There are two separate tools:

| If you want to… | Read |
|-----------------|------|
| Change **who** is in a mission squad, their **gear**, or their **tactics** | This page, then [squad_tactics_equipment.md](squad_tactics_equipment.md), then run `run-editor.bat` |
| Scale **enemy levels** to your party average | [ELI5_enemy_levels.md](ELI5_enemy_levels.md) |

Editor how-tos:

- [Mission editor README](../Tools/mission_editor/README.md) — install, tabs, export
- [Preset editor](../Tools/mission_editor/PRESET_EDITOR.md) — tactics presets in detail

Only if you are **changing** the level-scale mod itself (not required to use it):

- [enemy_and_stage_levels.md](enemy_and_stage_levels.md) — research log: addresses, dead ends, v37 hooks

## Tiny glossary

| Word | Meaning |
|------|---------|
| **UnitSet** | One squad: up to 6 seats |
| **CharaSet** | Who sits in a seat (class + optional named items) |
| **EquipAiSet** | A tactics preset. Id **0** = “use the class’s normal skills” |
| **PARAMSET / equip tier** | Which default-gear *band* empty slots use (NORMAL vs POWER vs BOSS) |
| **Stride** | Byte size of one row in a table. Row `id` is at `base + id × stride` |
| **Word / half** | 4-byte / 2-byte value in the game file |
| **`.pchtxt`** | Ryujinx patch file: “at this address, write these bytes” |

## Game / emulator

- Game: Unicorn Overlord US **1.0.5**
- Copy an exported mod folder into Ryujinx and enable it under **Manage Mods**.
  Fully quit the emulator before testing so the patch reloads.
