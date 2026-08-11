# Squads, tactics, and equipment

How Unicorn Overlord builds an enemy squad, and how the **Mission Squad Editor**
changes that. Written for someone who has played the game but has never looked
at its data.

You do not need the hex addresses in the first half of this doc. They are at the
end for later.

## The picture

A fight is not “a list of final soldiers with final swords.” The game stores
**templates** and fills in the rest when the battle loads.

```text
Mission  (e.g. The Blade of House Meillet)
  └── UnitSet  = one squad, 6 seats (formation)
        └── each seat:
              CharaSet     = who (Soldier, Witch, Melisandre, …)
              EquipAiSet   = which tactics list (or 0 = class defaults)
              flags
```

**Example — vanilla Blade of House Meillet (Melisandre’s map)**

Most squads are generic templates (Fighter, Swordsman, Witch, …) on tactics
preset **0**. The boss UnitSet (`…_MERIZAND`) seats **Melisandre** (named
CharaSet `C11_BOSS`) with Colm and two Witches — still preset **0** in vanilla,
not a unique tactics list.

If you change a shared template’s gear (e.g. blank `WITCH_F`), **every mission
that uses that same template** changes, unless the exporter can copy it to a
private row first.

## Formation

Same layout as in-game: **Back** row on top, **Front** on bottom.
Left / Middle / Right match the battle screen.

Empty seats are allowed. Swapping two seats in the editor swaps who stands where.

---

## Gear: two different sources

Each person has **four item slots** (weapon + accessories). For each slot the
game asks:

1. Does this CharaSet already name an item? → use that item.  
   (Boss unique weapons, story rings, anything you typed in the editor.)
2. Is the slot **empty** (item id 0)? → run **CreateDefaultEquip**.

There is no third “final gear” table. What you see in battle is (1) or (2).

**Example (vanilla)**

| Unit | What’s in the CharaSet | What you see at Meillet (Lv 11) |
|------|------------------------|----------------------------------|
| Generic Hoplite / Swordsman | all four slots empty | Bronze Spear or Bronze Sword, Bronze Bangle (CreateDefaultEquip) |
| Melisandre | **Stingray**, **Vitality Talisman**, **Lapis Pendant** | Those three named items (unpromoted Swordsman: weapon + two acc; no 4th slot) |
| Alain | **Ring of the Unicorn** (story accessory) | Always that ring |

So: **empty slots scale with level and equip tier. Named items do not.**
If the mission level were 20, the generic Swordsman would move to Iron Sword;
Melisandre would still hold Stingray.

### Equip tier (PARAMSET)

**Equip tier** on the UnitSet (sometimes overridden on the CharaSet) picks the
default-gear band for empty slots:

Note: ZAKO is usually used by the reinforcement spawns that infinitely spawn from forts. NORMAL is usually used by the weaker enemies in a mission.

| Tier | Typical empty-slot Soldier (low level) |
|------|----------------------------------------|
| DEFAULT (ZAKO clamps here) | Bronze Spear, Bronze Bangle |
| **NORMAL** (most mission fodder) | Bronze Spear, Bronze Bangle |
| **POWER** | Bronze Spear, **Lapis Pendant**, Bronze Bangle |
| **BOSS** | Boss-band accessories (Lapis, sometimes a 3rd slot fill) |

Melisandre’s boss pack is still PARAMSET **NORMAL**. The witches standing
with Melisandre pick up Lapis from the default table because they share her
pack — fodder squads on the same map stay Bronze Bangle only.

### Level bands (the three columns)

Empty slots also pick a **column** from the unit’s level:

| Level | Column | Example `NORMAL_SWORD` |
|-------|--------|-------------------------|
| 1–14 | 0 | Bronze Sword |
| 15–27 | 1 | Iron Sword |
| 28–50 | 2 | Steel Sword |

If a level-scale mod raises a Meillet Hoplite from Lv 11 → Lv 20 **and** their
weapon slot is still empty, they automatically get the mid-band spear (Iron).
If that slot had a named item (like Melisandre’s Stingray), it would not change.

You cannot add a fourth band without rewriting the game code. You *can* change
what sits in the three columns (Default gear tab).

### Why class rows say DEFAULT_LANCE (and that is OK)

`class_equiptypes` lists Soldier as `DEFAULT_LANCE`, `DEFAULT_ACC1`, …
That does **not** mean “Soldiers always use the DEFAULT band.”

It means “slot 0 is a **lance-type** slot.” The game then does:

```text
row  = class_slot_base + (tier × 11)
item = that row’s column for this level
```

