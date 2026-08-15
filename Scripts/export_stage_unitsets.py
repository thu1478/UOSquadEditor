"""Build mission ↔ UnitSet join (prefix heuristic + optional ASB spawn decode).

v1: quest_symbol → UnitSets matching UC_UNITSET_<quest>_…
v1.5: if stage ASB files exist under Extraction/asb_probe or cpk Script/,
      collect unique UC_UNITSET_* tokens that appear near create-call patterns
      (best-effort; ASBs also embed the full enum so we filter by quest prefix
      and by tokens that appear fewer than FULL_ENUM_THRESHOLD times).

Writes:
  Extraction/tables/stage_unitsets.csv
  Extraction/editor/missions.json  (lightweight mission index)
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"d:/Documents/Projects/Emulation/UnicornOverlord")
STAGES = ROOT / "Extraction/tables/stage_enemy_levels.csv"
UNITSETS = ROOT / "Extraction/tables/unitsets.csv"
OUT = ROOT / "Extraction/tables/stage_unitsets.csv"
OUT_JSON = ROOT / "Extraction/editor/missions.json"
ASB_DIRS = [
    ROOT / "Extraction/asb_probe",
    ROOT / "Extraction/cpk_data/scripts_probe",
    ROOT / "Extraction/cpk_data/Unicorn/Script",
]

SIDE_RE = re.compile(r"_(EN|NE|NT|FR|PL)_")
UNITSET_RE = re.compile(rb"UC_UNITSET_[A-Z0-9_]+")
FULL_ENUM_THRESHOLD = 200  # tokens appearing this often are enum dumps


def side_of(symbol: str) -> str:
    m = SIDE_RE.search(symbol)
    if m:
        return m.group(1)
    # Named stage bosses / unique leaders often omit _EN_
    # (e.g. UC_UNITSET_OW_C11_MERIZAND = Melisandre).
    if any(
        tok in symbol
        for tok in ("_BOSS", "_MIDBOSS", "_MBOSS", "_MERIZAND", "_ZOUEN", "_ZAKO")
    ):
        return "EN"
    return "UNKNOWN"


def quest_prefix(quest_symbol: str) -> str:
    # OW_C5 → UC_UNITSET_OW_C5_
    # OW_TK_C11 → UC_UNITSET_OW_TK_C11_
    if not quest_symbol or quest_symbol == "UNKNOWN":
        return ""
    return f"UC_UNITSET_{quest_symbol}_"


def load_unitsets() -> list[dict[str, str]]:
    with UNITSETS.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def asb_unitset_hits() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for d in ASB_DIRS:
        if not d.exists():
            continue
        for path in d.rglob("*.asb"):
            data = path.read_bytes()
            for m in UNITSET_RE.finditer(data):
                counts[m.group().decode("ascii")] += 1
    return counts


def best_quest_for_unitset(sym: str, quest_symbols: list[str]) -> str | None:
    """Own each UC_UNITSET_* by the longest matching quest (OW_C1 vs OW_C11)."""
    best = ""
    for q in quest_symbols:
        prefix = quest_prefix(q)
        if prefix and sym.startswith(prefix) and len(q) > len(best):
            best = q
    return best or None


def main() -> None:
    stages = list(csv.DictReader(STAGES.open(encoding="utf-8")))
    unitsets = load_unitsets()
    asb_counts = asb_unitset_hits()
    quest_symbols = [
        (st.get("quest_symbol") or "")
        for st in stages
        if (st.get("quest_symbol") or "") not in ("", "UNKNOWN")
    ]

    # Pre-assign every UnitSet to its longest matching quest.
    owned: dict[str, list[dict[str, str]]] = {q: [] for q in quest_symbols}
    for u in unitsets:
        sym = u.get("unitset_symbol") or ""
        owner = best_quest_for_unitset(sym, quest_symbols)
        if owner:
            owned[owner].append(u)

    out_rows: list[dict[str, object]] = []
    missions: list[dict[str, object]] = []

    for st in stages:
        qid = int(st.get("quest_id") or 0)
        qsym = st.get("quest_symbol") or ""
        matched = list(owned.get(qsym, []))

        # ASB-assisted: tokens owned by this quest (longest-prefix), rare enough
        asb_extra = []
        if qsym and asb_counts:
            for sym, cnt in asb_counts.items():
                if cnt >= FULL_ENUM_THRESHOLD:
                    continue
                if best_quest_for_unitset(sym, quest_symbols) != qsym:
                    continue
                if not any(u.get("unitset_symbol") == sym for u in matched):
                    for u in unitsets:
                        if u.get("unitset_symbol") == sym:
                            asb_extra.append(u)
                            break

        all_u = matched + asb_extra
        squads = []
        for u in all_u:
            sym = u["unitset_symbol"]
            side = side_of(sym)
            source = "prefix" if u in matched else "asb_token"
            out_rows.append(
                {
                    "quest_id": qid,
                    "quest_symbol": qsym,
                    "stage_name": st.get("stage_name") or "",
                    "region": st.get("region") or "",
                    "enemy_level": st.get("enemy_level") or "",
                    "unitset_id": u.get("unitset_id"),
                    "unitset_symbol": sym,
                    "side": side,
                    "exptype": u.get("exptype"),
                    "exptype_name": u.get("exptype_name"),
                    "join_source": source,
                }
            )
            squads.append(
                {
                    "unitset_id": int(u["unitset_id"]),
                    "unitset_symbol": sym,
                    "side": side,
                    "exptype_name": u.get("exptype_name"),
                    "join_source": source,
                }
            )

        missions.append(
            {
                "quest_id": qid,
                "quest_symbol": qsym,
                "stage_name": st.get("stage_name") or "",
                "region": st.get("region") or "",
                "category": st.get("category") or "",
                "enemy_level": st.get("enemy_level") or "",
                "squad_count": len(squads),
                "squads": squads,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "quest_id",
            "quest_symbol",
            "stage_name",
            "region",
            "enemy_level",
            "unitset_id",
            "unitset_symbol",
            "side",
            "exptype",
            "exptype_name",
            "join_source",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({"missions": missions}, indent=2) + "\n", encoding="utf-8"
    )

    covered = sum(1 for m in missions if m["squad_count"] > 0)
    print(f"wrote {OUT} ({len(out_rows)} rows)")
    print(f"wrote {OUT_JSON} ({covered}/{len(missions)} missions with squads)")


if __name__ == "__main__":
    main()
