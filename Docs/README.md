# Documentation

Start here if you have never opened this repo. You do **not** need to know
reverse engineering. You need the game (US v1.0.5) and Ryujinx.

There are two separate things. You do not need both.

| If you want to… | Do this |
|-----------------|---------|
| See both mods | Open the [UO Tools hub](https://thu1478.github.io/UOSquadEditor/) |
| Scale **enemy levels** to your party average | Download from the hub, or [Release/enemy_level_scale.zip](../Release/enemy_level_scale.zip). How it works: [ELI5_enemy_levels.md](ELI5_enemy_levels.md) |
| Change **who** is in a mission squad, their **gear**, or their **tactics** | Open the [Mission Squad Editor](https://thu1478.github.io/UOSquadEditor/editor/). How it works: [squad_tactics_equipment.md](squad_tactics_equipment.md) |

Editor how-tos:

- [Mission editor README](../Tools/mission_editor/README.md) — install, tabs, export
- [Preset editor](../Tools/mission_editor/PRESET_EDITOR.md) — tactics presets in detail

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
