# -*- coding: utf-8 -*-
"""把繪圖 AI 產生的「像素風」角色圖（白底、單一角色、通常 1024×1536）變成遊戲用的像素圖。

  python hd2d/tools/import_pixel_sprite.py <圖檔> <角色代號> [--cell=8] [--colors=64] [--probe=1]

這類圖其實是放大版的像素畫：畫面上每一格「假像素」是好幾個真像素。步驟：
  1. 找出假像素的格子大小和起點（看邊緣都落在哪些欄、列上）
  2. 每一格取中位數顏色，縮回真正的像素尺寸
  3. 從四邊往內灌，去掉白底
  4. 裁邊、壓色（去掉壓縮雜色）
  5. 用程式做四格走路：身體上下晃、兩腳輪流抬

產出：
  hd2d/art/sprites/<代號>.png    圖集，4 欄 × 1 列（只有圖上那個方向，朝左時由遊戲鏡像）
  hd2d/art/sprites/<代號>.json   每格尺寸、格子偵測結果

--probe=1 只印出格子偵測的結果，不存檔。
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(os.path.dirname(HERE), "art")
MAGIC = (255, 0, 255)


def fold_share(g: np.ndarray, p: int):
    """邊緣強度 g 依週期 p 摺疊後，最強的那個相位佔多少比例。越接近 1 表示邊緣越整齊地落在這個格線上。"""
    n = (len(g) // p) * p
    bins = g[:n].reshape(-1, p).sum(axis=0)
    total = bins.sum()
    if total <= 0:
        return 0.0, 0
    o = int(np.argmax(bins))
    return float(bins[o] / total), o


def detect_grid(arr: np.ndarray):
    """回傳 (格子大小, x 起點, y 起點, 分數表)。arr 是 H×W×3。"""
    a = arr.astype(float)
    gx = np.abs(np.diff(a, axis=1)).sum(axis=2).sum(axis=0)      # 每個欄界線上的顏色變化量
    gy = np.abs(np.diff(a, axis=0)).sum(axis=2).sum(axis=1)
    table = {}
    for p in range(3, 21):
        sx, ox = fold_share(gx, p)
        sy, oy = fold_share(gy, p)
        table[p] = (round((sx + sy) / 2, 3), ox, oy)
    best = max(v[0] for v in table.values())
    # 真正的格子大小的因數也會高分，所以在高分的候選裡挑最大的
    cands = [p for p, v in table.items() if v[0] >= best * 0.85]
    p = max(cands)
    _, ox, oy = table[p]
    return p, (ox + 1) % p, (oy + 1) % p, table


def downsample(arr: np.ndarray, p: int, ox: int, oy: int) -> np.ndarray:
    """每一格取中間區域的中位數顏色。"""
    h, w, _ = arr.shape
    xs = list(range(ox, w - p + 1, p))
    ys = list(range(oy, h - p + 1, p))
    m = max(1, p // 4)
    out = np.zeros((len(ys), len(xs), 3), dtype=np.uint8)
    for j, y in enumerate(ys):
        row = arr[y + m:y + p - m]
        for i, x in enumerate(xs):
            cell = row[:, x + m:x + p - m].reshape(-1, 3)
            out[j, i] = np.median(cell, axis=0)
    return out


def remove_white(img: Image.Image, tol: int = 70) -> Image.Image:
    """從四邊往內灌掉白底。角色有深色外框，所以衣服和鞋子上的白不會被吃掉。"""
    rgb = img.convert("RGB")
    w, h = rgb.size
    work = rgb.copy()
    seeds = [(x, y) for x in range(0, w, max(1, w // 12)) for y in (0, h - 1)]
    seeds += [(x, y) for x in (0, w - 1) for y in range(0, h, max(1, h // 12))]
    for s in seeds:
        if work.getpixel(s) != MAGIC and sum(work.getpixel(s)) > 600:
            ImageDraw.floodfill(work, s, MAGIC, thresh=tol)
    bg = np.all(np.array(work) == np.array(MAGIC), axis=2)
    a = ~bg
    px = np.array(rgb).astype(int)
    light = px.sum(axis=2) > 660                              # 邊緣上殘留的近白色像素再剝一圈
    for _ in range(2):
        edge = np.zeros_like(a)
        edge[1:, :] |= ~a[:-1, :]
        edge[:-1, :] |= ~a[1:, :]
        edge[:, 1:] |= ~a[:, :-1]
        edge[:, :-1] |= ~a[:, 1:]
        a &= ~(a & edge & light)
    out = rgb.copy()
    out.putalpha(Image.fromarray(np.where(a, 255, 0).astype(np.uint8)))
    return out


def clean_colors(img: Image.Image, colors: int) -> Image.Image:
    """壓到固定色數，把同一塊顏色裡的壓縮雜色抹掉。"""
    solid = np.array(img.getchannel("A")) > 0
    rgb = img.convert("RGB")
    arr = np.array(rgb)
    strip = Image.fromarray(arr[solid].reshape(1, -1, 3), "RGB")
    pal = strip.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    q = rgb.quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB")
    out = q.copy()
    out.putalpha(img.getchannel("A"))
    return out


def walk_frames(sprite: Image.Image):
    """四格走路。原圖墊底，上半身往下晃、兩腳輪流抬起。只是讓它看起來在動，不是真的逐格動畫。"""
    w, h = sprite.size
    hip = int(h * 0.62)
    a = np.array(sprite.getchannel("A")) > 0
    cols = np.where(a[hip:].any(axis=0))[0]
    mid = int((cols.min() + cols.max()) / 2) if len(cols) else w // 2
    top = sprite.crop((0, 0, w, hip))
    left = sprite.crop((0, hip, mid, h))
    right = sprite.crop((mid, hip, w, h))
    lift = max(1, h // 70)

    def compose(dl, dr):
        f = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        f.alpha_composite(left, (0, hip + dl))
        f.alpha_composite(right, (mid, hip + dr))
        f.alpha_composite(top, (0, lift))
        return f

    return [sprite, compose(-lift, 0), sprite, compose(0, -lift)]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {a.split("=")[0]: a.split("=")[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    src, cid = args[0], args[1]
    arr = np.array(Image.open(src).convert("RGB"))
    p, ox, oy, table = detect_grid(arr)
    if "--cell" in opts:
        p = int(opts["--cell"])
        _, ox1, oy1 = table.get(p, (0, -1, -1))
        ox, oy = (ox1 + 1) % p, (oy1 + 1) % p
    top5 = sorted(table.items(), key=lambda kv: -kv[1][0])[:6]
    print(f"{cid}: image {arr.shape[1]}x{arr.shape[0]}, cell={p} offset=({ox},{oy}); scores {[(k, v[0]) for k, v in top5]}")
    if opts.get("--probe") == "1":
        return
    small = Image.fromarray(downsample(arr, p, ox, oy), "RGB")
    cut = remove_white(small)
    cut = cut.crop(cut.getbbox())
    cut = clean_colors(cut, int(opts.get("--colors", 64)))
    pad = 3
    sprite = Image.new("RGBA", (cut.width + pad * 2, cut.height + pad), (0, 0, 0, 0))
    sprite.alpha_composite(cut, (pad, pad))                   # 腳貼著底邊
    frames = walk_frames(sprite)
    fw, fh = sprite.size
    sheet = Image.new("RGBA", (fw * 4, fh), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.alpha_composite(f, (i * fw, 0))
    os.makedirs(os.path.join(ART, "sprites"), exist_ok=True)
    sheet.save(os.path.join(ART, "sprites", cid + ".png"))
    meta = {"frame_w": fw, "frame_h": fh, "cols": 4, "rows": 1, "row_names": ["side_right"],
            "cell": p, "offset": [ox, oy], "source": os.path.basename(src)}
    with open(os.path.join(ART, "sprites", cid + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    print(f"{cid}: sprite {fw}x{fh} px, sheet {sheet.size}")


if __name__ == "__main__":
    main()
