"""Build stage_enemy_levels.csv from ROM stage DB (+ wiki fallback).

Primary levels come from main.decompressed.bin:
  stage DB 0x28C19F8 stride 0x50, level at +0xC
  joined by name via pointer table (~0xA1C6F0, stride 0x18):
    +0x00 ptr → stage DB row, +0x10 ptr → ST_* name

Quest symbols map as ST_OW_C_11 → OW_C11, ST_OW_TK_C11 → OW_TK_C11.
Wiki titles fill gaps only when the ROM has no ST_* row.
"""
from __future__ import annotations

import csv
import re
import struct
from pathlib import Path

ROOT = Path(r"d:/Documents/Projects/Emulation/UnicornOverlord")
QUEST_INC = ROOT / "Extraction/cpk_data/Unicorn_US/Debug/_UcEnum_QuestList.inc"
QUEST_FMS = ROOT / "Extraction/tables/fms/UcQuestList.csv"
MAIN = ROOT / "Extraction/exefs_out/main.decompressed.bin"
OUT = ROOT / "Extraction/tables/stage_enemy_levels.csv"

STAGE_DB = 0x28C19F8
STAGE_STRIDE = 0x50
# Pointer-table entry that holds ST_OW_TK_C11 (Sorm) — walk backward for start.
SORM_ENTRY = 0xA1CD50
ENTRY_STRIDE = 0x18
SORM_STR_OFF = 0xAEA0B9

# English stage name -> enemy level (from unilord.miraheze.org/wiki/Battle_Stages)
WIKI_BY_NAME = {
    "The Ravaged Swamp": 5,
    "The Priestess, Abducted": 8,
    "Unicorn Overlord": 40,
    "The General in Black": 10,
    "Another Prince": 14,
    "The Heir to the Dragonlands": 17,
    "Heir to the Dragonlands": 17,
    "O'er Wood and Water": 19,
    "Vile Desecration": 22,
    "The Witch's Word": 23,
    "Tempest of White": 25,
    "Legacy of the Lion Kings": 28,
    "The Snowbound King": 30,
    "A Fleeting Dream": 31,
    "Bound by Sacred Oath": 34,
    "The Holy March": 36,
    "A Solitary Resistance": 3,
    "As the Tricorns Ride": 4,
    "The Winged Knight": 4,
    "The Self-Effacing Sorcerer": 5,
    "Province of Famine": 6,
    "The Mercenary's Trial": 6,
    "Uprooting the Rock Rats": 7,
    "The Blade of House Meillet": 11,
    "The Unyielding Shield": 12,
    "The Tormented Helm": 14,
    "Dying Breath of an Empire Fallen": 45,
    "Beyond the Swirling Sands": 11,
    "Black Knight of the Dunes": 12,
    "The Champion of Order": 13,
    "Two Armies as One": 15,
    "Blooming Rose on Bare Rock": 16,
    "The Resistance Lives On": 15,
    "A Half-Elf's Resolve": 16,
    "A Shifting Tide": 17,
    "The Elven Knight": 18,
    "Ervelda, Guardian of the Fae": 20,
    "Ervélda, Guardian of the Fae": 20,
    "Bowman of the Setting Sun": 21,
    "The Kingdom of Gordonia": 26,
    "Ferocious Loyalty": 27,
    "To Resist or To Yield": 29,
    "The Faithless Knight": 30,
    "Shield to the Sacred": 31,
    "A Faded Flower": 32,
    "The Battle for Barbatimo": 5,
    "The Battle for Paradis": 5,
    "The Battle for Lisière": 6,
    "The Battle for Lisiere": 6,
    "The Battle for Lonteria": 7,
    "The Battle for Mier": 9,
    "The Battle for Elzecouvre": 10,
    "The Battle for Istania": 11,
    "The Battle for Fontille": 12,
    "The Battle for Prashvari": 12,
    "The Battle for Riviere": 13,
    "The Battle for Plaine": 14,
    "The Battle for Umbalcons": 25,
    "The Battle for Sorm": 38,
    "The Battle for Soirée Calme": 40,
    "The Battle for Plum Paferme": 40,
    "The Battle for Portolle": 40,
    "The Battle for Weszait": 10,
    "The Battle for Gaufa": 12,
    "The Battle for Gözefauss": 13,
    "The Battle for Gozefauss": 13,
    "The Battle for Schaetze": 14,
    "The Battle for Adopti": 15,
    "The Battle for Vansberg": 16,
    "The Battle for Kleinfeld": 18,
    "The Battle for Krannich": 24,
    "The Battle for Satama": 16,
    "The Battle for Paniveda": 17,
    "The Battle for Siltakulya": 18,
    "The Battle for Ysveda": 18,
    "The Battle for Quentari": 19,
    "The Battle for Voryatan": 20,
    "The Battle for Hildi": 21,
    "The Battle for Silmapelt": 24,
    "The Battle for Lunokeu": 30,
    "The Battle for Domghakom": 25,
    "The Battle for Zagavona": 29,
    "The Battle for Zagatul": 29,
    "The Battle for Solvaquad": 30,
    "The Battle for Nibessamost": 30,
    "The Battle for Largion": 31,
    "The Battle for Shroudford": 31,
    "The Battle for Citronpool": 32,
    "The Battle for Roastford": 32,
    "The Battle for Cherrywell": 33,
    "The Battle for Foxwell": 33,
    "The Battle for Peyston": 34,
    "The Sigil's Trial, Beginner 1": 6,
    "The Sigil's Trial, Beginner 2": 10,
    "The Sigil's Trial, Moderate 1": 13,
    "The Sigil's Trial, Moderate 2": 15,
    "The Sigil's Trial, Moderate 3": 18,
    "The Sigil's Trial, Advanced 1": 21,
    "The Sigil's Trial, Advanced 2": 26,
    "The Sigil's Trial, Advanced 3": 29,
    "The Sigil's Trial, Expert 1": 31,
    "The Sigil's Trial, Expert 2": 34,
    "The Sigil's Trial, Zenith": 38,
}

