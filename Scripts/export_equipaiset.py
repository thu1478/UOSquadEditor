"""Export EquipAiSet preset catalog, IF enum, and vanilla tactic lines.

Static rows live in main at 0x2787F28, stride 0x130 (getter 0x124A9C).
Type-manager id is still EquipAiSet id + 486 (runtime RTTI / apply path).

Overrides (GUI / hand) win over vanilla when present:
  Extraction/editor/equipaiset_line_overrides.json
  { \"56\": [ {\"action\": 2, \"if0\": 15, \"if1\": 2}, ... ], ... }
"""
from __future__ import annotations

import csv
import json
import re
import struct
from collections import Counter
from pathlib import Path

ROOT = Path(r"d:/Documents/Projects/Emulation/UnicornOverlord")
MAIN = ROOT / "Extraction/exefs_out/main.decompressed.bin"
CLASS_EDITOR_PATCH = ROOT / "Mods/class_editor/exefs/main.pchtxt"
DEBUG = ROOT / "Extraction/cpk_data/Unicorn_US/Debug"
UNITSETS = ROOT / "Extraction/tables/unitsets.csv"
OUT_PRESETS = ROOT / "Extraction/tables/equipaiset_presets.csv"
OUT_IF = ROOT / "Extraction/tables/equipai_if.csv"
OUT_LINES = ROOT / "Extraction/tables/equipaiset_lines.csv"
OUT_FIELDS = ROOT / "Extraction/tables/equipaiset_fields.csv"
OVERRIDES = ROOT / "Extraction/editor/equipaiset_line_overrides.json"

EQUIPAISET_BASE = 0x2787F28
EQUIPAISET_STRIDE = 0x130
EQUIPAISET_COUNT = 358
TYPE_MANAGER_BASE_ID = 486  # EquipAiSet id N → type index N+486

# Authoritative per-preset tactics list (unit init 0xDDB90 → getter 0x229B4).
# Indexed by EquipAiSet id; 8 slots × 8 bytes. Id 0 is empty → class-default path.
TACTICS_SLOT_BASE = 0x270AF48
TACTICS_SLOT_STRIDE = 0x48
TACTICS_SLOT_COUNT = 8  # applicator 0xDDB90 / writer 0x2CAD04 accept slots 0..7
# Entry: if0 u16, if1 u16, skill_ref u32
# skill_ref is either BT_SKILLID EQUIPAI_ACTIVE/PASSIVE_SKILL_LVn (3..10) or a
# concrete skill id (e.g. 360 PAS_LIFE_DIVIDE for C12_BOSS Lifeshare).

# Per-skill default tactics IF pair lives at the same stride as EquipAiSet rows:
#   if0 @ +0xAC, if1 @ +0xB0, indexed by skill_id (extends past named presets).
# Used by class-default builder 0xDD610 — NOT by non-zero EquipAiSet presets.
SKILL_DEFAULT_IF0_OFF = 0xAC
SKILL_DEFAULT_IF1_OFF = 0xB0

# BT_SKILLID marker range that means "use class skill in this action slot".
EQUIPAI_MARKER_MIN = 2  # EQUIPAI_NORMAL_ATTACK
EQUIPAI_MARKER_MAX = 10  # EQUIPAI_PASSIVE_SKILL_LV4

# Item data (id-indexed): granted combat skill at +0x28.
ITEM_BASE = 0x2716168
ITEM_STRIDE = 0xB8
ITEM_SKILL_OFF = 0x28

# Per-skill AI profiles (getter 0x124ACC); EquipAiSet +0x04 indexes this table.
SKILL_AI_BASE = 0x27AAE78
SKILL_AI_STRIDE = 0x100
SKILL_AI_COUNT = 172  # ids 0..171; getter accepts 1..172

# Class → up to 4 skill-AI ids (same length as CLASSTYPE).
CLASS_SKILL_AI_BASE = 0xD36D94
CLASS_SKILL_AI_STRIDE = 0x8C
CLASS_SKILL_AI_SLOTS = (0x0C, 0x10, 0x14, 0x18)

# Confirmed condition blocks (matcher at 0x12619C): primary @+0x0C, secondary @+0x04
COND_BLOCKS = (0x2C, 0x50, 0x74)
COND_STRIDE = 0x24

