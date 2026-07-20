"""Apply ExeFS pchtxt overlays and emit live class/IF maps for the mission editor.

Usage:
  python Scripts/resolve_tactics_mods.py --patches path1.pchtxt path2.pchtxt
  python Scripts/resolve_tactics_mods.py --json '{"patches":["Mods/class_editor/exefs/main.pchtxt"]}'

Stdout: JSON with class_tactics, skill_default_ifs, item_skills, patches_applied.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(r"d:/Documents/Projects/Emulation/UnicornOverlord")
sys.path.insert(0, str(ROOT / "Scripts"))

from export_equipaiset import (  # noqa: E402
    EQUIPAISET_BASE,
    EQUIPAISET_STRIDE,
    MAIN,
    apply_pchtxt,
    apply_pchtxt_text,
    item_granted_skill,
    parse_enum,
    skill_default_ifs,
    synthesize_class_default_lines,
)

DEBUG = ROOT / "Extraction/cpk_data/Unicorn_US/Debug"


def resolve_paths(raw: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in raw:
        path = Path(p)
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        if path.exists():
            out.append(path)
    return out


def build_payload(blob: bytes, patch_count: int) -> dict:
    from export_equipaiset import parse_enum_comments
    import csv

    if_pairs = parse_enum_comments(DEBUG / "_UcEnum_EquipAi.inc", "EQUIPAI_IF:")
    n_ifs = len(if_pairs)
    if_syms = [s for s, _ in if_pairs]
    classes = parse_enum(DEBUG / "_UcEnum_Class.inc", "CLASSTYPE:")
    skill_names = parse_enum(DEBUG / "_UcEnum_Skill.inc", "BT_SKILLID:")
    item_names = parse_enum(DEBUG / "_UcEnum_Item.inc", "ITEMID:")

    skill_labels: dict[int, str] = {}
    for csv_name in ("item_skills.csv", "class_default_tactics_lines.csv"):
        path = ROOT / "Extraction/tables" / csv_name
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                try:
                    sid = int(row["skill_id"])
                except (KeyError, ValueError):
                    continue
                name = (row.get("skill_name") or "").strip()
                if sid and name and name.lower() not in ("none", "null"):
                    skill_labels[sid] = name

    def label(sid: int, ssym: str) -> str:
        if sid in skill_labels:
            return skill_labels[sid]
        name = ssym
        for prefix in ("ACT_", "PAS_", "DEFAULT_"):
            if name.startswith(prefix):
                name = name[len(prefix) :]
                break
        return name.replace("_", " ").title()

    class_tactics = []
    for ci, cname in enumerate(classes):
        lines = synthesize_class_default_lines(blob, ci, n_ifs, skill_names)
        out_lines = []
        for line in lines:
            sid = int(line.get("skill_id") or 0)
            ssym = str(line.get("skill_symbol") or "")
            i0 = int(line.get("if0") or 0)
            i1 = int(line.get("if1") or 0)
            entry = {
                "action": int(line["action"]),
                "skill_id": sid,
                "skill_symbol": ssym,
                "skill_name": label(sid, ssym),
                "learn_level": int(line.get("learn_level") or 1),
                "if0": i0,
                "if1": i1,
            }
            if 0 < i0 < n_ifs:
                entry["if0_symbol"] = if_syms[i0]
            if 0 < i1 < n_ifs:
                entry["if1_symbol"] = if_syms[i1]
            out_lines.append(entry)
        class_tactics.append(
            {
                "class_id": ci,
                "class_symbol": cname,
                "lines": out_lines,
            }
        )

    skill_ifs: dict[str, dict] = {}
    max_probe = min(500, (len(blob) - EQUIPAISET_BASE) // EQUIPAISET_STRIDE)
    for sid in range(1, max_probe):
        off = EQUIPAISET_BASE + sid * EQUIPAISET_STRIDE
        if off + EQUIPAISET_STRIDE > len(blob):
            break
        if struct.unpack_from("<I", blob, off)[0] != sid:
            continue
        i0, i1 = skill_default_ifs(blob, sid, n_ifs)
        if i0 or i1:
            entry = {"if0": i0, "if1": i1}
            if 0 < i0 < n_ifs:
                entry["if0_symbol"] = if_syms[i0]
            if 0 < i1 < n_ifs:
                entry["if1_symbol"] = if_syms[i1]
            skill_ifs[str(sid)] = entry

    item_skills: dict[str, dict] = {}
    for iid, _isym in enumerate(item_names):
        sid = item_granted_skill(blob, iid)
        if not sid:
            continue
        ssym = skill_names[sid] if sid < len(skill_names) else ""
        if ssym.startswith("EQUIPAI_") or ssym in (
            "UNKNOWN",
            "EQUIPAI_START",
            "EQUIPAI_END",
        ):
            continue
        i0, i1 = skill_default_ifs(blob, sid, n_ifs)
        entry = {
            "skill_id": sid,
            "skill_symbol": ssym,
            "skill_name": label(sid, ssym),
            "if0": i0,
            "if1": i1,
        }
        if 0 < i0 < n_ifs:
            entry["if0_symbol"] = if_syms[i0]
        if 0 < i1 < n_ifs:
            entry["if1_symbol"] = if_syms[i1]
        item_skills[str(iid)] = entry

    return {
        "ok": True,
        "patches_applied": patch_count,
        "class_tactics": class_tactics,
        "skill_default_ifs": skill_ifs,
        "item_skills": item_skills,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patches", nargs="*", default=[])
    ap.add_argument("--json", default="")
    ap.add_argument("--json-file", default="")
    args = ap.parse_args()

    patch_paths: list[str] = list(args.patches)
    patch_texts: list[tuple[str, str]] = []
    body: dict = {}
    if args.json_file:
        body = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    elif args.json:
        body = json.loads(args.json)
    for p in body.get("patches") or []:
        if isinstance(p, str):
            patch_paths.append(p)
        elif isinstance(p, dict):
            if p.get("text") is not None:
                patch_texts.append(
                    (str(p.get("name") or "upload.pchtxt"), str(p["text"]))
                )
            elif p.get("path"):
                patch_paths.append(str(p["path"]))

    blob = MAIN.read_bytes()
    total = 0
    applied_names: list[str] = []
    for path in resolve_paths(patch_paths):
        blob, n = apply_pchtxt(blob, path)
        total += n
        if n:
            applied_names.append(str(path))
    for name, text in patch_texts:
        blob, n = apply_pchtxt_text(blob, text)
        total += n
        if n:
            applied_names.append(name)

    payload = build_payload(blob, total)
    payload["files"] = applied_names
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
