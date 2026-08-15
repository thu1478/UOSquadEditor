# Enemy and stage levels

**You probably do not need this file.** It is a research log for the
`enemy_level_scale` mod (addresses, failed hooks, how v37 was built).

- Scaling enemy levels, as a player/mod user → [ELI5_enemy_levels.md](ELI5_enemy_levels.md)
- Mission squads, gear, tactics → [squad_tactics_equipment.md](squad_tactics_equipment.md)

This page was **not** rewritten in the newcomer pass. Facts below are still
the shipping level-scale design on US v1.0.5; the tone is “lab notebook,”
not a tutorial.



---



## Target



| Item | Value |

|------|--------|

| Game | Unicorn Overlord (Switch, US) |

| Version | 1.0.5 |

| Title ID | `010069401adb8000` |

| NSO build id (`@nsobid`) | `C841FFE2717FF03A13990480C51DA73F091C04FA` |

| Emulator mods | Ryujinx → **Manage Mods** for this game |

| Decompressed `main` | `Extraction/exefs_out/main.decompressed.bin` (file offset ≈ VA for pchtxt) |

| Wiki / table dump | `Extraction/tables/stage_enemy_levels.csv` |



All ExeFS `.pchtxt` patches in this project use:



```text

@nsobid-C841FFE2717FF03A13990480C51DA73F091C04FA

@flag offset_shift 0x100

```



Same header as `Mods/battle_timer_freeze` (known-good control).



---



## Mental model



```text

Mission sticker / briefing "Enemy Level"

    └── NSO stage DB record, field +0xC

            rewritten to GetCharaAverageLv(10) by UI cave (v25/v37)



Wandering overworld party (combat)

    └── field object +0x1bc4

            loaded at engage 0x199AF0 → resolve create-param +0x10

            replaced with GetCharaAverageLv(10) (v37)



In-battle / scripted stage spawns

    ├── stage base (DB / GetStageBaseLevel / live +0x9e0)

    ├── + OffsetLv

    ├── FlCreateEnemy(..., _nLv)  — spawn-time; wanderers on a save already exist

    └── sometimes an ASB immediate level



Player-relative scaling

    └── GetCharaAverageLv(count)  — W1 = count (use 10)

            only call when chara singleton (0x19684) is ready

```



**Two channels (both shipping in v37):**



1. **Mission labels** — stage DB `+0xC` via numdraw allowlist cave  

2. **Wanderer combat** — field engage `+0x1bc4`  



Patching one does not automatically fix the other.



---



## What does *not* store the stage / wanderer level



### UnitSets



`UC_UNITSET_*` entries describe **who** is in a squad. They do **not** store the absolute stage enemy level. Editing UnitSets will not change mission “Enemy Level: 38”.



Binary table in `main`: base `0x28120B8`, stride `0x88`, ~2860 rows. Each row has six slots (`+0x3C`, step `0x0C`): **CharaSet id**, optional **EquipAiSet id** (tactics preset; `0` = class default), flags. Dump: `Extraction/tables/unitsets.csv` (via `Scripts/export_unitsets.py`).



**Tactics:** EquipAiSet names live in `_UcEnum_EquipAiSet.inc` (~358 presets: tutor `CH_*`, boss `C5_BOSS`, arena, etc.). Only ~717 slots set an explicit preset; the rest inherit class defaults. **Preset row contents** (action + IF conditions) are applied at runtime (`char+0xFB0` / `+0x12F0`); static decode still needs a Ryujinx dump when EquipAiSet id ≠ 0 (break near create `0x2D624C`).



**Equipment:** per-CharaSet item slots are in `main` at `0x276DD68`, stride `0x48`, gear u16s at `+0x38..+0x3E` (empty = CreateDefaultEquip / EQUIPTYPE). Dump: `Extraction/tables/charasets.csv` (`Scripts/export_charasets.py`). Generic zako with empty slots still use the unmapped EQUIPTYPE default path.



### Shared digit module alone (wanderer display)



Forcing every number capture in `0x5C9xxx` (including siblings of `0x5C9980`) to `7` did **not** change wanderer levels. Wanderer combat level is not painted exclusively by that HUD digit path.



### Character `+0xa18`



Level-like field; forcing it did **not** change Sorm mission info. Not the mission-sticker source.