# Skill-AI condition blocks (copy helper 0xC89BC reads IF at +0x0C, param at +0x10).
SKILL_AI_COND_BLOCKS = (0x60, 0x84, 0xA8)

OUT_CLASS_SKILL_AI = ROOT / "Extraction/tables/class_skill_ai.csv"
OUT_CLASS_LINES = ROOT / "Extraction/tables/class_default_tactics_lines.csv"
OUT_CLASS_SKILLS = ROOT / "Extraction/tables/class_skills.csv"
OUT_ITEM_SKILLS = ROOT / "Extraction/tables/item_skills.csv"

# BT_SKILLID EQUIPAI_* action ids used by the in-game tactics UI.
ACTION_NORMAL = 2
ACTION_ACTIVE0 = 3
ACTION_PASSIVE0 = 7

# Class skill list inside 0xD36D94 (not the skill-AI profile ids at +0x0C).
# Layout per skill slot is (learn_level u32, skill_id u32):
#   Normal:  +0x1C skill (no adjacent level in the same pattern; often DEFAULT_*)
#   Actives: +0x20/+0x24, +0x28/+0x2C, +0x30/+0x34, +0x38/+0x3C
#   Passives:+0x50/+0x54, +0x58/+0x5C, +0x60/+0x64, +0x68/+0x6C
CLASS_SKILL_NORMAL = 0x1C
CLASS_SKILL_ACTIVE_LEVELS = (0x20, 0x28, 0x30, 0x38)
CLASS_SKILL_ACTIVES = (0x24, 0x2C, 0x34, 0x3C)
CLASS_SKILL_PASSIVE_LEVELS = (0x50, 0x58, 0x60, 0x68)
CLASS_SKILL_PASSIVES = (0x54, 0x5C, 0x64, 0x6C)


def apply_pchtxt_text(blob: bytes, text: str) -> tuple[bytes, int]:
    """Overlay simple address/hex patches from pchtxt text content."""
    out = bytearray(blob)
    applied = 0
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line or line.startswith("@"):
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            address = int(parts[0], 16)
            data = bytes.fromhex(parts[1])
        except ValueError:
            continue
        if address < 0 or address + len(data) > len(out):
            continue
        out[address : address + len(data)] = data
        applied += 1
    return bytes(out), applied


def apply_pchtxt(blob: bytes, path: Path) -> tuple[bytes, int]:
    """Overlay simple address/hex patches so exports reflect installed editor mods."""
    if not path.exists():
        return blob, 0
    return apply_pchtxt_text(blob, path.read_text(encoding="utf-8-sig"))


def parse_enum(path: Path, header: str) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    start = None
    end_tok = header.split(":")[0] + "_END"
    for i, ln in enumerate(lines):
        if ln.startswith(header):
            start = i + 1
            break
    if start is None:
        raise RuntimeError(header)
    names: list[str] = []
    for ln in lines[start:]:
        if ln.strip().startswith(end_tok):
            break
        m = re.match(r"\s*([A-Za-z0-9_]+)\s*,", ln)
        if m:
            names.append(m.group(1))
    return names


def parse_enum_comments(path: Path, header: str) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    start = None
    end_tok = header.split(":")[0] + "_END"
    for i, ln in enumerate(lines):
        if ln.startswith(header):
            start = i + 1
            break
    if start is None:
        raise RuntimeError(header)
    out: list[tuple[str, str]] = []
    for ln in lines[start:]:
        if ln.strip().startswith(end_tok):
            break
        m = re.match(r"\s*([A-Za-z0-9_]+)\s*,\s*(?://\s*(.*))?", ln)
        if m:
            out.append((m.group(1), (m.group(2) or "").strip()))
    return out


def _valid_if(v: int, n_ifs: int) -> int:
    return v if 0 < v < n_ifs else 0


