"""Build enemy_level_scale ExeFS mod for Unicorn Overlord US 1.0.5.

Scales enemy stage levels to GetCharaAverageLv(10), with floor exceptions
and Sigil Trial skips. UI cave rewrites stage DB on allowlisted draws;
only mission sticker LRs replace W20 with avg (battle UI keeps widget ids).

Usage:
  python Scripts/gen_enemy_level_scale.py           # Release/ + zip
  python Scripts/gen_enemy_level_scale.py --install # also Ryujinx + clear PTC
"""
from __future__ import annotations

import argparse
import shutil
import struct
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN_PATH = ROOT / "Extraction/exefs_out/main.decompressed.bin"
RELEASE_DIR = ROOT / "Release" / "enemy_level_scale"
RELEASE = RELEASE_DIR / "exefs"
MODS = ROOT / "Mods" / "enemy_level_scale" / "exefs"
RYU = Path.home() / (
    "AppData/Roaming/Ryujinx/mods/contents/010069401adb8000/enemy_level_scale/exefs"
)
PTC = Path.home() / "AppData/Roaming/Ryujinx/games/010069401adb8000/cache/cpu"
SITE_ZIP = ROOT / "Tools" / "site" / "enemy_level_scale.zip"

NSOBID = "C841FFE2717FF03A13990480C51DA73F091C04FA"
AVG = 0x2FD640
GET_SINGLETON = 0x19684
CAVE = 0xC6EFAC
ENGAGE_CAVE = 0xC6F380
NUMDRAW_MOV = 0x5C9994
ENGAGE_LDR = 0x199AF0
STAGE_DB = 0x28C19F8
STAGE_STRIDE = 0x50
STAGE_LV_OFF = 0x0C

BIN: bytes = b""

# (stage_db_index, vanilla_floor) — scale up only
FLOOR_STAGES = [
    (55, 40),  # OW_Z1
    (56, 40),  # OW_Z1 (duplicate row)
    (57, 45),  # OW_Z2
    (68, 38),  # OW_TK_C11
    (100, 40),  # OW_GK_Z01
    (101, 40),  # OW_GK_Z02
    (102, 40),  # OW_GK_Z03
]

# (stage_db_index, vanilla) — never touch (restore after avg fill)
SKIP_STAGES = [
    (43, 6),  # OW_FREESTAGE_1 Beginner 1
    (44, 13),  # OW_FREESTAGE_2 Moderate 1
    (45, 10),  # OW_FREESTAGE_3 Beginner 2
    (46, 15),  # OW_FREESTAGE_4 Moderate 2
    (47, 18),  # OW_FREESTAGE_5 Moderate 3
    (48, 21),  # OW_FREESTAGE_6 Advanced 1
    (49, 26),  # OW_FREESTAGE_7 Advanced 2
    (50, 29),  # OW_FREESTAGE_8 Advanced 3
    (51, 31),  # OW_FREESTAGE_9 Expert 1
    (52, 34),  # OW_FREESTAGE_10 Expert 2
    (53, 38),  # OW_FREESTAGE_11 Apex
]

# Return addresses (LR) after BL 0x5C9980 that may trigger stage DB rewrite.
AVG_LRS = sorted(
    {
        0x1087D8,
        0x108B50,
        0x336940,
        0x336A44,
        0x336F48,
        0x33A6D8,
        0x33AB84,
        0x33AC58,
        0x33AD2C,
        0x33AE00,
        0x33B7BC,
        0x33B8B0,
        0x33BD48,
    }
)

# Only these treat W1 as a level digit and may replace W20 with avg.
STICKER_LRS = frozenset({0x1087D8, 0x108B50})


def collect_count() -> int:
    n = 0
    for i in range(400):
        base = STAGE_DB + i * STAGE_STRIDE
        if base + 0x10 > len(BIN):
            break
        lv = struct.unpack_from("<I", BIN, base + STAGE_LV_OFF)[0]
        if lv == 0 or lv > 200:
            if n > 50:
                break
            continue
        if 1 <= lv <= 99:
            n += 1
    return n


