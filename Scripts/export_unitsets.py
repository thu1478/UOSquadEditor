"""Export UnitSet → members + EquipAiSet (tactics presets).

UnitSet table (US v1.0.5 main):
  base   0x28120B8
  stride 0x88
  count  ~2860

Per-record (confirmed):
  +0x10  EXPTYPE reward flag (1=ZAKO … 4=BOSS). Mission enemies are often
         BOSS here even when they are ordinary squads — do not treat as role.
  +0x14  PARAMSET (1=ZAKO, 2=NORMAL, 3=POWER, 4=BOSS, …) — CreateDefaultEquip
  +0x18  formation / misc
  +0x38  leader slot hint (0..3)
  +0x3C  six slots × 0x0C:
           +0x0 CharaSet id
           +0x4 EquipAiSet id (0 = class default tactics)
           +0x8 flags (0x100 often marks leader)

Equipment items are NOT stored in UnitSet rows. Gear uses EQUIPTYPE
tiers at create time / CharaSet defaults — separate follow-up.

Writes: Extraction/tables/unitsets.csv
"""
from __future__ import annotations

import csv
import re
import struct
from pathlib import Path

ROOT = Path(r"d:/Documents/Projects/Emulation/UnicornOverlord")
MAIN = ROOT / "Extraction/exefs_out/main.decompressed.bin"
ASB = ROOT / "Extraction/asb_probe/St_OW_TK_C11.asb"
DEBUG = ROOT / "Extraction/cpk_data/Unicorn_US/Debug"
OUT = ROOT / "Extraction/tables/unitsets.csv"

UNITSET_BASE = 0x28120B8
UNITSET_STRIDE = 0x88
UNITSET_COUNT = 2860  # excludes NUM sentinel


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
        raise RuntimeError(f"header {header} not found in {path}")
    names: list[str] = []
    for ln in lines[start:]:
        if ln.strip().startswith(end_tok):
            break
        m = re.match(r"\s*([A-Za-z0-9_]+)\s*,", ln)
        if m:
            names.append(m.group(1))
    return names


def unitset_names() -> list[str]:
    raw = ASB.read_bytes()
    found = re.findall(rb"UC_UNITSET_[A-Z0-9_]+", raw)
    seen: set[str] = set()
    ordered: list[str] = []
    for b in found:
        s = b.decode("ascii")
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    # Expect UNKNOWN..NUM
    if ordered[-1] == "UC_UNITSET_NUM":
        ordered = ordered[:-1]
    return ordered


def exp_name(v: int) -> str:
    return {0: "NONE", 1: "ZAKO", 2: "NORMAL", 3: "POWER", 4: "BOSS"}.get(v, str(v))


def main() -> None:
    blob = MAIN.read_bytes()
    names = unitset_names()
    cs = parse_enum(DEBUG / "_UcEnum_CharaSet.inc", "CHARASET:")
    ai = parse_enum(DEBUG / "_UcEnum_EquipAiSet.inc", "EQUIPAISET:")

    assert names[1870] == "UC_UNITSET_OW_TK_C11_BOSS"
    assert struct.unpack_from("<I", blob, UNITSET_BASE + 1870 * UNITSET_STRIDE + 0x48)[0] == 635

    rows: list[dict[str, object]] = []
    for idx in range(min(UNITSET_COUNT, len(names))):
        off = UNITSET_BASE + idx * UNITSET_STRIDE
        exptype = struct.unpack_from("<I", blob, off + 0x10)[0]
        f14 = struct.unpack_from("<I", blob, off + 0x14)[0]
        f18 = struct.unpack_from("<I", blob, off + 0x18)[0]
        leader = struct.unpack_from("<I", blob, off + 0x38)[0]
        row: dict[str, object] = {
            "unitset_id": idx,
            "unitset_symbol": names[idx],
            "exptype": exptype,
            "exptype_name": exp_name(exptype),
            "field_14": f14,
            "field_18": f18,
            "leader_hint": leader,
        }
        for s in range(6):
            slot = off + 0x3C + s * 0xC
            ch, aiset, flags = struct.unpack_from("<III", blob, slot)
            row[f"slot{s}_chara_id"] = ch if ch else ""
            row[f"slot{s}_chara"] = cs[ch] if 0 < ch < len(cs) else ("" if ch == 0 else ch)
            row[f"slot{s}_equipai_id"] = aiset if aiset else ""
            row[f"slot{s}_equipai"] = ai[aiset] if 0 < aiset < len(ai) else ("" if aiset == 0 else aiset)
            row[f"slot{s}_flags"] = flags if flags else ""
        rows.append(row)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    with_ai = sum(
        1
        for r in rows
        for s in range(6)
        if r[f"slot{s}_equipai_id"] not in ("", 0)
    )
    filled = sum(1 for r in rows for s in range(6) if r[f"slot{s}_chara_id"] not in ("", 0))
    print(f"wrote {OUT} rows={len(rows)} filled_slots={filled} explicit_equipai={with_ai}")


if __name__ == "__main__":
    main()
