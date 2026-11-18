# -*- coding: utf-8 -*-
"""Windows 主控台設定：UTF-8 代碼頁與中文字型。"""
import os
import sys

CJK_FONTS = ("細明體", "MingLiU", "NSimSun", "新宋体", "SimSun", "MS Gothic", "ＭＳ ゴシック", "Microsoft YaHei Mono")


def setup():
    """回傳實際使用的字型名稱，失敗回傳 None。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if sys.platform != "win32":
        return None
    os.system("chcp 65001 >nul")
    try:
        return set_font()
    except Exception:
        return None


def probe_widths(chars: str):
    """實際量每個字在這個主控台佔幾格：寫到畫面上，看游標前進多少。只在真的主控台（tty）做，其他回傳 {}。
    模糊寬度字（· … → ※）在不同字型下 1 格或 2 格都有，用猜的會對不齊，量過最準。"""
    if sys.platform != "win32" or not sys.stdout.isatty():
        return {}
    try:
        import ctypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [("L", ctypes.c_short), ("T", ctypes.c_short), ("R", ctypes.c_short), ("B", ctypes.c_short)]

        class CSBI(ctypes.Structure):
            _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD), ("wAttributes", ctypes.c_ushort),
                        ("srWindow", SMALL_RECT), ("dwMaximumWindowSize", COORD)]

        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        info = CSBI()
        written = ctypes.c_ulong(0)

        def write(t):
            k.WriteConsoleW(h, t, len(t), ctypes.byref(written), None)

        def x():
            k.GetConsoleScreenBufferInfo(h, ctypes.byref(info))
            return info.dwCursorPosition.X

        out = {}
        write("\r")
        for ch in chars:
            write("\r" + ch)
            n = x()
            if 1 <= n <= 2:
                out[ch] = n
        write("\r" + " " * 4 + "\r")
        return out
    except Exception:
        return {}


def set_font():
    import ctypes

    class COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

    class CONSOLE_FONT_INFOEX(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("nFont", ctypes.c_ulong), ("dwFontSize", COORD),
                    ("FontFamily", ctypes.c_uint), ("FontWeight", ctypes.c_uint), ("FaceName", ctypes.c_wchar * 32)]

    k = ctypes.windll.kernel32
    h = k.GetStdHandle(-11)
    cur = CONSOLE_FONT_INFOEX()
    cur.cbSize = ctypes.sizeof(cur)
    if not k.GetCurrentConsoleFontEx(h, False, ctypes.byref(cur)):
        return None
    if cur.FaceName in CJK_FONTS:
        return cur.FaceName
    size_y = cur.dwFontSize.Y if cur.dwFontSize.Y >= 14 else 18
    for name in CJK_FONTS:
        info = CONSOLE_FONT_INFOEX()
        info.cbSize = ctypes.sizeof(info)
        info.nFont = 0
        info.dwFontSize = COORD(0, size_y)
        info.FontFamily = 54
        info.FontWeight = 400
        info.FaceName = name
        if not k.SetCurrentConsoleFontEx(h, False, ctypes.byref(info)):
            continue
        back = CONSOLE_FONT_INFOEX()
        back.cbSize = ctypes.sizeof(back)
        k.GetCurrentConsoleFontEx(h, False, ctypes.byref(back))
        if back.FaceName == name:
            return name
    return None
