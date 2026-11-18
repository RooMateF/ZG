# -*- coding: utf-8 -*-
"""在真的主控台裡：把遊戲會畫出來的所有字串實際寫上畫面，量游標位置，跟 textw.w 的估算比對。寫結果到檔案。"""
import sys, os, io, json, ctypes
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ZG_WIDE"] = "1"
from zg.console import setup, probe_widths
from zg.textw import set_ambiguous_wide, set_overrides, PROBE_CHARS, w
font = setup()
set_ambiguous_wide(font is not None)
ov = probe_widths(PROBE_CHARS)
set_overrides(ov)
from zg.world import build_world
from zg.engine import Engine
from zg import ui, options, mapdraw

k = ctypes.windll.kernel32
h = k.GetStdHandle(-11)


class COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class SMALL_RECT(ctypes.Structure):
    _fields_ = [("L", ctypes.c_short), ("T", ctypes.c_short), ("R", ctypes.c_short), ("B", ctypes.c_short)]


class CSBI(ctypes.Structure):
    _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD), ("wAttributes", ctypes.c_ushort),
                ("srWindow", SMALL_RECT), ("dwMaximumWindowSize", COORD)]


k.SetConsoleScreenBufferSize(h, COORD(400, 300))
written = ctypes.c_ulong(0)
info = CSBI()


def measure(t):
    k.WriteConsoleW(h, "\r" + t, len(t) + 1, ctypes.byref(written), None)
    k.GetConsoleScreenBufferInfo(h, ctypes.byref(info))
    x = info.dwCursorPosition.X
    k.WriteConsoleW(h, "\r" + " " * min(390, x + 2) + "\r", min(390, x + 2) + 2, ctypes.byref(written), None)
    return x


bad = {}
checked = 0
seen = set()


def check(s):
    global checked
    for line in s.split("\n"):
        line = line.rstrip()
        if not line or line in seen or w(line) > 380:
            continue
        seen.add(line)
        checked += 1
        real = measure(line)
        if real != w(line):
            bad[line] = (w(line), real)


for seed in (1, 2, 3):
    g = build_world(seed)
    eng = Engine(g)
    for rid in list(g.rooms):
        g.room = rid
        g.cur.visited = True
        eng.new_turn()
        eng.say(eng.room_desc())
        buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
        try:
            ui.draw(eng, None, options.build(g), "")
        finally:
            sys.stdout = old
        check(buf.getvalue())
        check("\n".join(mapdraw.mini_floor(g)))
        check(mapdraw.city_map(g))
        check(mapdraw.floor_map(g))
        for name, fn in (("inv", options.inventory_menu), ("people", options.people_menu), ("base", options.base_menu),
                         ("craft", options.craft_menu), ("rest", options.rest_menu)):
            try:
                m = fn(g)
                check("\n".join(str(e[0]) for e in m.entries))
            except Exception as ex:  # noqa: BLE001
                bad[f"menu {name} @ {rid}"] = repr(ex)
    for n in g.npcs:
        check(options.npc_summary(g, n))
here = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(here, "screen_probe.json"), "w", encoding="utf-8").write(
    json.dumps({"font": font, "overrides": ov, "checked": checked, "bad": bad}, ensure_ascii=False, indent=1))