def decode_row_fields(row: bytes) -> dict:
    rid = struct.unpack_from("<I", row, 0x00)[0]
    skill_ai = struct.unpack_from("<I", row, 0x04)[0]
    count_a = struct.unpack_from("<h", row, 0x0A)[0]
    count_b = struct.unpack_from("<h", row, 0x0C)[0]
    mode = struct.unpack_from("<I", row, 0x10)[0]
    group = struct.unpack_from("<I", row, 0x98)[0]
    if_bc = struct.unpack_from("<i", row, 0xBC)[0]
    if_e4 = struct.unpack_from("<i", row, 0xE4)[0]
    if_108 = struct.unpack_from("<i", row, 0x108)[0]
    if_11c = struct.unpack_from("<i", row, 0x11C)[0]
    flags = struct.unpack_from("<I", row, 0x128)[0]
    mask = struct.unpack_from("<I", row, 0x12C)[0]
    param_18 = struct.unpack_from("<f", row, 0x18)[0]
    return {
        "id": rid,
        "skill_ai_id": skill_ai,
        "count_a": count_a,
        "count_b": count_b,
        "mode_10": mode,
        "group_98": group,
        "if_bc": if_bc,
        "if_e4": if_e4,
        "if_108": if_108,
        "if_11c": if_11c,
        "flags_128": flags,
        "mask_12c": mask,
        "param_18": param_18,
    }


def is_equipai_marker(skill_ref: int) -> bool:
    return EQUIPAI_MARKER_MIN <= skill_ref <= EQUIPAI_MARKER_MAX


def tactics_slot_row(blob: bytes, equipaiset_id: int) -> bytes | None:
    if equipaiset_id < 0:
        return None
    off = TACTICS_SLOT_BASE + equipaiset_id * TACTICS_SLOT_STRIDE
    if off + TACTICS_SLOT_STRIDE > len(blob):
        return None
    return blob[off : off + TACTICS_SLOT_STRIDE]


def synthesize_lines(
    row: bytes, n_ifs: int, blob: bytes | None = None, *, equipaiset_id: int = -1
) -> list[dict]:
    """Preset tactics slots from table 0x270AF48 (not 0x130 condition blocks).

    Non-zero EquipAiSet ids install this list via 0xDDB90. Each occupied slot is
    either a class-slot marker (EQUIPAI_ACTIVE/PASSIVE_SKILL_LVn) or an explicit
    skill id. IF0/IF1 in the slot are authoritative (0/0 = no condition shown).

    The 0x130 row's +0x2C/+0x50/+0x74 blocks are skill-effect conditions for the
    skill that shares the same numeric id — they are NOT unit Active-slot overlays.
    """
    del row  # 0x130 body is unrelated to the displayed tactics list
    lines: list[dict] = []
    if blob is None or equipaiset_id <= 0:
        return lines
    slot_row = tactics_slot_row(blob, equipaiset_id)
    if not slot_row:
        return lines
    for slot in range(TACTICS_SLOT_COUNT):
        off = slot * 8
        if0_raw, if1_raw = struct.unpack_from("<HH", slot_row, off)
        skill_ref = struct.unpack_from("<I", slot_row, off + 4)[0]
        if not skill_ref:
            continue
        if0 = if0_raw if 0 <= if0_raw < n_ifs else 0
        if1 = if1_raw if 0 <= if1_raw < n_ifs else 0
        marker = is_equipai_marker(skill_ref)
        lines.append(
            {
                "action": skill_ref if marker else ACTION_ACTIVE0,
                "slot": slot,
                "if0": if0,
                "if1": if1,
                "skill_id": skill_ref,
                "ref_kind": "class_slot" if marker else "skill",
                "source_field": f"tactics_slot_{slot}",
            }
        )
    return lines


def class_skill_ai_ids(blob: bytes, class_id: int) -> list[int]:
    if class_id < 0:
        return []
    base = CLASS_SKILL_AI_BASE + class_id * CLASS_SKILL_AI_STRIDE
    if base + CLASS_SKILL_AI_STRIDE > len(blob):
        return []
    out: list[int] = []
    for off in CLASS_SKILL_AI_SLOTS:
        v = struct.unpack_from("<I", blob, base + off)[0]
        if 0 < v < SKILL_AI_COUNT:
            out.append(v)
    return out


