# -*- coding: utf-8 -*-
"""把美術總監交的轉身圖（A 組）匯入成場景用的像素圖集。

  python hd2d/tools/import_turn.py <轉身圖> <角色代號> [--side=right|left] [--cm=170]

輸入規格（見 docs/handoff/art_to_eng.md）：一列三格，正面、側面、背面；每格等寬；
背景是精確的洋紅 #FF00FF；每格的腳底在同一列。

產出：
  hd2d/art/sprites/<代號>.png    4 欄（走路四格）× 3 列（朝下、朝右、朝上）
  hd2d/art/sprites/<代號>.json   每格尺寸、腳底留白、人物像素高、身高（公分）

--side 是原圖側面那一格的朝向。圖集裡一律存成朝右，往左走時引擎自己翻面。
--cm 是角色身高，引擎拿它算三個人站在一起時的相對大小。

走路四格是程式做的：身體下沉一格、兩腳輪流抬起一格（側面再前後錯開一格）。
只是讓它看起來在動。等 B 組走路圖來了就換掉。
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(os.path.dirname(HERE), "art")
KEY = (255, 0, 255)


def cut_key(img: Image.Image) -> Image.Image:
    a = np.array(img.convert("RGBA"))
    key = (a[..., 0] == KEY[0]) & (a[..., 1] == KEY[1]) & (a[..., 2] == KEY[2])
    a[key] = 0
    return Image.fromarray(a)


def walk_frames(cell: Image.Image, side: bool):
    w, h = cell.size
    al = np.array(cell.getchannel("A")) > 0
    ys = np.where(al.any(axis=1))[0]
    top_y, foot_y = int(ys.min()), int(ys.max())
    hip = top_y + int((foot_y - top_y + 1) * 0.80)          # 三頭身的腿很短，只佔最下面兩成
    cols = np.where(al[hip:].any(axis=0))[0]
    mid = int((cols.min() + cols.max() + 1) / 2)
    top = cell.crop((0, 0, w, hip))
    left = cell.crop((0, hip, mid, h))
    right = cell.crop((mid, hip, w, h))

    def compose(dl, dr, sl=0, sr=0):
        f = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        f.alpha_composite(left, (sl, hip + dl))
        f.alpha_composite(right, (mid + sr, hip + dr))
        f.alpha_composite(top, (0, 1))                      # 身體下沉一格，蓋住腿抬起來露出的縫
        return f

    if side:
        return [cell, compose(-1, 0, 1, -1), cell, compose(0, -1, -1, 1)]
    return [cell, compose(-1, 0), cell, compose(0, -1)]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {a.split("=")[0]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    src, cid = args[0], args[1]
    img = cut_key(Image.open(src))
    cw = img.width // 3
    cells = [img.crop((i * cw, 0, (i + 1) * cw, img.height)) for i in range(3)]
    if opts.get("--side", "right") == "left":
        cells[1] = cells[1].transpose(Image.FLIP_LEFT_RIGHT)
    spans = []
    for c in cells:
        ys = np.where((np.array(c.getchannel("A")) > 0).any(axis=1))[0]
        spans.append((int(ys.min()), int(ys.max())))
    if len({s[1] for s in spans}) != 1:
        print(f"WARNING: feet are not on the same row across the three cells: {spans}")
    foot = max(s[1] for s in spans)
    body_h = max(s[1] - s[0] + 1 for s in spans)
    rows = [walk_frames(cells[0], False), walk_frames(cells[1], True), walk_frames(cells[2], False)]
    sheet = Image.new("RGBA", (cw * 4, img.height * 3), (0, 0, 0, 0))
    for r, frames in enumerate(rows):
        for c, f in enumerate(frames):
            sheet.alpha_composite(f, (c * cw, r * img.height))
    os.makedirs(os.path.join(ART, "sprites"), exist_ok=True)
    sheet.save(os.path.join(ART, "sprites", cid + ".png"))
    meta = {"frame_w": cw, "frame_h": img.height, "cols": 4, "rows": 3, "row_names": ["down", "side_right", "up"],
            "foot_pad": img.height - 1 - foot, "body_h": body_h, "cm": int(opts.get("--cm", 170)),
            "source": os.path.basename(src)}
    with open(os.path.join(ART, "sprites", cid + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    print(f"{cid}: cell {cw}x{img.height}, body {body_h}px, foot pad {meta['foot_pad']}, sheet {sheet.size}")


if __name__ == "__main__":
    main()
