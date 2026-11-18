# -*- coding: utf-8 -*-
"""顯示寬度。中文、全形 2 格；箭頭、·、★ 這類「模糊寬度」字元在傳統主控台配中文字型時也是 2 格，
在 Windows Terminal 之類的新終端機是 1 格。play.py 依照有沒有成功設定中文字型來決定；環境變數 ZG_AMBIG=1/2 可強制。"""
import os
import unicodedata

AMBIG_WIDE = False
OVERRIDES = {}          # 實際量出來的寬度（console.probe_widths），優先於規則
PROBE_CHARS = "…·§※→–★◎"   # 介面裡用到的模糊寬度字，啟動時量一次


def set_overrides(d):
    global OVERRIDES
    OVERRIDES = dict(d or {})


def set_ambiguous_wide(flag: bool):
    global AMBIG_WIDE
    env = os.environ.get("ZG_AMBIG")
    if env in ("1", "2"):
        AMBIG_WIDE = env == "2"
    else:
        AMBIG_WIDE = bool(flag)


def cw(ch: str) -> int:
    """一個字元佔幾格。"""
    o = ord(ch)
    if o < 0x80:
        return 1
    if ch in OVERRIDES:
        return OVERRIDES[ch]
    e = unicodedata.east_asian_width(ch)
    if e in ("W", "F"):
        return 2
    if e == "A" and AMBIG_WIDE:
        return 2
    return 1


def w(s: str) -> int:
    return sum(cw(c) for c in s)


def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - w(s))