def class_skill_entries(blob: bytes, class_id: int, skill_names: list[str]) -> list[dict]:
    """Real tactics rows: Active×4 / Passive×4 skill ids + learn levels from 0xD36D94."""
    if class_id < 0:
        return []
    base = CLASS_SKILL_AI_BASE + class_id * CLASS_SKILL_AI_STRIDE
    if base + CLASS_SKILL_AI_STRIDE > len(blob):
        return []
    n_skills = len(skill_names)
    entries: list[dict] = []

    def add(action: int, skill_off: int, level_off: int | None, kind: str) -> None:
        sid = struct.unpack_from("<I", blob, base + skill_off)[0]
        if not (0 < sid < n_skills):
            return
        sym = skill_names[sid]
        # Skip empty / marker / generic shared attack stubs. In-game tactics
        # lists class skills (Passive Curse, Fireball, …), not DEFAULT_MAGIC.
        if sym in (
            "UNKNOWN",
            "EQUIPAI_START",
            "EQUIPAI_END",
            "DEFAULT_START",
            "DEFAULT_END",
            "DEFAULT",
            "DEFAULT_FLY",
            "DEFAULT_BOW",
            "DEFAULT_MAGIC",
            "DEFAULT_HEAL",
        ):
            return
        if sym.startswith("EQUIPAI_"):
            return
        learn_lv = 1
        if level_off is not None:
            learn_lv = struct.unpack_from("<I", blob, base + level_off)[0]
            if learn_lv <= 0 or learn_lv > 99:
                learn_lv = 1
        entries.append(
            {
                "action": action,
                "skill_id": sid,
                "skill_symbol": sym,
                "kind": kind,
                "learn_level": learn_lv,
                "if0": 0,
                "if1": 0,
                "source_field": f"class_{kind}_{skill_off:02x}",
            }
        )

    add(ACTION_NORMAL, CLASS_SKILL_NORMAL, None, "normal")
    for i, (loff, soff) in enumerate(
        zip(CLASS_SKILL_ACTIVE_LEVELS, CLASS_SKILL_ACTIVES)
    ):
        add(ACTION_ACTIVE0 + i, soff, loff, "active")
    for i, (loff, soff) in enumerate(
        zip(CLASS_SKILL_PASSIVE_LEVELS, CLASS_SKILL_PASSIVES)
    ):
        add(ACTION_PASSIVE0 + i, soff, loff, "passive")
    return entries


def skill_default_ifs(blob: bytes, skill_id: int, n_ifs: int) -> tuple[int, int]:
    """Per-skill default tactics IF0/IF1 (EquipAiSet-shaped row @ skill_id).

    The table is skill-indexed and extends well past the 358 *named* presets
    (each row's +0x00 equals its own id, verified up to skill 470). So bound the
    lookup by the blob and validate the row id rather than the preset count —
    otherwise skills like Lifeshare (360), Magick Barrier (413), Holy Guard (455)
    silently lose their defaults.
    """
    if skill_id <= 0:
        return 0, 0
    off = EQUIPAISET_BASE + skill_id * EQUIPAISET_STRIDE
    if off + EQUIPAISET_STRIDE > len(blob):
        return 0, 0
    if struct.unpack_from("<I", blob, off)[0] != skill_id:
        return 0, 0
    if0 = _valid_if(
        struct.unpack_from("<I", blob, off + SKILL_DEFAULT_IF0_OFF)[0], n_ifs
    )
    if1 = _valid_if(
        struct.unpack_from("<I", blob, off + SKILL_DEFAULT_IF1_OFF)[0], n_ifs
    )
    return if0, if1


def item_granted_skill(blob: bytes, item_id: int) -> int:
    """Combat skill granted by an item, or 0."""
    if item_id <= 0:
        return 0
    off = ITEM_BASE + item_id * ITEM_STRIDE
    if off + ITEM_SKILL_OFF + 4 > len(blob):
        return 0
    if struct.unpack_from("<I", blob, off)[0] != item_id:
        return 0
    sid = struct.unpack_from("<I", blob, off + ITEM_SKILL_OFF)[0]
    return sid if 0 < sid < 2000 else 0


def synthesize_class_default_lines(
    blob: bytes, class_id: int, n_ifs: int, skill_names: list[str]
) -> list[dict]:
    """Tactics for EquipAiSet id 0 (no preset row).

    EquipAiSet 0 clears preset state (apply 0x571390) and builds the skill list
    at runtime from the class learn pool: Active slots high→low, then Passive
    slots high→low (item skills are inserted between those groups by the
    gear path). IF0/IF1 come from EquipAiSet[skill_id]+0xAC/+0xB0.
    """
    pool = class_skill_entries(blob, class_id, skill_names)
    if not pool:
        return []

    normals = [e for e in pool if e.get("kind") == "normal"]
    # Class table stores slot0..slotN low→high; runtime walks high→low.
    actives = list(reversed([e for e in pool if e.get("kind") == "active"]))
    passives = list(reversed([e for e in pool if e.get("kind") == "passive"]))

    lines: list[dict] = []
    for e in normals + actives + passives:
        sid = int(e.get("skill_id") or 0)
        if0, if1 = skill_default_ifs(blob, sid, n_ifs)
        entry = dict(e)
        entry.update(
            {
                "if0": if0,
                "if1": if1,
                "source_field": f"skill_default_if_{sid}",
                "equipped": True,
            }
        )
        lines.append(entry)
    return lines


