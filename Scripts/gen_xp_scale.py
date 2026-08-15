"""Generate ExeFS combat XP scale mods for Unicorn Overlord US 1.0.5.

Multipliers: 0.1, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 10

Hooks (cave 0xC6F800, no overlap with enemy_level_scale):
  0xDF59C / 0xDF5F8 — scale grant after DF51C overlevel adjust
  0x27D5D0          — GetExp flytext
  0xEC5D8           — SysMsg +%d EXP
  0xF7F50           — battle pool UI return

Book / item EXP is not modified.

Usage:
  python Scripts/gen_xp_scale.py           # build Release/xp_scale zips
  python Scripts/gen_xp_scale.py --install # also install x10 into Ryujinx
"""
from __future__ import annotations

import argparse
import json
import shutil
import struct
import zipfile
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "Extraction/exefs_out/main.decompressed.bin"
OUT_DIR = ROOT / "Release/xp_scale"
MODS = ROOT / "Mods/xp_scale"
RYU = Path.home() / (
    "AppData/Roaming/Ryujinx/mods/contents/010069401adb8000/xp_scale"
)
PTC = Path.home() / "AppData/Roaming/Ryujinx/games/010069401adb8000/cache/cpu"
MODS_JSON = Path.home() / "AppData/Roaming/Ryujinx/games/010069401adb8000/mods.json"

NSOBID = "C841FFE2717FF03A13990480C51DA73F091C04FA"
CAVE0 = 0xC6F800

# (hook, orig, kind, src, dst, cont)
HOOKS = [
    (0xDF59C, 0x2A1303E0, "movscale", 19, 0, 0xDF5A0),
    (0xDF5F8, 0x2A1303E0, "movscale", 19, 0, 0xDF5FC),
    (0x27D5D0, 0xB91D8759, "str_1d84_x26", 25, 25, 0x27D5D4),
    (0xF7F50, 0x2A1403E0, "movscale", 20, 0, 0xF7F54),
    (0xEC5D8, 0x0B0002E9, "add_then_scale", 9, 9, 0xEC5DC),
]

MULTIPLIERS = [0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 10.0]


def u32le(x: int) -> str:
    return struct.pack("<I", x & 0xFFFFFFFF).hex().upper()


