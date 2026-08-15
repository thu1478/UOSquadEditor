"""Export real CreateDefaultEquip tables from main.

ROM facts (US v1.0.5):
  Class table   0xD2DFC8 stride 0x58 — s16 equiptype slots at +0x44..+0x4A (4 slots)
  EQUIPTYPE→item 0xD13E30 stride 0x0C — 3 u16s = level bands (getter 0x123884)
  Level→column   0x123844 — lv 1..14→0, 15..27→1, 28..50→2
  EXPTYPE offset — UnitSet +0x10: 1 ZAKO / 2 NORMAL / 3 POWER / 4 BOSS
                  adds +11 / +22 / +33 / +44 to class DEFAULT equiptype id

Writes:
  Extraction/tables/equiptype_items.csv
  Extraction/tables/class_equiptypes.csv
  Extraction/tables/equiptype_by_class.csv  (resolved DEFAULT tier, col0 — editor helper)
"""
from __future__ import annotations

import csv
import re
import struct
from pathlib import Path

ROOT = Path(r"d:/Documents/Projects/Emulation/UnicornOverlord")
MAIN = ROOT / "Extraction/exefs_out/main.decompressed.bin"
DEBUG = ROOT / "Extraction/cpk_data/Unicorn_US/Debug"
OUT_ITEMS = ROOT / "Extraction/tables/equiptype_items.csv"
OUT_CLASS = ROOT / "Extraction/tables/class_equiptypes.csv"
OUT_BY_CLASS = ROOT / "Extraction/tables/equiptype_by_class.csv"

CLASS_BASE = 0xD2DFC8
CLASS_STRIDE = 0x58
CLASS_ET_OFF = 0x44  # 4 × s16
EQUIPTYPE_ITEM_BASE = 0xD13E30
EQUIPTYPE_ITEM_STRIDE = 0xC
EXPTYPE_OFFSET = {0: 0, 1: 11, 2: 22, 3: 33, 4: 44}


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


def resolve_item(
    equiptype_base: int,
    exptype: int,
    level: int,
    item_rows: list[tuple[int, int, int]],
    n_et: int,
) -> int:
    col = level_column(level)
    if col < 0 or equiptype_base <= 0:
        return 0
    off = EXPTYPE_OFFSET.get(exptype, 0)
    et = equiptype_base + off
    if not (0 <= et < n_et):
        return 0
    return item_rows[et][col]


def main() -> None:
    blob = MAIN.read_bytes()
    classes = parse_enum(DEBUG / "_UcEnum_Class.inc", "CLASSTYPE:")
    equiptypes = parse_enum(DEBUG / "_UcEnum_Class.inc", "EQUIPTYPE:")
    items = parse_enum(DEBUG / "_UcEnum_Item.inc", "ITEMID:")
    assert len(equiptypes) == 56

    item_rows: list[tuple[int, int, int]] = []
    for i in range(56):
        a, b, c = struct.unpack_from(
            "<HHH", blob, EQUIPTYPE_ITEM_BASE + i * EQUIPTYPE_ITEM_STRIDE
        )
        item_rows.append((a, b, c))

    OUT_ITEMS.parent.mkdir(parents=True, exist_ok=True)
    with OUT_ITEMS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "equiptype_id",
                "equiptype_symbol",
                "item_col0_id",
                "item_col0",
                "item_col1_id",
                "item_col1",
                "item_col2_id",
                "item_col2",
                "note",
            ],
        )
        w.writeheader()
        for i, sym in enumerate(equiptypes):
            a, b, c = item_rows[i]
            w.writerow(
                {
                    "equiptype_id": i,
                    "equiptype_symbol": sym,
                    "item_col0_id": a,
                    "item_col0": items[a] if a < len(items) else "",
                    "item_col1_id": b,
                    "item_col1": items[b] if b < len(items) else "",
                    "item_col2_id": c,
                    "item_col2": items[c] if c < len(items) else "",
                    "note": "col = level band: 1-14 / 15-27 / 28-50 (0x123844)",
                }
            )

    class_slots: list[list[int]] = []
    with OUT_CLASS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "class_id",
                "class_symbol",
                "slot0_equiptype",
                "slot0_symbol",
                "slot1_equiptype",
                "slot1_symbol",
                "slot2_equiptype",
                "slot2_symbol",
                "slot3_equiptype",
                "slot3_symbol",
            ],
        )
        w.writeheader()
        for i, csym in enumerate(classes):
            off = CLASS_BASE + i * CLASS_STRIDE + CLASS_ET_OFF
            slots = list(struct.unpack_from("<hhhh", blob, off))
            class_slots.append(slots)

            def esym(v: int) -> str:
                return equiptypes[v] if 0 <= v < len(equiptypes) else ""

            w.writerow(
                {
                    "class_id": i,
                    "class_symbol": csym,
                    "slot0_equiptype": slots[0],
                    "slot0_symbol": esym(slots[0]),
                    "slot1_equiptype": slots[1],
                    "slot1_symbol": esym(slots[1]),
                    "slot2_equiptype": slots[2],
                    "slot2_symbol": esym(slots[2]),
                    "slot3_equiptype": slots[3],
                    "slot3_symbol": esym(slots[3]),
                }
            )

    # Helper: DEFAULT tier (exptype 0), level col0 — for quick class→gear view
    with OUT_BY_CLASS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "class_id",
                "class_symbol",
                "slot0_item_id",
                "slot0_item",
                "slot1_item_id",
                "slot1_item",
                "slot2_item_id",
                "slot2_item",
                "slot3_item_id",
                "slot3_item",
                "note",
            ],
        )
        w.writeheader()
        for i, csym in enumerate(classes):
            rec: dict[str, object] = {
                "class_id": i,
                "class_symbol": csym,
                "note": (
                    "ROM CreateDefaultEquip: DEFAULT tier, level col0 (lv1-14). "
                    "Mission join applies EXPTYPE offset + stage level column."
                ),
            }
            for s in range(4):
                iid = resolve_item(class_slots[i][s], 0, 1, item_rows, 56)
                rec[f"slot{s}_item_id"] = iid
                rec[f"slot{s}_item"] = items[iid] if iid < len(items) else ""
            w.writerow(rec)

    print(f"wrote {OUT_ITEMS}")
    print(f"wrote {OUT_CLASS}")
    print(f"wrote {OUT_BY_CLASS}")
    print(
        "example KNIGHT ZAKO lv5:",
        [
            (
                equiptypes[class_slots[25][s] + 11]
                if class_slots[25][s]
                else "NONE",
                items[
                    resolve_item(class_slots[25][s], 1, 5, item_rows, 56)
                ]
                if resolve_item(class_slots[25][s], 1, 5, item_rows, 56)
                else "",
            )
            for s in range(4)
        ],
    )


if __name__ == "__main__":
    main()
