# -*- coding: utf-8 -*-
"""把已經去好背的立繪（透明 PNG，正面和四分之三側面並排）匯入成人物面板用的素材。

  python hd2d/tools/import_portrait.py <透明 PNG> <角色代號> [--preview=預覽圖路徑]

產出（都在 hd2d/art/ 底下）：
  full/<代號>.png        正面全身，最高 1200
  full/<代號>_side.png   四分之三側面全身，最高 1200（面板目前沒用到，先留著）
  portraits/<代號>.png   半身頭像 256x256

和 make_sprite.py 的差別：這支不自己去背，只相信圖裡的透明度。圖是美術總監審過、去好背才放進 inbox 的。
做的清理只有兩件：很淡的殘留透明度（低於 16）歸零；半透明邊緣上偏離主體很遠的雜色不處理，有問題就退回。
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(os.path.dirname(HERE), "art")


def clean_alpha(img: Image.Image, floor: int = 16) -> Image.Image:
    a = np.array(img.convert("RGBA"))
    faint = a[..., 3] < floor
    a[faint] = 0                                            # 連顏色一起清掉，縮圖時才不會把底色混進邊緣
    return Image.fromarray(a)


def split_figures(img: Image.Image, min_w: int = 60):
    """照透明度找出左右並排的人。回傳由左到右各自裁好的圖。"""
    al = np.array(img)[..., 3]
    solid = (al > 128).sum(axis=0) > 5
    runs, start = [], None
    for x, v in enumerate(solid):
        if v and start is None:
            start = x
        if not v and start is not None:
            runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, len(solid)))
    runs = [r for r in runs if r[1] - r[0] >= min_w]
    figs = []
    for i, (x0, x1) in enumerate(runs):
        left = (runs[i - 1][1] + x0) // 2 if i > 0 else 0   # 切在兩個人中間，髮絲之類的淡邊才不會被切掉
        right = (x1 + runs[i + 1][0]) // 2 if i + 1 < len(runs) else img.width
        part = img.crop((left, 0, right, img.height))
        box = part.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
        figs.append(part.crop(box))
    return figs


def shrink(fig: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """用預乘透明度縮圖，邊緣不會出現深色或亮色的框。"""
    scale = min(max_w / fig.width, max_h / fig.height, 1.0)
    size = (max(1, round(fig.width * scale)), max(1, round(fig.height * scale)))
    a = np.array(fig).astype(np.float32) / 255.0
    a[..., :3] *= a[..., 3:4]
    pre = Image.merge("RGBA", [Image.fromarray((a[..., i] * 255).astype(np.uint8)) for i in range(4)])
    pre = pre.resize(size, Image.LANCZOS)
    b = np.array(pre).astype(np.float32) / 255.0
    al = np.clip(b[..., 3:4], 1e-4, 1)
    b[..., :3] = np.clip(b[..., :3] / al, 0, 1)
    return Image.fromarray((b * 255).round().astype(np.uint8))


def bust(front: Image.Image) -> Image.Image:
    ph = int(front.height * 0.30)                           # 上面三成，方形
    cx = front.width // 2
    half = min(ph, front.width) // 2
    return shrink(front.crop((max(0, cx - half), 0, min(front.width, cx + half), ph)).resize((512, 512), Image.LANCZOS), 256, 256)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {a.split("=")[0]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    src, cid = args[0], args[1]
    for d in ("full", "portraits"):
        os.makedirs(os.path.join(ART, d), exist_ok=True)
    img = clean_alpha(Image.open(src))
    figs = split_figures(img)
    if not figs:
        print("no figure found (is the image transparent?)")
        sys.exit(2)
    front = figs[0]
    full = shrink(front, 900, 1200)
    full.save(os.path.join(ART, "full", cid + ".png"))
    bust(front).save(os.path.join(ART, "portraits", cid + ".png"))
    sizes = [f"front {full.size}"]
    if len(figs) > 1:
        side = shrink(figs[1], 900, 1200)
        side.save(os.path.join(ART, "full", cid + "_side.png"))
        sizes.append(f"side {side.size}")
    print(f"{cid}: {len(figs)} figure(s), " + ", ".join(sizes))
    if "--preview" in opts:                                 # 放在面板底色和中灰上各一份，檢查邊緣
        outs = [full] + ([side] if len(figs) > 1 else [])
        w = sum(o.width for o in outs) + 20 * (len(outs) + 1)
        sheet = Image.new("RGBA", (w * 2, 1240), (0, 0, 0, 255))
        for k, bg in enumerate([(18, 20, 28, 255), (128, 128, 128, 255)]):
            sheet.paste(Image.new("RGBA", (w, 1240), bg), (k * w, 0))
            x = k * w + 20
            for o in outs:
                sheet.alpha_composite(o, (x, 1220 - o.height))
                x += o.width + 20
        sheet.convert("RGB").save(opts["--preview"])


if __name__ == "__main__":
    main()
