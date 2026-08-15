#!/usr/bin/env python3
"""Decode Vanillaware FMS type-3 string sheets and build unit/class/skill CSVs."""

from __future__ import annotations

import csv
import re
import struct
import sys
from pathlib import Path

PROJECT = Path(r"d:\Documents\Projects\Emulation\UnicornOverlord")
CPK_US = PROJECT / "Extraction" / "cpk_data" / "Unicorn_US" / "MsgSheet"
TABLES = PROJECT / "Extraction" / "tables"
DEBUG = PROJECT / "Extraction" / "cpk_data" / "Unicorn_US" / "Debug"

RANK_MAP = {"E": 1, "D": 2, "C": 3, "B": 4, "A": 5, "S": 6, "F": 0}

# Source: https://ragequithq.site/unicorn-overlord/uo-class-status-growth-rate-table/
CLASS_GROWTH: dict[str, dict[str, str]] = {
    "Lord": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,C,B,C,B,B,B,C,A,B".split(","))),
    "High Lord": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "A,C,A,C,B,B,A,C,S,A".split(","))),
    "Fighter": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,C,B,D,E,C,E,D,S,C".split(","))),
    "Vanguard": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,C,A,D,E,C,E,D,S,C".split(","))),
    "Soldier": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,B,C,D,C,D,C,D,E,C".split(","))),
    "Sergeant": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,B,B,D,C,C,C,D,E,B".split(","))),
    "Housecarl": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,A,C,F,E,D,D,E,D,B".split(","))),
    "Viking": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,A,C,F,E,C,D,D,C,B".split(","))),
    "Sword Fighter": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,C,E,D,B,S,S,S,E,S".split(","))),
    "Swordmaster": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,C,E,D,B,S,S,S,E,S".split(","))),
    "Sellsword": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,S,B,F,D,E,E,D,C,E".split(","))),
    "Landsknecht": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "A,S,B,F,D,E,E,C,B,E".split(","))),
    "Hoplite": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,D,S,E,F,D,F,F,S,F".split(","))),
    "Legionnaire": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,C,S,E,F,D,F,F,S,F".split(","))),
    "Gladiator": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "S,B,F,F,E,F,F,E,F,F".split(","))),
    "Berserker": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "S,A,F,F,E,E,F,E,D,F".split(","))),
    "Warrior": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,S,B,F,C,D,D,F,C,C".split(","))),
    "Breaker": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,S,A,F,C,D,D,F,B,C".split(","))),
    "Hunter": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,C,E,D,B,S,C,B,E,C".split(","))),
    "Sniper": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,B,E,D,A,S,B,A,E,C".split(","))),
    "Arbalist": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,A,D,E,B,A,E,E,B,E".split(","))),
    "Shield Shooter": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,A,C,E,B,S,E,E,S,D".split(","))),
    "Thief": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "E,D,F,D,C,A,S,A,F,S".split(","))),
    "Rogue": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "E,D,F,D,C,A,S,S,F,S".split(","))),
    "Knight": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,B,B,D,C,E,F,C,C,C".split(","))),
    "Great Knight": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,A,A,D,C,E,F,B,B,C".split(","))),
    "Radiant Knight": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,D,C,C,S,D,F,F,B,C".split(","))),
    "Sainted Knight": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,C,C,B,S,C,F,F,B,C".split(","))),
    "Dark Knight": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,A,A,D,C,E,F,B,B,C".split(","))),
    "Doom Knight": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "A,S,B,A,D,D,F,E,B,D".split(","))),
    "Cleric": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,F,E,C,S,C,B,F,F,E".split(","))),
    "Bishop": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,F,D,C,S,C,B,F,F,E".split(","))),
    "Wizard": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,F,E,A,A,E,D,F,F,E".split(","))),
    "Warlock": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,F,E,S,S,E,D,F,F,E".split(","))),
    "Witch": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "E,F,E,B,S,D,C,F,F,E".split(","))),
    "Sorceress": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,F,E,A,S,D,C,F,F,E".split(","))),
    "Shaman": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,D,C,D,S,C,B,C,F,B".split(","))),
    "Druid": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,D,C,D,S,C,B,C,F,A".split(","))),
    "Wyvern Knight": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,B,B,F,E,C,A,C,E,C".split(","))),
    "Wyvern Master": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,A,B,F,E,B,S,C,E,B".split(","))),
    "Gryphon Knight": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,B,D,E,B,D,S,D,F,D".split(","))),
    "Gryphon Master": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,B,C,E,A,D,S,D,F,C".split(","))),
    "Elven Fencer": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,B,D,A,B,C,B,D,D,C".split(","))),
    "Elven Archer": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,C,E,A,A,S,D,D,F,A".split(","))),
    "Werewolf": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,B,D,F,E,S,C,B,F,B".split(","))),
    "Werefox": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,C,E,D,C,A,S,S,F,S".split(","))),
    "Werebear": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "S,B,C,F,F,F,F,E,S,F".split(","))),
    "Wereowl": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,F,F,C,S,C,B,F,F,B".split(","))),
    "Feathersword": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,C,C,D,B,B,S,E,B,C".split(","))),
    "Featherbow": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,C,D,D,B,S,S,D,F,A".split(","))),
    "Featherstaff": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,F,E,C,S,C,S,F,F,A".split(","))),
    "Feathershield": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,D,C,D,S,C,B,E,B,C".split(","))),
    "Priestess": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,E,D,C,A,C,B,F,F,D".split(","))),
    "High Priestess": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,E,C,B,S,C,A,F,F,D".split(","))),
    "Crusader": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,A,B,E,C,C,E,E,S,E".split(","))),
    "Valkyria": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "A,A,A,E,C,C,E,D,S,D".split(","))),
    "Elven Sibyl": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,C,D,A,S,C,A,F,F,C".split(","))),
    "Elven Augur": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "D,B,D,B,S,C,A,F,F,C".split(","))),
    "Snow Ranger": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,C,D,D,C,S,S,S,F,B".split(","))),
    "Werelion": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "S,A,F,F,E,E,F,E,D,F".split(","))),
    "Paladin": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "B,B,C,B,S,C,E,D,B,C".split(","))),
    "Prince": dict(zip(["HP", "P_ATK", "P_DEF", "M_ATK", "M_DEF", "ACC", "EVA", "CRT", "GR", "INIT"], "C,C,C,C,C,C,C,C,C,C".split(","))),
}

