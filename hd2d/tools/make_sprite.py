# -*- coding: utf-8 -*-
"""把角色概念圖（淺灰底、正面 + 四分之三側面並排）轉成遊戲用的素材。

  python hd2d/tools/make_sprite.py <概念圖> <角色代號> [--head=20] [--body=34] [--colors=20] [--real=1]

產出（都在 hd2d/art/ 底下）：
  concept/<代號>.png     原圖轉存
  full/<代號>.png        去背的正面全身立繪（選單用，保留原畫質感）
  portraits/<代號>.png   去背的半身頭像（對話、列表用）
  sprites/<代號>.png     像素小人圖集：4 欄（走路四格）× 3 列（朝下、朝側、朝上）
  sprites/<代號>.json    每格尺寸

像素小人預設是大頭短身（頭 20 像素、身體 34 像素），因為寫實頭身比縮小後臉只剩幾個點，認不出人。
加 --real=1 則維持原比例。

限制：概念圖沒有背面，所以「朝上」那一列暫時用正面代替；走路是用程式把腿錯開、身體上下晃做出來的，
不是真的逐格重畫。要更好就得補背面圖，或交給專門做像素動畫的工具。
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(os.path.dirname(HERE), "art")
MAGIC = (255, 0, 255)
OUTLINE = (24, 20, 28, 255)


def remove_background(img: Image.Image, tol: int = 38) -> Image.Image:
    """從四邊往內灌：跟邊緣灰底連通、顏色接近的都當背景。只吃連通的部分，所以衣服上的灰不會被挖掉。"""
    rgb = img.convert("RGB")
    w, h = rgb.size
    work = rgb.copy()
    seeds = [(x, y) for x in (0, w // 4, w // 2, 3 * w // 4, w - 1) for y in (0, h - 1)]
    seeds += [(x, y) for x in (0, w - 1) for y in (h // 4, h // 2, 3 * h // 4)]
    for s in seeds:
        if work.getpixel(s) != MAGIC:
            ImageDraw.floodfill(work, s, MAGIC, thresh=tol)
    bg = np.all(np.array(work) == np.array(MAGIC), axis=2)
    alpha = Image.fromarray(np.where(bg, 0, 255).astype(np.uint8))
    alpha = alpha.filter(ImageFilter.MinFilter(5))          # 往內縮兩圈，去掉灰邊
    # 去殘底：邊緣上顏色還很接近背景的像素（髮絲之間的灰、描邊的白暈）一層一層剝掉
    px = np.array(rgb).astype(int)
    bgc = np.median(px[bg], axis=0) if bg.any() else np.array([180, 180, 184])
    close = np.abs(px - bgc).sum(axis=2) < 75
    a = np.array(alpha) > 0
    for _ in range(6):
        edge = np.zeros_like(a)
        edge[1:, :] |= ~a[:-1, :]
        edge[:-1, :] |= ~a[1:, :]
        edge[:, 1:] |= ~a[:, :-1]
        edge[:, :-1] |= ~a[:, 1:]
        peel = a & edge & close
        if not peel.any():
            break
        a &= ~peel
    out = rgb.copy()
    out.putalpha(Image.fromarray(np.where(a, 255, 0).astype(np.uint8)))
    return out


def split_figures(img: Image.Image):
    """沿水平方向找出兩個人形（正面、側面），回傳各自裁好的圖。"""
    a = np.array(img.getchannel("A")) > 0
    cols = a.sum(axis=0) > max(3, a.shape[0] * 0.004)
    runs, start = [], None
    for x, on in enumerate(cols):
        if on and start is None:
            start = x
        elif not on and start is not None:
            runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, len(cols)))
    merged = []
    for r in runs:                                           # 很近的片段併在一起（手上拿的東西）
        if merged and r[0] - merged[-1][1] < img.width * 0.03:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(r)
    merged.sort(key=lambda r: r[1] - r[0], reverse=True)
    figs = sorted(merged[:2])
    out = []
    for x0, x1 in figs:
        part = img.crop((x0, 0, x1, img.height))
        out.append(part.crop(part.getbbox()))
    if len(out) == 1:
        out.append(out[0])
    return out


def shrink(img: Image.Image, size) -> Image.Image:
    """預乘透明度再縮，邊緣才不會帶到背景色。"""
    return img.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def flatten(fig: Image.Image) -> Image.Image:
    """把原畫的筆觸抹平一點，縮小後才不會變成雜點。"""
    rgb = fig.convert("RGB").filter(ImageFilter.MedianFilter(7)).filter(ImageFilter.GaussianBlur(1.2))
    out = rgb.copy()
    out.putalpha(fig.getchannel("A"))
    return out


def quant(small: Image.Image, colors: int) -> Image.Image:
    """壓色，並把半透明切成實心或透明。只拿實心的像素去算調色盤，背景不佔名額。"""
    rgb = small.convert("RGB")
    rgb = ImageEnhance.Color(rgb).enhance(1.3)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.15)
    solid = np.array(small.getchannel("A")) >= 110
    arr = np.array(rgb)
    if solid.any():
        strip = Image.fromarray(arr[solid].reshape(1, -1, 3), "RGB")
        pal = strip.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        q = rgb.quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB")
    else:
        q = rgb
    out = q.copy()
    out.putalpha(Image.fromarray(np.where(solid, 255, 0).astype(np.uint8)))
    return out


def outline(img: Image.Image) -> Image.Image:
    """外面描一圈深色邊。"""
    w, h = img.size
    arr = np.zeros((h + 2, w + 2, 4), dtype=np.uint8)
    arr[1:-1, 1:-1] = np.array(img)
    opaque = arr[:, :, 3] > 0
    near = np.zeros_like(opaque)
    near[1:, :] |= opaque[:-1, :]
    near[:-1, :] |= opaque[1:, :]
    near[:, 1:] |= opaque[:, :-1]
    near[:, :-1] |= opaque[:, 1:]
    arr[near & ~opaque] = OUTLINE
    return Image.fromarray(arr, "RGBA")


def finish(small: Image.Image, colors: int) -> Image.Image:
    return outline(quant(small, colors))


def find_neck(fig: Image.Image) -> int:
    """頭和身體的分界：在身高 9%～19% 之間找最窄的那一列。"""
    a = np.array(fig.getchannel("A")) > 0
    h = a.shape[0]
    widths = a.sum(axis=1).astype(float)
    lo, hi = int(h * 0.09), int(h * 0.19)
    seg = np.convolve(widths[lo:hi], np.ones(9) / 9, mode="same")
    return lo + int(np.argmin(seg[4:-4])) + 4


def to_real(fig: Image.Image, height: int, colors: int):
    w = max(1, round(fig.width * height / fig.height))
    sp = finish(shrink(flatten(fig), (w, height)), colors)
    return sp, int(sp.height * 0.56)


def to_chibi(fig: Image.Image, head_h: int, body_h: int, colors: int):
    """大頭短身：頭和身體分開縮，頭放大，再疊回去。回傳 (像素圖, 腰的列數)。"""
    fig = flatten(fig)
    neck = find_neck(fig)
    head = fig.crop((0, 0, fig.width, neck))
    hb = head.getbbox()
    head = head.crop(hb)
    head_cx = (hb[0] + hb[2]) / 2
    body = fig.crop((0, neck - int(fig.height * 0.01), fig.width, fig.height))
    sb = body_h / body.height
    wide = 1.35                                              # 身體橫向加寬，不然大頭配細身體像竹竿
    bw = max(1, round(fig.width * sb * wide))
    body_s = quant(shrink(body, (bw, body_h)), max(8, colors * 3 // 5))   # 頭和身體各自壓色，臉才不會被衣服的顏色吃掉
    hw = max(1, round(head.width * head_h / head.height))
    head_s = quant(shrink(head, (hw, head_h)), max(6, colors * 2 // 5))
    overlap = 3
    W = max(bw, hw) + 2
    H = head_h + body_h - overlap
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bx = (W - bw) // 2
    canvas.alpha_composite(body_s, (bx, head_h - overlap))
    hx = int(round(bx + head_cx * sb * wide - hw / 2))
    hx = max(0, min(W - hw, hx))
    canvas.alpha_composite(head_s, (hx, 0))
    sp = outline(canvas)
    hip = 1 + head_h - overlap + int(body_h * 0.42)
    return sp, hip


def walk_frames(sprite: Image.Image, hip: int, side: bool):
    """四格走路：站、邁一腳、站、邁另一腳。原圖墊底，再把下半身左右兩半位移後蓋上去，所以不會露出縫。"""
    w, h = sprite.size
    mid = w // 2
    top = sprite.crop((0, 0, w, hip))
    left = sprite.crop((0, hip, mid, h))
    right = sprite.crop((mid, hip, w, h))

    def compose(dl, dr, bob):
        f = sprite.copy()
        f.alpha_composite(left, (dl[0], hip + dl[1]))
        f.alpha_composite(right, (mid + dr[0], hip + dr[1]))
        f.alpha_composite(top, (0, bob))
        return f

    if side:                                                 # 側面：兩腿前後分開
        return [sprite, compose((-1, 0), (1, 0), 1), sprite, compose((1, 0), (-1, 0), 1)]
    return [sprite, compose((0, -1), (0, 1), 1), sprite, compose((0, 1), (0, -1), 1)]   # 正面：左右腳輪流抬


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {a.split("=")[0]: a.split("=")[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    src, cid = args[0], args[1]
    head_h = int(opts.get("--head", 20))
    body_h = int(opts.get("--body", 34))
    colors = int(opts.get("--colors", 20))
    real = opts.get("--real") == "1"
    for d in ("concept", "full", "portraits", "sprites"):
        os.makedirs(os.path.join(ART, d), exist_ok=True)

    img = Image.open(src).convert("RGBA")
    img.convert("RGB").save(os.path.join(ART, "concept", cid + ".png"))
    cut = remove_background(img)
    front, side = split_figures(cut)

    full = front.copy()
    full.thumbnail((900, 1200), Image.LANCZOS)
    full.save(os.path.join(ART, "full", cid + ".png"))

    ph = int(front.height * 0.30)                            # 半身：上面三成，方形
    cx = front.width // 2
    half = min(ph, front.width) // 2
    bust = front.crop((max(0, cx - half), 0, min(front.width, cx + half), ph))
    bust.resize((256, 256), Image.LANCZOS).save(os.path.join(ART, "portraits", cid + ".png"))

    if real:
        sp_front, hip_f = to_real(front, head_h + body_h, colors)
        sp_side, hip_s = to_real(side, head_h + body_h, colors)
    else:
        sp_front, hip_f = to_chibi(front, head_h, body_h, colors)
        sp_side, hip_s = to_chibi(side, head_h, body_h, colors)
    fw = max(sp_front.width, sp_side.width) + 4              # 留邊，走路位移才不會被切掉
    fh = max(sp_front.height, sp_side.height) + 2
    rows = [walk_frames(sp_front, hip_f, False), walk_frames(sp_side, hip_s, True), walk_frames(sp_front, hip_f, False)]
    sheet = Image.new("RGBA", (fw * 4, fh * 3), (0, 0, 0, 0))
    for r, frames in enumerate(rows):
        for c, f in enumerate(frames):
            sheet.alpha_composite(f, (c * fw + (fw - f.width) // 2, r * fh + (fh - f.height)))
    sheet.save(os.path.join(ART, "sprites", cid + ".png"))
    meta = {"frame_w": fw, "frame_h": fh, "cols": 4, "rows": 3, "row_names": ["down", "side", "up_placeholder"],
            "head": head_h, "body": body_h, "colors": colors, "chibi": not real}
    with open(os.path.join(ART, "sprites", cid + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    print(f"{cid}: front {front.size} side {side.size} -> frame {fw}x{fh}, sheet {sheet.size}")


if __name__ == "__main__":
    main()
