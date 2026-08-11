# UO Squad Editor

Unofficial fan tools for Unicorn Overlord (Ryujinx, US v1.0.5).

Not affiliated with Atlus, Sega, Vanillaware, or Nintendo. You need your own copy of the game. This repo does not include ROMs, keys, or firmware.

Original code is [MIT](LICENSE). Game names and data stay with their owners.

These are **two separate things**. You can use either, or both.

| Want | Get |
|------|-----|
| Enemy levels = your party average | [Download the level scaler](Dist/enemy_level_scale.zip) — copy the folder into Ryujinx. Done. |
| Change mission squads / gear / tactics | The editor below (website or `run-editor.bat`). |

## Just the level scaler

1. Download [Dist/enemy_level_scale.zip](Dist/enemy_level_scale.zip)
2. Unzip so you have a folder named `enemy_level_scale` that contains `exefs/`
3. In Ryujinx: right-click **Unicorn Overlord** → **Open Mods Directory** → paste that folder
4. Enable it under **Manage Mods**. Fully quit Ryujinx, then boot.

Details: [Dist/enemy_level_scale/README.md](Dist/enemy_level_scale/README.md) · how it works: [Docs/ELI5_enemy_levels.md](Docs/ELI5_enemy_levels.md)

## Squad editor

Double-click `run-editor.bat`, or:

```powershell
cd Tools\mission_editor
npm install
npm run dev
```

Open the localhost URL Vite prints. Export writes a mod under `Mods/` for Ryujinx.

**Website (browse / edit only):** https://thu1478.github.io/UOSquadEditor/  
GitHub Pages cannot write a `.pchtxt`. Download edits JSON there, then import it in the local editor and Export.

After the first deploy, if the site 404s: **Settings → Pages → Source: Deploy from a branch** → `gh-pages` / `/ (root)`.

**New to the data model?** Read [Docs/squad_tactics_equipment.md](Docs/squad_tactics_equipment.md) (examples first, hex later).

How-tos: [Tools/mission_editor/README.md](Tools/mission_editor/README.md) · [PRESET_EDITOR.md](Tools/mission_editor/PRESET_EDITOR.md) · [Docs/README.md](Docs/README.md)
