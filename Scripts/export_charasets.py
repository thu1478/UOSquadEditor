"""Export CharaSet rows: class + up to 4 equipment item slots.

CharaSet table (US v1.0.5 main):
  base   0x276DD68
  stride 0x48
  count  1388

Layout (partial):
  +0x08  low byte = CLASSTYPE
  +0x1E  u8 equip PARAMSET override (0 = use UnitSet +0x14; else ZAKO/NORMAL/POWER/BOSS)
  +0x1F  u8 related override (used by alternate getter at 0x2CC034)
  +0x38  u16 item slot 0 (weapon / primary)
  +0x3A  u16 item slot 1 (shield / secondary)
  +0x3C  u16 item slot 2 (accessory)
  +0x3E  u16 item slot 3 (accessory)
  0      = use CreateDefaultEquip / EQUIPTYPE for that slot

Writes: Extraction/tables/charasets.csv
"""
from __future__ import annotations

import csv
import re
import struct
from pathlib import Path

ROOT = Path(r"d:/Documents/Projects/Emulation/UnicornOverlord")
MAIN = ROOT / "Extraction/exefs_out/main.decompressed.bin"
DEBUG = ROOT / "Extraction/cpk_data/Unicorn_US/Debug"
ITEMS_CSV = ROOT / "Extraction/tables/items.csv"
OUT = ROOT / "Extraction/tables/charasets.csv"

CHARASET_BASE = 0x276DD68
CHARASET_STRIDE = 0x48
CHARASET_COUNT = 1388
GEAR_OFFS = (0x38, 0x3A, 0x3C, 0x3E)
PARAMSET_NAME = {
    0: "",
    1: "ZAKO",
    2: "NORMAL",
    3: "POWER",
    4: "BOSS",
    5: "JOSEPH",
    6: "CALL_ALLIES",
}


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


def load_item_names() -> dict[int, str]:
    out: dict[int, str] = {}
    with ITEMS_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rid = row.get("id") or row.get("item_id") or next(iter(row.values()))
            name = row.get("name_en") or row.get("name") or ""
            try:
                out[int(rid)] = name
            except ValueError:
                continue
    return out


def main() -> None:
    blob = MAIN.read_bytes()
    cs = parse_enum(DEBUG / "_UcEnum_CharaSet.inc", "CHARASET:")
    classes = parse_enum(DEBUG / "_UcEnum_Class.inc", "CLASSTYPE:")
    items = parse_enum(DEBUG / "_UcEnum_Item.inc", "ITEMID:")
    item_names = load_item_names()

    assert len(cs) == CHARASET_COUNT
    assert struct.unpack_from("<H", blob, CHARASET_BASE + 2 * CHARASET_STRIDE + 0x38)[0] == 959
    assert struct.unpack_from("<H", blob, CHARASET_BASE + 635 * CHARASET_STRIDE + 0x38)[0] == 304
    assert blob[CHARASET_BASE + 635 * CHARASET_STRIDE + 0x1E] == 4  # Culloran BOSS override

    rows: list[dict[str, object]] = []
    for idx in range(CHARASET_COUNT):
        off = CHARASET_BASE + idx * CHARASET_STRIDE
        class_id = struct.unpack_from("<H", blob, off + 0x08)[0] & 0xFF
        ov = blob[off + 0x1E]
        ov2 = blob[off + 0x1F]
        row: dict[str, object] = {
            "chara_id": idx,
            "chara_symbol": cs[idx],
            "class_id": class_id,
            "class_enum": classes[class_id] if class_id < len(classes) else class_id,
            "equip_param_override": ov if ov else "",
            "equip_param_override_name": PARAMSET_NAME.get(ov, str(ov) if ov else ""),
            "equip_param_override_b": ov2 if ov2 else "",
        }
        for slot, goff in enumerate(GEAR_OFFS):
            iid = struct.unpack_from("<H", blob, off + goff)[0]
            row[f"equip{slot}_id"] = iid if iid else ""
            if iid:
                sym = items[iid] if iid < len(items) else str(iid)
                name = item_names.get(iid, "")
                row[f"equip{slot}_symbol"] = sym
                row[f"equip{slot}_name"] = name
            else:
                row[f"equip{slot}_symbol"] = ""
                row[f"equip{slot}_name"] = ""
        rows.append(row)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    with_gear = sum(1 for r in rows if any(r[f"equip{s}_id"] for s in range(4)))
    with_ov = sum(1 for r in rows if r["equip_param_override"])
    print(
        f"wrote {OUT} rows={len(rows)} with_explicit_gear={with_gear} "
        f"with_equip_param_override={with_ov}"
    )


if __name__ == "__main__":
    main()
