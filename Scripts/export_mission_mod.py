"""Export mission editor JSON diffs as a Ryujinx ExeFS .pchtxt mod.

Reads:
  Extraction/editor/mission_squads.json          (vanilla baseline join)
  Extraction/editor/mission_edits.json           (user edits from GUI)

Writes:
  Mods/<mod_name>/exefs/main.pchtxt
  Mods/<mod_name>/CHANGELOG.txt
  Mods/<mod_name>/mission_editor_edits.json
  Mods/<mod_name>/README.md

Patches UnitSet slots, CharaSet gear, and EquipAiSet static rows (0x2787F28).
Shared CharaSets / EquipAiSets are duplicated into free rows when requested.
Never patches EquipAiSet id 0 as a class-default body — allocate a new id.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Scripts"))
from export_equipaiset import (  # noqa: E402
    EQUIPAISET_BASE,
    EQUIPAISET_COUNT,
    EQUIPAISET_STRIDE,
    TACTICS_SLOT_BASE,
    TACTICS_SLOT_STRIDE,
    apply_lines_to_tactics_slots,
)

BASELINE = ROOT / "Extraction/editor/mission_squads.json"
EDITS = ROOT / "Extraction/editor/mission_edits.json"
MAIN = ROOT / "Extraction/exefs_out/main.decompressed.bin"
OVERRIDES = ROOT / "Extraction/editor/equipaiset_line_overrides.json"
MODS = ROOT / "Mods"

NSOBID = "C841FFE2717FF03A13990480C51DA73F091C04FA"
UNITSET_BASE = 0x28120B8
UNITSET_STRIDE = 0x88
CHARASET_BASE = 0x276DD68
CHARASET_STRIDE = 0x48
CHARASET_COUNT = 1388
# CharaSet 0 (UNKNOWN sentinel) and 1 (PLAYER_START, the protagonist slot) look
# "empty" (class 0, no gear) but are reserved by the engine. Overwriting them
# corrupts boot, so they must never be handed out as duplication targets.
RESERVED_CHARASETS = {0, 1}
GEAR_OFFS = (0x38, 0x3A, 0x3C, 0x3E)

# Engine fix: enemy accessory equip-slot placement (US v1.0.5).
# Unit init (0xDCD74) keeps non-zero CharaSet gear per slot, but equips
# ACCESSORIES via a "find first free slot" search (0x2CB590) instead of their
# fixed slot index. The default pre-fill pass (0xDD290) plants a default
# accessory (Bronze Bangle in ACC1) for CharaSets with id > 560, so the
# free-slot search collides -> duplicate accessory (e.g. two Bronze Bangles)
# and custom accessories are lost. NOP the two branches in each accessory
# equip loop (ACC1 / ACC2 / slot 3) that divert to the free-slot search so each
# slot equips into its own fixed index, overwriting the pre-fill. Weapon slot
# is untouched; empty slots still resolve to their per-slot default (boss
# default-accessory behavior preserved). Each NOP word = 0xD503201F.
ENGINE_FIX_NOP_ADDRS = (0xDD138, 0xDD150, 0xDD198, 0xDD1B0, 0xDD1F8, 0xDD210)
ENGINE_FIX_NOP_WORD = 0xD503201F

# CreateDefaultEquip tables (US v1.0.5)
CLASS_BASE = 0xD2DFC8
CLASS_STRIDE = 0x58
CLASS_ET_OFF = 0x44  # 4 × s16 equiptype bases
EQUIPTYPE_ITEM_BASE = 0xD13E30
EQUIPTYPE_ITEM_STRIDE = 0xC  # 3 × u16 level bands

N_IFS = 203
CLASS_SKILL_BASE = 0xD36D94
CLASS_SKILL_STRIDE = 0x8C
CLASS_ACTIVE_LEVELS = (0x20, 0x28, 0x30, 0x38)
CLASS_ACTIVES = (0x24, 0x2C, 0x34, 0x3C)
CLASS_PASSIVE_LEVELS = (0x50, 0x58, 0x60, 0x68)
CLASS_PASSIVES = (0x54, 0x5C, 0x64, 0x6C)
SKILL_DEFAULT_IF0_OFF = 0xAC
SKILL_DEFAULT_IF1_OFF = 0xB0


def pchtxt_word(va: int, value: int) -> str:
    return f"{va:08X} {struct.pack('<I', value & 0xFFFFFFFF).hex().upper()}"


def pchtxt_half(va: int, value: int) -> str:
    return f"{va:08X} {struct.pack('<H', value & 0xFFFF).hex().upper()}"


def reserved_charaset_ranges() -> list[tuple[int, int, int]]:
    """(charaset_id, start_va, end_va_exclusive) for engine-reserved rows."""
    ranges: list[tuple[int, int, int]] = []
    for cid in sorted(RESERVED_CHARASETS):
        start = CHARASET_BASE + cid * CHARASET_STRIDE
        ranges.append((cid, start, start + CHARASET_STRIDE))
    return ranges


def assert_no_reserved_charaset_writes(patches: list[str]) -> None:
    """Abort export if any binary patch would overwrite CharaSet 0/1.

    Those rows look empty but are live engine sentinels (PLAYER_START etc.).
    Overwriting them crashes boot — this is the last-line guard after the
    find_free_charasets / edited-flag filters.
    """
    ranges = reserved_charaset_ranges()
    for line in patches:
        if not line or line.startswith("//"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            va = int(parts[0], 16)
        except ValueError:
            continue
        for cid, start, end in ranges:
            if start <= va < end:
                raise SystemExit(
                    f"Refusing to export: patch `{line}` writes into reserved "
                    f"CharaSet {cid} (PLAYER_START/UNKNOWN). This would crash "
                    f"the game. Report this as a bug — no squad-editor edit "
                    f"should target that row."
                )


def find_free_charasets(
    blob: bytes,
    need: int,
    reserved: set[int],
    used: dict[int, int] | None = None,
) -> list[int]:
    """Return genuinely blank CharaSet rows safe to overwrite.

    A row only qualifies if its whole binary record is zeroed AND it is not a
    reserved sentinel or referenced by any baseline UnitSet. In practice this
    game ships no blank rows (0/1 are the only class-0 rows and are reserved),
    so this returns [] and callers fall back to editing the shared row in place.
    """
    free: list[int] = []
    for i in range(1, CHARASET_COUNT):
        if i in reserved or i in RESERVED_CHARASETS:
            continue
        if used and used.get(i, 0) > 0:
            continue
        off = CHARASET_BASE + i * CHARASET_STRIDE
        row = blob[off : off + CHARASET_STRIDE]
        if any(row):
            continue
        free.append(i)
        if len(free) >= need:
            break
    return free


def equipaiset_usage(baseline: dict) -> dict[int, int]:
    """Prefer catalog usage (all UnitSets); fall back to joined missions."""
    counts: dict[int, int] = {}
    for preset in baseline.get("equipaiset_presets") or []:
        eid = int(preset.get("id") or 0)
        usage = int(preset.get("usage") or 0)
        if eid and usage:
            counts[eid] = usage
    if counts:
        return counts
    for m in baseline.get("missions", []):
        for sq in m.get("squads", []):
            for sl in sq.get("slots", []):
                eid = int(sl.get("equipaiset_id") or 0)
                if eid:
                    counts[eid] = counts.get(eid, 0) + 1
    return counts


def find_free_equipaisets(
    blob: bytes, need: int, reserved: set[int], used: dict[int, int]
) -> list[int]:
    """Allocate ids with catalog usage 0 (high ids first).

    Prefer rows whose 0x130 meta + 0x270AF48 slots look empty; otherwise reuse
    unused named presets (still usage 0) by overwriting them.
    """
    empty: list[int] = []
    unused: list[int] = []
    for i in range(EQUIPAISET_COUNT - 1, 0, -1):
        if i in reserved or used.get(i, 0) > 0:
            continue
        off = EQUIPAISET_BASE + i * EQUIPAISET_STRIDE
        row_id = struct.unpack_from("<I", blob, off)[0]
        if row_id not in (0, i):
            continue
        skill_ai = struct.unpack_from("<I", blob, off + 0x04)[0]
        count_a = struct.unpack_from("<h", blob, off + 0x0A)[0]
        count_b = struct.unpack_from("<h", blob, off + 0x0C)[0]
        slot_off = TACTICS_SLOT_BASE + i * TACTICS_SLOT_STRIDE
        slot_row = blob[slot_off : slot_off + TACTICS_SLOT_STRIDE]
        slots_empty = all(
            struct.unpack_from("<I", slot_row, s * 8 + 4)[0] == 0 for s in range(8)
        )
        if skill_ai == 0 and count_a == 0 and count_b == 0 and slots_empty:
            empty.append(i)
        else:
            unused.append(i)
    return (empty + unused)[:need]


def normalize_lines(lines: list) -> list[dict]:
    out: list[dict] = []
    for index, ln in enumerate(lines):
        entry = {
            # Array order is authoritative. Slots are always contiguous and unique.
            "slot": index,
            "action": int(ln.get("action") or 3),
            "if0": int(ln.get("if0") or 0),
            "if1": int(ln.get("if1") or 0),
        }
        if ln.get("skill_id") is not None:
            entry["skill_id"] = int(ln["skill_id"])
        if ln.get("skill_symbol"):
            entry["skill_symbol"] = ln["skill_symbol"]
        if ln.get("skill_name"):
            entry["skill_name"] = ln["skill_name"]
        if ln.get("ref_kind"):
            entry["ref_kind"] = ln["ref_kind"]
        if ln.get("learn_level") is not None:
            entry["learn_level"] = int(ln["learn_level"])
        if ln.get("if0_symbol"):
            entry["if0_symbol"] = ln["if0_symbol"]
        if ln.get("if1_symbol"):
            entry["if1_symbol"] = ln["if1_symbol"]
        out.append(entry)
    return out


CLASS_MARKERS = {
    3: "class Active 1",
    4: "class Active 2",
    5: "class Active 3",
    6: "class Active 4",
    7: "class Passive 1",
    8: "class Passive 2",
    9: "class Passive 3",
    10: "class Passive 4",
}


def add_comment(patches: list[str], text: str) -> None:
    """Record a changelog-oriented comment in the patch list.

    Comments are stripped from main.pchtxt (detail lives in CHANGELOG). Do not
    insert blank spacer lines — Ryujinx 1.1.1403 IPSwitch stops applying ADDRESS
    patches after a blank line (working companion mods ship zero blanks).
    """
    clean = " ".join(str(text).split()).replace("/", " ")
    patches.append(f"// {clean}")


def describe_tactics_line(
    line: dict, skills: dict[int, str], ifs: dict[int, str]
) -> str:
    sid = int(line.get("skill_id") or line.get("action") or 0)
    ref_kind = str(line.get("ref_kind") or "")
    if ref_kind == "class_slot" or sid in CLASS_MARKERS:
        skill = CLASS_MARKERS.get(sid, f"class marker {sid}")
    else:
        # Prefer official catalog name over stale skill_name baked into edits.
        skill = (
            skills.get(sid)
            or str(line.get("skill_name") or line.get("skill_symbol") or "")
            or f"skill {sid}"
        )
    if0 = int(line.get("if0") or 0)
    if1 = int(line.get("if1") or 0)
    if0_name = str(line.get("if0_symbol") or "") or ifs.get(if0) or "none"
    if1_name = str(line.get("if1_symbol") or "") or ifs.get(if1) or "none"
    slot = int(line.get("slot") or 0) + 1
    return f"slot {slot}: {skill}; IF0={if0_name} ({if0}); IF1={if1_name} ({if1})"


def write_equipaiset_row(
    patches: list[str], blob: bytes, new_id: int, source_id: int, lines: list[dict]
) -> None:
    """Write a preset's tactics into 0x270AF48[new_id].

    IMPORTANT: an EquipAiSet/preset is defined *solely* by its tactics-slot row at
    0x270AF48 + id*0x48. The runtime apply routine (0xDDB90 -> getter 0x229B4)
    reads only that table; a nonzero unit+8 (EquipAiSet id) plus a valid slot row
    is all that is required.

    The table at 0x2787F28 (stride 0x130, getter 0x124A9C) is the *skill*
    definition table (indexed by skill id), NOT EquipAiSet metadata. Earlier
    versions copied a "meta" row there indexed by preset id, which silently
    corrupted skill rows whose id matched the reused preset id (e.g. skill 79
    Assaulting Blow, skill 202). We no longer touch that table.
    """
    if 0 < source_id < EQUIPAISET_COUNT:
        src_slots = bytearray(
            blob[
                TACTICS_SLOT_BASE
                + source_id * TACTICS_SLOT_STRIDE : TACTICS_SLOT_BASE
                + (source_id + 1) * TACTICS_SLOT_STRIDE
            ]
        )
    else:
        src_slots = bytearray(TACTICS_SLOT_STRIDE)
    apply_lines_to_tactics_slots(src_slots, lines, N_IFS)
    add_comment(patches, f"EquipAiSet {new_id} tactics slot table")
    slot_dst = TACTICS_SLOT_BASE + new_id * TACTICS_SLOT_STRIDE
    for off in range(0, TACTICS_SLOT_STRIDE, 4):
        patches.append(
            pchtxt_word(slot_dst + off, struct.unpack_from("<I", src_slots, off)[0])
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edits", type=Path, default=EDITS)
    ap.add_argument("--baseline", type=Path, default=BASELINE)
    ap.add_argument("--mod-name", default="mission_squad_editor")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if not args.edits.exists():
        raise SystemExit(f"No edits file: {args.edits}")
    baseline = (
        json.loads(args.baseline.read_text(encoding="utf-8"))
        if args.baseline.exists()
        else {}
    )
    edits = json.loads(args.edits.read_text(encoding="utf-8-sig"))
    blob = MAIN.read_bytes()

    charaset_users: dict[int, int] = {}
    unit_labels: dict[tuple[int, int], str] = {}
    charaset_labels: dict[int, list[str]] = {}
    for m in baseline.get("missions", []):
        for sq in m.get("squads", []):
            for sl in sq.get("slots", []):
                cid = int(sl["charaset_id"])
                charaset_users[cid] = charaset_users.get(cid, 0) + 1
                unit_name = str(
                    sl.get("chara_name") or sl.get("charaset_symbol") or f"CharaSet {cid}"
                )
                stage = str(m.get("stage_name") or m.get("quest_symbol") or "unknown mission")
                label = f"{unit_name} in {stage}"
                unit_labels.setdefault(
                    (int(sq.get("unitset_id") or 0), int(sl.get("slot") or 0)),
                    label,
                )
                labels = charaset_labels.setdefault(cid, [])
                if label not in labels:
                    labels.append(label)

    skill_labels = {
        int(x.get("id") or 0): str(x.get("name") or x.get("symbol") or "")
        for x in baseline.get("skills", [])
    }
    if_labels = {
        int(x.get("id") or 0): str(x.get("name") or x.get("symbol") or "")
        for x in baseline.get("equipai_if", [])
    }
    item_labels = {
        int(x.get("id") or 0): str(x.get("name") or x.get("symbol") or "")
        for x in baseline.get("items", [])
    }
    class_labels = {
        int(x.get("class_id") or 0): str(x.get("class_symbol") or "")
        for x in baseline.get("class_tactics", [])
    }
    preset_labels = {
        int(x.get("id") or 0): str(x.get("symbol") or "")
        for x in baseline.get("equipaiset_presets", [])
    }

    ea_used = equipaiset_usage(baseline)
    patches: list[str] = []
    notes: list[str] = []
    changes: list[str] = []
    reserved_cs: set[int] = set()
    reserved_ea: set[int] = set()
    dup_map: dict[int, int] = {}
    ea_map: dict[str | int, int] = {}
    allocated_ids: set[int] = set()

    unit_edits = edits.get("unitsets", [])
    chara_edits = edits.get("charasets", [])
    tactics_overrides = dict(edits.get("equipaiset_lines") or {})
    allocations = edits.get("equipaiset_allocations") or []
    creates = edits.get("equipaiset_creates") or []
    class_edits = edits.get("class_tactics") or []
    equiptype_item_edits = edits.get("equiptype_items") or []
    class_et_edits = edits.get("class_equiptypes") or []

    # Brand-new empty (or authored) presets: allocate free ids, write 0x270AF48.
    for create in creates:
        key = str(create.get("key") or "")
        if not key:
            notes.append("WARNING: equipaiset_create missing key")
            continue
        src = int(create.get("source_id") or 0)
        lines = normalize_lines(create.get("lines") or [])
        want = create.get("new_id")
        if want is not None and str(want).isdigit() and int(want) > 0:
            new_id = int(want)
        else:
            frees = find_free_equipaisets(blob, 1, reserved_ea, ea_used)
            if not frees:
                notes.append(f"WARNING: no free EquipAiSet for create {key}")
                continue
            new_id = frees[0]
        if new_id == 0:
            notes.append("WARNING: refusing EquipAiSet id 0 create")
            continue
        reserved_ea.add(new_id)
        allocated_ids.add(new_id)
        ea_used[new_id] = ea_used.get(new_id, 0) + 1
        symbol = str(create.get("symbol") or key)
        add_comment(
            patches,
            f"NEW PRESET: {symbol} -> EquipAiSet {new_id}; "
            f"{len(lines)} authored tactics slots",
        )
        for line in lines:
            patches.append(f"//   {describe_tactics_line(line, skill_labels, if_labels)}")
        write_equipaiset_row(patches, blob, new_id, src, lines)
        tactics_overrides[str(new_id)] = lines
        ea_map[key] = new_id
        temp_id = create.get("temp_id")
        if temp_id is not None:
            try:
                ea_map[int(temp_id)] = new_id
            except (TypeError, ValueError):
                pass
        change = (
            f"Created preset {symbol} as EquipAiSet {new_id} "
            f"(source {src}, {len(lines)} tactics slots)"
        )
        notes.append(change)
        changes.append(change)
        changes.extend(
            f"  - {describe_tactics_line(line, skill_labels, if_labels)}"
            for line in lines
        )

    for alloc in allocations:
        src = int(alloc.get("source_id") or alloc.get("from_id") or 0)
        lines = normalize_lines(alloc.get("lines") or [])
        want = alloc.get("new_id")
        if want is not None and str(want).isdigit() and int(want) > 0:
            new_id = int(want)
        else:
            frees = find_free_equipaisets(blob, 1, reserved_ea, ea_used)
            if not frees:
                notes.append(f"WARNING: no free EquipAiSet to allocate from {src}")
                continue
            new_id = frees[0]
        if new_id == 0:
            notes.append("WARNING: refusing EquipAiSet id 0 allocation")
            continue
        reserved_ea.add(new_id)
        allocated_ids.add(new_id)
        unit_label = unit_labels.get(
            (int(alloc.get("unitset_id") or 0), int(alloc.get("slot") or 0)),
            f"UnitSet {alloc.get('unitset_id', '?')} slot {alloc.get('slot', '?')}",
        )
        add_comment(
            patches,
            f"PRIVATE PRESET for {unit_label}: EquipAiSet {src} -> {new_id}",
        )
        for line in lines:
            patches.append(f"//   {describe_tactics_line(line, skill_labels, if_labels)}")
        write_equipaiset_row(patches, blob, new_id, src, lines)
        tactics_overrides[str(new_id)] = lines
        change = (
            f"Allocated private EquipAiSet {src} -> {new_id} for {unit_label} "
            f"({len(lines)} tactics slots)"
        )
        notes.append(change)
        changes.append(change)
        changes.extend(
            f"  - {describe_tactics_line(line, skill_labels, if_labels)}"
            for line in lines
        )
        if alloc.get("key"):
            ea_map[str(alloc["key"])] = new_id
        if src:
            ea_map[src] = new_id
        if alloc.get("unitset_id") is not None and alloc.get("slot") is not None:
            ea_map[f"{alloc['unitset_id']}:{alloc['slot']}"] = new_id

    for ce in chara_edits:
        cid = int(ce["charaset_id"])
        gear = ce.get("gear") or []
        # Skip CharaSet entries that carry no genuine user gear edit. The editor
        # used to record resolved (runtime CreateDefaultEquip) gear on every slot
        # change, which spuriously duplicated shared CharaSets. Real edits carry
        # an "edited" flag on the changed slot(s).
        if not any(g.get("edited") for g in gear):
            continue
        shared = charaset_users.get(cid, 0) > 1 and ce.get("duplicate_if_shared", True)
        target = cid
        if shared:
            if cid not in dup_map:
                frees = find_free_charasets(blob, 1, reserved_cs, charaset_users)
                if not frees:
                    shared_names = ", ".join(charaset_labels.get(cid, [])[:3]) or (
                        f"CharaSet {cid}"
                    )
                    warn = (
                        f"WARNING: CharaSet {cid} is shared by {charaset_users.get(cid, 0)} "
                        f"units and this game has no free CharaSet rows to duplicate into. "
                        f"Editing it in place changes gear for ALL of them ({shared_names})."
                    )
                    notes.append(warn)
                    changes.append(warn)
                else:
                    new_id = frees[0]
                    reserved_cs.add(new_id)
                    dup_map[cid] = new_id
                    src = CHARASET_BASE + cid * CHARASET_STRIDE
                    dst = CHARASET_BASE + new_id * CHARASET_STRIDE
                    affected = ", ".join(charaset_labels.get(cid, [])[:3])
                    add_comment(
                        patches,
                        f"Duplicate shared CharaSet {cid} -> {new_id}"
                        + (f" for {affected}" if affected else ""),
                    )
                    for off in range(0, CHARASET_STRIDE, 4):
                        val = struct.unpack_from("<I", blob, src + off)[0]
                        patches.append(pchtxt_word(dst + off, val))
                    notes.append(f"Duplicated CharaSet {cid} -> {new_id}")
                    target = new_id
            else:
                target = dup_map[cid]
        base = CHARASET_BASE + target * CHARASET_STRIDE
        affected = ", ".join(charaset_labels.get(cid, [])[:3]) or f"CharaSet {cid}"
        add_comment(patches, f"GEAR EDIT for {affected}; target CharaSet {target}")

        def _write_id(g: dict) -> int:
            # Only user-edited slots write their chosen item. Untouched slots
            # keep their true ROM value (rom_item_id, 0 for slots the game fills
            # at runtime), so we never bake resolved defaults into the CharaSet.
            if g.get("edited"):
                return int(g.get("item_id", 0))
            return int(g.get("rom_item_id", g.get("item_id", 0)) or 0)

        for gi, g in enumerate(gear[:4]):
            iid = _write_id(g)
            item_name = (
                str(g.get("item_name") or g.get("item_symbol") or "")
                or item_labels.get(iid)
                or ("empty" if iid == 0 else f"item {iid}")
            )
            patches.append(f"//   gear slot {gi + 1}: {item_name} ({iid})")
            patches.append(pchtxt_half(base + GEAR_OFFS[gi], iid))
        change = (
            f"Changed gear for {affected}: "
            + ", ".join(
                (
                    str(g.get("item_name") or g.get("item_symbol") or "")
                    or item_labels.get(_write_id(g))
                    or "empty"
                )
                for g in gear[:4]
            )
        )
        notes.append(change)
        changes.append(change)

    for class_edit in class_edits:
        class_id = int(class_edit["class_id"])
        class_base = CLASS_SKILL_BASE + class_id * CLASS_SKILL_STRIDE
        lines = normalize_lines(class_edit.get("lines") or [])
        class_name = class_labels.get(class_id) or f"class {class_id}"
        add_comment(
            patches,
            f"GLOBAL CLASS TACTICS EDIT: {class_name} ({class_id})",
        )
        for line in lines:
            patches.append(f"//   {describe_tactics_line(line, skill_labels, if_labels)}")

        # Class skill slots are global: all player/enemy units of this class use them.
        class_words: dict[int, int] = {}
        for level_off, skill_off in zip(CLASS_ACTIVE_LEVELS, CLASS_ACTIVES):
            class_words[level_off] = 0
            class_words[skill_off] = 0
        for level_off, skill_off in zip(CLASS_PASSIVE_LEVELS, CLASS_PASSIVES):
            class_words[level_off] = 0
            class_words[skill_off] = 0

        for line in lines:
            action = int(line.get("action") or 0)
            skill_id = int(line.get("skill_id") or 0)
            learn_level = max(1, int(line.get("learn_level") or 1))
            if 3 <= action <= 6:
                idx = action - 3
                level_off = CLASS_ACTIVE_LEVELS[idx]
                skill_off = CLASS_ACTIVES[idx]
            elif 7 <= action <= 10:
                idx = action - 7
                level_off = CLASS_PASSIVE_LEVELS[idx]
                skill_off = CLASS_PASSIVES[idx]
            else:
                notes.append(
                    f"WARNING: class {class_id} skips unsupported action {action}"
                )
                continue
            class_words[level_off] = learn_level
            class_words[skill_off] = skill_id

            # Defaults belong to the skill, not the class or unit.
            if 0 < skill_id < EQUIPAISET_COUNT:
                skill_row = EQUIPAISET_BASE + skill_id * EQUIPAISET_STRIDE
                patches.append(
                    pchtxt_word(skill_row + SKILL_DEFAULT_IF0_OFF, int(line.get("if0") or 0))
                )
                patches.append(
                    pchtxt_word(skill_row + SKILL_DEFAULT_IF1_OFF, int(line.get("if1") or 0))
                )
        for word_off, value in sorted(class_words.items()):
            patches.append(pchtxt_word(class_base + word_off, value))
        change = (
            f"Patched global class tactics for {class_name} ({class_id}): "
            f"{len(lines)} skill slots/default IF pairs"
        )
        notes.append(change)
        changes.append(change)
        changes.extend(
            f"  - {describe_tactics_line(line, skill_labels, if_labels)}"
            for line in lines
        )

    for et_edit in equiptype_item_edits:
        eid = int(et_edit.get("equiptype_id") or et_edit.get("id") or 0)
        if eid < 0:
            notes.append(f"WARNING: skip equiptype_items id {eid}")
            continue
        cols = [
            int(et_edit.get("item_col0_id") or 0),
            int(et_edit.get("item_col1_id") or 0),
            int(et_edit.get("item_col2_id") or 0),
        ]
        base = EQUIPTYPE_ITEM_BASE + eid * EQUIPTYPE_ITEM_STRIDE
        sym = et_edit.get("equiptype_symbol") or f"EQUIPTYPE_{eid}"
        add_comment(patches, f"EQUIPTYPE ITEMS: {sym} ({eid})")
        for col, iid in enumerate(cols):
            patches.append(pchtxt_half(base + col * 2, iid))
            patches.append(
                f"//   col{col} (lv band): {item_labels.get(iid) or iid}"
            )
        change = (
            f"Changed default gear band {sym} ({eid}): "
            + ", ".join(
                item_labels.get(iid) or str(iid) for iid in cols
            )
        )
        notes.append(change)
        changes.append(change)

    for cet in class_et_edits:
        class_id = int(cet.get("class_id") or 0)
        slots = cet.get("slots") or []
        if isinstance(slots, dict):
            # allow {0: et, 1: et, ...} or slot0_equiptype keys
            slot_ids = [
                int(
                    slots.get(s)
                    or slots.get(str(s))
                    or slots.get(f"slot{s}_equiptype")
                    or 0
                )
                for s in range(4)
            ]
        else:
            slot_ids = [int(x) for x in list(slots)[:4]]
            while len(slot_ids) < 4:
                slot_ids.append(0)
        class_name = class_labels.get(class_id) or f"class {class_id}"
        row = CLASS_BASE + class_id * CLASS_STRIDE + CLASS_ET_OFF
        add_comment(patches, f"CLASS EQUIPTYPES: {class_name} ({class_id})")
        for s, et in enumerate(slot_ids[:4]):
            patches.append(pchtxt_half(row + s * 2, et & 0xFFFF))
            patches.append(f"//   slot {s}: equiptype {et}")
        change = (
            f"Changed class equiptype bases for {class_name} ({class_id}): "
            f"{slot_ids[:4]}"
        )
        notes.append(change)
        changes.append(change)

    for ue in unit_edits:
        uid = int(ue["unitset_id"])
        uoff = UNITSET_BASE + uid * UNITSET_STRIDE
        for sl in ue.get("slots", []):
            si = int(sl["slot"])
            slot_off = uoff + 0x3C + si * 0xC
            cid = int(sl["charaset_id"])
            if cid in dup_map and sl.get("use_duplicate", True):
                cid = dup_map[cid]
            eid = int(sl.get("equipaiset_id", 0))
            alloc_key = sl.get("equipaiset_alloc_key")
            if alloc_key and alloc_key in ea_map:
                eid = int(ea_map[alloc_key])
            elif f"{uid}:{si}" in ea_map:
                eid = int(ea_map[f"{uid}:{si}"])
            elif eid in ea_map:
                eid = int(ea_map[eid])
            if eid < 0:
                # Still apply CharaSet/flags — skipping the whole row used to
                # leave the old unit in-game (e.g. Witch) after a Soldier swap.
                notes.append(
                    f"WARNING: unitset {uid} slot {si} unresolved temp "
                    f"EquipAiSet id {eid}; writing CharaSet/flags with preset 0"
                )
                eid = 0
            flags = int(sl.get("flags", 0))
            unit_label = unit_labels.get(
                (uid, si), f"UnitSet {uid} slot {si}"
            )
            preset_name = preset_labels.get(eid) or next(
                (
                    str(c.get("symbol") or "")
                    for c in creates
                    if ea_map.get(str(c.get("key") or "")) == eid
                ),
                "",
            )
            row = "Front" if si < 3 else "Back"
            # In-game UI: Left=2/5, Middle=1/4, Right=0/3
            col = ("Right", "Middle", "Left")[si % 3]
            pos = f"{row} {col}"
            add_comment(
                patches,
                f"UNIT EDIT: {unit_label}; {pos} (slot {si}); CharaSet {cid}; "
                f"preset {preset_name or 'EquipAiSet'} ({eid}); flags 0x{flags:X}",
            )
            patches.append(pchtxt_word(slot_off + 0x0, cid))
            patches.append(pchtxt_word(slot_off + 0x4, eid))
            patches.append(pchtxt_word(slot_off + 0x8, flags))
            if cid == 0:
                change = f"Cleared {unit_label} at {pos} (slot {si})"
            else:
                change = (
                    f"Changed {unit_label} at {pos} (slot {si}): CharaSet {cid}, "
                    f"preset {preset_name or 'EquipAiSet'} ({eid}), flags 0x{flags:X}"
                )
            notes.append(change)
            changes.append(change)

    if tactics_overrides:
        existing: dict = {}
        if OVERRIDES.exists():
            existing = json.loads(OVERRIDES.read_text(encoding="utf-8"))
        comment = existing.pop("_comment", None)
        for k, lines in tactics_overrides.items():
            try:
                eid = int(k)
            except ValueError:
                notes.append(f"WARNING: skip non-numeric EquipAiSet key {k}")
                continue
            if eid == 0:
                notes.append(
                    "WARNING: refusing to patch EquipAiSet id 0; use allocation"
                )
                continue
            if not (0 < eid < EQUIPAISET_COUNT):
                notes.append(f"WARNING: EquipAiSet id out of range: {eid}")
                continue
            existing[str(eid)] = normalize_lines(lines)
            if eid in allocated_ids:
                continue
            normalized = normalize_lines(lines)
            preset_name = preset_labels.get(eid) or "EquipAiSet"
            add_comment(
                patches,
                f"SHARED PRESET EDIT: {preset_name} ({eid}); "
                f"{len(normalized)} tactics slots",
            )
            for line in normalized:
                patches.append(
                    f"//   {describe_tactics_line(line, skill_labels, if_labels)}"
                )
            slot_base = TACTICS_SLOT_BASE + eid * TACTICS_SLOT_STRIDE
            slot_row = bytearray(
                blob[slot_base : slot_base + TACTICS_SLOT_STRIDE]
            )
            apply_lines_to_tactics_slots(slot_row, normalized, N_IFS)
            for off in range(0, TACTICS_SLOT_STRIDE, 4):
                old = struct.unpack_from("<I", blob, slot_base + off)[0]
                new = struct.unpack_from("<I", slot_row, off)[0]
                if old != new:
                    patches.append(pchtxt_word(slot_base + off, new))
            change = (
                f"Patched preset {preset_name} ({eid}): "
                f"{len(normalized)} tactics slots"
            )
            notes.append(change)
            changes.append(change)
            changes.extend(
                f"  - {describe_tactics_line(line, skill_labels, if_labels)}"
                for line in normalized
            )
        if comment:
            existing = {"_comment": comment, **existing}
        OVERRIDES.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")

    # Always bundle the enemy accessory equip-slot fix so exported gear sticks
    # in-game (custom accessories otherwise get duplicated/replaced by defaults).
    for addr in ENGINE_FIX_NOP_ADDRS:
        patches.append(pchtxt_word(addr, ENGINE_FIX_NOP_WORD))

    seen: set[str] = set()
    uniq_patches: list[str] = []
    for p in patches:
        if not p or p.startswith("//"):
            if not (not p and uniq_patches and uniq_patches[-1] == ""):
                uniq_patches.append(p)
        elif p not in seen:
            seen.add(p)
            uniq_patches.append(p)
    patches = uniq_patches
    assert_no_reserved_charaset_writes(patches)
    patch_count = sum(1 for p in patches if p and not p.startswith("//"))

    out_dir = args.out or (MODS / args.mod_name)
    exefs = out_dir / "exefs"
    exefs.mkdir(parents=True, exist_ok=True)
    # Ryujinx 1.1.1403 IPSwitchPatcher defaults enabled=false (silent skip until
    # @enabled). Use main.pchtxt like shop/char editors. Keep pchtxt comments
    # minimal — verbose // blocks have been observed to yield Match-with-0-patches
    # on this build; put detail in CHANGELOG instead. LF-only, no '/' in comments.
    pchtxt = exefs / "main.pchtxt"
    body = [
        f"@nsobid-{NSOBID}",
        "@flag offset_shift 0x100",
        "@enabled",
        f"// {args.mod_name}",
    ]
    for p in patches:
        if not p or p.startswith("//"):
            continue  # blanks break IPSwitch; detail lives in CHANGELOG
        body.append(p)
    with pchtxt.open("w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(body) + "\n")

    editor_data = out_dir / "mission_editor_edits.json"
    editor_data.write_text(
        json.dumps(edits, indent=2) + "\n",
        encoding="utf-8",
    )

    changelog = out_dir / "CHANGELOG.txt"
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    changelog.write_text(
        "\n".join(
            [
                f"{args.mod_name} - Changelog",
                f"Generated: {generated}",
                "Game: Unicorn Overlord US v1.0.5",
                "",
                "Changes",
                "-------",
            ]
            + (changes if changes else ["No gameplay edits recorded."])
            + (
                ["", "Warnings / export notes", "-----------------------"]
                + [n for n in notes if n.startswith("WARNING:")]
                if any(n.startswith("WARNING:") for n in notes)
                else []
            )
            + ["", f"Binary patch lines: {patch_count}"]
        )
        + "\n",
        encoding="utf-8",
    )

    if tactics_overrides:
        side = out_dir / "equipaiset_line_overrides.json"
        side.write_text(
            json.dumps(tactics_overrides, indent=2) + "\n", encoding="utf-8"
        )

    meta = {
        "charaset_duplicates": {str(k): v for k, v in dup_map.items()},
        "equipaiset_allocations": {
            str(k): v for k, v in ea_map.items() if not str(k).isdigit() or ":" in str(k)
        },
    }
    (out_dir / "export_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    readme = out_dir / "README.md"
    readme.write_text(
        "\n".join(
            [
                f"# {args.mod_name}",
                "",
                "Ryujinx ExeFS mod for Unicorn Overlord US v1.0.5.",
                "",
                "Install: copy this folder to",
                "`%AppData%\\Ryujinx\\mods\\contents\\010069401adb8000\\`",
                "",
                "Clear PTC after changing patches:",
                "`%AppData%\\Ryujinx\\games\\010069401adb8000\\cache\\cpu`",
                "",
                "## Notes",
            ]
            + ([f"- {n}" for n in notes] if notes else ["- (none)"])
            + [
                "",
                "See `CHANGELOG.txt` for a human-readable list of edits.",
                "Use `mission_editor_edits.json` with **Import editor mod…** to continue editing.",
                f"Patches: {patch_count}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {pchtxt} ({patch_count} patches)")
    print(f"wrote {readme}")
    print(f"wrote {changelog}")
    print(f"wrote {editor_data}")
    if ea_map:
        print("equipaiset map", {str(k): v for k, v in ea_map.items()})
    if dup_map:
        print("charaset map", dup_map)


if __name__ == "__main__":
    main()
