# ELI5 — What’s going on?



You’re used to **memory edits**: find a number, change it, game behaves differently.



This project does that too — but for a Switch game running in **Ryujinx**, the “memory” we edit is usually the **game program file** (`main`), via small text patch files (`.pchtxt`), not a live cheat trainer.



---



## The one-sentence version



**`enemy_level_scale` sets enemy levels to your top-10 party average** — for mission stickers on the map, and for wandering overworld squads when you fight them.

To **install** it, download [Dist/enemy_level_scale.zip](../Dist/enemy_level_scale.zip). You do not need this page, the squad editor, or any scripts.



---



## Picture the game like three drawers



### Drawer 1 — Mission sticker (map / briefing)



When you open Solm / Sorm and see a level, the game is mostly doing:



1. Look up this stage in a **big table** baked into `main`  

2. Read a number at a fixed spot in that row (`+0xC`)  

3. Draw that number on screen  



For Sorm, that word lives at **`0x28C2F44`** and is normally **38**.



**What the mod does:** when certain mission UI digits draw, it asks the game for your **top-10 average**, writes that into **every** stage table row, and shows it. Stickers may still look vanilla until the first teleport / liberation hover — then they update and stay updated.



### Drawer 2 — Wandering overworld parties



Those patrol squads on the map are **not** the same as mission stickers.



When you **engage** one, the game loads a level from the party object (`+0x1bc4`) and feeds it into unit create. The mod replaces that load with your top-10 average (same function the stickers use).



Wanderers **don’t respawn** once beaten, so spawn-time hooks miss parties already on a save — engage-time is the right moment.



### Drawer 3 — “Average of my party”



Function: **`GetCharaAverageLv(10)`** — average of your top 10 characters.



Call it too early (boot / some create paths) → **crash**.  

Call it from mission UI (after the party exists) or from field engage → OK.



---



## How *this repo* is organized (only what you need)



```text

UnicornOverlord/

  Docs/                 ← you’re reading this

  Mods/                 ← patch packs we install into Ryujinx

    enemy_level_scale/  ← level scaling (mission + wanderers)

    battle_timer_freeze/← tiny “stop the clock” mod (proves patches load)

  Extraction/           ← dumped game files + tables for research

  Scripts/              ← Python helpers that generate patches

```



Day to day:



1. Generate / edit files under `Mods/enemy_level_scale/exefs/`  

2. Copy them into Ryujinx’s mods folder for this game (generators usually do this)  

3. Enable the mod in **Manage Mods**  

4. Clear CPU cache if the game seems to ignore changes  

5. Quit Ryujinx fully, boot, teleport once, check a sticker and a wanderer  



---



## What a `.pchtxt` file is



A line like:



```text

028C2F44 07000000

```



means: at offset **`0x28C2F44`**, write bytes **`07 00 00 00`** (the number 7).



The header says “only this build” (`@nsobid-…`) and “add `0x100` on load” (`offset_shift`).



---



## Why it felt so complicated



We patched many paths that looked like “level” (UI drawers, FlCreate args, type enums, digit renderers). Most were wrong for what we cared about:



| Wrong guess | What happened |

|-------------|----------------|

| Always call average from every digit draw | Crash on save load |

| Force type / unitset fields to 7 | Empty squads |

| Force FlCreate argument regs to 7 | Wrong player overworld sprite |

| Force whole digit module to 7 | Wanderers unchanged (they don’t use it) |

| Write live stage `+0x9e0` from sticker cave | Freeze on teleport |



**What actually worked:**



1. Mission stickers → rewrite stage DB when safe UI digits draw  

2. Wanderers → replace field engage’s `+0x1bc4` load with average  



---



## Rules of thumb



| Do | Don’t |

|----|--------|

| Change **stage table** numbers for mission labels | Expect UnitSet edits to change “Enemy Level” |

| Scale wanderers at **engage** (`+0x1bc4`) | Rely on FlCreate alone (no respawn) |

| Keep **timer freeze** and **level scale** separate | Merge random patches into the timer mod |

| Use **ASCII** `.pchtxt`s; one clear set of files | Leave old diag files fighting each other |

| Quit Ryujinx + clear **CPU cache** after changes | Assume a running session picked up new files |

| Check logs for `Matching IPSwitch` if unsure | Assume “mod enabled” means patches applied |



---



## Where to go next



- Mod folder → `Mods/enemy_level_scale/`  



**Bottom line:** stickers = stage table rewritten to your average (after first safe UI touch). Wanderers = average applied when you engage them.


