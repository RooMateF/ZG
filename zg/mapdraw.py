# -*- coding: utf-8 -*-
"""用文字方塊畫地圖：城市總覽 + 目前建築的樓層平面圖。中文佔 2 格，ASCII 佔 1 格。"""
from .data import LOCATIONS
from .world import room_floor, floor_label
from .textw import w as _w, cw, pad as _pad

OFFS = {"北": (0, -1), "南": (0, 1), "東": (1, 0), "西": (-1, 0)}


def _wide(ch):
    return cw(ch) == 2


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.rows = [[" "] * w for _ in range(h)]

    def put(self, r, c, text):
        if r < 0 or r >= self.h:
            return
        for ch in text:
            if c >= self.w:
                break
            if c >= 0:
                self.rows[r][c] = ch
            if _wide(ch):
                c += 1
                if 0 <= c < self.w:
                    self.rows[r][c] = ""
            c += 1

    def box(self, r, c, inner_w, lines):
        """畫一個框，lines 是框內每一行文字。"""
        self.put(r, c, "+" + "-" * inner_w + "+")
        for i, text in enumerate(lines):
            self.put(r + 1 + i, c, "|" + _pad(text, inner_w) + "|")
        self.put(r + 1 + len(lines), c, "+" + "-" * inner_w + "+")

    def render(self):
        out = []
        for row in self.rows:
            out.append("".join(row).rstrip())
        while out and not out[-1]:
            out.pop()
        return "\n".join(out)


# ---------------------------------------------------------------- 城市
BOX_W = 10      # 框內寬
STEP_X = 16     # 欄距（框 12 + 連線 4）
STEP_Y = 4      # 列距（框 3 + 連線 1）


