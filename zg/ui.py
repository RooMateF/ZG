# -*- coding: utf-8 -*-
"""固定版面：狀態列 / 這裡有什麼 / 訊息區 / 選項區 / 快捷鍵列，視窗夠寬時右欄常駐小地圖。每次輸入後整個重畫。"""
import os
import shutil
import sys

from .textw import w as _w, cw, pad  # noqa: F401

WIDTH = 78       # 單欄模式一行最多幾格（中文佔 2 格）
LEFT_W = 68      # 雙欄模式左欄寬
RIGHT_W = 45     # 右欄小地圖寬
GAP = " | "
MSG_LINES = 8    # 訊息區固定高度，不夠就補空行

HOTKEYS = [("M", "地圖"), ("I", "背包"), ("C", "製作"), ("P", "人物"), ("H", "據點"), ("R", "休息"),
           ("T", "狀態"), ("J", "日誌"), ("?", "說明"), ("B", "老闆"), ("Q", "離開")]


def wrap(text, width=WIDTH):
    """依顯示寬度斷行，保留原本的換行。"""
    out = []
    for raw in str(text).split("\n"):
        cur, cur_w = "", 0
        for ch in raw:
            ww = cw(ch)
            if cur_w + ww > width:
                out.append(cur)
                cur, cur_w = "", 0
            cur += ch
            cur_w += ww
        out.append(cur)
    return out


def pack(pieces, width=WIDTH, sep="  "):
    """把短字串盡量排在同一行。"""
    lines, cur = [], ""
    for piece in pieces:
        if cur and _w(cur) + _w(sep) + _w(piece) > width:
            lines.append(cur)
            cur = piece
        else:
            cur = piece if not cur else cur + sep + piece
    if cur:
        lines.append(cur)
    return lines


def rule(title="", width=WIDTH):
    if not title:
        return "-" * width
    head = f"-- {title} "
    return head + "-" * max(0, width - _w(head))


def clear():
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")
    else:
        print("\n" + "#" * 20 + " 重畫 " + "#" * 20)


def wide_mode():
    """視窗夠寬就雙欄（右欄小地圖）；環境變數 ZG_WIDE=1/0 可強制。"""
    env = os.environ.get("ZG_WIDE")
    if env in ("0", "1"):
        return env == "1"
    try:
        cols = shutil.get_terminal_size((80, 24)).columns
    except Exception:
        cols = 80
    return cols >= LEFT_W + _w(GAP) + RIGHT_W + 1


def columns(left, right, lw):
    out = []
    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        out.append((pad(l, lw) + GAP + r).rstrip())
    return out


def bar(width=WIDTH):
    return pack([f"{k}{name}" for k, name in HOTKEYS], width, sep=" ")


def is_header(entry):
    return entry[1] is None and str(entry[0]).startswith("§")


def selectable(entries):
    """拿掉群組標題，剩下的才有編號。"""
    return [e for e in entries if not is_header(e)]


def _pack_pieces(pieces, width):
    colw = (width - 2) // 2
    if len(pieces) >= 2 and max(_w(p) for p in pieces) <= colw:
        half = (len(pieces) + 1) // 2
        left, right = pieces[:half], pieces[half:]
        return [(pad(l, colw) + "  " + (right[i] if i < len(right) else "")).rstrip() for i, l in enumerate(left)]
    out = []
    for p in pieces:
        out.extend(wrap(p, width))
    return [ln.rstrip() for ln in out]


def render_entries(entries, back=False, width=WIDTH):
    """選項直排兩欄，編號靠右對齊；§ 群組標題獨佔一行，編號跨群組連續。"""
    out = []
    block, i = [], 0
    for e in entries:
        if is_header(e):
            if block:
                out.extend(_pack_pieces(block, width))
                block = []
            out.append(f"[{e[0][1:]}]")
            continue
        i += 1
        block.append(f"{i:>2} {e[0]}")
    if back:
        block.append(" 0 返回")
    if block:
        out.extend(_pack_pieces(block, width))
    return out