def apply_lines_to_row(row: bytearray, lines: list[dict], n_ifs: int) -> None:
    """Deprecated for tactics: 0x130 condition blocks are not unit tactics.

    Kept as a no-op-preserving stub so older callers do not wipe globals/params.
    Use apply_lines_to_tactics_slots() to write the real preset list.
    """
    del row, lines, n_ifs


def apply_lines_to_tactics_slots(
    slot_row: bytearray, lines: list[dict], n_ifs: int
) -> None:
    """Write editor tactics lines into a 0x48 tactics-slot row."""
    if len(slot_row) < TACTICS_SLOT_STRIDE:
        raise ValueError("tactics slot row too small")
    slot_row[:] = b"\x00" * TACTICS_SLOT_STRIDE
    for index, line in enumerate(lines[:TACTICS_SLOT_COUNT]):
        slot = int(line.get("slot", index))
        if not (0 <= slot < TACTICS_SLOT_COUNT):
            continue
        if0 = int(line.get("if0", 0))
        if1 = int(line.get("if1", 0))
        if not (0 <= if0 < n_ifs):
            if0 = 0
        if not (0 <= if1 < n_ifs):
            if1 = 0
        skill_ref = int(line.get("skill_id") or 0)
        if not skill_ref:
            # Marker form: action 3..10 means class slot.
            action = int(line.get("action") or 0)
            if is_equipai_marker(action):
                skill_ref = action
        if not skill_ref:
            continue
        off = slot * 8
        struct.pack_into("<HH", slot_row, off, if0, if1)
        struct.pack_into("<I", slot_row, off + 4, skill_ref)


