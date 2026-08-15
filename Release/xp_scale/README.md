# XP Scale

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
