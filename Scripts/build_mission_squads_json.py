"""Build unified mission editor document from CSVs.

Writes Extraction/editor/mission_squads.json — full join for the GUI.

Gear: CharaSet item ids when set; empty slots filled via CreateDefaultEquip
(class EQUIPTYPE × gear tier × stage level). Tier from native 0x2CBFE8
(PARAMSET + CharaSet +0x1E) + clamp. Companions in a UnitSet that also has a
BOSS CharaSet override (+0x1E) use POWER (Sorm Wyvern) — not every EXPTYPE-BOSS row.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(r"d:/Documents/Projects/Emulation/UnicornOverlord")
TABLES = ROOT / "Extraction/tables"
OUT = ROOT / "Extraction/editor/mission_squads.json"
OVERRIDES = ROOT / "Extraction/editor/equipaiset_line_overrides.json"
DEBUG = ROOT / "Extraction/cpk_data/Unicorn_US/Debug"

PARAMSET_NAME = {
    0: "NONE",
    1: "ZAKO",
    2: "NORMAL",
    3: "POWER",
    4: "BOSS",
    5: "JOSEPH",
    6: "CALL_ALLIES",
}

# EQUIPTYPE id offset by PARAMSET tier (native CreateDefaultEquip).
PARAMSET_ET_OFFSET = {0: 0, 1: 11, 2: 22, 3: 33, 4: 44}


def level_column(level: int) -> int:
    """Match native 0x123844."""
    if level < 1:
        return -1
    if level < 15:
        return 0
    if level < 28:
        return 1
    if level < 51:
        return 2
    return -1


def clamp_equip_param(tier: int) -> int:
    """Match native 0x123834: keep values in [2, 4], else 0."""
    if 2 <= tier <= 4:
        return tier
    return 0


def resolve_equip_param(
    exptype: int,
    paramset: int,
    chara_override: int,
    *,
    squad_boss_override: bool = False,
) -> int:
    """CreateDefaultEquip tier for a unit.

    Native 0x2CBFE8: PARAMSET (+0x14) when non-zero; when PARAMSET is 0 use
    NORMAL (2) if EXPTYPE < 5 else 0. Then CharaSet +0x1E overrides.
    Clamp 0x123834 keeps only [2,4] (else 0 → DEFAULT equiptype band).

    Squad quirk (observed Sorm): UnitSets that include a CharaSet with
    +0x1E=BOSS (e.g. Culloran) equip generic companions in the POWER band
    (Wyvern: Spear+Lapis+Gold). Midboss packs with the same PARAMSET/EXPTYPE
    but no such character stay NORMAL (no Lapis). Do not raise from EXPTYPE alone.
    """
    if paramset == 0:
        tier = 2 if exptype < 5 else 0
    else:
        tier = paramset
    if chara_override:
        tier = chara_override
    tier = clamp_equip_param(tier)
    if not chara_override and squad_boss_override and tier == 2:
        tier = 3  # POWER
    return tier



def squad_role(symbol: str) -> str:
    """Human role from UnitSet name — not EXPTYPE."""
    u = (symbol or "").upper()
    if "MIDBOSS" in u or "_MBOSS" in u:
        return "Midboss"
    if "ZOUEN" in u:
        return "Reinforce"
    if "_ZAKO" in u or u.endswith("ZAKO"):
        return "Zako"
    if "MERIZAND" in u or "_BOSS" in u or u.endswith("BOSS"):
        return "Boss"
    return "Enemy"


def load_csv(name: str) -> list[dict[str, str]]:
    path = TABLES / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def parse_enum(path: Path, header: str) -> list[str]:
    text = path.read_text(encoding="utf-8-sig").splitlines()
    start = None
    end_tok = header.split(":")[0] + "_END"
    for i, ln in enumerate(text):
        if ln.startswith(header):
            start = i + 1
            break
    if start is None:
        return []
    names: list[str] = []
    for ln in text[start:]:
        if ln.strip().startswith(end_tok):
            break
        m = re.match(r"\s*([A-Za-z0-9_]+)\s*,", ln)
        if m:
            names.append(m.group(1))
    return names


def load_item_catalog() -> tuple[dict[int, str], dict[int, str], list[dict]]:
    """English display names from items.csv + symbols from ITEMID enum."""
    names: dict[int, str] = {}
    for r in load_csv("items.csv"):
        rid = r.get("id") or ""
        try:
            names[int(rid)] = (r.get("name_en") or "").strip()
        except ValueError:
            continue

    symbols: dict[int, str] = {}
    enum_path = DEBUG / "_UcEnum_Item.inc"
    if enum_path.exists():
        text = enum_path.read_text(encoding="utf-8-sig").splitlines()
        start = next(i for i, ln in enumerate(text) if ln.startswith("ITEMID:")) + 1
        idx = 0
        for ln in text[start:]:
            if ln.strip().startswith("ITEMID_END"):
                break
            m = re.match(r"\s*([A-Za-z0-9_]+)\s*,", ln)
            if m:
                symbols[idx] = m.group(1)
                idx += 1

    catalog: list[dict] = []
    for iid in sorted(set(names) | set(symbols)):
        if iid <= 0:
            continue
        catalog.append(
            {
                "id": iid,
                "symbol": symbols.get(iid, ""),
                "name": names.get(iid, ""),
            }
        )
    return names, symbols, catalog


def load_charaset_catalog(
    item_names: dict[int, str],
    item_symbols: dict[int, str],
    chara_names: dict[str, str],
) -> list[dict]:
    """All CharaSet templates for the unit composition picker."""
    class_names: dict[int, str] = {}
    for r in load_csv("characters.csv"):
        try:
            class_id = int(r.get("class_id") or 0)
        except ValueError:
            continue
        cname = (r.get("class_name") or "").strip()
        if class_id and cname and class_id not in class_names:
            class_names[class_id] = cname

    catalog: list[dict] = []
    for r in load_csv("charasets.csv"):
        try:
            cid = int(r.get("chara_id") or r.get("charaset_id") or 0)
        except ValueError:
            continue
        if cid <= 0:
            continue
        sym = (r.get("chara_symbol") or r.get("charaset_symbol") or "").strip()
        try:
            class_id = int(r.get("class_id") or 0)
        except ValueError:
            class_id = 0
        class_symbol = (r.get("class_enum") or r.get("class_symbol") or "").strip()
        gear: list[dict] = []
        for g in range(4):
            try:
                iid = int(r.get(f"equip{g}_id") or 0)
            except ValueError:
                iid = 0
            if iid:
                gear.append(
                    {
                        "item_id": iid,
                        "rom_item_id": iid,
                        "item_symbol": item_symbols.get(iid)
                        or (r.get(f"equip{g}_symbol") or "").strip(),
                        "item_name": item_names.get(iid)
                        or (r.get(f"equip{g}_name") or "").strip(),
                        "source": "charaset",
                    }
                )
            else:
                gear.append(
                    {
                        "item_id": 0,
                        "rom_item_id": 0,
                        "item_symbol": "",
                        "item_name": "",
                        "source": "empty",
                    }
                )
        catalog.append(
            {
                "id": cid,
                "symbol": sym,
                "name": chara_names.get(sym, "") or chara_names.get(str(cid), ""),
                "class_id": class_id,
                "class_symbol": class_symbol,
                "class_name": class_names.get(class_id, ""),
                "gear": gear,
            }
        )
    return catalog


def strip_fms_markup(text: str) -> str:
    """Remove in-game markup tokens (#c(14)…#/c, #(70), etc.) from FMS strings."""
    t = (text or "").replace("%%", "%")
    t = re.sub(
        r"#(?:\([^)]*\)|c\([^)]*\)|/c|/i|i|/s|s\([^)]*\)|w\([^)]*\)|b|/b|Y\([^)]*\))",
        "",
        t,
    )
    return re.sub(r"\s+", " ", t).strip()


def load_fms_skill_names() -> dict[int, str]:
    """Official EN skill labels from UcSkillList.fms (index ≈ skill_id + 15).

    Prefixed rows `(A) …` / `(P) …` are the combat skill name table used in-game.
    """
    path = TABLES / "fms" / "UcSkillList.csv"
    if not path.exists():
        return {}
    out: dict[int, str] = {}
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                fid = int(row.get("index") or "0")
            except ValueError:
                continue
            text = (row.get("text") or "").strip()
            if text.startswith("(A) "):
                name = text[4:].strip()
            elif text.startswith("(P) "):
                name = text[4:].strip()
            else:
                continue
            sid = fid - 15
            if sid > 0 and name:
                out[sid] = name
    return out


def load_fms_factor_names() -> dict[int, str]:
    """Official EN IF/condition labels from UcFactorList.fms (index == if_id)."""
    path = TABLES / "fms" / "UcFactorList.csv"
    if not path.exists():
        return {}
    out: dict[int, str] = {}
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                fid = int(row.get("index") or "0")
            except ValueError:
                continue
            name = strip_fms_markup(row.get("text") or "")
            if not name or name == "???":
                continue
            out[fid] = name
    return out


def _enum_title_name(sym: str) -> str:
    pretty = sym
    for prefix in ("ACT_", "PAS_", "DEFAULT_"):
        if pretty.startswith(prefix):
            pretty = pretty[len(prefix) :]
            break
    return pretty.replace("_", " ").title()


def _is_stub_skill_name(name: str) -> bool:
    n = (name or "").strip()
    if not n or n.lower() in ("none", "null"):
        return True
    if "プログラム" in n:
        return True
    return False


def load_skill_catalog() -> list[dict]:
    """Skills for searchable picker: id, symbol, official EN name, kind folder.

    Name priority: UcSkillList FMS → class_skills.csv → enum title-case.
    (item_skills.csv is applied later only to fill gaps — some item rows use
    short/wrong labels like Evade for Nimble Fighter.)
    """
    fms_names = load_fms_skill_names()
    by_id: dict[int, dict] = {}

    enum = parse_enum(DEBUG / "_UcEnum_Skill.inc", "BT_SKILLID:")
    skip_syms = {
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
    }
    for sid, sym in enumerate(enum):
        if sid <= 0:
            continue
        if sym in skip_syms or sym.startswith("EQUIPAI_"):
            continue
        kind = (
            "passive"
            if sym.startswith("PAS_")
            else ("active" if sym.startswith("ACT_") else "other")
        )
        name = fms_names.get(sid) or _enum_title_name(sym)
        by_id[sid] = {
            "id": sid,
            "symbol": sym,
            "name": name,
            "kind": kind,
        }

    for r in load_csv("class_skills.csv"):
        try:
            sid = int(r["skill_id"])
        except (KeyError, ValueError):
            continue
        if sid <= 0:
            continue
        sym = (r.get("skill_symbol") or "").strip()
        name = (r.get("skill_name") or "").strip()
        kind = (
            "passive"
            if sym.startswith("PAS_")
            else ("active" if sym.startswith("ACT_") else "other")
        )
        entry = by_id.get(sid)
        if entry is None:
            by_id[sid] = {
                "id": sid,
                "symbol": sym,
                "name": fms_names.get(sid)
                or (name if not _is_stub_skill_name(name) else sym),
                "kind": kind,
            }
            continue
        if sym and not entry.get("symbol"):
            entry["symbol"] = sym
        # Prefer FMS; only use class_skills when FMS missing.
        if sid not in fms_names and name and not _is_stub_skill_name(name):
            entry["name"] = name

    return [by_id[k] for k in sorted(by_id)]


def main() -> None:
    stages = load_csv("stage_unitsets.csv")
    unitsets = {r["unitset_id"]: r for r in load_csv("unitsets.csv")}
    charasets = {
        (r.get("chara_id") or r.get("charaset_id")): r
        for r in load_csv("charasets.csv")
    }
    chara_names: dict[str, str] = {}
    for r in load_csv("characters.csv"):
        sym = (r.get("charaset_symbol") or "").strip()
        name = (r.get("name_en") or "").strip()
        if sym and name and name.lower() not in ("none", "null"):
            chara_names[sym] = name
        cid = (r.get("character_id") or "").strip()
        if cid and name and name.lower() not in ("none", "null"):
            chara_names[cid] = name
    presets = {r["equipaiset_id"]: r for r in load_csv("equipaiset_presets.csv")}
    ifs = {r["if_id"]: r for r in load_csv("equipai_if.csv")}
    factor_names = load_fms_factor_names()

    def if_label(if_id: int | str | None, fallback: str = "") -> str:
        try:
            iid = int(if_id or 0)
        except (TypeError, ValueError):
            return (fallback or "").strip()
        if iid <= 0:
            return ""
        name = factor_names.get(iid, "")
        if name and name.lower() != "none":
            return name
        return (fallback or "").strip()
    item_names, item_symbols, item_catalog = load_item_catalog()
    skill_catalog = load_skill_catalog()
    charaset_catalog = load_charaset_catalog(item_names, item_symbols, chara_names)

    class_ets: dict[int, list[int]] = {}
    class_et_symbols: dict[int, list[str]] = {}
    class_equiptypes_catalog: list[dict] = []
    for r in load_csv("class_equiptypes.csv"):
        try:
            cid = int(r["class_id"])
        except (KeyError, ValueError):
            continue
        slots = [int(r.get(f"slot{s}_equiptype") or 0) for s in range(4)]
        slot_syms = [r.get(f"slot{s}_symbol") or "" for s in range(4)]
        class_ets[cid] = slots
        class_et_symbols[cid] = slot_syms
        class_equiptypes_catalog.append(
            {
                "class_id": cid,
                "class_symbol": r.get("class_symbol") or "",
                "slots": [
                    {
                        "slot": s,
                        "equiptype_id": slots[s],
                        "equiptype_symbol": slot_syms[s],
                    }
                    for s in range(4)
                ],
            }
        )

    et_items: dict[int, tuple[int, int, int]] = {}
    equiptype_symbols: dict[int, str] = {}
    equiptype_items_catalog: list[dict] = []
    for r in load_csv("equiptype_items.csv"):
        try:
            eid = int(r["equiptype_id"])
        except (KeyError, ValueError):
            continue
        cols = (
            int(r.get("item_col0_id") or 0),
            int(r.get("item_col1_id") or 0),
            int(r.get("item_col2_id") or 0),
        )
        et_items[eid] = cols
        sym = r.get("equiptype_symbol") or ""
        equiptype_symbols[eid] = sym
        equiptype_items_catalog.append(
            {
                "id": eid,
                "symbol": sym,
                "item_col0_id": cols[0],
                "item_col0": item_names.get(cols[0], r.get("item_col0") or ""),
                "item_col1_id": cols[1],
                "item_col1": item_names.get(cols[1], r.get("item_col1") or ""),
                "item_col2_id": cols[2],
                "item_col2": item_names.get(cols[2], r.get("item_col2") or ""),
                "note": (
                    "col0=lv1-14, col1=lv15-27, col2=lv28-50; "
                    "tier adds +0/+11/+22/+33/+44 to class DEFAULT base"
                ),
            }
        )

    def item_meta(iid: int, fallback_symbol: str = "") -> tuple[str, str]:
        sym = fallback_symbol or item_symbols.get(iid, "")
        name = item_names.get(iid, "")
        return sym, name

    def resolve_default_item(
        class_id: int,
        slot: int,
        equip_param: int,
        level: int,
        *,
        charaset_id: int = 0,
    ) -> tuple[int, int, int]:
        """Return (item_id, equiptype_id, level_col) for an empty CharaSet slot.

        Matches CreateDefaultEquip 0xDD290: item = EQUITYPE[tier*11 + class_ET]
        with NO skip when class_ET == 0 (NONE). BOSS+NONE indexes POWER_ACC2
        (Gold Bangle) — that is how Culloran gets ACC slot 3.
        """
        bases = class_ets.get(class_id) or [0, 0, 0, 0]
        if not (0 <= slot < 4):
            return 0, 0, -1
        base_et = bases[slot]
        # base_et may be 0 (NONE); native still computes tier*11 + 0.
        col = level_column(level)
        if col < 0:
            return 0, 0, -1
        et = base_et + PARAMSET_ET_OFFSET.get(equip_param, 0)
        row = et_items.get(et)
        if not row:
            return 0, et, col
        iid = row[col]
        # Native DD290: skip accessory fills when 0x30c2c(item) && 0x124898(chara)
        # (CharaSet ids 1..560). Liberation bosses like Culloran (635) are uncapped.
        if iid and 1 <= charaset_id <= 560 and 0x30F <= iid < 0x30F + 0xC8:
            return 0, et, col
        return iid, et, col

    skill_name_by_id = {
        int(s["id"]): (s.get("name") or s.get("symbol") or "")
        for s in skill_catalog
    }
    skill_symbol_by_id = {
        int(s["id"]): (s.get("symbol") or "") for s in skill_catalog
    }
    fms_names = load_fms_skill_names()
    # Fill gaps only. Prefer FMS / catalog over item_skills (some item rows use
    # short labels that are not the official skill name).
    for r in load_csv("item_skills.csv"):
        try:
            sid = int(r["skill_id"])
        except (KeyError, ValueError):
            continue
        sym = (r.get("skill_symbol") or "").strip()
        if sid and sym and sid not in skill_symbol_by_id:
            skill_symbol_by_id[sid] = sym
        if sid in fms_names:
            skill_name_by_id[sid] = fms_names[sid]
            continue
        name = (r.get("skill_name") or "").strip()
        if (
            sid
            and name
            and not _is_stub_skill_name(name)
            and (
                sid not in skill_name_by_id
                or _is_stub_skill_name(skill_name_by_id.get(sid, ""))
            )
        ):
            skill_name_by_id[sid] = name

    lines_by_id: dict[str, list[dict]] = {}
    for r in load_csv("equipaiset_lines.csv"):
        eid = r["equipaiset_id"]
        sid = int(r.get("skill_id") or 0)
        entry = {
            "action": int(r["action"]),
            "slot": int(r.get("slot") or r.get("line_index") or 0),
            "if0": int(r["if0"]),
            "if1": int(r["if1"]),
            "skill_id": sid,
            "skill_symbol": r.get("skill_symbol")
            or skill_symbol_by_id.get(sid, ""),
            "ref_kind": r.get("ref_kind")
            or (
                "class_slot"
                if 2 <= sid <= 10
                else ("skill" if sid else "")
            ),
        }
        if0 = entry["if0"]
        if1 = entry["if1"]
        if if0:
            entry["if0_symbol"] = if_label(
                if0,
                r["if0_symbol"]
                if r.get("if0_symbol") and r["if0_symbol"] != "UNKNOWN"
                else "",
            )
        if if1:
            entry["if1_symbol"] = if_label(
                if1,
                r["if1_symbol"]
                if r.get("if1_symbol") and r["if1_symbol"] != "UNKNOWN"
                else "",
            )
        if sid and sid not in range(2, 11):
            entry["skill_name"] = skill_name_by_id.get(sid, "")
        lines_by_id.setdefault(eid, []).append(entry)

    class_lines: dict[str, list[dict]] = {}
    for r in load_csv("class_default_tactics_lines.csv"):
        cid = r["class_id"]
        entry = {
            "action": int(r["action"]),
            "if0": int(r.get("if0") or 0),
            "if1": int(r.get("if1") or 0),
            "from_class_default": True,
            "learn_level": int(r.get("learn_level") or 1),
        }
        if entry["if0"]:
            entry["if0_symbol"] = if_label(entry["if0"], r.get("if0_symbol") or "")
        if entry["if1"]:
            entry["if1_symbol"] = if_label(entry["if1"], r.get("if1_symbol") or "")
        if r.get("skill_id"):
            entry["skill_id"] = int(r["skill_id"])
            entry["skill_symbol"] = r.get("skill_symbol") or ""
            entry["skill_name"] = r.get("skill_name") or ""
        class_lines.setdefault(cid, []).append(entry)

    class_names = parse_enum(DEBUG / "_UcEnum_Class.inc", "CLASSTYPE:")
    class_tactics = [
        {
            "class_id": cid,
            "class_symbol": class_names[cid],
            "lines": class_lines.get(str(cid), []),
        }
        for cid in range(len(class_names))
    ]

    preset_fields = {
        r["equipaiset_id"]: r for r in load_csv("equipaiset_fields.csv")
    }

    item_skills: dict[int, dict] = {}
    for r in load_csv("item_skills.csv"):
        try:
            iid = int(r["item_id"])
            sid = int(r["skill_id"])
        except (KeyError, ValueError):
            continue
        if not (iid and sid):
            continue
        entry = {
            "skill_id": sid,
            "skill_symbol": r.get("skill_symbol") or "",
            "skill_name": r.get("skill_name") or "",
            "if0": int(r.get("if0") or 0),
            "if1": int(r.get("if1") or 0),
        }
        if entry["if0"]:
            entry["if0_symbol"] = if_label(entry["if0"], r.get("if0_symbol") or "")
        if entry["if1"]:
            entry["if1_symbol"] = if_label(entry["if1"], r.get("if1_symbol") or "")
        item_skills[iid] = entry

    def tactics_for_class(
        class_id: int, unit_level: int, gear: list[dict] | None = None
    ) -> list[dict]:
        """Equipped class-default tactics + item skills, filtered by learn level."""
        lvl = unit_level if unit_level > 0 else 1
        # In-game the tactics list shows every class slot; skills above the unit's
        # level render locked (red) rather than being removed. Keep them and flag.
        class_rows = []
        for line in class_lines.get(str(class_id)) or []:
            row = dict(line)
            row["locked"] = int(line.get("learn_level") or 1) > lvl
            class_rows.append(row)
        actives = [r for r in class_rows if int(r.get("action") or 0) < 7]
        passives = [r for r in class_rows if int(r.get("action") or 0) >= 7]

        have = {int(r.get("skill_id") or 0) for r in class_rows}
        item_active: list[dict] = []
        item_passive: list[dict] = []
        for g in gear or []:
            iid = int(g.get("item_id") or 0)
            meta = item_skills.get(iid)
            if not meta:
                continue
            sid = int(meta["skill_id"])
            if not sid or sid in have:
                continue
            have.add(sid)
            ssym = meta["skill_symbol"]
            kind_passive = ssym.startswith("PAS_")
            entry = {
                "action": 7 if kind_passive else 3,
                "if0": int(meta.get("if0") or 0),
                "if1": int(meta.get("if1") or 0),
                "from_item": True,
                "item_id": iid,
                "learn_level": 1,
                "skill_id": sid,
                "skill_symbol": ssym,
                "skill_name": meta["skill_name"],
            }
            if meta.get("if0_symbol"):
                entry["if0_symbol"] = meta["if0_symbol"]
            if meta.get("if1_symbol"):
                entry["if1_symbol"] = meta["if1_symbol"]
            (item_passive if kind_passive else item_active).append(entry)

        return actives + item_active + item_passive + passives

    def tactics_for_preset(
        class_id: int,
        unit_level: int,
        gear: list[dict] | None,
        preset_lines: list[dict],
    ) -> list[dict]:
        """Non-zero EquipAiSet: authoritative list from tactics-slot table 0x270AF48.

        Unit init (0xDDB90) installs that list and skips the class+item builder
        (0xDD610). Markers 3..10 resolve to the class skill for that action;
        other skill ids are explicit (often item-granted, e.g. Lifeshare).
        Slot IF0/IF1 are final — 0/0 means no condition, not skill-default IFs.
        `gear` is unused for resolution but kept for call-site compatibility.
        """
        del gear
        lvl = unit_level if unit_level > 0 else 1
        class_by_action: dict[int, dict] = {}
        for line in class_lines.get(str(class_id)) or []:
            class_by_action[int(line.get("action") or 0)] = line

        if not preset_lines:
            return tactics_for_class(class_id, unit_level, None)

        out: list[dict] = []
        for ln in preset_lines:
            sid = int(ln.get("skill_id") or 0)
            ref_kind = ln.get("ref_kind") or (
                "class_slot" if 2 <= sid <= 10 else "skill"
            )
            if0 = int(ln.get("if0") or 0)
            if1 = int(ln.get("if1") or 0)
            entry: dict = {
                "slot": int(ln.get("slot") or 0),
                "if0": if0,
                "if1": if1,
                "from_equipaiset_preset": True,
                "ref_kind": ref_kind,
            }
            if ln.get("if0_symbol"):
                entry["if0_symbol"] = ln["if0_symbol"]
            if ln.get("if1_symbol"):
                entry["if1_symbol"] = ln["if1_symbol"]

            if ref_kind == "class_slot" or 2 <= sid <= 10:
                base = class_by_action.get(sid)
                if not base:
                    continue
                entry.update(
                    {
                        "action": int(base.get("action") or sid),
                        "skill_id": int(base.get("skill_id") or 0),
                        "skill_symbol": base.get("skill_symbol") or "",
                        "skill_name": base.get("skill_name") or "",
                        "learn_level": int(base.get("learn_level") or 1),
                        "locked": int(base.get("learn_level") or 1) > lvl,
                        "from_class_default": True,
                    }
                )
            else:
                entry.update(
                    {
                        "action": int(ln.get("action") or 3),
                        "skill_id": sid,
                        "skill_symbol": ln.get("skill_symbol")
                        or skill_symbol_by_id.get(sid, ""),
                        "skill_name": ln.get("skill_name")
                        or skill_name_by_id.get(sid, ""),
                        "learn_level": 1,
                        "locked": False,
                        "from_item": True,
                    }
                )
            out.append(entry)
        return out

    overrides = {}
    if OVERRIDES.exists():
        overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
        overrides.pop("_comment", None)

    missions: dict[str, dict] = {}
    for st in stages:
        qid = st["quest_id"]
        if qid not in missions:
            missions[qid] = {
                "quest_id": int(qid),
                "quest_symbol": st["quest_symbol"],
                "stage_name": st["stage_name"],
                "region": st["region"],
                "enemy_level": st.get("enemy_level") or "",
                "squads": [],
            }
        uid = st["unitset_id"]
        u = unitsets.get(uid, {})
        try:
            exptype = int(st.get("exptype") or u.get("exptype") or 0)
        except ValueError:
            exptype = 0
        try:
            paramset = int(u.get("field_14") or 0)
        except ValueError:
            paramset = 0
        if paramset < 0 or paramset > 6:
            paramset = 0
        try:
            level = int(float(st.get("enemy_level") or 0))
        except ValueError:
            level = 0
        role = squad_role(st.get("unitset_symbol") or u.get("unitset_symbol") or "")

        squad_boss_override = False
        for i in range(6):
            raw_cid = u.get(f"slot{i}_chara_id") or ""
            try:
                sci = int(raw_cid) if raw_cid else 0
            except ValueError:
                sci = 0
            if not sci:
                continue
            sch = charasets.get(str(sci), {})
            try:
                if int(sch.get("equip_param_override") or 0) >= 4:
                    squad_boss_override = True
                    break
            except ValueError:
                pass

        slots = []
        for i in range(6):
            cid = u.get(f"slot{i}_chara_id") or ""
            eid = u.get(f"slot{i}_equipai_id") or "0"
            flags = u.get(f"slot{i}_flags") or "0"
            if not cid:
                continue
            try:
                ci = int(cid)
            except ValueError:
                continue
            if ci == 0:
                continue
            ch = charasets.get(str(ci), {})
            try:
                ei = int(eid) if eid else 0
            except ValueError:
                ei = 0
            class_id_s = ch.get("class_id") or ch.get("classtype") or "0"
            try:
                class_id = int(class_id_s)
            except ValueError:
                class_id = 0

            try:
                ove = int(ch.get("equip_param_override") or 0)
            except ValueError:
                ove = 0
            equip_param = resolve_equip_param(
                exptype, paramset, ove, squad_boss_override=squad_boss_override
            )

            gear = []
            for g in range(4):
                gid = ch.get(f"equip{g}_id") or ch.get(f"gear{g}_id") or "0"
                gsym = ch.get(f"equip{g}_symbol") or ch.get(f"gear{g}") or ""
                gname = ch.get(f"equip{g}_name") or ""
                try:
                    gi = int(gid) if gid else 0
                except ValueError:
                    gi = 0
                if gi:
                    sym, name = item_meta(gi, gsym)
                    gear.append(
                        {
                            "item_id": gi,
                            "rom_item_id": gi,
                            "item_symbol": sym,
                            "item_name": name or gname,
                            "source": "charaset",
                        }
                    )
                else:
                    di, et, col = resolve_default_item(
                        class_id, g, equip_param, level, charaset_id=ci
                    )
                    if di:
                        sym, name = item_meta(di)
                        gear.append(
                            {
                                "item_id": di,
                                "rom_item_id": 0,
                                "item_symbol": sym,
                                "item_name": name,
                                "source": "createdefault",
                                "from_equiptype": True,
                                "equiptype_id": et,
                                "equiptype_symbol": equiptype_symbols.get(et, ""),
                                "equiptype_param": equip_param,
                                "equiptype_param_name": PARAMSET_NAME.get(
                                    equip_param, str(equip_param)
                                ),
                                "unit_paramset": paramset,
                                "unit_paramset_name": PARAMSET_NAME.get(
                                    paramset, str(paramset)
                                ),
                                "chara_param_override": ove,
                                "equiptype_level": level,
                                "equiptype_col": col,
                                "note": (
                                    "ROM CharaSet slot empty; filled at unit init by "
                                    "CreateDefaultEquip (0xDCD74)."
                                ),
                            }
                        )
                    else:
                        gear.append(
                            {
                                "item_id": 0,
                                "rom_item_id": 0,
                                "item_symbol": "",
                                "item_name": "",
                                "source": "empty",
                            }
                        )

            if ei:
                preset = overrides.get(str(ei)) or lines_by_id.get(str(ei)) or []
                lines = tactics_for_preset(class_id, level, gear, preset)
            else:
                lines = tactics_for_class(class_id, level, gear)
            sym_key = (
                u.get(f"slot{i}_chara")
                or ch.get("chara_symbol")
                or ch.get("charaset_symbol")
                or ""
            )
            slots.append(
                {
                    "slot": i,
                    "charaset_id": ci,
                    "charaset_symbol": sym_key,
                    "chara_name": chara_names.get(sym_key, ""),
                    "class_id": class_id,
                    "class_symbol": ch.get("class_enum")
                    or ch.get("class_symbol")
                    or "",
                    "flags": int(flags) if str(flags).isdigit() else 0,
                    "equipaiset_id": ei,
                    "equipaiset_symbol": u.get(f"slot{i}_equipai")
                    or (presets.get(str(ei), {}) or {}).get("equipaiset_symbol")
                    or "",
                    "gear": gear,
                    "tactics_lines": lines,
                    "equip_param": equip_param,
                    "equip_param_name": PARAMSET_NAME.get(equip_param, str(equip_param)),
                    "chara_param_override": ove,
                }
            )
        missions[qid]["squads"].append(
            {
                "unitset_id": int(uid),
                "unitset_symbol": st["unitset_symbol"],
                "side": st["side"],
                "role": role,
                "paramset": paramset,
                "paramset_name": PARAMSET_NAME.get(paramset, str(paramset)),
                "exptype": st.get("exptype"),
                "exptype_name": st.get("exptype_name"),
                "field_14": paramset,
                "join_source": st.get("join_source"),
                "slots": slots,
            }
        )

    # Preset usage across ALL UnitSets (not just the 90 joined story missions).
    # Map each UnitSet to a mission when possible; otherwise label by symbol.
    unitset_to_mission: dict[str, dict] = {}
    for st in stages:
        uid = str(st["unitset_id"])
        if uid not in unitset_to_mission:
            try:
                st_level = int(float(st.get("enemy_level") or 0))
            except ValueError:
                st_level = 0
            unitset_to_mission[uid] = {
                "quest_symbol": st.get("quest_symbol") or "",
                "stage_name": st.get("stage_name") or "",
                "side": st.get("side") or "",
                "enemy_level": st_level,
                "paramset": int(st.get("field_14") or st.get("paramset") or 0)
                if str(st.get("field_14") or st.get("paramset") or "")
                .lstrip("-")
                .isdigit()
                else 0,
                "exptype": int(st.get("exptype") or 0)
                if str(st.get("exptype") or "").lstrip("-").isdigit()
                else 0,
            }

    def context_label(symbol: str) -> str:
        body = (symbol or "").replace("UC_UNITSET_", "")
        if body.startswith("ARENA"):
            return "Arena"
        if body.startswith("OW_TK_"):
            return "Battle of Sorm"
        head = body.split("_")[0] if body else ""
        return {
            "OW": "Overworld",
            "EV": "Event",
            "TUTO": "Tutorial",
            "TEST": "Test",
            "DLC": "DLC",
        }.get(head, head or "Other")

    ASSUMED_OUTSIDE_LEVEL = 1

    def resolve_slot_gear(
        ch: dict,
        class_id: int,
        equip_param: int,
        level: int,
        charaset_id: int,
    ) -> list[dict]:
        gear: list[dict] = []
        for g in range(4):
            gid = ch.get(f"equip{g}_id") or ch.get(f"gear{g}_id") or "0"
            gsym = ch.get(f"equip{g}_symbol") or ch.get(f"gear{g}") or ""
            gname = ch.get(f"equip{g}_name") or ""
            try:
                gi = int(gid) if gid else 0
            except ValueError:
                gi = 0
            if gi:
                sym, name = item_meta(gi, gsym)
                gear.append(
                    {
                        "item_id": gi,
                        "rom_item_id": gi,
                        "item_symbol": sym,
                        "item_name": name or gname,
                        "source": "charaset",
                    }
                )
            else:
                di, et, col = resolve_default_item(
                    class_id, g, equip_param, level, charaset_id=charaset_id
                )
                if di:
                    sym, name = item_meta(di)
                    gear.append(
                        {
                            "item_id": di,
                            "rom_item_id": 0,
                            "item_symbol": sym,
                            "item_name": name,
                            "source": "createdefault",
                            "from_equiptype": True,
                            "equiptype_id": et,
                            "equiptype_col": col,
                        }
                    )
                else:
                    gear.append(
                        {
                            "item_id": 0,
                            "rom_item_id": 0,
                            "item_symbol": "",
                            "item_name": "",
                            "source": "empty",
                        }
                    )
        return gear

    preset_refs: dict[int, list[dict]] = {}
    for uid, u in unitsets.items():
        usym = u.get("unitset_symbol") or ""
        mission = unitset_to_mission.get(str(uid))
        try:
            us_paramset = int(u.get("field_14") or u.get("paramset") or 0)
        except ValueError:
            us_paramset = 0
        try:
            us_exptype = int(u.get("exptype") or 0)
        except ValueError:
            us_exptype = 0

        squad_boss_override = False
        for i in range(6):
            raw_cid = u.get(f"slot{i}_chara_id") or ""
            try:
                sci = int(raw_cid) if raw_cid else 0
            except ValueError:
                sci = 0
            if not sci:
                continue
            sch = charasets.get(str(sci), {})
            try:
                if int(sch.get("equip_param_override") or 0) >= 4:
                    squad_boss_override = True
                    break
            except ValueError:
                pass

        for i in range(6):
            raw = u.get(f"slot{i}_equipai_id") or ""
            if not (raw.isdigit() and int(raw) > 0):
                continue
            eid = int(raw)
            sym_key = u.get(f"slot{i}_chara") or ""
            raw_cid = u.get(f"slot{i}_chara_id") or ""
            try:
                ci = int(raw_cid) if raw_cid else 0
            except ValueError:
                ci = 0
            ch = charasets.get(str(ci), {}) if ci else {}
            try:
                class_id = int(ch.get("class_id") or ch.get("classtype") or 0)
            except ValueError:
                class_id = 0
            try:
                ove = int(ch.get("equip_param_override") or 0)
            except ValueError:
                ove = 0

            joined = bool(mission and (mission.get("stage_name") or mission.get("quest_symbol")))
            if mission and int(mission.get("enemy_level") or 0) > 0:
                level = int(mission["enemy_level"])
                level_source = "stage"
            else:
                level = ASSUMED_OUTSIDE_LEVEL
                level_source = "assumed"

            paramset = int(mission.get("paramset") or 0) if mission else us_paramset
            if not paramset:
                paramset = us_paramset
            exptype = int(mission.get("exptype") or 0) if mission else us_exptype
            if not exptype:
                exptype = us_exptype
            equip_param = resolve_equip_param(
                exptype, paramset, ove, squad_boss_override=squad_boss_override
            )
            gear = resolve_slot_gear(ch, class_id, equip_param, level, ci)
            preset_lines = overrides.get(str(eid)) or lines_by_id.get(str(eid)) or []
            resolved = tactics_for_preset(class_id, level, gear, preset_lines)

            preset_refs.setdefault(eid, []).append(
                {
                    "unitset_id": int(uid),
                    "unitset_symbol": usym,
                    "squad_name": usym.replace("UC_UNITSET_", ""),
                    "slot": i,
                    "unit": chara_names.get(sym_key, "") or sym_key,
                    "quest_symbol": (mission or {}).get("quest_symbol", ""),
                    "stage_name": (mission or {}).get("stage_name", ""),
                    "context": (mission or {}).get("stage_name")
                    or context_label(usym),
                    "charaset_id": ci,
                    "charaset_symbol": sym_key
                    or ch.get("chara_symbol")
                    or ch.get("charaset_symbol")
                    or "",
                    "class_id": class_id,
                    "class_symbol": ch.get("class_enum")
                    or ch.get("class_symbol")
                    or "",
                    "resolution": {
                        "joined_mission": joined,
                        "enemy_level": level if level_source == "stage" else None,
                        "level_source": level_source,
                        "assumed_level": level if level_source == "assumed" else None,
                        "equip_param": equip_param,
                        "equip_param_name": PARAMSET_NAME.get(
                            equip_param, str(equip_param)
                        ),
                        "gear": gear,
                    },
                    "resolved_tactics": resolved,
                }
            )

    marker_label = {
        2: "Normal Attack",
        3: "Active Lv1",
        4: "Active Lv2",
        5: "Active Lv3",
        6: "Active Lv4",
        7: "Passive Lv1",
        8: "Passive Lv2",
        9: "Passive Lv3",
        10: "Passive Lv4",
    }

    def enrich_marker_lines(raw_lines: list[dict], refs: list[dict]) -> list[dict]:
        """Resolve EQUIPAI class-slot markers (3..10) to the real class skill.

        A preset may be shared by several classes; resolve against each
        referenced class and attach the concrete skill when they agree.
        """
        ref_classes: list[int] = []
        for r in refs:
            cid = int(r.get("class_id") or 0)
            if cid and cid not in ref_classes:
                ref_classes.append(cid)

        out: list[dict] = []
        for ln in raw_lines:
            entry = dict(ln)
            sid = int(ln.get("skill_id") or 0)
            is_marker = (ln.get("ref_kind") == "class_slot") or (2 <= sid <= 10)
            if is_marker:
                entry["marker_id"] = sid
                entry["marker_label"] = marker_label.get(sid, f"Slot {sid}")
                resolved: list[tuple[int, str, str]] = []
                for cid in ref_classes:
                    base = None
                    for cl in class_lines.get(str(cid)) or []:
                        if int(cl.get("action") or 0) == sid:
                            base = cl
                            break
                    if base and int(base.get("skill_id") or 0):
                        resolved.append(
                            (
                                int(base["skill_id"]),
                                base.get("skill_name") or "",
                                base.get("skill_symbol") or "",
                            )
                        )
                uniq = list(dict.fromkeys(resolved))
                if uniq:
                    rsid, rname, rsym = uniq[0]
                    entry["resolved_skill_id"] = rsid
                    entry["resolved_skill_name"] = rname or skill_name_by_id.get(
                        rsid, ""
                    )
                    entry["resolved_skill_symbol"] = rsym
                    if len(uniq) > 1:
                        entry["resolved_ambiguous"] = True
                        entry["resolved_alternatives"] = [
                            {
                                "class_id": ref_classes[i],
                                "skill_id": u[0],
                                "skill_name": u[1]
                                or skill_name_by_id.get(u[0], ""),
                                "skill_symbol": u[2],
                            }
                            for i, u in enumerate(uniq)
                        ]
            else:
                entry.setdefault(
                    "skill_name", skill_name_by_id.get(sid, "")
                )
            out.append(entry)
        return out

    equipaiset_catalog = []
    for eid_s, preset in sorted(presets.items(), key=lambda x: int(x[0])):
        eid = int(eid_s)
        if eid == 0:
            continue
        fields = preset_fields.get(eid_s, {})
        refs = preset_refs.get(eid, [])
        equipaiset_catalog.append(
            {
                "id": eid,
                "symbol": preset.get("equipaiset_symbol") or "",
                "usage": len(refs),
                "skill_ai_id": int(fields.get("skill_ai_id") or 0),
                "count_a": int(fields.get("count_a") or 0),
                "count_b": int(fields.get("count_b") or 0),
                "lines": enrich_marker_lines(lines_by_id.get(eid_s, []), refs),
                "references": refs,
            }
        )

    doc = {
        "build": {
            "title_id": "010069401adb8000",
            "nsobid": "C841FFE2717FF03A13990480C51DA73F091C04FA",
            "offset_shift": "0x100",
            "version": "US 1.0.5",
            "gear_policy": "charaset_then_createdefault",
            "preset_resolve_policy": {
                "outside_level": "assume_band0",
                "assumed_level": ASSUMED_OUTSIDE_LEVEL,
                "tactics_table": "0x270AF48",
                "note": (
                    "Non-zero EquipAiSet installs tactics-slot table 0x270AF48 "
                    "(getter 0x229B4 / apply 0xDDB90) and skips class+item builder "
                    "0xDD610. Outside stage_unitsets: no enemy_level; locked flags "
                    "use assumed_level."
                ),
            },
        },
        "addresses": {
            "unitset_base": "0x28120B8",
            "unitset_stride": "0x88",
            "charaset_base": "0x276DD68",
            "charaset_stride": "0x48",
            "charaset_equip_param_override": "0x1E",
            "equip_param_resolver": "0x2CBFE8",
            "equip_param_clamp": "0x123834",
            "equipaiset_base": "0x2787F28",
            "equipaiset_stride": "0x130",
            "equipaiset_tactics_slots_base": "0x270AF48",
            "equipaiset_tactics_slots_stride": "0x48",
            "skill_ai_base": "0x27AAE78",
            "skill_ai_stride": "0x100",
            "class_skill_ai_base": "0xD36D94",
            "class_skill_ai_stride": "0x8C",
            "class_base": "0xD2DFC8",
            "class_stride": "0x58",
            "class_equiptype_offset": "0x44",
            "equiptype_item_base": "0xD13E30",
            "equiptype_item_stride": "0xC",
            "equipaiset_type_manager_base": 486,
        },
        "equipai_if": [
            {
                "id": int(k),
                "symbol": v.get("if_symbol"),
                "name": if_label(k, v.get("if_symbol") or ""),
                "comment": v.get("comment_jp"),
            }
            for k, v in sorted(ifs.items(), key=lambda x: int(x[0]))
        ],
        "items": item_catalog,
        "charasets": charaset_catalog,
        "skills": skill_catalog,
        "class_tactics": class_tactics,
        "equiptype_items": equiptype_items_catalog,
        "class_equiptypes": class_equiptypes_catalog,
        "equipaiset_presets": equipaiset_catalog,
        "missions": sorted(missions.values(), key=lambda m: m["quest_id"]),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    public_data = (
        ROOT / "Tools" / "mission_editor" / "public" / "data" / "mission_squads.json"
    )
    public_data.parent.mkdir(parents=True, exist_ok=True)
    public_data.write_text(OUT.read_text(encoding="utf-8"), encoding="utf-8")
    print(
        f"wrote {OUT} ({len(doc['missions'])} missions, "
        f"{len(skill_catalog)} skills, {len(charaset_catalog)} charasets, "
        f"gear=charaset_then_createdefault)"
    )
    print(f"synced {public_data}")


if __name__ == "__main__":
    main()