def b_inst(pc: int, target: int) -> int:
    return 0x14000000 | (((target - pc) // 4) & 0x3FFFFFF)


def movz_w(rd: int, imm: int) -> int:
    return 0x52800000 | ((imm & 0xFFFF) << 5) | rd


def movk_w(rd: int, imm: int, hw: int) -> int:
    return 0x72800000 | (hw << 21) | ((imm & 0xFFFF) << 5) | rd


def mov_imm_w(rd: int, imm: int) -> list[int]:
    imm &= 0xFFFFFFFF
    out = [movz_w(rd, imm & 0xFFFF)]
    if imm > 0xFFFF:
        out.append(movk_w(rd, (imm >> 16) & 0xFFFF, 1))
    return out


def mul_w(rd: int, rn: int, rm: int) -> int:
    return 0x1B007C00 | (rm << 16) | (rn << 5) | rd


def udiv_w(rd: int, rn: int, rm: int) -> int:
    return 0x1AC00800 | (rm << 16) | (rn << 5) | rd


def mov_w(rd: int, rm: int) -> int:
    return 0x2A0003E0 | (rm << 16) | rd


def b_cond(pc: int, target: int, eq: bool) -> int:
    imm19 = ((target - pc) // 4) & ((1 << 19) - 1)
    return 0x54000000 | (imm19 << 5) | (0x0 if eq else 0x1)


def cmp_w_imm0(rn: int) -> int:
    return 0x7100001F | (rn << 5)


def str_w(rt: int, rn: int, imm: int) -> int:
    assert imm % 4 == 0
    return 0xB9000000 | ((imm // 4) << 10) | (rn << 5) | rt


def mult_label(m: float) -> str:
    if float(m) == int(m):
        return str(int(m)) if m >= 1 else str(m)
    return str(m)


def emit_scale(cave_base: int, src: int, dst: int, mult: float) -> list[int]:
    frac = Fraction(str(mult)).limit_denominator(1000)
    num, den = frac.numerator, frac.denominator
    t0, t1 = 16, 17
    assert src not in (t0, t1) and dst not in (t0, t1)
    insns: list[int] = []

    def emit(w: int) -> int:
        insns.append(w)
        return len(insns) - 1

    def addr(i: int) -> int:
        return cave_base + 4 * i

    emit(mov_w(t0, src))
    if num != 1:
        for w in mov_imm_w(t1, num):
            emit(w)
        emit(mul_w(dst, t0, t1))
    else:
        emit(mov_w(dst, t0))
    if den != 1:
        for w in mov_imm_w(t1, den):
            emit(w)
        emit(udiv_w(dst, dst, t1))

    emit(cmp_w_imm0(t0))
    i_beq = emit(0)
    emit(cmp_w_imm0(dst))
    i_bne = emit(0)
    emit(movz_w(dst, 1))
    i_after = len(insns)
    insns[i_beq] = b_cond(addr(i_beq), addr(i_after), eq=True)
    insns[i_bne] = b_cond(addr(i_bne), addr(i_after), eq=False)
    return insns


def build_cave(
    cave_base: int, kind: str, src: int, dst: int, mult: float, cont, orig: int
) -> list[int]:
    if kind == "add_then_scale":
        body = [orig]
        body.extend(emit_scale(cave_base + 4, src, dst, mult))
        body.append(0)
        body[-1] = b_inst(cave_base + 4 * (len(body) - 1), cont)
        return body
    if kind == "str_1d84_x26":
        body = emit_scale(cave_base, src, dst, mult)
        body.append(str_w(dst, 26, 0x1D84))
        body.append(0)
        body[-1] = b_inst(cave_base + 4 * (len(body) - 1), cont)
        return body
    if kind == "movscale":
        body = emit_scale(cave_base, src, dst, mult)
        body.append(0)
        body[-1] = b_inst(cave_base + 4 * (len(body) - 1), cont)
        return body
    raise ValueError(kind)


def write_pchtxt(path: Path, mult: float, patches: list[tuple[int, int]]) -> None:
    lines = [
        f"@nsobid-{NSOBID}",
        "@flag offset_shift 0x100",
        "@enabled",
        f"// XP scale x{mult_label(mult)}: combat grant exits + GetExp/pool/SysMsg",
    ]
    for addr, word in patches:
        lines.append(f"{addr:08X} {u32le(word)}")
    lines += ["@stop", ""]
    path.write_bytes(("\r\n".join(lines)).encode("ascii"))


def readme_text(mult: float) -> str:
    return f"""# XP Scale (x{mult_label(mult)})

Ryujinx ExeFS mod for **Unicorn Overlord US 1.0.5**.

Multiplies **combat** EXP by **{mult_label(mult)}** (grants and on-screen +EXP text).
Does not change book / item EXP.

## Install

1. Unzip - folder `xp_scale` with `exefs/`
2. Paste into Ryujinx mods, enable **xp_scale**
3. Fully quit Ryujinx, then boot

US 1.0.5 only. Only one XP scale zip at a time.
"""


def make_zip(mult: float, pchtxt: bytes, readme: str) -> Path:
    path = OUT_DIR / f"xp_scale_{mult_label(mult)}.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xp_scale/README.md", readme.replace("\n", "\r\n"))
        zf.writestr("xp_scale/exefs/00_xp_scale.pchtxt", pchtxt)
    return path


def install_ryujinx(src_variant: Path) -> None:
    if RYU.exists():
        shutil.rmtree(RYU)
    shutil.copytree(src_variant, RYU)
    if PTC.exists():
        shutil.rmtree(PTC, ignore_errors=True)
        print("cleared PTC")
    if MODS_JSON.exists():
        data = json.loads(MODS_JSON.read_text(encoding="utf-8-sig"))
        found = False
        for m in data.get("mods", []):
            if m.get("name") == "xp_scale":
                m["enabled"] = True
                m["path"] = str(RYU)
                found = True
        if not found:
            data.setdefault("mods", []).append(
                {"name": "xp_scale", "enabled": True, "path": str(RYU)}
            )
        MODS_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print("enabled xp_scale in mods.json")
    print("installed Ryujinx xp_scale x10")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--install",
        action="store_true",
        help="Also install the x10 variant into Ryujinx and clear PTC",
    )
    args = ap.parse_args()

    blob = BIN.read_bytes()
    resolved = []
    for hook, orig, kind, src, dst, cont in HOOKS:
        got = struct.unpack_from("<I", blob, hook)[0]
        assert got == orig, f"0x{hook:X}: expected {orig:08X} got {got:08X}"
        resolved.append((hook, orig, kind, src, dst, cont))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("xp_scale_*.zip"):
        old.unlink()

    staged = OUT_DIR / "_staged"
    if staged.exists():
        shutil.rmtree(staged)

    for mult in MULTIPLIERS:
        patches: list[tuple[int, int]] = []
        cave = CAVE0
        for hook, orig, kind, src, dst, cont in resolved:
            body = build_cave(cave, kind, src, dst, mult, cont, orig)
            patches.append((hook, b_inst(hook, cave)))
            for i, insn in enumerate(body):
                patches.append((cave + 4 * i, insn))
            cave = (cave + 4 * len(body) + 0xF) & ~0xF
        assert cave < 0xC6FC00, hex(cave)

        folder = staged / f"x{mult_label(mult)}"
        p = folder / "exefs" / "00_xp_scale.pchtxt"
        p.parent.mkdir(parents=True, exist_ok=True)
        write_pchtxt(p, mult, patches)
        readme = readme_text(mult)
        (folder / "README.md").write_text(readme, encoding="utf-8")
        make_zip(mult, p.read_bytes(), readme)
        print(f"x{mult_label(mult)}: {len(patches)} words end=0x{cave:X}")

    if MODS.exists():
        shutil.rmtree(MODS)
    shutil.copytree(staged / "x1", MODS)

    variants = OUT_DIR / "variants"
    if variants.exists():
        shutil.rmtree(variants)
    shutil.copytree(staged, variants)
    shutil.rmtree(staged)

    (OUT_DIR / "README.md").write_text(
        """# XP Scale

Ryujinx ExeFS mods for **Unicorn Overlord US 1.0.5**.

Each zip multiplies **combat** EXP (battle grants and the on-screen +EXP text)
by the labeled factor. Book / item EXP is unchanged.

| Zip | Multiplier |
|-----|------------|
| `xp_scale_0.1.zip` | ×0.1 |
| `xp_scale_0.25.zip` | ×0.25 |
| `xp_scale_0.5.zip` | ×0.5 |
| `xp_scale_0.75.zip` | ×0.75 |
| `xp_scale_1.zip` | ×1 (identity) |
| `xp_scale_1.25.zip` | ×1.25 |
| `xp_scale_1.5.zip` | ×1.5 |
| `xp_scale_2.zip` | ×2 |
| `xp_scale_10.zip` | ×10 |

## Install

1. Download **one** zip (only one XP scale mod at a time)
2. Unzip - folder `xp_scale/exefs/...`
3. Ryujinx → Unicorn Overlord → Open Mods Directory → paste `xp_scale`
4. Enable **xp_scale** under Manage Mods
5. Fully quit Ryujinx, then boot

## Rebuild

```text
python Scripts/gen_xp_scale.py
python Scripts/gen_xp_scale.py --install   # optional: push x10 to local Ryujinx
```

Requires `Extraction/exefs_out/main.decompressed.bin` (US 1.0.5).
""",
        encoding="utf-8",
    )

    if args.install:
        install_ryujinx(variants / "x10")

    print(f"wrote {OUT_DIR}")


if __name__ == "__main__":
    main()