def u32le(x: int) -> str:
    return struct.pack("<I", x & 0xFFFFFFFF).hex().upper()


def movz_w(rd: int, imm: int) -> int:
    return 0x52800000 | ((imm & 0xFFFF) << 5) | rd


def movk_w(rd: int, imm: int, hw: int) -> int:
    return 0x72800000 | (hw << 21) | ((imm & 0xFFFF) << 5) | rd


def mov_w(rd: int, rm: int) -> int:
    return 0x2A0003E0 | (rm << 16) | rd


def bl(pc: int, target: int) -> int:
    return 0x94000000 | (((target - pc) // 4) & 0x3FFFFFF)


def ret() -> int:
    return 0xD65F03C0


def adrp(rd: int, pc: int, target: int) -> int:
    page_pc = pc & ~0xFFF
    page_tgt = target & ~0xFFF
    imm = ((page_tgt - page_pc) >> 12) & ((1 << 21) - 1)
    immlo = imm & 3
    immhi = (imm >> 2) & ((1 << 19) - 1)
    return 0x90000000 | (immlo << 29) | (immhi << 5) | rd


def add_x_imm(rd: int, rn: int, imm12: int) -> int:
    return 0x91000000 | ((imm12 & 0xFFF) << 10) | (rn << 5) | rd


def add_x_reg(rd: int, rn: int, rm: int) -> int:
    return 0x8B000000 | (rm << 16) | (rn << 5) | rd


def str_w(rt: int, rn: int, imm: int) -> int:
    return 0xB9000000 | ((imm >> 2) << 10) | (rn << 5) | rt


def ldr_x(rt: int, rn: int, imm: int) -> int:
    return 0xF9400000 | ((imm >> 3) << 10) | (rn << 5) | rt


def ldr_w(rt: int, rn: int, imm: int) -> int:
    return 0xB9400000 | ((imm >> 2) << 10) | (rn << 5) | rt


def subs_w_imm(rd: int, rn: int, imm12: int) -> int:
    return 0x71000000 | ((imm12 & 0xFFF) << 10) | (rn << 5) | rd


def cmp_w(rn: int, rm: int) -> int:
    return 0x6B00001F | (rm << 16) | (rn << 5)


def csel_w_hi(rd: int, rn: int, rm: int) -> int:
    """Wrd = (HI) ? Wrn : Wrm  — unsigned greater-than."""
    return 0x1A800000 | (rm << 16) | (0x8 << 12) | (rn << 5) | rd


def b_ne(pc: int, target: int) -> int:
    imm19 = ((target - pc) // 4) & ((1 << 19) - 1)
    return 0x54000000 | (imm19 << 5) | 0x1


def b_eq(pc: int, target: int) -> int:
    imm19 = ((target - pc) // 4) & ((1 << 19) - 1)
    return 0x54000000 | (imm19 << 5) | 0x0


def cbz(rt: int, pc: int, target: int) -> int:
    imm19 = ((target - pc) // 4) & ((1 << 19) - 1)
    return 0xB4000000 | (imm19 << 5) | rt


def b_inst(pc: int, target: int) -> int:
    return 0x14000000 | (((target - pc) // 4) & 0x3FFFFFF)


def write_pchtxt(path: Path, comment: str, patches: list[tuple[int, int]]) -> None:
    lines = [
        f"@nsobid-{NSOBID}",
        "@flag offset_shift 0x100",
        "@enabled",
        f"// {comment}",
    ]
    for a, insn in patches:
        lines.append(f"{a:08X} {u32le(insn)}")
    lines += ["@stop", ""]
    path.write_bytes(("\r\n".join(lines)).encode("ascii"))


def emit_row_write(insns: list[int], idx: int, level: int, use_csel_avg: bool) -> None:
    """X19 = stage DB. W8 = avg. Write level (or max(avg, level) if use_csel_avg)."""
    off = idx * STAGE_STRIDE
    insns.append(movz_w(9, off & 0xFFFF))
    if off > 0xFFFF:
        insns.append(movk_w(9, (off >> 16) & 0xFFFF, 1))
    insns.append(add_x_reg(10, 19, 9))
    insns.append(movz_w(11, level))
    if use_csel_avg:
        insns.append(cmp_w(8, 11))
        insns.append(csel_w_hi(11, 8, 11))
    insns.append(str_w(11, 10, STAGE_LV_OFF))


def build_ui_cave() -> list[int]:
    nrec = collect_count()
    insns: list[int] = []

    def emit(w: int) -> int:
        insns.append(w)
        return len(insns) - 1

    def addr(i: int) -> int:
        return CAVE + 4 * i

    emit(ldr_x(9, 31, 8))
    i_adr = emit(0x10000008)
    cave_adr_off = CAVE + 4
    emit(movz_w(10, cave_adr_off & 0xFFFF))
    emit(movk_w(10, (cave_adr_off >> 16) & 0xFFFF, 1))
    emit(0xCB0A0108)
    emit(0xCB080129)
    # Original hooked insn: mov w20, w1 (widget id).
    emit(mov_w(20, 1))

    sticker_beq: list[int] = []
    keep_beq: list[int] = []
    for lr in AVG_LRS:
        emit(movz_w(8, lr & 0xFFFF))
        hi = (lr >> 16) & 0xFFFF
        if hi:
            emit(movk_w(8, hi, 1))
        emit(0xEB08013F)
        if lr in STICKER_LRS:
            sticker_beq.append(emit(0))
        else:
            keep_beq.append(emit(0))
    emit(ret())

    # W11 = 1 → sticker digit path may replace W20; 0 → restore saved widget id.
    i_enter_sticker = len(insns)
    emit(movz_w(11, 1))
    i_b_avg_s = emit(0)
    i_enter_keep = len(insns)
    emit(movz_w(11, 0))
    i_b_avg_k = emit(0)

    i_do_avg = len(insns)
    emit(0xA9BC7BFD)
    emit(0xF9000BF3)
    emit(0xF9000FE0)
    emit(0xB90023F4)  # str w20, [sp, #0x20]  saved widget id
    emit(str_w(11, 31, 0x24))  # sticker flag
    emit(0x910003FD)

    i_bl_sing = emit(0)
    i_cbz = emit(0)

    emit(movz_w(1, 10))
    i_bl_avg = emit(0)
    emit(mov_w(8, 0))  # W8 = avg
    i_adrp = emit(0)
    i_add = emit(0)
    emit(movz_w(1, nrec))
    i_loop = len(insns)
    emit(str_w(8, 19, STAGE_LV_OFF))
    emit(add_x_imm(19, 19, STAGE_STRIDE))
    emit(subs_w_imm(1, 1, 1))
    i_bne = emit(0)

    i_adrp2 = emit(0)
    i_add2 = emit(0)
    for idx, floor in FLOOR_STAGES:
        emit_row_write(insns, idx, floor, use_csel_avg=True)
    for idx, van in SKIP_STAGES:
        emit_row_write(insns, idx, van, use_csel_avg=False)

    # Non-sticker: keep original W20 (widget id). Sticker: avg/digit display.
    emit(ldr_w(11, 31, 0x24))
    i_cbz_keep = emit(0)

    emit(mov_w(20, 8))
    emit(ldr_w(9, 31, 0x20))
    skip_eq_slots: list[int] = []
    skip_digits = sorted({van for _, van in SKIP_STAGES})
    for dig in skip_digits:
        emit(movz_w(10, dig))
        emit(cmp_w(9, 10))
        skip_eq_slots.append(emit(0))
    floor_eq_slots: list[int] = []
    for floor in (38, 40, 45):
        emit(movz_w(10, floor))
        emit(cmp_w(9, 10))
        floor_eq_slots.append(emit(0))
    i_skip_disp = emit(0)

    i_keep_digit = len(insns)
    emit(mov_w(20, 9))
    i_b_done_from_keep = emit(0)

    i_apply_floor_disp = len(insns)
    emit(cmp_w(8, 9))
    emit(csel_w_hi(20, 8, 9))
    i_b_done_from_floor = emit(0)

    i_fail = len(insns)
    emit(0xB94023F4)  # ldr w20, [sp, #0x20]

    i_done = len(insns)
    emit(0xF9400FE0)
    emit(0xF9400BF3)
    emit(0xA8C47BFD)
    emit(ret())

    for bi in sticker_beq:
        insns[bi] = b_eq(addr(bi), addr(i_enter_sticker))
    for bi in keep_beq:
        insns[bi] = b_eq(addr(bi), addr(i_enter_keep))
    insns[i_b_avg_s] = b_inst(addr(i_b_avg_s), addr(i_do_avg))
    insns[i_b_avg_k] = b_inst(addr(i_b_avg_k), addr(i_do_avg))
    insns[i_bl_sing] = bl(addr(i_bl_sing), GET_SINGLETON)
    insns[i_cbz] = cbz(0, addr(i_cbz), addr(i_fail))
    insns[i_bl_avg] = bl(addr(i_bl_avg), AVG)
    insns[i_adrp] = adrp(19, addr(i_adrp), STAGE_DB)
    insns[i_add] = add_x_imm(19, 19, STAGE_DB & 0xFFF)
    insns[i_bne] = b_ne(addr(i_bne), addr(i_loop))
    insns[i_adrp2] = adrp(19, addr(i_adrp2), STAGE_DB)
    insns[i_add2] = add_x_imm(19, 19, STAGE_DB & 0xFFF)
    insns[i_cbz_keep] = cbz(11, addr(i_cbz_keep), addr(i_fail))
    for bi in skip_eq_slots:
        insns[bi] = b_eq(addr(bi), addr(i_keep_digit))
    for bi in floor_eq_slots:
        insns[bi] = b_eq(addr(bi), addr(i_apply_floor_disp))
    insns[i_skip_disp] = b_inst(addr(i_skip_disp), addr(i_done))
    insns[i_b_done_from_keep] = b_inst(addr(i_b_done_from_keep), addr(i_done))
    insns[i_b_done_from_floor] = b_inst(addr(i_b_done_from_floor), addr(i_done))

    assert addr(i_adr) == cave_adr_off
    page_pc = addr(i_adrp) & ~0xFFF
    w = insns[i_adrp]
    imm = ((w >> 29) & 3) | (((w >> 5) & ((1 << 19) - 1)) << 2)
    if imm & (1 << 20):
        imm -= 1 << 21
    assert page_pc + (imm << 12) == (STAGE_DB & ~0xFFF)
    assert addr(len(insns)) <= ENGAGE_CAVE, (
        f"UI cave overflow: end {hex(addr(len(insns)))} > engage {hex(ENGAGE_CAVE)}"
    )
    return insns


def build_engage_cave() -> list[int]:
    insns: list[int] = []

    def emit(w: int) -> int:
        insns.append(w)
        return len(insns) - 1

    def addr(i: int) -> int:
        return ENGAGE_CAVE + 4 * i

    emit(0xA9BD7BFD)
    emit(0xF9000BF3)
    emit(0xF9000FE0)
    emit(0xF90013E1)
    emit(0x910003FD)

    i_bl_sing = emit(0)
    i_cbz = emit(0)
    emit(movz_w(1, 10))
    i_bl_avg = emit(0)
    emit(mov_w(8, 0))
    emit(str_w(8, 20, 0x1BC4))
    i_to_done = emit(0)

    i_fail = len(insns)
    emit(ldr_w(8, 20, 0x1BC4))

    i_done = len(insns)
    emit(0xF94013E1)
    emit(0xF9400FE0)
    emit(0xF9400BF3)
    emit(0xA8C37BFD)
    emit(ret())

    insns[i_bl_sing] = bl(addr(i_bl_sing), GET_SINGLETON)
    insns[i_cbz] = cbz(0, addr(i_cbz), addr(i_fail))
    insns[i_bl_avg] = bl(addr(i_bl_avg), AVG)
    insns[i_to_done] = b_inst(addr(i_to_done), addr(i_done))
    assert addr(len(insns)) <= 0xC6F500
    return insns


def write_ship_zip() -> Path:
    zip_path = ROOT / "Release" / "enemy_level_scale.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(RELEASE_DIR / "README.md", "enemy_level_scale/README.md")
        for name in ("00_cave.pchtxt", "01_numdraw.pchtxt", "02_engage.pchtxt"):
            zf.write(RELEASE / name, f"enemy_level_scale/exefs/{name}")
    if SITE_ZIP.parent.is_dir():
        shutil.copy2(zip_path, SITE_ZIP)
    return zip_path


def main() -> None:
    global BIN
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install",
        action="store_true",
        help="Also copy into Mods/ + Ryujinx and clear PTC",
    )
    args = parser.parse_args()

    BIN = BIN_PATH.read_bytes()
    assert struct.unpack_from("<I", BIN, NUMDRAW_MOV)[0] == 0x2A0103F4
    assert struct.unpack_from("<I", BIN, ENGAGE_LDR)[0] == 0xB95BC688

    for idx, floor in FLOOR_STAGES:
        lv = struct.unpack_from("<I", BIN, STAGE_DB + idx * STAGE_STRIDE + STAGE_LV_OFF)[0]
        assert lv == floor, f"floor idx {idx}: rom {lv} != {floor}"
    for idx, van in SKIP_STAGES:
        lv = struct.unpack_from("<I", BIN, STAGE_DB + idx * STAGE_STRIDE + STAGE_LV_OFF)[0]
        assert lv == van, f"skip idx {idx}: rom {lv} != {van}"

    ui = build_ui_cave()
    eng = build_engage_cave()

    targets = [RELEASE]
    if args.install:
        targets.extend([MODS, RYU])

    for d in targets:
        d.mkdir(parents=True, exist_ok=True)
        for p in d.glob("*.pchtxt"):
            p.unlink()

    comment = "v39.2 UI cave: rewrite on full allowlist; W20 avg only for stickers"
    patches_cave = [(CAVE + 4 * i, ui[i]) for i in range(len(ui))]
    patches_num = [(NUMDRAW_MOV, bl(NUMDRAW_MOV, CAVE))]
    patches_eng = [(ENGAGE_LDR, bl(ENGAGE_LDR, ENGAGE_CAVE))] + [
        (ENGAGE_CAVE + 4 * i, eng[i]) for i in range(len(eng))
    ]

    for d in targets:
        write_pchtxt(d / "00_cave.pchtxt", comment, patches_cave)
        write_pchtxt(d / "01_numdraw.pchtxt", "0x5C9994 -> BL cave", patches_num)
        write_pchtxt(
            d / "02_engage.pchtxt",
            "engage +0x1bc4 -> GetCharaAverageLv(10)",
            patches_eng,
        )

    if args.install and PTC.exists():
        shutil.rmtree(PTC, ignore_errors=True)
        print("cleared PTC")

    zip_path = write_ship_zip()
    print(f"ui cave {hex(CAVE)}..{hex(CAVE + 4 * len(ui))} n={len(ui)}")
    print(f"engage {hex(ENGAGE_CAVE)}..{hex(ENGAGE_CAVE + 4 * len(eng))} n={len(eng)}")
    print(f"wrote {zip_path} ({zip_path.stat().st_size} bytes)")
    print("files:", sorted(p.name for p in RELEASE.glob("*.pchtxt")))


if __name__ == "__main__":
    main()
