# -*- coding: utf-8 -*-
"""把像素圖的 Godot 匯入設定改成「不壓縮、不做縮圖鏈、不要自動偵測成 3D 貼圖」。

  python hd2d/tools/fix_imports.py

Godot 發現一張圖被用在 3D 場景裡，會自動把它改成顯示卡壓縮格式，像素圖會糊掉。
新圖放進 hd2d/art/ 之後的順序：

  1. Godot --headless --path hd2d --import     （產生 .import 檔）
  2. python hd2d/tools/fix_imports.py          （改設定）
  3. Godot --headless --path hd2d --import     （照新設定重新匯入）
"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(os.path.dirname(HERE), "art")
FOLDERS = ["sprites", "tiles", "furniture"]
WANT = {"compress/mode": "0", "mipmaps/generate": "false", "detect_3d/compress_to": "0"}


def main():
    changed = 0
    for folder in FOLDERS:
        for path in sorted(glob.glob(os.path.join(ART, folder, "*.png.import"))):
            with open(path, encoding="utf-8") as f:
                text = f.read()
            new = text
            for key, val in WANT.items():
                new = re.sub(r"(?m)^%s=.*$" % re.escape(key), "%s=%s" % (key, val), new)
            if new != text:
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(new)
                changed += 1
    print("patched", changed, "import files")


if __name__ == "__main__":
    main()