GROWTH_TYPES: dict[str, dict[str, int]] = {
    "Hardy": {"HP": 3, "P_ATK": 0, "P_DEF": 1, "M_ATK": 0, "M_DEF": 1, "ACC": -1, "EVA": 0, "CRT": -1, "GR": 0, "INIT": 0},
    "Offensive": {"HP": 1, "P_ATK": 2, "P_DEF": -1, "M_ATK": 2, "M_DEF": -1, "ACC": 0, "EVA": 0, "CRT": 0, "GR": 0, "INIT": 0},
    "Defensive": {"HP": 0, "P_ATK": -1, "P_DEF": 2, "M_ATK": -1, "M_DEF": 2, "ACC": 0, "EVA": 0, "CRT": 0, "GR": 1, "INIT": 0},
    "Precise": {"HP": -2, "P_ATK": 0, "P_DEF": -1, "M_ATK": 0, "M_DEF": -1, "ACC": 5, "EVA": 0, "CRT": 1, "GR": 0, "INIT": 1},
    "Lucky": {"HP": 0, "P_ATK": -1, "P_DEF": 0, "M_ATK": -1, "M_DEF": 0, "ACC": 1, "EVA": 4, "CRT": 0, "GR": 0, "INIT": 0},
    "Keen": {"HP": 0, "P_ATK": 1, "P_DEF": 0, "M_ATK": 1, "M_DEF": 0, "ACC": 0, "EVA": 0, "CRT": 3, "GR": -1, "INIT": -1},
    "Guardian": {"HP": 0, "P_ATK": 0, "P_DEF": 1, "M_ATK": 0, "M_DEF": 0, "ACC": 0, "EVA": 0, "CRT": -1, "GR": 3, "INIT": 0},
    "Go-Getter": {"HP": 0, "P_ATK": -1, "P_DEF": 0, "M_ATK": -1, "M_DEF": 0, "ACC": 0, "EVA": 2, "CRT": 1, "GR": 0, "INIT": 2},
    "All-Rounder": {"HP": 0, "P_ATK": 1, "P_DEF": 0, "M_ATK": 1, "M_DEF": 0, "ACC": 1, "EVA": 1, "CRT": 0, "GR": 0, "INIT": 0},
}