def city_map(g):
    cur_loc = g.cur.loc
    base_loc = g.rooms[g.base.room].loc if g.base.room else None
    cv = Canvas(STEP_X * 3, STEP_Y * 7)
    pos = {}
    for loc, spec in LOCATIONS.items():
        x, y = spec["pos"]
        pos[loc] = (x, y)
        mark = ""
        if loc == cur_loc:
            mark += "@"
        if loc == base_loc:
            mark += "#"
        if g.threat.get(loc, 0) >= 6:
            mark += "!"
        if loc == "軍方檢查站" and g.flags.get("checkpoint_gone"):
            mark += "x"
        name = loc if _w(loc) <= BOX_W - len(mark) else loc[:4]
        text = _pad(name, BOX_W - len(mark)) + mark
        r, c = y * STEP_Y, (x - 1) * STEP_X
        cv.box(r, c, BOX_W, [text])
    # 連線
    for loc, spec in LOCATIONS.items():
        x, y = pos[loc]
        for d, other in spec["exits"].items():
            ox, oy = pos[other]
            if d == "東":
                cv.put(y * STEP_Y + 1, (x - 1) * STEP_X + BOX_W + 2, "-" * (STEP_X - BOX_W - 2))
            elif d == "南":
                cv.put(y * STEP_Y + 3, (x - 1) * STEP_X + 1 + BOX_W // 2, "|")
    lines = ["城市（@你在這 #據點 !高威脅 x已撤離）", cv.render()]
    return "\n".join(lines)


# ---------------------------------------------------------------- 建築內的樓層配置
def _plan(g):
    """目前建築：rooms, 入口房 id, floors {樓層: {room_id: (x, y)}}。"""
    loc = g.cur.loc
    rooms = {r.id: r for r in g.rooms.values() if r.loc == loc}
    entrance = next(r for r in rooms.values() if r.is_street())
    first_id = entrance.exits.get("進")
    floors = {}
    for rid, r in rooms.items():
        if not r.is_street():
            floors.setdefault(room_floor(r.tags), []).append(rid)
    plans = {}
    for k, ids in floors.items():
        start = first_id if k == 1 and first_id in ids else ids[0]
        coords = {start: (0, 0)}
        stack = [start]
        while stack:
            rid = stack.pop()
            x, y = coords[rid]
            for d, tid in rooms[rid].exits.items():
                if d in OFFS and tid in ids and tid not in coords:
                    coords[tid] = (x + OFFS[d][0], y + OFFS[d][1])
                    stack.append(tid)
        plans[k] = coords
    return rooms, first_id, plans


def _draw_floor(g, rooms, coords, first_id, inner_w, box_h, label_fn, gap=None):
    """畫一層。回傳 list[str]。"""
    xs = [c[0] for c in coords.values()]
    ys = [c[1] for c in coords.values()]
    minx, miny = min(xs), min(ys)
    cols = max(xs) - minx + 1
    rows = max(ys) - miny + 1
    gap_x = gap if gap else (3 if inner_w >= 10 else 1)
    sx, sy = inner_w + 2 + gap_x, box_h + 1
    cv = Canvas(cols * sx - gap_x, rows * sy - 1)
    seen = {rid for rid in coords if rooms[rid].visited or rid == g.room}
    named = set(seen)
    for rid in seen:                       # 去過的房間，門上寫的鄰房名字也算知道
        named.update(t for t in rooms[rid].exits.values() if t in coords)
    for rid, (x, y) in coords.items():
        r = rooms[rid]
        gx, gy = x - minx, y - miny
        top, left = gy * sy, gx * sx
        cv.box(top, left, inner_w, label_fn(r, rid in seen, rid in named, rid == first_id))
        for d, tid in r.exits.items():
            if d == "東" and tid in coords:
                cv.put(top + 1, left + inner_w + 2, "-" * gap_x)
            elif d == "南" and tid in coords:
                cv.put(top + box_h, left + 1 + inner_w // 2, "|")
    return cv.render().split("\n")


def _floor_line(g, rooms, plans, cur_k, bracket=True):
    """樓層一覽：[2F] 是你在的那層，? 是整層都沒去過。"""
    parts = []
    for k in sorted(plans, reverse=True):
        lab = floor_label(k)
        if any(rooms[rid].visited or rid == g.room for rid in plans[k]):
            tag = ""
        else:
            tag = "?"
        parts.append(f"[{lab}{tag}]" if k == cur_k and bracket else f"{lab}{tag}")
    return "樓層：" + " ".join(parts)


# ---------------------------------------------------------------- 完整平面圖（M 鍵 / 單欄模式）
ROOM_W = 12


def floor_map(g):
    r0 = g.cur
    loc = r0.loc
    rooms, first_id, plans = _plan(g)
    if not plans:
        return f"{loc}：只有街道。"
    cur_k = 1 if r0.is_street() else room_floor(r0.tags)

    def label(r, known, named, is_door):
        name = r.name if named else "？" * max(2, len(r.name))
        marks = []
        if r.id == g.room:
            marks.append("@你")
        if is_door:
            marks.append("門")
        if "上" in r.exits:
            marks.append("^上")
        if "下" in r.exits:
            marks.append("v下")
        if r.locked:
            marks.append("鎖")
        if r.id == g.base.room:
            marks.append("#據點")
        if known:
            if r.enemies:
                marks.append(f"Z{len(r.enemies)}")
            if r.items:
                marks.append("$")
            if r.searched and not r.loot and not r.items:
                marks.append("空")
        if r.rumor:
            marks.append("聞")
        line2 = " ".join(marks)
        if _w(line2) > ROOM_W:
            line2 = line2[:ROOM_W // 2]
        return [name, line2]

    lines = [f"{loc}平面圖（@你 門=入口 ^上樓 v下樓 Z=喪屍 $=地上有東西 空=搜過了 ？=沒去過）"]
    for k in sorted(plans, reverse=True):
        mark = "  <- 你在這層" if k == cur_k else ""
        lines.append(f"-- {floor_label(k)} --{mark}")
        lines.extend(_draw_floor(g, rooms, plans[k], first_id, ROOM_W, 4, label))
    if r0.is_street():
        lines.append(f"你在街上（{r0.name}）。進建築：in")
    return "\n".join(lines)


# ---------------------------------------------------------------- 右側常駐小地圖
MINI_W = 8      # 框內寬：房名最多 3 個字 + 記號


def street_map(g):
    """站在街上時的右欄：十字形顯示四個方向通往哪一區，中間是本區和可以進的建築。"""
    r0 = g.cur
    loc = r0.loc
    spec = LOCATIONS[loc]
    base_loc = g.rooms[g.base.room].loc if g.base.room else None

    def tag(other):
        m = ""
        if other == base_loc:
            m += "#"
        if g.threat.get(other, 0) >= 6:
            m += "!"
        if other == "軍方檢查站" and g.flags.get("checkpoint_gone"):
            m += "x"
        if not any(r.visited for r in g.rooms.values() if r.loc == other):
            m += "?"
        return m

    NW, CW = 10, 10           # 鄰區框內寬、中間框內寬（地區名最多 5 個字）
    cx = NW + 2 + 2           # 中間框的左邊欄位
    cv = Canvas(cx + CW + 2 + 2 + NW + 2, 13)
    ex = spec["exits"]
    # 中間：本區 + 進建築
    first = r0.exits.get("進")
    mid = [_pad(loc[:5], CW)]
    mid.append(_pad(f"進:{g.rooms[first].name[:3]}" if first else "沒有建築", CW))
    cv.box(4, cx, CW, mid)
    if "北" in ex:
        o = ex["北"]
        cv.box(0, cx, CW, [_pad(o[:4], CW - len(tag(o))) + tag(o)])
        cv.put(3, cx + 1 + CW // 2, "|")
    if "南" in ex:
        o = ex["南"]
        cv.box(9, cx, CW, [_pad(o[:4], CW - len(tag(o))) + tag(o)])
        cv.put(8, cx + 1 + CW // 2, "|")
    if "西" in ex:
        o = ex["西"]
        cv.box(4, 0, NW, [_pad(o[:4], NW - len(tag(o))) + tag(o)])
        cv.put(5, NW + 2, "--")
    if "東" in ex:
        o = ex["東"]
        cv.box(4, cx + CW + 2 + 2, NW, [_pad(o[:4], NW - len(tag(o))) + tag(o)])
        cv.put(5, cx + CW + 2, "--")
    body = cv.render().split("\n")
    while body and not body[0].strip():      # 沒有北邊出口時，去掉上面的空行
        body.pop(0)
    lines = [f"{loc}·{r0.name}（街道）"] + body
    lines.append("跨區 20分；in 進建築 5分")
    lines.append("#據點 !高威脅 ?沒去過 x已撤離")
    return lines


def mini_floor(g, max_lines=None):
    """目前建築的壓縮平面圖，一行最多 45 格，給主畫面右欄用。所有樓層由上往下排，你在的那層標 [2F]；
    沒去過的房間畫「？？」。max_lines 是右欄最多幾行：放不下就先保留你這層和最近的樓層，其他樓層只列名字。回傳 list[str]。"""
    r0 = g.cur
    if r0.is_street():
        return street_map(g)
    loc = r0.loc
    rooms, first_id, plans = _plan(g)
    cur_k = 1 if r0.is_street() else room_floor(r0.tags)
    head = f"{loc}·{r0.name}" + ("" if r0.is_street() else f"（{floor_label(cur_k)}）")
    if not plans or cur_k not in plans:
        return [head, "（只有街道）"]
    legend = "@你 Z屍 $物 *鎖 #據 o門 ^上 v下 .空 !沒翻完"
    blocks = {k: _mini_block(g, rooms, plans[k], first_id, k, cur_k) for k in plans}
    budget = (max_lines - 2) if max_lines else None          # 扣掉抬頭和圖例
    chosen = [cur_k]
    used = len(blocks[cur_k])
    for k in sorted((k for k in plans if k != cur_k), key=lambda k: (abs(k - cur_k), -k)):
        need = len(blocks[k])
        if budget is None or used + need + (1 if len(chosen) + 1 < len(plans) else 0) <= budget:
            chosen.append(k)
            used += need
    lines = [head]
    for k in sorted(plans, reverse=True):
        if k in chosen:
            lines.extend(blocks[k])
    rest = [k for k in sorted(plans, reverse=True) if k not in chosen]
    if rest:
        lines.append("其他樓層：" + " ".join(
            floor_label(k) + ("" if any(rooms[rid].visited for rid in plans[k]) else "?") for k in rest))
    lines.append(legend)
    return lines


def _mini_block(g, rooms, coords, first_id, k, cur_k):
    """一層的小圖：第一行是樓層名（你在的那層加 [ ]），下面是框。"""
    xs = [c[0] for c in coords.values()]
    cols = max(xs) - min(xs) + 1
    longest = max(_w(rooms[rid].name) for rid in coords)
    mw = min(max(MINI_W, longest + 2), (46 // cols) - 3)   # 名字放得下就放寬，但整層不能超過 45 格

    def label(r, known, named, is_door):
        if not named and r.id != g.room:
            return [_pad("？？", mw)]
        marks = ""
        if r.id == g.room:
            marks += "@"
        if known and r.enemies:
            marks += "Z"
        if known and r.items:
            marks += "$"
        if r.locked:
            marks += "*"
        if r.id == g.base.room:
            marks += "#"
        if is_door:
            marks += "o"
        if known and r.searched and not r.is_street():
            if r.loot:
                marks += "!"                    # 翻過但還有沒翻到的
            elif not r.items:
                marks += "."                    # 翻乾淨而且地上也沒東西，才算清空
        if "上" in r.exits:
            marks += "^"
        if "下" in r.exits:
            marks += "v"
        marks = marks[:mw - 2]
        name = r.name[:max(1, (mw - len(marks)) // 2)] if named else "？？"   # 記號一定看得到，名字不夠就截
        return [_pad(name, mw - len(marks)) + marks]

    visited_any = any(rooms[rid].visited or rid == g.room for rid in coords)
    title = (f"[{floor_label(k)}] 你在這層" if k == cur_k else floor_label(k) + ("" if visited_any else " ?沒去過"))
    return [title] + _draw_floor(g, rooms, coords, first_id, mw, 3, label, gap=1)
