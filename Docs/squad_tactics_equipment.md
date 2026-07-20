# Squad composition, tactics, and equipment

US v1.0.5 `main` tables for editing later. Regenerate CSVs with the scripts under `Scripts/`.

## What you can edit today (static)

| What | Where | How |
|------|--------|-----|
| Squad members | UnitSet `0x28120B8`, stride `0x88` | 6 slots at `+0x3C` step `0xC`: CharaSet id |
| Which tactics **preset** | Same slots, word `+0x4` | EquipAiSet id (`0` = class default) |
| Unique / boss **items** | CharaSet `0x276DD68`, stride `0x48` | u16s at `+0x38..+0x3E` (4 gear slots). Empty = runtime CreateDefaultEquip — **there is no separate final-gear table** |
| Equip tier override | CharaSet `+0x1E` | Non-zero overrides UnitSet PARAMSET in `0x2CBFE8` (Culloran = 4 / BOSS → Lapis) |
| EXP reward flag | UnitSet `+0x10` | EXPTYPE — mission enemies are often `BOSS` even for fodder; **not** squad role |
| Enemy / gear PARAMSET | UnitSet `+0x14` | PARAMSET: 1 ZAKO / 2 NORMAL / 3 POWER / 4 BOSS. ZAKO clamps to DEFAULT band. Named bosses often force BOSS via CharaSet `+0x1E`. |
| Squad role (UI) | UnitSet symbol | Midboss / Boss / Zako / Reinforce / Enemy from the name |
| Tactic **lines** | EquipAiSet tactics slots `0x270AF48` + class skills `0xD36D94` | Preset list (markers/skills) or class defaults |

CSV dumps:

- `Extraction/tables/unitsets.csv` — `Scripts/export_unitsets.py`
- `Extraction/tables/charasets.csv` — `Scripts/export_charasets.py`
- `Extraction/tables/stage_unitsets.csv` — mission↔UnitSet join (`Scripts/export_stage_unitsets.py`)
- `Extraction/tables/equipaiset_presets.csv` / `equipaiset_lines.csv` / `equipaiset_fields.csv` / `equipai_if.csv` — `Scripts/export_equipaiset.py`
- `Extraction/tables/equiptype_by_class.csv` — guessed defaults (`Scripts/export_equiptype_defaults.py`)

Examples already verified:

- Culloran (`TK_C11_BOSS`): CharaSet sword+shield; ACC empties → CreateDefaultEquip BOSS: `DEFAULT_ACC1+44` → Lapis (slot 2), and `NONE+44` → `POWER_ACC2` → Gold Bangle (slot 3). Native does **not** skip class ET 0.
- C5 knight boss (`C5A_BOSS`): `LANCE_BOSS_01` + `ACC_AP_PP_03`; UnitSet uses EquipAiSet `C5_BOSS`
- Alain: `ACC_STORY_01` (Ring of the Unicorn)
- Generic `KNIGHT_M`: empty gear slots filled from class EQUIPTYPE × UnitSet PARAMSET × stage level

## Mission Squad Editor (GUI → Ryujinx mod)

1. Refresh data: `Scripts/sync_mission_editor_data.ps1`
2. Run GUI: `cd Tools/mission_editor && npm run dev` (see its README; preset
   walkthrough: `Tools/mission_editor/PRESET_EDITOR.md`)
