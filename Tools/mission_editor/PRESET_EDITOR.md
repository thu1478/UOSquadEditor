# EquipAiSet preset editor — user guide

This guide covers the **EquipAiSet presets** tab in the Mission Squad Editor:
finding presets, editing tactics slots, creating new presets, assigning them to
mission units, and exporting a Ryujinx mod.

If UnitSet / CharaSet / “preset 0” are new, start with
[`Docs/squad_tactics_equipment.md`](../../Docs/squad_tactics_equipment.md)
(plain-language examples). Addresses are in that doc’s **Reference** section.
For setup (`run-editor.bat` / `npm run dev`), see [`README.md`](README.md).

---

## 1. Mental model (read this first)

Every mission unit has an **EquipAiSet id** on its UnitSet slot. That id picks
**how** the game builds the tactics list you see in battle.

| EquipAiSet id | What the game uses for tactics |
|---------------|--------------------------------|
| **`0` (class defaults)** | Class skill slots (Active/Passive Lv1–4) **plus** skills granted by equipped items. Gear skills are merged automatically. |
| **Any other id (named preset)** | **Only** that preset’s fixed slot list. Class defaults are **skipped**. Item skills are **not** auto-added unless you put that skill id into the preset yourself. |

So:

- Editing **Class defaults** changes every unit still on Preset `0` (and also
  changes what **markers** in non-zero presets resolve to).
- Editing a **named preset** changes every unit that points at that preset id
  (see **Affects**). Units on Preset `0` are untouched.
- An **empty** non-zero preset is dangerous: the unit gets **no tactics** in
  game. Creating an empty preset alone does nothing until you assign it.

### Markers vs concrete skills

Each tactics slot stores either:

1. A **class marker** (`Active Lv1` … `Active Lv4`, `Passive Lv1` … `Passive Lv4`)  
   Stored as skill refs `3`–`10`. At runtime (and in **Final results**) these
   resolve to whatever skill that class currently has in that slot — including
   after you load a class mod.
2. A **concrete skill** (e.g. Lifeshare / `PAS_LIFE_DIVIDE` id `360`)  
   Always that skill, regardless of class. Use this for item skills you want
   on a non-zero preset, or for any skill that is not “whatever the class has
   in slot X”.

**Example — vanilla `C12_BOSS` (id 58):**

| Slot | Stored in preset | Resolves to (White Knight) |
|------|------------------|----------------------------|
| 0 | marker Active Lv2 | Heal |
| 1 | marker Active Lv1 | Hache |
| 2 | **skill 360** Lifeshare + IFs | Lifeshare (hardcoded; not from gear) |
| 3 | marker Passive Lv2 | Holy Guard |
| 4 | marker Passive Lv1 | Magick Barrier |

The four class lines are *not* stored as “Heal / Hache / …”; they are markers.
Lifeshare **is** stored by id, because a non-zero preset would otherwise never
pick it up from the accessory.

---

## 2. Finding the right preset

Open **EquipAiSet presets**.

### Filter by story mission

1. Use the **Mission** dropdown (e.g. “The Unyielding Shield”).
2. The left list shows only presets used by that mission’s units.
3. Each row shows how many units in that mission use it and their names.
4. **Clear** returns to the full catalog.

From **Mission units**, select a mission and click **Presets for mission** —
same filter, one click.

### Text search

The search box matches:

- preset id / symbol
- unit names, classes, squad / UnitSet symbols
- mission / stage names on references

Example: type `Yahna`, `C12_BOSS`, or `Unyielding`.

### Affects list

Selecting a preset shows **Affects** — every UnitSet slot that uses it. Click a
row to drive the **Final results** preview (correct class + level for that
reference). With a mission filter active, Affects defaults to that mission’s
units; use **Show all refs** if the preset is shared with other content.

---

## 3. The preset panel layout

```
┌─────────────────────────────────────────────┐
│ Preset title + id / usage                   │
│ Affects  — pick a unit for preview          │
│ (a) Editable preset effects  — the real edit│
│ (b) Final results            — resolved view│
└─────────────────────────────────────────────┘
```