| Class stores | NORMAL (+22) | POWER (+33) | BOSS (+44) |
|--------------|--------------|-------------|------------|
| `DEFAULT_SWORD` | `NORMAL_SWORD` | `POWER_SWORD` | `BOSS_SWORD` |
| `DEFAULT_LANCE` | `NORMAL_LANCE` | `POWER_LANCE` | `BOSS_LANCE` |
| `DEFAULT_SWORD_M` | `NORMAL_SWORD_M` | … | mixed phys/magic |

**Example — Elheim:** Elf Fencers/Archers use the `_M` family, so empty slots
become Greatwood Sword/Bow. Human Thieves in the same region still use plain
`NORMAL_SWORD` → Iron Sword at that level. Same default system, different
*family*.

The `ENEMY_*` rows (the +11 band) exist in the table but CreateDefaultEquip
**does not use them**: ZAKO is clamped to DEFAULT.

The editor does **not** let you change class slot types (we do not want Soldiers
to start wielding swords by accident). You only edit the **item columns** on
those rows.

### Editing default gear (what most people want)

**Default gear** tab = the 56 EQUIPTYPE rows × 3 level columns.

**Example:** “I want early-game swords to be Recruit’s Shortsword.”

1. Edit **`NORMAL_SWORD`** column 0 (most mission enemies).  
2. Also edit **`DEFAULT_SWORD`** if you care about ZAKO / clamped-DEFAULT.  
3. Edit **`POWER_SWORD` / `BOSS_SWORD`** only if those tiers should change too.  
4. Elf hybrids are **`NORMAL_SWORD_M`**, not `NORMAL_SWORD`.

Editing only `DEFAULT_SWORD` and then staring at a Cornia Fighter will still
show a Bronze Sword — they are on **NORMAL**.

This is **global**: every empty-slot unit that lands on that row changes, not
just one mission.

Mission-unit gear *preview* in the UI is computed when data is built. After
band edits, re-sync data if you want the preview to match; the exported mod
still applies in-game.

### Named gear on one unit

On **Mission units**, changing a dropdown writes that item onto the **CharaSet**.
**Restore default** puts the vanilla CharaSet / empty-slot preview back and
drops that override from the export.

**Shared templates:** `KNIGHT_M`, blank Soldiers, etc. are reused everywhere.
The exporter tries to **copy** the template to a free CharaSet so you do not
rewrite every Knight in the game. If there are no free rows, it warns and would
edit in place.

### Why edited accessories used to duplicate (and why exports fix it)

Vanilla equips **weapons** into a fixed slot, but **accessories** used “find a
free slot” after planting class defaults. If you write a custom accessory onto
a generic template (ids above 560, like Meillet’s blank Witch), the default
Bronze Bangle can already occupy ACC1 — your item never lands, and you can end
up with **two Bronze Bangles**.

Every mission-squad export includes a small code patch so accessories go into
**fixed slots** (like weapons already did). You do not install a separate fix
mod.

---

## Tactics: preset 0 vs a named list

Each seat also stores an **EquipAiSet id**.

| Id | What the unit actually uses in battle |
|----|----------------------------------------|
| **0** | This class’s skills (that they have learned at this level) **plus** skills granted by their gear |
| **Any other id** | **Only** that preset’s list of up to 8 lines. Class skills are skipped. Gear skills appear **only** if you put that skill on the preset yourself |

**Example**

- Vanilla Meillet **Witch** (preset **0**): Magick Missile, Icebolt, Magick
  Conferral from the class, plus anything her staff/accessories grant.
- Vanilla **Monica** (`C12_BOSS`, a named preset): only that preset’s list
  (Heal, Hache, Lifeshare, …). Item skills are **not** auto-added; Lifeshare is
  on the list because the preset names it explicitly.

**Empty named preset:** assigning a brand-new empty id is not “do nothing.”
It is “use this empty list” → **no tactics in battle**. Fill it before you
assign it. Creating it and leaving it unassigned is fine.

### Markers vs a specific skill

A preset line is: **skill + IF0 + IF1**.

The skill is either:

- A **marker**: “whatever this class has as Active Lv1.” If you later change
  the class’s Active 1 from Icebolt to Fireball, every preset that still says
  “Active Lv1” follows.
- A **specific skill**: “Lifeshare, period.” Used when a named preset would
  otherwise never pick up an item skill.

IF 0 / 0 means “no extra condition.”

**Example — Monica’s `C12_BOSS` preset**

1. Active Lv2 → Heal  
2. Active Lv1 → Hache  
3. **Lifeshare** (specific id) when HP is low  
4. Passive Lv2 → Holy Guard (only if she is high enough level to have learned it)  
5. Passive Lv1 → Magick Barrier  

### Class defaults vs presets in the editor

| Tab | What you change | Who it hits |
|-----|-----------------|-------------|
| **Class defaults** | The class skill slots and each skill’s default IFs | Every unit still on preset 0, **and** every marker in named presets |
| **EquipAiSet presets** | One named list of 8 lines | Every unit pointing at that preset id |
| **Mission units** | This seat’s CharaSet, gear, and which preset id it uses | That seat (gear may still be a shared template) |

