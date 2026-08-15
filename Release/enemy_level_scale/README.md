# Enemy level scale

A Ryujinx ExeFS mod for **Unicorn Overlord US 1.0.5**.

Sets enemy levels to the **average of your top 10 units** — mission stickers on the map, and wandering overworld squads when you fight them.

This is **not** the squad editor. You do not need Node, Python, or the website.

## Install

1. Download [enemy_level_scale.zip](enemy_level_scale.zip)
2. Unzip — you get a folder named `enemy_level_scale` that contains `exefs/`
3. In Ryujinx: right-click **Unicorn Overlord** → **Open Mods Directory** → paste that folder
4. Enable it under **Manage Mods**
5. Fully quit Ryujinx. If you are replacing an older build, delete  
   `%AppData%\Ryujinx\games\010069401adb8000\cache\cpu`  
   then boot again.

Wrong game version = the mod will not apply. **US 1.0.5 only.**

## What you should see

- **Mission stickers** may still show vanilla until you teleport or hover a liberation fight once; then they update and stay updated.
- A few late missions (Z1 / Z2 / Sorm / some Elheim Z fights) **never scale down** — they only go above their vanilla level if your average is higher.
- **Sigil Trials** (Beginner through Apex) stay at their vanilla levels and are not scaled.
- **Wanderers** update when you engage them.

## Notes

- Safe to run alongside the squad editor and XP scale mods (separate folders).
- After updating this mod, always fully quit Ryujinx and clear the CPU cache folder above if levels or audio look stuck on an old build.