### (a) Editable preset effects

This is the authoritative slot list written to the game (`0x270AF48`). Each row:

| Field | Meaning |
|-------|---------|
| **Slot** | Index `0`–`7` (order in the tactics UI). |
| **Skill** | Class marker **or** concrete skill (searchable). Markers show `→ Heal` etc. when a reference is selected. |
| **IF0 / IF1** | Conditions for that line. `0` / `(none)` = no condition. |
| **Remove** | Deletes that row from the preset. |
| **Add tactics slot** | Appends a new row (default: Active Lv1 marker). |

Edits apply immediately in the UI. They are recorded in the edit log and written
on **Export Ryujinx mod**.

### (b) Final results

Read-only preview of what the selected **Affects** unit would actually get:

- markers → real skill names for that unit’s class, tagged **`class slot (= default)`**
- learn-level locks (skills not yet unlocked at the assumed / stage level)
- your IF0/IF1 as stored on the slot
- explicit skills the class does **not** have are flagged **`not in class — needs gear`**
  with a ⚠ — a preset can’t grant a skill, so those rows are inert unless the
  unit gets the skill from equipment

> **Marker-only warning.** If every effect is a class-slot marker, the editor
> shows a warning: the preset resolves to the unit’s own class skills, so it
> plays **identically to default (id 0)**. To get different behavior, add an
> explicit skill, or change the slot order / IF conditions. This is the usual
> reason a newly assigned preset “still uses vanilla tactics.”

If you **Load mods folder…** (e.g. `Mods/class_editor`), markers re-resolve
against the patched class table live. That does **not** bundle those class patches
into the mission export — install class mods in Ryujinx separately unless you
also edited **Class defaults** in this editor.

---

## 4. Editing an existing preset

### Goal: change what every user of that preset gets

1. Find the preset (mission filter / search / open from a unit).
2. Pick a reference under **Affects** so Final results makes sense.
3. Edit rows under **(a)**:
   - change Skill (marker ↔ concrete skill)
   - change IF0 / IF1
   - **Remove** unwanted rows
   - **Add preset effect** for new lines
   - drag the `⋮⋮` handle to reorder effects
4. Watch **(b)** update.
5. Export when ready.

Effect order is the slot order. The editor assigns contiguous slots `0–7`
automatically, so slots cannot be duplicated or skipped.

**Shared presets** (usage &gt; 1) change **all** listed Affects entries. If you only
want one boss different, either:

- create a **new** preset and assign only that unit to it, or
- from the unit panel, edit in a way that **forks** a private EquipAiSet (see §7).

### Goal: remove a skill from tactics

Same idea: delete the row that produces that skill in **Final results**.

#### Worked example A — remove Lifeshare from `C12_BOSS`

1. Filter mission **The Unyielding Shield** (or search `C12_BOSS`).
2. Open preset **58 — C12_BOSS**.
3. In **(a)**, find the row whose Skill is **Lifeshare** (concrete id, not a marker).
4. Click **Remove** on that row.
5. **Final results** should now show four lines (Heal, Hache, Holy Guard, Magick Barrier) and no Lifeshare.
6. Export.

Both Yahna (C12) and Holonius (later reuse of the same preset) lose Lifeshare
unless you fork / create a private preset for only one of them.

#### Worked example B — remove a class skill (e.g. no Magick Barrier)

1. Same preset. Magick Barrier comes from marker **Passive Lv1**, not from the
   word “Magick Barrier” in the slot list.
2. Remove the row whose Skill is **Passive Lv1** (or whatever marker Final
   results maps to Magick Barrier for that class).
3. Do **not** expect removing Magick Barrier from **Class defaults** alone to
   clear it here — this preset lists the marker explicitly; clearing the class
   slot would make the marker resolve to empty/wrong for *all* markers of that
   type, which is usually the wrong tool.

#### Worked example C — unit on Preset 0 (no named preset)