If a preset is used by many units, editing it from a mission seat **forks** a
private copy on export so you do not rewrite every user of `C12_BOSS`.

---

## Using the editor (short)

1. Double-click `run-editor.bat` (or see [Tools/mission_editor/README.md](../Tools/mission_editor/README.md)).
2. **Mission units** — pick a map, a squad, a seat. Swap who stands there, edit
   gear, pick preset 0 / a named preset / create one.
3. **Default gear** — change Bronze→Recruit’s Shortsword on `NORMAL_SWORD`, etc.
4. **Export Ryujinx mod** — writes `Mods/<name>/exefs/main.pchtxt`.
5. Copy that folder into Ryujinx, enable it under **Manage Mods**, fully quit,
   then boot again.

More preset walkthroughs: [PRESET_EDITOR.md](../Tools/mission_editor/PRESET_EDITOR.md).

---

## Glossary

| Term | Meaning |
|------|---------|
| **Stride** | Size of one table row in bytes. Entry `id` lives at `base + id × stride` |
| **Word** | 4 bytes. **Half** = 2 bytes (item ids are halves) |
| **PARAMSET** | UnitSet field that chooses DEFAULT/NORMAL/POWER/BOSS for empty gear |
| **EXPTYPE** | A different UnitSet field (EXP reward). Often says BOSS even on fodder. Not gear by itself |
| **CreateDefaultEquip** | Runtime fill for empty CharaSet slots |

---

## Reference (when you want the guts)

US v1.0.5 `main`. CSV dumps live under `Extraction/tables/` (scripts in `Scripts/`).

### Tables you can think of as “the data”

| What | Where in `main` | Notes |
|------|-----------------|--------|
| Squad seats | UnitSet `0x28120B8`, stride `0x88` | 6 slots at `+0x3C`, each `0xC` bytes: CharaSet, EquipAiSet, flags |
| Named items | CharaSet `0x276DD68`, stride `0x48` | Four u16s at `+0x38..+0x3E`. 0 = default-fill |
| Equip tier override | CharaSet `+0x1E` | Non-zero beats UnitSet PARAMSET |
| PARAMSET | UnitSet `+0x14` | 1 ZAKO / 2 NORMAL / 3 POWER / 4 BOSS; ZAKO clamps to DEFAULT |
| EXPTYPE | UnitSet `+0x10` | Rewards; not the same as PARAMSET |
| Named tactics list | `0x270AF48`, stride `0x48` | 8 × (IF0, IF1, skill) |
| Preset / skill meta | `0x2787F28`, stride `0x130` | Per-skill default IFs at `+0xAC / +0xB0` |
| Class skill slots | `0xD36D94`, stride `0x8C` | What markers resolve to |
| Class slot *types* | `0xD2DFC8 + 0x44` | DEFAULT_LANCE etc. Not edited in the GUI |
| EQUIPTYPE → items | `0xD13E30`, stride `0x0C` | 3 u16s = the three level columns |

Preset **0** is never patched as a body. The editor allocates a free preset id
instead.

### How empty slots pick an item

```text
tier   = PARAMSET, then CharaSet +0x1E, then clamp to 2–4 or 0
row    = class_slot_base + tier×11
column = level 1–14 / 15–27 / 28–50
item   = equiptype_items[row][column]
```

Accessories on CharaSet ids **1–560** skip some default ACC fills. Ids above
that (many named/reused enemy templates) do not.

### Gear init (why accessories needed a code fix)

At unit init the game:

1. Pre-fills class defaults into the equip container.
2. Then, per slot: keep a non-zero CharaSet item, else the default.
3. Weapons go to a **fixed** slot index. Vanilla **accessories** used “first
   free slot,” which collided with the pre-fill.

Exports NOP the six branches that divert to that free-slot search
(`0xDD138`, `0xDD150`, `0xDD198`, `0xDD1B0`, `0xDD1F8`, `0xDD210`).

### Patch files

```text
@nsobid-C841FFE2717FF03A13990480C51DA73F091C04FA
@flag offset_shift 0x100
```

Copy the exported mod folder into Ryujinx and enable it under **Manage Mods**.

### Code map

| Area | File |
|------|------|
| Joined editor data / gear preview | `Scripts/build_mission_squads_json.py` |
| Export + accessory NOPs + default-gear patches | `Scripts/export_mission_mod.py` |
| GUI | `Tools/mission_editor/src/App.tsx` |
| Disassemble gear/tactics | `Scripts/_disasm_equipai.py` |

Suggested order if you want to follow along in code: UnitSet seats → CharaSet
items → default-gear rows → preset 0 vs named lists → exporter.