# Symbol typos / aliases in CharaSet → CLASSTYPE enum name
CHARASET_CLASS_ALIASES = {
    "PRIESTES": "ALBION_PRINCESS",
    "PRIESTESS": "ALBION_PRINCESS",
    "WHITEKNIGHT": "WHITE_KNIGHT",
    "SWORDMAN": "SWORDSMAN",
    "GRADIATOR": "GLADIATOR",
    "SYAMAN": "SHAMAN",
    "BLACKK_NIGHT": "BLACK_KNIGHT",  # typo in CharaSet symbol
    "BLACKKNIGHT": "BLACK_KNIGHT",
}


def read_fms_strings(path: Path) -> tuple[int, list[str]]:
    data = path.read_bytes()
    if data[:4] != b"FMSB":
        raise ValueError(f"{path} is not FMSB")
    count = struct.unpack_from("<I", data, 20)[0]
    start = 32 + count * 8
    while start < len(data) and data[start] == 0:
        start += 1
    strings: list[str] = []
    off = start
    while off < len(data):
        end = data.find(b"\x00", off)
        if end == -1:
            break
        if end > off:
            strings.append(data[off:end].decode("utf-8", "replace"))
        off = end + 1
    return count, strings


def parse_enum(path: Path, marker: str) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    entries: list[tuple[int, str]] = []
    in_block = False
    idx = -1
    for line in text.splitlines():
        if marker in line and ":" in line:
            in_block = True
            continue
        if in_block and marker.replace(":", "") + "_END" in line:
            break
        if not in_block:
            continue
        m = re.match(r"\s*([A-Z0-9_]+)\s*,", line)
        if m:
            idx += 1
            entries.append((idx, m.group(1)))
    return entries


def load_name_map(path: Path) -> dict[int, str]:
    names: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if parts[0].isdigit():
            names[int(parts[0])] = parts[1].strip()
    return names


def parse_charaset(path: Path) -> list[tuple[int, str]]:
    """CHARASET index == character_id. Symbol encodes starting class (e.g. PL_HOPLITE_C0)."""
    return parse_enum(path, "CHARASET:")


def chapter_tag(symbol: str) -> str | None:
    """Last story-chapter token in a CharaSet symbol (C11, C0, D1, …)."""
    matches = re.findall(r"(?:^|_)((?:C|D|E|B|A)\d+[A-Z]?)(?:_|$)", symbol or "")
    return matches[-1] if matches else None


def infer_class_from_charaset(symbol: str, class_enum_names: list[str]) -> str | None:
    """Extract CLASSTYPE enum name from a CharaSet symbol."""
    s = symbol
    for pref in ("DRNPC_", "FLNPC_", "STNPC_", "PL_", "Z2_", "Z1_", "Z0_"):
        if s.startswith(pref):
            s = s[len(pref) :]
            break
    for alias, canonical in CHARASET_CLASS_ALIASES.items():
        if s == alias or s.startswith(alias + "_") or s.endswith("_" + alias):
            return canonical
    # Longest match first so FEATHER_SWORD beats SWORD, WHITE_KNIGHT beats KNIGHT, etc.
    # Match as prefix (PL_FIGHTER_C11), whole token, or suffix (C11_FIGHTER, Z2_C11_FIGHTER).
    for name in sorted(class_enum_names, key=len, reverse=True):
        if name == "UNKNOWN":
            continue
        if s == name or s.startswith(name + "_") or s.endswith("_" + name):
            return name
        # Mid-token: C13_CLERIC_BOSS, D2_MID_BOSS_WITCH
        if f"_{name}_" in f"_{s}_":
            return name
    return None