Units with **0 — Class defaults (+ gear skills)** do **not** use the Presets tab
list for their body.

- To drop a **class** skill for everyone of that class: **Class defaults** tab →
  clear / change that Active/Passive slot.
- To drop an **item** skill: remove / change the gear that grants it on that
  unit (Mission units → Gear), or move the unit onto a **named preset** that
  omits that skill.
- To give one Preset-0 unit a custom list without touching the class: create a
  new preset (§5), fill slots, assign that unit.

#### Worked example D — “remove Heal but keep Active Lv2 as something else”

Don’t only think in resolved names. Either:

- change the **marker** to a different slot, or
- replace the marker with a **concrete** skill, or
- change **Class defaults** Active Lv2 for White Knight (affects all marker users).

---

## 5. Creating a new preset

### From the Presets tab

1. Click **New empty**.
2. You land on a temporary id (negative, e.g. `-1`) named `NEW_PRESET_N`.
3. Edit **New preset name** to give it a readable name. Vanilla preset names
   remain read-only.
4. **Affects** is empty — nothing uses it yet.
5. Add effects under **(a)** (markers and/or concrete skills + IFs), then drag
   them into the desired order.
6. Assign units later (§6).

Creating alone **does not** change the game. Export allocates a free real
EquipAiSet id and writes the slot table.

### From a mission unit

1. **Mission units** → mission → squad → unit.
2. **Tactics preset** dropdown → **Create new empty preset…**
3. Editor opens the new preset; fill slots **before** assigning if you can.
4. Back on the unit, pick the new preset from the dropdown (listed as
   `NEW_PRESET_N (new)` / `(new, empty)`).

If you assign while still empty, the UI warns: a non-zero empty preset **wipes**
tactics.

### What to put in a new preset

Typical boss-style list (mirrors `C12_BOSS`):

1. Active Lv2 / Lv1 markers (or concrete actives you want)
2. Any item skills you need as **concrete** skill ids (with IFs if desired)
3. Passive Lv2 / Lv1 markers

If you only list markers and no item skills, the unit will **not** get Lifeshare /
other accessory skills even if the gear still grants them in the inventory sense
for display — tactics come only from the preset list.

---

## 6. Assigning presets to units

On **Mission units**, open the unit → **Tactics preset**:

| Choice | Effect |
|--------|--------|
| **0 — Class defaults (+ gear skills)** | Vanilla builder: class + item skills. |
| Existing id / symbol | Point this UnitSet slot at that preset. |
| A `NEW_PRESET_*` you created | Assign the pending create (export allocates id). |
| **Create new empty preset…** | Create + jump to Presets (does not assign until you pick it). |

**Open in Presets tab** jumps to the current non-zero preset for editing.

After assignment, the unit panel’s tactics preview follows the same rules as
Final results (Preset 0 vs named list).

---

## 7. Shared presets and forking

Many presets have **usage &gt; 1** (same id on multiple UnitSets). Editing the
preset body in the Presets tab updates **all** of them on export.

From a **unit** panel, changing IF rows on a shared preset / Preset 0 is set up
to **fork**: export allocates a **private** EquipAiSet copied from the source so
other users of the vanilla id stay unchanged. The UI shows a hint when that will
happen.

Rule of thumb:

- Want **all** C12_BOSS users changed → edit preset **58** in Presets.
- Want **only Yahna** changed → new preset (or fork) + assign only her UnitSet.

---

## 8. Loading class mods for preview

**Load mods folder…** → pick e.g. `Mods/class_editor`.

- All `.pchtxt` under that folder are applied in memory.
- Marker → skill resolution in Final results updates to the modded class kit.
- **Clear mods** restores the baseline JSON.

Use this when your class mod swaps White Knight skills and you need to see what
`C12_BOSS` markers become. Exporting the mission mod still only patches what
*this* editor changed (UnitSets, preset slots, optional class edits from the
Class defaults tab).

---

## 9. Export, reset, install