### Resolve `def+0x10` / `unit+0x4`



Small **type enum** (~1–4), not a 1–99 level. Forcing `7` emptied squads.



### FlCreate argument registers (blind force-7)



Broke the overworld **player sprite** (character-id-like args). Did not reliably change wanderer levels for parties already on the map.



---



## Stage DB (mission info source of truth)



### Layout



| | |

|--|--|

| Base (NSO) | `0x28C19F8` |

| Stride | `0x50` bytes per stage record |

| Level field | `+0x0C` (32-bit little-endian integer) |



### Known example — Battle for Sorm



| | |

|--|--|

| Stage | `ST_OW_TK_C11` / `OW_TK_C11` |

| Wiki level | 38 |

| Level word address | `0x28C2F44` |

| Vanilla value | `0x00000026` (38) |



**Proven:** static patch of that word to `7` changes Sorm mission info. Shipping mod instead rewrites **all** plausible DB rows to the party average at runtime.



### How the UI consumes it



1. Resolve stage record pointer  

2. Representative fill: `0x518D8C` `LDR` DB `+0xC` → UI object  

3. Digit draw via shared renderer `0x5C9980` (and sisters)



Shipping path does **not** rely on patching every fill site: a cave hooked from numdraw (`0x5C9994`) filters by **outer caller LR**, calls average when allowlisted, rewrites the DB, and sets the drawn value.



**Allowlisted LRs (mission / panel digits):**  

`0x1087D8`, `0x108B50`, `0x336940`, `0x336A44`, `0x336F48`, `0x33A6D8`, `0x33AB84`, `0x33AC58`, `0x33AD2C`, `0x33AE00`, `0x33B7BC`, `0x33B8B0`, `0x33BD48`



**Excluded on purpose:** `0x335E90` / early HUD callers — calling average from *all* numdraw sites crashed on save load.



**Timing:** on a fresh load, stickers can still show vanilla until the first allowlisted draw (e.g. teleport or hover a liberation fight). After that, the DB holds the average.



**Cave must preserve X0** — numdraw’s next `MOV X21,X0` needs the original X0; clobbering it caused teleport crashes (fixed in v25).



---



## Combat / spawn level



### Create path (story-style)



Around `0x248338`: stage live base `+0x9e0` + OffsetLv → create-param `+0x10` → resolve `0x2D6E20`.



### FlCreateEnemy



Signature (AngelScript):  

`FlCreateEnemy(symbol, callback, unitSet, pos, degree=45, nLv=1)`  



Around `0x315BC0`, `W6`/`W25` feeds object `+0x1bc4`. Useful for **new** field spawns; existing wanderers on a save are already created (they do not respawn).



### GetStageBaseLevel (`0x313298`)



Returns `[stageRecord + 0xC]`. Do **not** replace with naked average — runs too early and crashed in testing.



### Live stage `+0x9e0`



Set by `StSetStageUnitBaseLv`-style code (`0x324440` area). Used by some create/UI paths. **Do not** write this from the mission UI cave — v35 did and **froze on teleport**.



### ASB scripts



Some stages pass absolute levels in script. DB rewrite helps table-driven cases; hard-coded ASB immediates may still need LayeredFS / extra hooks.



### Wandering overworld parties (shipping)



| | |

|--|--|

| Engage load | `0x199AF0` `LDR W8,[X20,#0x1bc4]` |

| Next | `STR` into resolve param `+0x10`, then `BL 0x2D6E20` |

| Proof (v36) | `MOVZ W8,#7` → wanderers fought at Lv7 |

| Shipping (v37) | `BL` cave at `0xC6F100`: singleton guard → `GetCharaAverageLv(10)` → `W8`, write-back to `+0x1bc4` |



UI cave (mission stickers) is unchanged from v25 and does **not** touch engage.



---



## GetCharaAverageLv



| | |

|--|--|

| Address | `0x2FD640` |

| Argument | Count in **W1** (`10` for top-10) |

| Result | Average in **W0** |

| Singleton helper | `0x19684` — null → crash if you call average too early |



### What crashed / broke in practice



| Approach | Result |

|----------|--------|

| Hook `GetStageBaseLevel` → average | Crash at boot / early |