REGION = {
    "OW_C": "Cornia",
    "OW_D": "Drakenhold",
    "OW_E": "Elheim",
    "OW_B": "Bastorias",
    "OW_A": "Albion",
    "OW_Z": "Zenoiran",
    "OW_TK_C": "Cornia",
    "OW_TK_D": "Drakenhold",
    "OW_TK_E": "Elheim",
    "OW_TK_B": "Bastorias",
    "OW_TK_A": "Albion",
    "OW_FREESTAGE": "Auxiliary",
}


def region_of(sym: str) -> str:
    for prefix, name in sorted(REGION.items(), key=lambda x: -len(x[0])):
        if sym.startswith(prefix):
            return name
    return ""


def category_of(sym: str) -> str:
    if sym.startswith("OW_TK_"):
        return "liberation"
    if sym.startswith("OW_FREESTAGE"):
        return "auxiliary"
    if sym.startswith("OW_"):
        return "quest"
    return "other"


def load_quests() -> list[tuple[int, str]]:
    out = []
    for line in QUEST_INC.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Z0-9_]+)\s*,", line)
        if not m:
            continue
        sym = m.group(1)
        if "UC_QUESTID" in line or sym == "END":
            continue
        out.append((len(out), sym))
    return out


def load_quest_names() -> dict[int, str]:
    names: dict[int, str] = {}
    with QUEST_FMS.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            names[int(row["index"])] = row["text"]
    return names


def normalize(name: str) -> str:
    return (
        name.replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("ë", "e")
        .replace("á", "a")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("’", "'")
        .replace("‘", "'")
    )


def stage_name_to_quest(st: str) -> str:
    """ST_OW_C_11 → OW_C11, ST_OW_TK_C11 → OW_TK_C11."""
    s = st[3:] if st.startswith("ST_") else st
    return re.sub(r"([A-Z])_(\d)", r"\1\2", s)


def load_rom_levels(blob: bytes) -> dict[str, tuple[int, int]]:
    """quest_symbol → (enemy_level, stage_db_index)."""

    def cstr(off: int) -> str:
        if not (0 < off < len(blob)):
            return ""
        end = blob.find(b"\x00", off)
        return blob[off:end].decode("ascii", "replace")

    # Confirm Sorm anchor still valid.
    if struct.unpack_from("<Q", blob, SORM_ENTRY + 0x10)[0] != SORM_STR_OFF:
        raise RuntimeError("stage name pointer table anchor moved")

    start = SORM_ENTRY
    for _ in range(400):
        prev = start - ENTRY_STRIDE
        row_ptr = struct.unpack_from("<Q", blob, prev)[0]
        name_ptr = struct.unpack_from("<Q", blob, prev + 0x10)[0]
        if not (STAGE_DB <= row_ptr <= STAGE_DB + 400 * STAGE_STRIDE):
            break
        if not cstr(name_ptr).startswith("ST_"):
            break
        start = prev

    out: dict[str, tuple[int, int]] = {}
    off = start
    while off + ENTRY_STRIDE <= len(blob):
        row_ptr = struct.unpack_from("<Q", blob, off)[0]
        name_ptr = struct.unpack_from("<Q", blob, off + 0x10)[0]
        if not (STAGE_DB <= row_ptr <= STAGE_DB + 400 * STAGE_STRIDE):
            break
        st = cstr(name_ptr)
        if not st.startswith("ST_"):
            break
        db_idx = (row_ptr - STAGE_DB) // STAGE_STRIDE
        lv = struct.unpack_from("<I", blob, row_ptr + 0xC)[0]
        qsym = stage_name_to_quest(st)
        # Prefer first mapping if duplicates.
        out.setdefault(qsym, (lv, db_idx))
        off += ENTRY_STRIDE
    return out


def main() -> None:
    quests = load_quests()
    names = load_quest_names()
    wiki_norm = {normalize(k): v for k, v in WIKI_BY_NAME.items()}
    rom = load_rom_levels(MAIN.read_bytes())

    rows = []
    rom_n = wiki_n = 0
    for qid, sym in quests:
        # UcQuestList.fms title block skips UNKNOWN: fms_index = quest_id - 1
        name = names.get(qid - 1, "") if qid >= 1 else ""
        if sym == "UNKNOWN":
            name = ""

        level: int | None = None
        source = ""
        rom_hit = rom.get(sym)
        if rom_hit is not None:
            level, _db = rom_hit
            source = "rom"
            rom_n += 1
        else:
            level = wiki_norm.get(normalize(name))
            if level is None and name:
                for k, v in wiki_norm.items():
                    if normalize(name).startswith(k) or k.startswith(normalize(name)):
                        if abs(len(k) - len(normalize(name))) <= 8:
                            level = v
                            break
            if level is None and "Apex" in name:
                level = 38
            if level is not None:
                source = "wiki"
                wiki_n += 1

        rows.append(
            {
                "quest_id": qid,
                "quest_symbol": sym,
                "stage_name": name,
                "region": region_of(sym),
                "category": category_of(sym),
                "enemy_level": level if level is not None else "",
                "source": source,
            }
        )

    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "quest_id",
                "quest_symbol",
                "stage_name",
                "region",
                "category",
                "enemy_level",
                "source",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    with_level = sum(1 for r in rows if r["enemy_level"] != "")
    print(
        f"wrote {OUT} rows={len(rows)} with_level={with_level} "
        f"(rom={rom_n} wiki_fallback={wiki_n})"
    )


if __name__ == "__main__":
    main()