1. Make edits (presets, assignments, gear, class defaults as needed).
2. Optionally set **Mod folder name**.
3. **Export Ryujinx mod** → writes under `Mods/<name>/` with `exefs/main.pchtxt`
   (same IPSwitch shape as `shop_editor` / `class_editor`: `@nsobid`,
   `@flag offset_shift 0x100`, `@enabled`, then contiguous address lines — **no
   blank lines**; Ryujinx 1.1.1403 stops applying patches after a blank). Readable
   change detail goes in `CHANGELOG.txt`; the mod folder also has
   `mission_editor_edits.json` for round-trip import.
4. Copy that mod folder into Ryujinx, enable it under **Manage Mods**,
   and fully quit/relaunch so ExeFS patches reload. Confirm in the log with
   `Matching IPSwitch patch 'main.pchtxt' in '<mod>'` plus
   `Patching address offset …` lines for your edited addresses.
5. **Reset changes** discards the in-editor edit log (does not delete an already
   exported mod folder).

**Download edits JSON** saves the edit log without running the exporter.

To continue an exported project, click **Import editor mod…** and pick the whole
exported **mod folder** — it finds `mission_editor_edits.json` inside (other files
like `.pchtxt` / `CHANGELOG.txt` are ignored). You can also select a single JSON
edits file directly, including older downloaded `mission_edits_*.json` files.
Import replaces the current unsaved edit set after confirmation.

Preset **0**’s body is never patched as a slot table; id `0` always means
“use class + gear builder”. New / edited non-zero presets patch
`0x270AF48` (and related meta). UnitSet assignment patches the EquipAiSet id on
the squad slot.

---

## 10. Recipes cheat sheet

| I want to… | Do this |
|------------|---------|
| Remove one skill from a boss preset | Presets → open preset → **Remove** that row in (a) → export |
| Remove Lifeshare but keep class kit | Remove the concrete Lifeshare row only |
| Stop using a whole preset on one unit | Mission units → set that unit to Preset **0** or another preset |
| Give one unit a custom list | **New empty** → fill slots → assign that unit |
| Change Heal for all White Knights on Preset 0 | **Class defaults** → White Knight Active slot |
| Change what Active Lv1 means inside `C12_BOSS` | Either edit class Active Lv1, or replace the marker with a concrete skill on the preset |
| Add an item skill to a named preset | **Add tactics slot** → pick the skill by official EN name (symbol shown as secondary, e.g. `#124 · ACT_CRASH`) → set IFs → export |
| Preview with a class overhaul mod | **Load mods folder…** → `class_editor` (or your folder) |
| Find all presets in a story map | Mission filter or **Presets for mission** |

---

## 11. Pitfalls

1. **Empty non-zero preset = no tactics.** Fill before assign, or keep Preset 0.
2. **Named presets ignore gear skills** unless hardcoded as skill ids.
3. **Markers are not skill names.** Removing “Heal” means removing/changing the
   marker (or class slot) that resolves to Heal.
4. **Shared usage.** Editing `C12_BOSS` hits every reference in Affects.
5. **Class defaults are global.** A class edit affects Preset 0 and every marker
   resolution for that class.
6. **Mission filter hides Preset 0.** Units on id 0 won’t appear as preset rows;
   open them under Mission units.
7. **Slot order matters** for the in-game tactics list order; use the Slot field
   / add order intentionally.

---

## 12. Quick walkthrough: “C12 boss without Lifeshare, only for Yahna”

1. **New empty** on Presets (or from Yahna’s unit dropdown).
2. Copy the spirit of `C12_BOSS` slots **without** Lifeshare, e.g.:
   - Active Lv2, Active Lv1, Passive Lv2, Passive Lv1  
   (or copy IFs from 58 if you need them on other lines).
3. Mission **The Unyielding Shield** → boss squad → Yahna.
4. Set **Tactics preset** to your new preset (not 58).
5. Confirm Final / unit preview: four class skills, no Lifeshare.
6. Leave other units on 58 if you want them unchanged.
7. Export.