def here_lines(g, width):
    """這裡有什麼：地上 / 有人 / 出口，固定兩行。"""
    r = g.cur
    parts = []
    if r.enemies:
        from .combat import numbered, focused
        f = focused(g)
        parts.append(("敵人 " if g.combat else "沒發現你 ") + "、".join(f"{'◎' if e is f else ''}{uid}:{e.label()}(血{max(0, e.hp)} 距{e.dist})" for uid, e in numbered(g)))
    if r.items:
        parts.append("地上 " + "、".join(it.label() for it in r.items))
    npcs = g.npcs_here()
    if npcs:
        parts.append("有人 " + "、".join(n.name for n in npcs))
    ex = []
    for d, tid in r.exits.items():
        t = g.rooms[tid]
        if t.loc != r.loc:
            ex.append(f"{d}[{t.loc}]")          # 方括號 = 通往另一個地區（跨區 20 分）
        else:
            ex.append(f"{d}{t.name}" + ("(鎖)" if t.locked else ""))
    parts.append("出口 " + " ".join(ex))
    if r.searched and not r.is_street():
        if r.loot:
            parts.insert(0, "翻過，還有東西沒翻到")
        elif not r.items:
            parts.insert(0, "翻乾淨了")       # 地上還有東西就不算清空，地上那段會寫
    return wrap("這裡：" + " | ".join(parts), width)


def draw(eng, menu, entries, hint=""):
    """主畫面。"""
    g = eng.g
    wide = wide_mode()
    W = LEFT_W if wide else WIDTH
    left = []
    left.extend(wrap(eng.status_line(), W))
    left.append(rule("", W))
    block = here_lines(g, W)
    if len(block) > 2:                      # 太長就截掉，保持版面高度固定
        block = block[:2]
        block[1] = block[1][:-1] + "…"
    block.extend([""] * (2 - len(block)))
    left.extend(block)
    left.append(rule("", W))
    opt_lines = render_entries(entries, back=menu is not None, width=W)
    msg_h = max(4, MSG_LINES + 6 - len(opt_lines))      # 選項多時訊息區讓位，整個畫面高度大致不變
    lines = []
    for t in eng.out:
        lines.extend(wrap(t, W))
    if hint:
        lines.extend(wrap("※ " + hint, W))
    hard_max = msg_h + 4
    if len(lines) > hard_max:                 # 太多就截，最後一行提示去日誌看
        cut = len(lines) - (hard_max - 1)
        lines = lines[:hard_max - 1] + [f"…還有 {cut} 行，按 J 看完整紀錄"]
    left.extend(lines)
    left.extend([""] * (msg_h - len(lines)))
    if g.over:
        title = "結束"
    elif menu:
        title = menu.title
    elif g.flags.get("pending"):
        title = "回答"
    elif g.combat:
        title = "戰鬥（輸入數字）"
    else:
        title = "選項（數字選，n s e w u d 直接走，L 看四周；沒寫時間的不花時間）"
    left.append(rule(title, W))
    left.extend(opt_lines)
    left.append(rule("", W))
    left.extend(bar(W))
    clear()
    if wide:
        from .mapdraw import mini_floor
        right = []
        for t in mini_floor(g, max_lines=len(left)):
            right.extend(wrap(t, RIGHT_W))
        for ln in columns(left, right, W):
            print(ln)
    else:
        for ln in left:
            print(ln)


def view(title, text, prompt="按 Enter 回到遊戲 "):
    """全畫面檢視（地圖、狀態、日誌、說明），按 Enter 回主畫面。"""
    try:
        cols = shutil.get_terminal_size((80, 24)).columns
    except Exception:
        cols = 80
    width = max(WIDTH, min(cols - 2, 118))
    clear()
    print(rule(title, width))
    for t in (text if isinstance(text, (list, tuple)) else [text]):
        for ln in wrap(t, width):
            print(ln)
    print(rule("", width))
    try:
        input(prompt)
        return True
    except (EOFError, KeyboardInterrupt):
        return False