3. Edit gear / tactics (searchable dropdowns). EquipAiSet `0` or shared presets allocate a private row on edit.
4. **Export Ryujinx mod** in the GUI (writes `Extraction/editor/mission_edits.json` + `Mods/<name>/`), or download edits JSON and run `python Scripts/export_mission_mod.py --mod-name my_mod`
5. Install folder under `%AppData%\Ryujinx\mods\contents\010069401adb8000\`

Joined document: `Extraction/editor/mission_squads.json` (`build.gear_policy = charaset_then_createdefault`).

## EquipAiSet tactic lines

Preset **names/ids** are static (`_UcEnum_EquipAiSet.inc`, 358 entries).

### Static tables (vanilla lines)

| | EquipAiSet meta | **Tactics slots** | Skill AI | Class skills |
|--|--|--|--|--|
| Base | `0x2787F28` | **`0x270AF48`** | `0x27AAE78` | `0xD36D94` |
| Stride | `0x130` | **`0x48`** | `0x100` | `0x8C` |
| Getter | `0x124A9C` | **`0x229B4`** | `0x124ACC` | — |
| Count | 358 presets | 358 (id-indexed) | 172 profiles | 74 classes |

Unit init (`~0xDCAE0`): if UnitSet EquipAiSet id (`unit+8`) ≠ 0 → apply tactics-slot
table via `0xDDB90` and **skip** class+item builder `0xDD610`. Id 0 → `0xDD610`.

Apply `0x571390` still reads EquipAiSet counts at `+0x0A` / `+0x0C` (enable slots)
and Skill-AI at `+0x04`.

#### Tactics-slot row (`0x270AF48`, stride `0x48`) — **authoritative preset list**

8 entries × 8 bytes (slots 0..7):

| Rel | Type | Meaning |
|-----|------|---------|
| `+0x00` | u16 | IF0 |
| `+0x02` | u16 | IF1 |
| `+0x04` | u32 | Skill ref: `EQUIPAI_ACTIVE/PASSIVE_SKILL_LVn` (3..10) **or** concrete `BT_SKILLID` |

Marker refs resolve to the class skill for that action. Explicit skills (e.g. C12
`PAS_LIFE_DIVIDE` 360 with IF `HP_50PER_LOWER` / `MY_HP_50PER_HIGHER`) appear as-is.
Slot IF 0/0 means **no condition** (does not fall back to skill-default `+0xAC/+0xB0`).

Fixture — EquipAiSet `58` `C12_BOSS` (Monica / Radiant Knight @ stage Lv12):

1. Active LV2 → Heal (no IF)
2. Active LV1 → Hache (no IF)
3. Skill 360 Lifeshare (`HP_50PER_LOWER`, `MY_HP_50PER_HIGHER`)
4. Passive LV2 → Holy Guard (locked when level &lt; 15)
5. Passive LV1 → Magick Barrier

#### EquipAiSet meta row (`0x2787F28`, stride `0x130`)

Same numeric index is also used as a **skill row** (`EquipAiSet[skill_id]`). Do not
treat preset-id condition blocks as unit Active-slot IF overlays.

| Offset | Type | Meaning |
|--------|------|---------|
| `+0x00` | u32 | EquipAiSet / skill id |
| `+0x04` | u32 | Skill-AI profile id (`0x27AAE78`, or 0) |
| `+0x0A` | s16 | Enable count A |
| `+0x0C` | s16 | Enable count B |
| `+0x2C` / `+0x50` / `+0x74` | 0x24×3 | Skill-effect condition blocks (not tactics UI rows) |
| `+0x98` | u32 | Group mode (1 or 2) |
| `+0xAC` / `+0xB0` | u32 | Per-**skill** default IF0/IF1 (class-default path only) |
| `+0xBC` / `+0xE4` / `+0x108` | i32 | Global target priority (not a tactics row) |
| `+0x128` | u32 | Flags bitfield |

Editor line synthesis (`equipaiset_lines.csv` / `class_default_tactics_lines.csv`):

- `export_equipaiset.py` overlays `Mods/class_editor/exefs/main.pchtxt` before
  exporting, so the mission editor reflects the currently installed class edits.
- **EquipAiSet id ≠ 0:** tactics list from `0x270AF48[id]` (markers + explicit skills).
- **EquipAiSet id = 0:** class learn pool at `0xD36D94` via `0xDD610`:
  - **Order:** Active slots **high→low**, then item-granted skills, then Passive **high→low**
  - Per-skill IF0/IF1 at `EquipAiSet[skill_id] +0xAC / +0xB0`
  - Item skills from `0x2716168` stride `0xB8`, skill at `+0x28`
- `class_skills.csv` = learn pool; `item_skills.csv` = item→skill grants
- Overrides in `equipaiset_line_overrides.json` win over vanilla (written to `0x270AF48`)

The editor separates the two writable scopes:

- **Class defaults:** class skill slots/learn levels at `0xD36D94`; default IFs
  at `EquipAiSet[skill_id] +0xAC/+0xB0`. Both are global.
- **EquipAiSet presets:** edits change the shared `0x270AF48` tactics-slot list.
  A mission-unit edit allocates a private id when needed.

Example — C11 Melisandre squad (EquipAiSet 0, Lv11):

- Fighter: Warding Slash · Quick Guard · Arrow Cover
- Witch: Magick Missile · Icebolt · Magick Conferral (IFs: Heavy / Heavy+2 enemies / none)
- Melisandre: Keen Edge · Artenie Strike (Stingray, Scout) · Parry · Hastened Strike (Scout)

Example — C11 midboss Shaman:

- Offensive Curse · Passive Curse · Quick Curse (learned at 10; all equipped when level allows)

## EQUIPTYPE / default zako gear

Empty CharaSet gear slots use CreateDefaultEquip **at runtime**. The editor resolves the same path for display (marked `from_equiptype`):

| | |
|--|--|
| Class → slot equiptypes | `0xD2DFC8` stride `0x58`, s16s at `+0x44..+0x4A` |
| EQUIPTYPE → item | `0xD13E30` stride `0x0C`, 3 u16s (level bands) |
| Level → column | `0x123844`: lv 1–14 / 15–27 / 28–50 |
| Equip tier | Native `0x2CBFE8` PARAMSET + CharaSet `+0x1E` + clamp. Companions only bump NORMAL→POWER when another UnitSet member has `+0x1E` BOSS (Sorm boss party / Wyvern). Midboss packs without that stay NORMAL — no Lapis. |
| NONE quirk | Class ET `0` still indexes `tier*11 + 0` (e.g. BOSS → EQUIPTYPE 44 `POWER_ACC2` / Gold Bangle) |
| ACC gate | Skip default accessories when CharaSet id ∈ 1..560 (`0x124898`) and item is ACC-range (`0x30c2c`) |

CSV: `equiptype_items.csv`, `class_equiptypes.csv`, `charasets.csv` (`equip_param_override`).


## Shared CharaSet warning

Templates like `KNIGHT_M` are global. The mod exporter **duplicates** into a free CharaSet row when `duplicate_if_shared` is set so one mission edit does not rewrite every user of that template.

## Patch conventions

ExeFS `.pchtxt` uses `@flag offset_shift 0x100` and nsobid `C841FFE2717FF03A13990480C51DA73F091C04FA`. For this decompressed `main`, file offset ≈ VA when writing patch addresses.

EquipAiSet line edits from the mission exporter patch words inside `0x2787F28 + id*0x130`.
Never patch EquipAiSet **id 0** (class default): the GUI/exporter allocates a free preset and retargets UnitSet `+0x4`. Shared presets duplicate-on-edit the same way.