def normalize_skill_label(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def match_skill_descriptions(skill_enum: list[tuple[int, str]], skill_strings: list[str]) -> dict[int, str]:
    # Build index of descriptive strings (skip UI fragments)
    desc_by_norm: dict[str, str] = {}
    for s in skill_strings:
        if len(s) < 4:
            continue
        if s in {"One Target", "Two Targets", "Three Targets", "Four Targets", "All"}:
            continue
        desc_by_norm[normalize_skill_label(s)] = s

    mapping: dict[int, str] = {}
    for sid, sym in skill_enum:
        if sid == 0 or sym in {"UNKNOWN", "EQUIPAI_START", "EQUIPAI_END"}:
            continue
        # ACT_CAVALRY_SLAY -> cavalry slay
        label = sym
        for prefix in ("ACT_", "PAS_", "DEFAULT_", "BT_", "FACILITY_", "ST_", "LEADER_"):
            label = label.replace(prefix, "")
        label = label.replace("_", " ").strip()
        norm = normalize_skill_label(label)
        # direct and partial matches
        for key, desc in desc_by_norm.items():
            if norm in key or key in norm:
                mapping[sid] = desc
                break
    return mapping


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    if not CPK_US.exists():
        print(f"Missing {CPK_US}. Run Scripts/extract-cpk.ps1 first.", file=sys.stderr)
        return 1

    TABLES.mkdir(parents=True, exist_ok=True)
    fms_out = TABLES / "fms"
    fms_out.mkdir(exist_ok=True)

    # Export raw FMS string tables
    for fms_path in sorted(CPK_US.glob("*.fms")):
        count, strings = read_fms_strings(fms_path)
        rows = [{"index": i, "text": strings[i] if i < len(strings) else ""} for i in range(max(count, len(strings)))]
        write_csv(fms_out / f"{fms_path.stem}.csv", ["index", "text"], rows)

    class_enum = parse_enum(DEBUG / "_UcEnum_Class.inc", "CLASSTYPE:")
    class_enum_names = [en for _, en in class_enum]
    skill_enum = parse_enum(DEBUG / "_UcEnum_Skill.inc", "BT_SKILLID:")
    charaset = parse_charaset(DEBUG / "_UcEnum_CharaSet.inc")
    _, class_fms = read_fms_strings(CPK_US / "UcClassList.fms")
    _, chara_fms = read_fms_strings(CPK_US / "UcCharaList.fms")
    _, skill_fms = read_fms_strings(CPK_US / "UcSkillList.fms")
    _, factor_fms = read_fms_strings(CPK_US / "UcFactorList.fms")

    # CLASSTYPE index → English display name (from UcClassList.fms / class.txt)
    enum_to_id = {en: cid for cid, en in class_enum}
    id_to_display: dict[int, str] = {}
    for cid, en in class_enum:
        if cid < len(class_fms) and class_fms[cid]:
            id_to_display[cid] = class_fms[cid]
        else:
            id_to_display[cid] = en.replace("_", " ").title()
    # Prefer turtle-insect class.txt labels when present
    class_txt = TABLES / "class.txt"
    if class_txt.exists():
        for line in class_txt.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            if parts[0].isdigit() and parts[1].strip():
                id_to_display[int(parts[0])] = parts[1].strip()

    names = load_name_map(TABLES / "name.txt")

    # classes_stats.csv
    class_rows = []
    for cid, en in class_enum:
        if cid == 0:
            continue
        display = id_to_display.get(cid, en)
        growth = CLASS_GROWTH.get(display)
        if not growth:
            for k in CLASS_GROWTH:
                if k.lower().replace(" ", "") in en.lower().replace("_", ""):
                    growth = CLASS_GROWTH[k]
                    break
        row = {"class_id": cid, "enum_name": en, "name_en": display}
        if growth:
            row.update(growth)
        class_rows.append(row)
    write_csv(TABLES / "classes_stats.csv", ["class_id", "enum_name", "name_en", *list(next(iter(CLASS_GROWTH.values())).keys())], class_rows)

    # growth_types.csv
    gt_rows = [{"growth_type": k, **v} for k, v in GROWTH_TYPES.items()]
    write_csv(TABLES / "growth_types.csv", ["growth_type", *list(GROWTH_TYPES["Hardy"].keys())], gt_rows)

    # factors.csv (AI / formation preference strings — not character classes)
    factor_rows = [{"factor_id": i, "text": factor_fms[i] if i < len(factor_fms) else ""} for i in range(len(factor_fms))]
    write_csv(TABLES / "factors.csv", ["factor_id", "text"], factor_rows)

    # skills.csv
    skill_desc = match_skill_descriptions(skill_enum, skill_fms)
    skill_rows = []
    for sid, sym in skill_enum:
        if sid == 0:
            continue
        skill_rows.append({
            "skill_id": sid,
            "enum_name": sym,
            "description_en": skill_desc.get(sid, ""),
        })
    write_csv(TABLES / "skills.csv", ["skill_id", "enum_name", "description_en"], skill_rows)

    # characters.csv — CharaSet id space (NOT UcCharaList.fms / UcUnitList).
    # Name resolution (vanilla display for tools only; does not patch the game):
    #   1) Extraction/tables/name.txt override (CharaSet-indexed)
    #   2) PL_ recruit counterpart with same chapter + class (e.g. C11_FIGHTER → Colm)
    #   3) empty — never chara_fms[cid] (that FMS is a different ID space; using it
    #      produced wrong labels like Beaumont on C11_FIGHTER / Yahna on C12_BOSS)
    max_id = max(
        max(names) if names else 0,
        max((i for i, _ in charaset), default=0),
        len(chara_fms) - 1,
    )
    charaset_by_id = {i: sym for i, sym in charaset}

    # Optional class ids from binary dump (symbol alone can't decode C12_BOSS → WHITE_KNIGHT).
    class_from_bin: dict[int, str] = {}
    charasets_csv = TABLES / "charasets.csv"
    if charasets_csv.exists():
        with charasets_csv.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    bid = int(row.get("chara_id") or "")
                except ValueError:
                    continue
                cen = (row.get("class_enum") or "").strip()
                if cen and cen != "UNKNOWN":
                    class_from_bin[bid] = cen

    pl_name_by_class_chapter: dict[tuple[str, str], str] = {}
    for cid, sym in charaset:
        if not sym.startswith("PL_"):
            continue
        chap = chapter_tag(sym)
        cls = infer_class_from_charaset(sym, class_enum_names) or class_from_bin.get(cid)
        if not chap or not cls:
            continue
        pl_name = names.get(cid) or (chara_fms[cid] if cid < len(chara_fms) else "")
        # PL_ rows 1–200 share id space with name.txt / early UcCharaList
        if pl_name and pl_name.lower() not in ("none", "null", "blank"):
            pl_name_by_class_chapter[(cls, chap)] = pl_name

    char_rows = []
    for cid in range(max_id + 1):
        sym = charaset_by_id.get(cid, "")
        enum_class = (
            (infer_class_from_charaset(sym, class_enum_names) if sym else None)
            or class_from_bin.get(cid)
        )
        class_id = ""
        class_name = ""
        if enum_class and enum_class in enum_to_id:
            class_id = enum_to_id[enum_class]
            class_name = id_to_display.get(class_id, enum_class)
        name_en = names.get(cid, "")
        if not name_en and enum_class:
            chap = chapter_tag(sym)
            if chap:
                name_en = pl_name_by_class_chapter.get((enum_class, chap), "")
        char_rows.append({
            "character_id": cid,
            "name_en": name_en,
            "charaset_symbol": sym,
            "class_id": class_id,
            "class_enum": enum_class or "",
            "class_name": class_name,
        })
    write_csv(
        TABLES / "characters.csv",
        ["character_id", "name_en", "charaset_symbol", "class_id", "class_enum", "class_name"],
        char_rows,
    )

    # characters_joined.csv — named characters + class growth ranks
    joined_rows = []
    for r in char_rows:
        if not r.get("name_en") or r["name_en"] in ("None", ""):
            continue
        class_name = r.get("class_name", "")
        growth = CLASS_GROWTH.get(class_name, {})
        joined_rows.append({
            **r,
            **{f"growth_{k}": v for k, v in growth.items()},
        })
    write_csv(
        TABLES / "characters_joined.csv",
        ["character_id", "name_en", "charaset_symbol", "class_id", "class_enum", "class_name", "growth_HP", "growth_P_ATK", "growth_P_DEF", "growth_M_ATK", "growth_M_DEF", "growth_ACC", "growth_EVA", "growth_CRT", "growth_GR", "growth_INIT"],
        joined_rows,
    )

    # Enrich sigma swaps with corrected class names
    sigma_path = TABLES / "sigma_swaps.csv"
    if sigma_path.exists():
        char_by_id = {int(r["character_id"]): r for r in char_rows}
        enriched = []
        with sigma_path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                exp = char_by_id.get(int(row["expected_id"]), {})
                act = char_by_id.get(int(row["actual_id"]), {})
                enriched.append({
                    **row,
                    "expected_class": exp.get("class_name", ""),
                    "actual_class": act.get("class_name", ""),
                    "expected_charaset": exp.get("charaset_symbol", ""),
                    "actual_charaset": act.get("charaset_symbol", ""),
                })
        write_csv(
            TABLES / "sigma_swaps_enriched.csv",
            list(enriched[0].keys()) if enriched else [],
            enriched,
        )

    print(f"Done. Tables written to {TABLES}")
    print(f"  characters.csv ({len(char_rows)} rows)")
    print(f"  classes_stats.csv ({len(class_rows)} classes)")
    print(f"  skills.csv ({len(skill_rows)} skills, {sum(1 for r in skill_rows if r['description_en'])} with descriptions)")
    print(f"  fms/*.csv ({len(list(fms_out.glob('*.csv')))} sheets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