| Average from create / FlCreate trampolines | Crash entering stages |

| Average from all numdraw (no LR filter) | Crash on save load |

| Clobber X0 in numdraw cave | Teleport crash |

| Force-7 on type enum / `unit+0x4` | Empty squads |

| Force-7 on FlCreate arg regs | Wrong player sprite |

| Write live `+0x9e0` from UI cave | Freeze on teleport |

| Force-7 entire digit module | Wanderers unchanged |

| Force-7 engage `+0x1bc4` load | **Wanderers Lv7** (correct channel) |



---



## Shipping mod (v37)



Under `Mods/enemy_level_scale/exefs/`:



| File | Effect |

|------|--------|

| `00_cave.pchtxt` | Cave `0xC6EFAC`: LR allowlist → average → rewrite stage DB `+0xC`; preserve X0 |

| `01_numdraw.pchtxt` | `0x5C9994` `MOV W20,W1` → `BL` UI cave |

| `02_engage.pchtxt` | `0x199AF0` → `BL` engage cave `0xC6F100` (average → wanderer level) |



Generators:



- Mission UI: `Scripts/_gen_level_scale_v25_preserve_x0.py` (embedded by v37)  

- Full ship: `Scripts/_gen_level_scale_v37_engage_avg.py`  



Install mirror:



`Mods/enemy_level_scale/exefs/` (copy that folder into Ryujinx and enable **Manage Mods**)



Keep **timer freeze** and **level scale** as separate mods. Archive old diags under `exefs/_archive/`.



### IPSwitch / pchtxt lessons



1. Same nsobid + `offset_shift` as timer mod or patches never match.  

2. Ryujinx applies **every** `*.pchtxt` in `exefs` — remove stale files.  

3. **ASCII-only** comments (no fancy Unicode).  

4. After changes: quit Ryujinx fully; clear this game’s **CPU cache** in Ryujinx.  

5. Confirm in logs: `Matching IPSwitch` + `Patching address offset …` for `00_cave`, `01_numdraw`, `02_engage`.



---



## How to verify



1. Quit Ryujinx fully; clear PTC if patches changed.  

2. Boot; confirm log matches all three pchtxts.  

3. Teleport or hover a liberation sticker — mission levels → top-10 average (may be vanilla before that first touch).  

4. Fight a wandering party — levels → same average.  

5. Check player overworld sprite still correct; squads non-empty.  

6. Teleport again — must **not** freeze.



---



## Quick address index



| Address | Role |

|---------|------|

| `0x28C19F8` | Stage DB base |

| `+0xC` / stride `0x50` | Per-stage level |

| `0x28C2F44` | Sorm level word (vanilla 38) |

| `0x5C9980` / `0x5C9994` | Shared numdraw; hook site for UI cave |

| `0xC6EFAC` | UI / DB-rewrite cave |

| `0xC6F100` | Engage average cave |

| `0x199AF0` | Field engage `LDR` party `+0x1bc4` |

| `0x1bc4` | Field party level token |

| `0x2D6E20` | Unit resolve / create |

| `0x313298` | `GetStageBaseLevel` (don’t early-hook to average) |

| `0x248338` | Story create base+OffsetLv |

| `0x315BC0` | `FlCreateEnemy` |

| `0x324440` | Live stage `+0x9e0` setter family |

| `0x2FD640` | `GetCharaAverageLv` (W1 = count) |

| `0x19684` | Chara singleton helper |

| `0x269740` | Timer tick BL (timer freeze NOP) |



---



## Related paths



| Path | Contents |

|------|----------|

| `Mods/enemy_level_scale/` | Active level mod + README |

| `Mods/battle_timer_freeze/` | Timer freeze control |

| `Extraction/tables/stage_enemy_levels.csv` | Wiki-oriented stage levels |

| `Extraction/exefs_out/main.decompressed.bin` | RE binary |

| `Scripts/_gen_level_scale_v37_engage_avg.py` | Shipping generator |

| `Scripts/_gen_level_scale_v25_preserve_x0.py` | Mission UI cave only |

| `Scripts/_gen_level_scale_*.py` | Older experiments / diags |

| `Docs/ELI5_enemy_levels.md` | Plain-language overview |

| `Docs/README.md` | Doc index |