def main() -> None:
    names = parse_enum(DEBUG / "_UcEnum_EquipAiSet.inc", "EQUIPAISET:")
    ifs = parse_enum_comments(DEBUG / "_UcEnum_EquipAi.inc", "EQUIPAI_IF:")
    assert len(names) == 358
    n_ifs = len(ifs)
    blob, class_patch_count = apply_pchtxt(MAIN.read_bytes(), CLASS_EDITOR_PATCH)
    if class_patch_count:
        print(
            f"applied {class_patch_count} class-editor patches from "
            f"{CLASS_EDITOR_PATCH}"
        )

    usage: Counter[int] = Counter()
    if UNITSETS.exists():
        with UNITSETS.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                for i in range(6):
                    raw = row.get(f"slot{i}_equipai_id") or ""
                    if raw.isdigit():
                        usage[int(raw)] += 1

    overrides: dict = {}
    if OVERRIDES.exists():
        overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
        overrides.pop("_comment", None)

    OUT_PRESETS.parent.mkdir(parents=True, exist_ok=True)
    if_syms = [s for s, _ in ifs]
    skill_names = parse_enum(DEBUG / "_UcEnum_Skill.inc", "BT_SKILLID:")

    with OUT_FIELDS.open("w", encoding="utf-8", newline="") as ff:
        fw = csv.DictWriter(
            ff,
            fieldnames=[
                "equipaiset_id",
                "equipaiset_symbol",
                "skill_ai_id",
                "count_a",
                "count_b",
                "mode_10",
                "group_98",
                "if_bc",
                "if_bc_symbol",
                "if_e4",
                "if_e4_symbol",
                "if_108",
                "if_108_symbol",
                "if_11c",
                "if_11c_symbol",
                "flags_128",
                "mask_12c",
                "param_18",
                "block0_en",
                "block0_if0",
                "block0_if1",
                "block1_en",
                "block1_if0",
                "block1_if1",
                "block2_en",
                "block2_if0",
                "block2_if1",
            ],
        )
        fw.writeheader()

        with OUT_PRESETS.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "equipaiset_id",
                    "equipaiset_symbol",
                    "type_manager_id",
                    "unitset_slot_refs",
                    "has_line_override",
                    "line_count",
                    "count_a",
                    "count_b",
                    "group_98",
                    "decode_note",
                ],
            )
            w.writeheader()

            with OUT_LINES.open("w", encoding="utf-8", newline="") as fl:
                lw = csv.DictWriter(
                    fl,
                    fieldnames=[
                        "equipaiset_id",
                        "equipaiset_symbol",
                        "line_index",
                        "slot",
                        "action",
                        "skill_id",
                        "skill_symbol",
                        "ref_kind",
                        "if0",
                        "if0_symbol",
                        "if1",
                        "if1_symbol",
                        "source",
                        "source_field",
                    ],
                )
                lw.writeheader()

                for i, name in enumerate(names):
                    off = EQUIPAISET_BASE + i * EQUIPAISET_STRIDE
                    row = blob[off : off + EQUIPAISET_STRIDE]
                    fields = decode_row_fields(row)

                    def if_sym(v: int) -> str:
                        return if_syms[v] if 0 < v < n_ifs else ""

                    block_cols: dict[str, int] = {}
                    for bi, boff in enumerate(COND_BLOCKS):
                        en, if1_raw, _p, if0_raw = struct.unpack_from(
                            "<IIII", row, boff
                        )
                        block_cols[f"block{bi}_en"] = en
                        block_cols[f"block{bi}_if0"] = if0_raw
                        block_cols[f"block{bi}_if1"] = if1_raw

                    fw.writerow(
                        {
                            "equipaiset_id": i,
                            "equipaiset_symbol": name,
                            "skill_ai_id": fields["skill_ai_id"],
                            "count_a": fields["count_a"],
                            "count_b": fields["count_b"],
                            "mode_10": fields["mode_10"],
                            "group_98": fields["group_98"],
                            "if_bc": fields["if_bc"],
                            "if_bc_symbol": if_sym(fields["if_bc"]),
                            "if_e4": fields["if_e4"],
                            "if_e4_symbol": if_sym(fields["if_e4"]),
                            "if_108": fields["if_108"],
                            "if_108_symbol": if_sym(fields["if_108"]),
                            "if_11c": fields["if_11c"],
                            "if_11c_symbol": if_sym(fields["if_11c"]),
                            "flags_128": fields["flags_128"],
                            "mask_12c": fields["mask_12c"],
                            "param_18": f"{fields['param_18']:.3f}",
                            **block_cols,
                        }
                    )

                    ov = overrides.get(str(i)) or overrides.get(name)
                    if ov:
                        lines = []
                        for xi, x in enumerate(ov):
                            sid = int(x.get("skill_id") or 0)
                            action = int(x.get("action") or 0)
                            if not sid and is_equipai_marker(action):
                                sid = action
                            marker = is_equipai_marker(sid)
                            lines.append(
                                {
                                    "action": sid if marker else action or ACTION_ACTIVE0,
                                    "slot": int(x.get("slot", xi)),
                                    "if0": int(x.get("if0", 0)),
                                    "if1": int(x.get("if1", 0)),
                                    "skill_id": sid,
                                    "ref_kind": "class_slot" if marker else "skill",
                                    "source_field": "override",
                                }
                            )
                        source = "override"
                    else:
                        lines = synthesize_lines(
                            row, n_ifs, blob, equipaiset_id=i
                        )
                        source = "vanilla"

                    w.writerow(
                        {
                            "equipaiset_id": i,
                            "equipaiset_symbol": name,
                            "type_manager_id": i + TYPE_MANAGER_BASE_ID,
                            "unitset_slot_refs": usage.get(i, 0),
                            "has_line_override": int(bool(ov)),
                            "line_count": len(lines),
                            "count_a": fields["count_a"],
                            "count_b": fields["count_b"],
                            "group_98": fields["group_98"],
                            "decode_note": (
                                "override"
                                if ov
                                else (
                                    "tactics_slots_0x270AF48"
                                    if lines
                                    else "empty_or_class_default"
                                )
                            ),
                        }
                    )

                    for li, line in enumerate(lines):
                        i0 = int(line["if0"])
                        i1 = int(line["if1"])
                        sid = int(line.get("skill_id") or 0)
                        ssym = (
                            skill_names[sid]
                            if 0 <= sid < len(skill_names)
                            else ""
                        )
                        lw.writerow(
                            {
                                "equipaiset_id": i,
                                "equipaiset_symbol": name,
                                "line_index": li,
                                "slot": int(line.get("slot", li)),
                                "action": int(line["action"]),
                                "skill_id": sid,
                                "skill_symbol": ssym,
                                "ref_kind": line.get("ref_kind") or "",
                                "if0": i0,
                                "if0_symbol": if_sym(i0),
                                "if1": i1,
                                "if1_symbol": if_sym(i1),
                                "source": source,
                                "source_field": line.get("source_field", ""),
                            }
                        )

    with OUT_IF.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["if_id", "if_symbol", "comment_jp"])
        w.writeheader()
        for i, (sym, cmt) in enumerate(ifs):
            w.writerow({"if_id": i, "if_symbol": sym, "comment_jp": cmt})

    classes = parse_enum(DEBUG / "_UcEnum_Class.inc", "CLASSTYPE:")
    skill_desc: dict[int, str] = {}
    skills_csv = ROOT / "Extraction/tables/skills.csv"
    if skills_csv.exists():
        with skills_csv.open(encoding="utf-8-sig") as sf:
            for row in csv.DictReader(sf):
                try:
                    skill_desc[int(row["skill_id"])] = (
                        row.get("description_en") or ""
                    ).strip()
                except ValueError:
                    continue
    # UcSkillList.csv mixed text table; combat skill labels sit at index ≈ skill_id+15.
    fms_skills = ROOT / "Extraction/tables/fms/UcSkillList.csv"
    if fms_skills.exists():
        with fms_skills.open(encoding="utf-8-sig") as sf:
            for row in csv.DictReader(sf):
                try:
                    fid = int(row.get("index") or "0")
                except ValueError:
                    continue
                name = (row.get("text") or "").strip()
                if not name.startswith("(A) ") and not name.startswith("(P) "):
                    continue
                sid = fid - 15
                if sid > 0 and (
                    sid not in skill_desc
                    or "プログラム" in skill_desc.get(sid, "")
                    or not skill_desc.get(sid)
                    or skill_desc.get(sid, "").strip().lower() in ("none", "null")
                ):
                    skill_desc[sid] = name

    def skill_label(sid: int, sym: str) -> str:
        desc = (skill_desc.get(sid, "") or "").strip()
        if desc and "プログラム" not in desc and desc.lower() not in ("none", "null"):
            return desc.replace("(A) ", "").replace("(P) ", "").strip()
        # Enum / symbol fallback (Fallen One, etc. when skills.csv says "None")
        name = sym
        for prefix in ("ACT_", "PAS_", "DEFAULT_"):
            if name.startswith(prefix):
                name = name[len(prefix) :]
                break
        return name.replace("_", " ").title()

    with OUT_CLASS_SKILL_AI.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "class_id",
                "class_symbol",
                "skill_ai_0",
                "skill_ai_1",
                "skill_ai_2",
                "skill_ai_3",
            ],
        )
        w.writeheader()
        with OUT_CLASS_SKILLS.open("w", encoding="utf-8", newline="") as fs:
            sw = csv.DictWriter(
                fs,
                fieldnames=[
                    "class_id",
                    "class_symbol",
                    "line_index",
                    "action",
                    "kind",
                    "skill_id",
                    "skill_symbol",
                    "skill_name",
                    "learn_level",
                ],
            )
            sw.writeheader()
            with OUT_CLASS_LINES.open("w", encoding="utf-8", newline="") as fl:
                lw = csv.DictWriter(
                    fl,
                    fieldnames=[
                        "class_id",
                        "class_symbol",
                        "line_index",
                        "action",
                        "skill_id",
                        "skill_symbol",
                        "skill_name",
                        "learn_level",
                        "if0",
                        "if0_symbol",
                        "if1",
                        "if1_symbol",
                        "source_field",
                    ],
                )
                lw.writeheader()
                for ci, cname in enumerate(classes):
                    ids = class_skill_ai_ids(blob, ci)
                    padded = ids + [0] * 4
                    w.writerow(
                        {
                            "class_id": ci,
                            "class_symbol": cname,
                            "skill_ai_0": padded[0],
                            "skill_ai_1": padded[1],
                            "skill_ai_2": padded[2],
                            "skill_ai_3": padded[3],
                        }
                    )
                    # Full learn pool (not tactics) for reference
                    pool = class_skill_entries(blob, ci, skill_names)
                    for li, line in enumerate(pool):
                        sid = int(line.get("skill_id") or 0)
                        ssym = str(line.get("skill_symbol") or "")
                        sname = skill_label(sid, ssym)
                        learn_lv = int(line.get("learn_level") or 1)
                        sw.writerow(
                            {
                                "class_id": ci,
                                "class_symbol": cname,
                                "line_index": li,
                                "action": int(line["action"]),
                                "kind": line.get("kind", ""),
                                "skill_id": sid,
                                "skill_symbol": ssym,
                                "skill_name": sname,
                                "learn_level": learn_lv,
                            }
                        )
                    # Equipped tactics + per-skill default IFs
                    lines = synthesize_class_default_lines(
                        blob, ci, n_ifs, skill_names
                    )
                    for li, line in enumerate(lines):
                        sid = int(line.get("skill_id") or 0)
                        ssym = str(line.get("skill_symbol") or "")
                        sname = skill_label(sid, ssym)
                        learn_lv = int(line.get("learn_level") or 1)
                        i0 = int(line["if0"])
                        i1 = int(line["if1"])
                        lw.writerow(
                            {
                                "class_id": ci,
                                "class_symbol": cname,
                                "line_index": li,
                                "action": int(line["action"]),
                                "skill_id": sid,
                                "skill_symbol": ssym,
                                "skill_name": sname,
                                "learn_level": learn_lv,
                                "if0": i0,
                                "if0_symbol": if_syms[i0]
                                if 0 < i0 < n_ifs
                                else "",
                                "if1": i1,
                                "if1_symbol": if_syms[i1]
                                if 0 < i1 < n_ifs
                                else "",
                                "source_field": line.get("source_field", ""),
                            }
                        )

    OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
    if not OVERRIDES.exists():
        OVERRIDES.write_text(
            json.dumps(
                {
                    "_comment": (
                        "Map equipaiset_id (string) -> list of "
                        "{slot, skill_id, if0, if1}. skill_id is either an "
                        "EQUIPAI_* class-slot marker (3..10) or a concrete "
                        "BT_SKILLID. Written to tactics table 0x270AF48, not "
                        "the 0x130 condition blocks. Class defaults (id 0) use "
                        "0xD36D94 + per-skill IF0/IF1 at EquipAiSet[skill]+AC/B0."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    # Item → granted skill (Stingray → Artenie Strike, etc.)
    item_names = parse_enum(DEBUG / "_UcEnum_Item.inc", "ITEMID:")
    with OUT_ITEM_SKILLS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "item_id",
                "item_symbol",
                "skill_id",
                "skill_symbol",
                "skill_name",
                "if0",
                "if0_symbol",
                "if1",
                "if1_symbol",
            ],
        )
        w.writeheader()
        for iid, isym in enumerate(item_names):
            sid = item_granted_skill(blob, iid)
            if not sid:
                continue
            ssym = skill_names[sid] if sid < len(skill_names) else ""
            if ssym in ("UNKNOWN", "EQUIPAI_START", "EQUIPAI_END") or ssym.startswith(
                "EQUIPAI_"
            ):
                continue
            i0, i1 = skill_default_ifs(blob, sid, n_ifs)
            w.writerow(
                {
                    "item_id": iid,
                    "item_symbol": isym,
                    "skill_id": sid,
                    "skill_symbol": ssym,
                    "skill_name": skill_label(sid, ssym),
                    "if0": i0,
                    "if0_symbol": if_syms[i0] if 0 < i0 < n_ifs else "",
                    "if1": i1,
                    "if1_symbol": if_syms[i1] if 0 < i1 < n_ifs else "",
                }
            )

    print(f"wrote {OUT_PRESETS}")
    print(f"wrote {OUT_FIELDS}")
    print(f"wrote {OUT_IF} ({n_ifs} IFs)")
    print(f"wrote {OUT_LINES}")
    print(f"wrote {OUT_CLASS_SKILL_AI}")
    print(f"wrote {OUT_CLASS_SKILLS}")
    print(f"wrote {OUT_CLASS_LINES}")
    print(f"wrote {OUT_ITEM_SKILLS}")
    print(f"table base 0x{EQUIPAISET_BASE:X} stride 0x{EQUIPAISET_STRIDE:X}")
    print(
        f"tactics slots base 0x{TACTICS_SLOT_BASE:X} "
        f"stride 0x{TACTICS_SLOT_STRIDE:X}"
    )


if __name__ == "__main__":
    main()
