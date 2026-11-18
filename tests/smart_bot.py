# -*- coding: utf-8 -*-
"""有目的的測試機器人：像一個講道理的玩家那樣玩，跑很多種子，收集當機、軟鎖、矛盾訊息與平衡統計。
用法：python -X utf8 tests/smart_bot.py [局數] [每局最多指令數] [--verbose] [--seed N] [--transcript 路徑]
"""
import os
import sys
import json
import random
import traceback
from collections import Counter, deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from zg.world import build_world
from zg.engine import Engine
from zg.commands import handle
from zg.state import to_dict, from_dict, inv_count, inv_find
from zg.data import ITEMS, ENEMIES, LOCATIONS, TRAIT_JOIN, FACTIONS, RECIPES, CLUE_ENEMY

DIR_CMD = {"北": "n", "南": "s", "東": "e", "西": "w", "上": "u", "下": "d", "進": "in", "出": "out"}
TENT = "軍方檢查站·帳篷"
LAB = "醫院·實驗室"
ROOF = "辦公大樓·屋頂"
CHECKPOINT = "軍方檢查站·路障"
CHURCH = "教堂·前庭"
WORKSHOP = "加油站·維修間"
OFFICE = "辦公大樓·辦公室"
GARAGE = "住宅區·車庫"
ARMORY = "警局·軍械庫"
START_BASE = "住宅區·客廳"
PRY_TOOLS = ("消防斧", "鐵撬")
GUNS = ("手槍", "霰彈槍")
JUNK_ORDER = ["腐壞食物", "日記", "石頭", "鐵絲", "不明藥丸", "空瓶"]
FOOD_PREF = ["麵包", "罐頭", "泡麵", "餅乾", "巧克力"]
WATER_PREF = ["瓶裝水", "汽水"]


def weapon_score(name, ammo_ok=True):
    s = ITEMS[name]
    if s.get("ammo") and not ammo_ok:
        return -1
    return (s["dmg"][0] + s["dmg"][1]) / 2 * s["hit"] / 100


class SmartBot:
    def __init__(self, seed, max_steps=1500, verbose=False, transcript=None, noinfect=False, god=False):
        self.seed = seed
        self.noinfect = noinfect or god
        self.god = god
        self.stats = Counter()
        self.g = build_world(seed)
        self.eng = Engine(self.g)
        self.max_steps = max_steps
        self.verbose = verbose
        self.transcript = transcript
        self.step_no = 0
        self.errors = []        # (seed, step, cmd, traceback)
        self.anomalies = []     # (seed, step, cmd, text)
        self.softlocks = []
        self.talks = Counter()      # (name, day) -> talks today
        self.talks_total = Counter()
        self.open_tries = Counter()  # room id -> shoulder attempts
        self.gave = Counter()
        self.recruited = set()
        self.last_sig = None
        self.repeat = 0
        self.stall = 0
        self.max_day = 1
        self.forced_waits = 0
        self.checked = set()
        self.target = None
        self._allow_hostile = False
        self.bitten = False
        self.combat_turns = 0
        self.looked = set()
        self.dropped_here = {}
        self.suspicious = set()
        self.ambushed = set()
        self.last_cmds = deque(maxlen=12)
        self.recent = deque(maxlen=10)

    # ------------------------------------------------------------ helpers
    @property
    def p(self):
        return self.g.player

    @property
    def r(self):
        return self.g.cur

    def count(self, name):
        return inv_count(self.p.inv, name)

    def has(self, name):
        return self.count(name) > 0

    def free_slots(self):
        return self.p.slots - len(self.p.inv)

    def flashlight(self):
        return self.has("手電筒")

    def gun_ready(self):
        for gname in GUNS:
            if self.has(gname) and self.count(ITEMS[gname]["ammo"]) > 0:
                return gname
        return None

    def best_melee(self):
        best, bs = None, -1
        for it in self.p.inv:
            s = ITEMS[it.name]
            if s["kind"] != "weapon" or s.get("ammo"):
                continue
            sc = weapon_score(it.name)
            if sc > bs:
                best, bs = it.name, sc
        return best

    def weapon_spec(self):
        if not self.p.weapon:
            return None
        if not inv_find(self.p.inv, self.p.weapon):
            return None
        return ITEMS[self.p.weapon]

    def best_food(self, allow_bad=False):
        for name in FOOD_PREF:
            if self.has(name):
                return name
        if allow_bad and self.has("腐壞食物"):
            return "腐壞食物"
        return None

    def best_water(self):
        for name in WATER_PREF:
            if self.has(name):
                return name
        return None

    def hostile_room(self, t):
        f = LOCATIONS[t.loc].get("faction")
        if f and "faction" in t.tags and self.g.factions.get(f, 50) < 20 and not (f == "軍方" and self.g.flags.get("checkpoint_gone")):
            return True
        return False

    def passable(self, t, final=False):
        if t.id == TENT:
            return False
        if t.locked and not final:
            return False
        if self.hostile_room(t) and not self._allow_hostile:
            return False
        return True

    def with_hostile_fallback(self, fn, *a, **k):
        """找不到路時，最後手段允許穿過敵對勢力的房間（總比困死好）。"""
        res = fn(*a, **k)
        if res is None and not self._allow_hostile:
            self._allow_hostile = True
            try:
                res = fn(*a, **k)
            finally:
                self._allow_hostile = False
        return res

    def path_to(self, target_id, avoid_enemies=True):
        return self.with_hostile_fallback(self._path_to, target_id, avoid_enemies)

    def _path_to(self, target_id, avoid_enemies=True):
        """BFS，回傳方向列表（中文）。"""
        g = self.g
        start = g.room
        if start == target_id:
            return []
        prev = {start: None}
        q = deque([start])
        while q:
            cur = q.popleft()
            for d, tid in g.rooms[cur].exits.items():
                if tid in prev:
                    continue
                t = g.rooms[tid]
                if not self.passable(t, final=(tid == target_id)):
                    continue
                if avoid_enemies and t.enemies and tid != target_id:
                    continue
                prev[tid] = (cur, d)
                if tid == target_id:
                    path = []
                    x = tid
                    while prev[x] is not None:
                        pc, pd = prev[x]
                        path.append(pd)
                        x = pc
                    return list(reversed(path))
                q.append(tid)
        if avoid_enemies:
            return self._path_to(target_id, avoid_enemies=False)
        return None

    def safe_path(self, target_id):
        return self.with_hostile_fallback(self._safe_path, target_id)

    def _safe_path(self, target_id):
        """只走沒有敵人的房間；找不到回 None。"""
        g = self.g
        start = g.room
        if start == target_id:
            return []
        prev = {start: None}
        q = deque([start])
        while q:
            cur = q.popleft()
            for d, tid in g.rooms[cur].exits.items():
                if tid in prev:
                    continue
                t = g.rooms[tid]
                if not self.passable(t, final=(tid == target_id)) or t.enemies:
                    continue
                prev[tid] = (cur, d)
                if tid == target_id:
                    path = []
                    x = tid
                    while prev[x] is not None:
                        pc, pd = prev[x]
                        path.append(pd)
                        x = pc
                    return list(reversed(path))
                q.append(tid)
        return None

    def nearest(self, pred, avoid_enemies=True):
        """BFS 找最近符合 pred 的房間，回傳 (room, path)。"""
        g = self.g
        start = g.room
        prev = {start: None}
        q = deque([start])
        while q:
            cur = q.popleft()
            r = g.rooms[cur]
            if cur != start and pred(r):
                path = []
                x = cur
                while prev[x] is not None:
                    pc, pd = prev[x]
                    path.append(pd)
                    x = pc
                return r, list(reversed(path))
            for d, tid in r.exits.items():
                if tid in prev:
                    continue
                t = g.rooms[tid]
                if not self.passable(t, final=pred(t)):
                    continue
                if avoid_enemies and t.enemies and not pred(t):
                    continue
                prev[tid] = (cur, d)
                q.append(tid)
        return None, None

    def move_along(self, path):
        if not path:
            return None
        d = path[0]
        t = self.g.rooms[self.r.exits[d]]
        if t.locked:
            return f"open {DIR_CMD[d]}"
        return DIR_CMD[d]

    def threat(self, loc=None):
        return self.g.threat.get(loc or self.r.loc, 0)

    def is_dark_here(self):
        return ("dark" in self.r.tags or self.g.is_night()) and not self.flashlight()

    # ------------------------------------------------------------ decisions
    def decide(self):
        g, p, r = self.g, self.p, self.r
        if g.flags.get("pending"):
            kind = g.flags["pending"]
            if kind == "help":
                return "yes" if self.strong() and not g.is_night() and (self.gun_ready() or len(g.companions()) >= 1) else "no"
            return "no"   # 半夜敲門：四成是喪屍，謹慎的人不開門
        if g.combat:
            return self.combat_cmd()
        if r.enemies:
            # 房裡有東西但沒進入戰鬥（例如轉化的隊友）
            if p.hp >= 50 and p.stamina >= 30:
                return "attack"
            d = self.flee_dir()
            if d:
                return d
            return "attack"
        c = self.survival_cmd()
        if c:
            return c
        c = self.base_cmd()
        if c:
            return c
        c = self.goal_cmd()
        if c:
            return c
        c = self.item_cmd()
        if c:
            return c
        c = self.npc_cmd()
        if c:
            return c
        if not r.is_street() and self.should_search(r, here=True):
            if r.id not in self.looked:
                return "look"
            return "search"
        if "water" in r.tags and self.has("空瓶") and g.day < 3 and r.loc not in ("公園", "加油站") and self.count("瓶裝水") < 4:
            return "refill"
        c = self.explore_cmd()
        if c:
            return c
        if g.base.room == g.room and not r.enemies and (p.hp < 100 or p.fatigue > 30):
            return "sleep 2"
        return "wait 1"

    # ---- combat
    def combat_cmd(self):
        g, p, r = self.g, self.p, self.r
        en = r.enemies
        if not en:
            return "look"   # 異常：戰鬥中沒敵人
        adj = [e for e in en if e.dist == 1]
        humans = [e for e in en if ENEMIES[e.kind].get("human")]
        if p.grabbed:
            return "push"
        defending = bool(g.flags.get("signal_at")) and g.room == ROOF
        gun = self.gun_ready()
        weak = p.hp < 50 or p.stamina < 20 or p.bleeding
        # 用藥現在會讓敵人動一次，只在必要時用
        if p.hp < 40 and self.has("急救包"):
            return "use 急救包"
        if p.bleeding and self.has("繃帶") and p.hp < 60 and not adj:
            return "use 繃帶"
        # 逃：虛弱、敵人太多、對方有槍而我沒有、牠們還在遠處而我狀況不好
        if not defending:
            run = (p.hp < 35 or len(en) >= 3 or (humans and not gun)
                   or (weak and not adj)
                   or (not adj and len(en) >= 2 and not gun and not self.has("燃燒瓶") and not self.strong()))
            if run:
                d = self.flee_dir()
                if d:
                    return f"flee {d}"
        if self.has("燃燒瓶") and not adj and len([e for e in en if e.dist >= 2]) >= 2:
            return "throw 燃燒瓶"
        if gun and (humans or len(en) >= 2 or p.hp < 50) and p.weapon != gun:
            return f"equip {gun}"
        if not gun and p.weapon in GUNS:
            bm = self.best_melee()
            if bm:
                return f"equip {bm}"
        wi = self.weapon_spec()
        rng_ = wi["range"] if wi else 1
        stam = wi["stam"] if wi else 6
        in_range = [e for e in en if e.dist <= rng_]
        if not in_range:
            # 絕不對搆不到的敵人揮刀：丟石頭引開或 aim 等牠來
            if self.has("石頭") and len(en) >= 2 and not p.aimed:
                return "throw 石頭"
            return "aim"
        if p.stamina < stam:
            # 沒體力：attack 現在是護頭休息回合（+10）；虛弱就逃
            if weak and not defending and adj:
                d = self.flee_dir()
                if d:
                    return f"flee {d}"
            return "attack"
        # 先 aim 再爆頭（沒 aim 的爆頭額外 -20）
        if not adj and not self.gun_ready():
            return "aim"          # 搆不到又沒子彈：瞄準等牠過來（瞄滿也會過回合）
        if p.aimed:
            return "attack head"
        return "aim"

    def flee_dir(self):
        g, r = self.g, self.r
        best, bs = None, -10 ** 9
        for d, tid in r.exits.items():
            t = g.rooms[tid]
            if t.locked or tid == TENT or self.hostile_room(t):
                continue
            s = 0
            if not t.enemies:
                s += 10
            else:
                s -= 5 * len(t.enemies)
            if t.visited:
                s += 2
            if t.id == g.base.room:
                s += 3
            if "dark" in t.tags and not self.flashlight():
                s -= 2
            if t.is_street():
                s += 1
            if s > bs:
                best, bs = d, s
        return DIR_CMD[best] if best else None

    # ---- survival
    def survival_cmd(self):
        g, p = self.g, self.p
        if p.bleeding:
            if self.has("繃帶"):
                return "use 繃帶"
            if self.has("急救包"):
                return "use 急救包"
            if self.count("布料") >= 2:
                return "craft 繃帶"
            if p.hp > 12 and (self.free_slots() >= 1 or self.has("布料")):
                return "craft 布料"
        if p.hp < 40 and self.has("急救包"):
            return "use 急救包"
        if p.hp < 60 and self.count("繃帶") >= 3:
            return "use 繃帶"
        # 發冷 / 傷口發黑 / 剛被咬 → 抗生素
        if (p.infection > 30 or self.bitten) and p.antibiotic == 0 and self.has("抗生素"):
            self.bitten = False
            return "use 抗生素"
        food_n = sum(self.count(n) for n in FOOD_PREF)
        water_n = sum(self.count(n) for n in WATER_PREF)
        if p.hunger > (50 if food_n >= 2 else 65):
            f = self.best_food(allow_bad=p.hunger > 90)
            if f:
                return f"use {f}"
        if p.thirst > (50 if water_n >= 2 else 65):
            w = self.best_water()
            if w:
                return f"use {w}"
            if self.has("髒水"):
                if self.has("打火機") and p.thirst < 90:
                    return "craft 淨水"
                if p.thirst > 80:
                    return "use 髒水"
        if self.has("背包"):
            return "use 背包"
        # 找水：第 3 天前有水龍頭的房間可以裝乾淨水
        if p.thirst > 50 and not self.best_water() and self.has("空瓶") and g.day < 3 and not g.combat:
            r = self.r
            if "water" in r.tags and r.loc not in ("公園", "加油站"):
                return "refill"
            rr, path = self.nearest(lambda x: "water" in x.tags and x.loc not in ("公園", "加油站") and not x.enemies)
            if path and len(path) <= 6:
                return self.move_along(path)
        # 武器
        bm = self.best_melee()
        if bm and p.weapon != bm and not g.combat:
            return f"equip {bm}"
        if not p.weapon or not inv_find(p.inv, p.weapon):
            if bm:
                return f"equip {bm}"
        # 製作
        cur_score = weapon_score(bm) if bm else 0
        if self.count("木板") >= 1 and self.count("釘子") >= 2 and cur_score < weapon_score("釘棒") and (self.count("木板") >= 3 or g.base.fort >= 2 or not g.base.room) and (self.free_slots() >= 1 or self.count("木板") == 1):
            return "craft 釘棒"
        room = self.free_slots() >= 1
        if self.count("燃燒瓶") < 2 and self.has("空瓶") and self.has("布料") and (self.has("酒精") or self.has("汽油")) and (room or self.has("燃燒瓶")):
            return "craft 燃燒瓶"
        if self.count("布料") >= 2 and self.count("繃帶") < 2 and (room or self.has("繃帶") or self.count("布料") == 2):
            return "craft 繃帶"
        if self.has("髒水") and self.has("打火機") and self.count("瓶裝水") < 3 and (room or self.has("瓶裝水") or self.count("髒水") == 1):
            return "craft 淨水"
        if p.fatigue >= 92 and not self.r.enemies:
            return "sleep 2"
        return None

    # ---- base / night
    def base_cmd(self):
        g, p, r = self.g, self.p, self.r
        hour = g.hour
        at_base = g.base.room == g.room
        night = hour >= 19 or hour < 6
        # 第 14 天撤離：屋頂當據點，交給 goal_cmd
        if self.evac_phase():
            return None
        if not g.base.room:
            if r.base_ok and not r.enemies:
                return "search" if r.hidden else "claim"
            if self.r.base_ok and self.r.hidden and not self.r.enemies:
                return "search"      # claim 會說「先搜過再說」
            rr, path = self.nearest(lambda x: x.base_ok and not x.locked)
            if path:
                return self.move_along(path)
            return None
        # 白天血低：回據點睡覺回血（據點每小時 +3）
        heal_rest = (p.hp < 55 and not p.bleeding and p.hunger < 70 and p.thirst < 70
                     and not (self.has("急救包") and p.hp < 40))
        if not (night or p.fatigue > 78 or heal_rest):
            return None
        if at_base:
            if g.base.fort < 5 and self.count("木板") >= 2 and self.count("釘子") >= 1:
                return "fortify"
            for n in g.companions():
                if n.order != "guard":
                    return f"order {n.name} guard"
            if not night:
                return "sleep 3"
            hours = (6 - hour) % 24
            return f"sleep {max(1, min(hours, 10))}"
        if heal_rest and not night and p.fatigue <= 78:
            path = self.safe_path(g.base.room)
            if path is not None and len(path) <= 6:
                return self.move_along(path)
            return None
        base_room = g.rooms[g.base.room]
        if base_room.enemies and self.weak():
            # 據點被占了而且打不過：找另一個能當據點的房間
            rr, path2 = self.nearest(lambda x: x.base_ok and not x.locked and not x.enemies)
            if path2 is not None and len(path2) <= 4:
                return self.move_along(path2)
            if r.base_ok and not r.enemies:
                return "search" if r.hidden else "claim"
            if not r.enemies and not r.is_street():
                return "sleep 3"
            return None
        path = self.safe_path(g.base.room) if self.weak() else self.path_to(g.base.room)
        if path is not None and len(path) <= 10:
            return self.move_along(path)
        if p.fatigue > 80 and not r.enemies and not r.is_street():
            return "sleep 3"
        if path:
            return self.move_along(path)
        return None

    def evac_phase(self):
        g = self.g
        if g.goal == "疫苗" and self.has("疫苗樣本") and not g.flags.get("checkpoint_gone"):
            return False
        if g.goal == "撤離" or (g.goal == "疫苗" and g.flags.get("checkpoint_gone")):
            if self.has("收音機") and self.has("訊號彈"):
                return g.day >= 14 or (g.day == 13 and g.hour >= 15)
        return False

    # ---- goal
    def goal_cmd(self):
        g, p, r = self.g, self.p, self.r
        if g.goal == "撤離" and not self.evac_phase():
            c = self.evac_prep_cmd()
            if c:
                return c
        if g.goal == "疫苗" and not g.flags.get("checkpoint_gone"):
            if self.has("疫苗樣本"):
                if g.day < 5:
                    return None   # 軍官第 5 天才收
                if g.room == CHECKPOINT:
                    return "deliver"
                path = self.safe_path(CHECKPOINT) if self.weak() else self.path_to(CHECKPOINT)
                if path:
                    return self.move_along(path)
            elif g.day <= 10:
                lab = g.rooms[LAB]
                can_force = self.has("消防斧") or self.has("鐵撬") or (self.threat("醫院") < 6 and p.hp > 50 and self.open_tries[LAB] < 4)
                if g.room == LAB:
                    if (lab.loot or lab.searched == 0) and not self.weak():
                        if self.threat() < 8:
                            return "search"
                    elif any(it.name == "疫苗樣本" for it in lab.items):
                        return "take 疫苗樣本"
                elif (not lab.locked or can_force) and self.threat("醫院") < 7 and not self.weak():
                    path = self.path_to(LAB)
                    if path:
                        d = path[0]
                        t = g.rooms[r.exits[d]]
                        if t.enemies and (len(t.enemies) >= 3 or (len(t.enemies) == 2 and not self.strong())):
                            path = None
                    if path:
                        if t.locked:
                            if t.id == LAB:
                                if not (self.has("消防斧") or self.has("鐵撬")):
                                    self.open_tries[LAB] += 1
                                return f"open {DIR_CMD[d]}"
                            return None
                        return DIR_CMD[d]
        if self.evac_phase():
            if g.room != ROOF:
                path = self.path_to(ROOF)
                if path:
                    return self.move_along(path)
                return None
            if g.base.room != ROOF:
                return "claim"
            if g.day >= 14 and 6 <= g.hour < 12 and not g.flags.get("signal_at"):
                return "signal"
            if g.flags.get("signal_at"):
                return "wait 1"
            if g.day < 14 or g.hour < 6:
                hours = (6 - g.hour) % 24
                return f"sleep {max(1, min(8, hours))}"
            return "wait 1"
        if g.goal == "護送":
            comps = g.companions()
            if comps:
                # 感染已知的隊友先放生（教堂不收）
                for n in comps:
                    if n.revealed and n.infected and r.loc != "教堂":
                        return f"leave {n.name}"
                if r.loc == "教堂":
                    return f"leave {comps[0].name}"
                strangers_left = [n for n in g.npcs if n.status == "stranger"]
                need_more = len(comps) < 3 and strangers_left and g.day < 12
                if not need_more or (len(comps) >= 2 and g.day >= 6):
                    path = self.path_to(CHURCH)
                    if path:
                        return self.move_along(path)
        return None

    def evac_prep_cmd(self):
        """撤離：鐵撬/消防斧 → 撬開加油站維修間拿訊號彈；辦公大樓辦公室拿收音機。"""
        g, p, r = self.g, self.p, self.r
        if self.weak() or g.is_night() or g.hour >= 19:
            return None
        tools = self.has("消防斧") or self.has("鐵撬")
        targets = []
        if not self.has("訊號彈"):
            ws = g.rooms[WORKSHOP]
            if ws.loot or ws.searched == 0 or any(it.name == "訊號彈" for it in ws.items):
                if not ws.locked or tools:
                    targets.append(ws)
                elif self.open_tries[WORKSHOP] < 3 and p.hp > 60 and self.threat("加油站") < 5:
                    targets.append(ws)   # 用肩膀試幾次
            if not tools:
                garage = g.rooms[GARAGE]   # 車庫保底有消防斧
                if garage.locked and self.open_tries[GARAGE] < 4 and p.hp > 60 and self.threat("住宅區") < 5:
                    targets.append(garage)
                elif not garage.locked and (garage.loot or garage.searched == 0):
                    targets.append(garage)
        if not self.has("收音機"):
            off = g.rooms[OFFICE]
            if off.loot or off.searched == 0 or any(it.name == "收音機" for it in off.items):
                targets.append(off)
        for t in targets:
            if g.room == t.id:
                wanted = [it.name for it in r.items if it.name in ("訊號彈", "收音機", "消防斧", "鐵撬")]
                if wanted:
                    if self.free_slots() <= 0:
                        for name in JUNK_ORDER + ["木板", "釘子", "空瓶", "汽油", "鐵絲"]:
                            if self.has(name):
                                return f"drop {name}"
                        return None
                    return "take " + wanted[0]
                if self.threat() < 7 and self.should_search(r, here=True):
                    if r.id not in self.looked:
                        return "look"
                    return "search"
                continue
            if self.threat(t.loc) >= 7:
                continue
            path = self.path_to(t.id)
            if not path:
                continue
            d = path[0]
            nxt = g.rooms[r.exits[d]]
            if nxt.enemies and (len(nxt.enemies) >= 3 or self.weak() or (len(nxt.enemies) == 2 and not self.strong())):
                continue
            if nxt.locked:
                if nxt.id == t.id:
                    if not tools:
                        self.open_tries[t.id] += 1
                    return f"open {DIR_CMD[d]}"
                continue
            return DIR_CMD[d]
        return None

    # ---- items
    def item_cmd(self):
        g, p, r = self.g, self.p, self.r
        def worthy(it):
            kind = ITEMS[it.name]["kind"]
            if it.name in ("腐壞食物", "石頭", "日記", "鐵絲", "不明藥丸"):
                return it.name == "日記" and not self.has("日記") and self.free_slots() >= 3
            if it.name == "空瓶":
                return self.count("空瓶") < 2 and (g.day < 3 or self.has("打火機")) and self.free_slots() >= 3
            if kind == "weapon" and it.name not in GUNS:
                bm = self.best_melee()
                return not bm or weapon_score(it.name) > weapon_score(bm)
            if kind == "material" and self.free_slots() < 3:
                return False
            if it.name in self.dropped_here.get(g.room, set()):
                return False
            return True
        worth = [it for it in r.items if worthy(it)] if r.items else []
        if worth and self.free_slots() > 0:
            return f"take {worth[0].name}"
        if self.free_slots() <= 0:
            for name in JUNK_ORDER:
                if self.has(name) and not (name == "空瓶" and self.count("空瓶") <= 2 and g.day < 3):
                    return f"drop {name}"
            # 多餘武器
            bm = self.best_melee()
            for it in p.inv:
                s = ITEMS[it.name]
                if s["kind"] == "weapon" and it.name != bm and it.name not in GUNS and it.name != p.weapon:
                    if g.base.room == g.room:
                        return f"store {it.name}"
                    return f"drop {it.name}"
            if self.count("布料") >= 2 and (self.free_slots() >= 1 or self.count("布料") == 2 or self.has("繃帶")):
                return "craft 繃帶"
            if self.free_slots() < 1:
                junk = next((it for it in p.inv if it.name in ("空瓶", "石頭", "髒水", "布料", "鐵絲")), None)
                if junk:
                    return f"drop {junk.name}"
            # 吃掉一些
            f = self.best_food()
            if f and p.hunger > 30:
                return f"use {f}"
            w = self.best_water()
            if w and p.thirst > 30:
                return f"use {w}"
            if worth:
                return None
        # 隊友檢查
        if g.base.room == g.room and p.hp >= 60:
            bm = self.best_melee()
            for it in p.inv:
                s = ITEMS[it.name]
                if s["kind"] == "weapon" and it.name != bm and it.name not in GUNS and it.name != p.weapon:
                    return f"store {it.name}"
        return None

    # ---- npcs
    def npc_cmd(self):
        g, p, r = self.g, self.p, self.r
        comps = g.companions()
        # 檢查隊友是否感染
        can_check = self.has("急救包") or any(c.skill == "醫療" for c in comps)
        if can_check:
            for n in comps:
                if n.name not in self.checked and not n.revealed:
                    self.checked.add(n.name)
                    return f"check {n.name}"
        for n in comps:
            if n.revealed and n.infected and g.goal != "護送":
                return f"leave {n.name}"
        if g.is_night() or p.thirst > 75 or p.hunger > 80:
            return None
        cap = 3 if g.goal == "護送" else 2
        for n in g.npcs_here():
            if n.status != "stranger":
                continue
            if g.goal != "護送" and n.trait == "貪婪" and n.intro_seen:
                continue
            if not n.intro_seen:
                return f"look {n.name}"
            if len(comps) >= cap:
                continue
            if n.trust >= TRAIT_JOIN[n.trait]:
                self.recruited.add(n.name)
                return f"ask {n.name} join"
            gift = self.gift_for(n)
            if gift and self.gave[n.name] < 2:
                self.gave[n.name] += 1
                return f"give {n.name} {gift}"
            key = (n.name, g.day)
            limit_day = 3 if g.goal == "護送" else 2
            limit_total = 12 if g.goal == "護送" else 6
            if self.talks[key] < limit_day and self.talks_total[n.name] < limit_total and g.hour < 18:
                self.talks[key] += 1
                self.talks_total[n.name] += 1
                return f"talk {n.name}"
        # 勢力交易
        f = None
        for fname, spec in FACTIONS.items():
            if spec["loc"] == r.loc and spec["room"] == r.name:
                f = fname
        if f == "教堂" and g.factions[f] >= 20 and self.count("繃帶") < 2 and self.count("罐頭") >= 3:
            return "trade 修女 罐頭 繃帶"
        return None

    def gift_for(self, n):
        need = n.need
        if need == "食物" and self.count("餅乾") >= 3:
            return "餅乾"
        if need == "食物" and self.count("罐頭") >= 3:
            return "罐頭"
        if need == "水" and self.count("瓶裝水") >= 3:
            return "瓶裝水"
        if need == "藥" and self.count("繃帶") >= 3:
            return "繃帶"
        if need in ("武器", "安全"):
            bm = self.best_melee()
            for it in self.p.inv:
                s = ITEMS[it.name]
                if s["kind"] == "weapon" and it.name != bm and it.name not in GUNS and it.name != self.p.weapon:
                    return it.name
            if need == "安全" and self.count("木板") >= 4:
                return "木板"
        return None

    # ---- search / explore
    def should_search(self, r, here=False):
        p = self.p
        if r.is_street():
            return False
        if self.threat(r.loc) >= 7:
            return False
        if here and p.bleeding:
            return False
        if p.hp < 35:
            return False
        if r.id in self.suspicious and (p.hp < 80 or p.stamina < 60):
            return False
        if r.id in self.ambushed and p.hp < 70:
            return False
        if r.searched == 0:
            return True
        if r.loot and r.searched < 8:
            return True
        return False

    def weak(self):
        p = self.p
        return p.hp < 70 or p.stamina < 50 or p.bleeding

    def strong(self):
        p = self.p
        return p.hp >= 80 and p.stamina >= 60 and not p.bleeding

    def want_room(self, x):
        p = self.p
        tools = self.has("消防斧") or self.has("鐵撬")
        if x.is_street():
            return False
        if self.threat(x.loc) >= 7:
            return False
        if x.enemies and (self.weak() or len(x.enemies) >= 3 or (len(x.enemies) == 2 and not self.strong())):
            return False
        if x.id == ARMORY and self.g.factions.get("警局", 50) >= 20:
            return False   # 撬軍械庫會讓警局翻臉
        if x.locked:
            if tools:
                return True
            return x.loot_level >= 3 and self.open_tries[x.id] < 1 and p.hp > 60
        return self.should_search(x)

    def stranger_room(self, x):
        g = self.g
        if x.locked or self.threat(x.loc) >= 7:
            return False
        if x.enemies and self.weak():
            return False
        for n in g.npcs:
            if n.status == "stranger" and n.loc == x.loc and n.room == x.name:
                if g.goal != "護送" and n.trait == "貪婪" and n.intro_seen:
                    continue
                if self.talks_total[n.name] >= (12 if g.goal == "護送" else 6):
                    continue
                if self.talks[(n.name, g.day)] >= (3 if g.goal == "護送" else 2):
                    continue
                if len(g.companions()) >= (3 if g.goal == "護送" else 2):
                    continue
                return True
        return False

    def explore_cmd(self):
        g, p, r = self.g, self.p, self.r
        if self.threat() >= 8 and g.base.room and g.base.room != g.room:
            path = self.path_to(g.base.room)
            if path:
                return self.move_along(path)
        tools = self.has("消防斧") or self.has("鐵撬")
        # 目標持續到達成或失效
        if self.target:
            t = g.rooms[self.target]
            if t.id == g.room or not (self.want_room(t) or self.stranger_room(t)):
                self.target = None
        if not self.target:
            for avoid in ((True,) if self.weak() else (True, False)):
                tgt, path = self.nearest(self.want_room, avoid_enemies=avoid)
                if g.goal == "護送" and g.day < 12:
                    t2, p2 = self.nearest(self.stranger_room, avoid_enemies=avoid)
                    if p2 and (path is None or len(p2) <= len(path) + 2):
                        tgt, path = t2, p2
                elif tgt is None and g.day < 12:
                    tgt, path = self.nearest(self.stranger_room, avoid_enemies=avoid)
                if tgt:
                    self.target = tgt.id
                    break
        if self.target:
            path = self.path_to(self.target, avoid_enemies=True) if not self.weak() else self.safe_path(self.target)
            if path:
                d = path[0]
                t = g.rooms[r.exits[d]]
                if t.enemies and self.weak():
                    self.target = None
                    return None
                if t.locked:
                    if not tools:
                        self.open_tries[t.id] += 1
                    return f"open {DIR_CMD[d]}"
                return DIR_CMD[d]
            self.target = None
        # 沒事做：回據點
        if g.base.room and g.base.room != g.room:
            path = self.path_to(g.base.room)
            if path:
                return self.move_along(path)
        return None

    # ------------------------------------------------------------ run
    def signature(self):
        g, p = self.g, self.p
        return (g.day, g.minute, g.room, g.combat, len(p.inv), p.hp, p.stamina, tuple(e.dist for e in g.cur.enemies),
                tuple((it.name, it.qty) for it in p.inv), g.base.room, g.base.fort, g.flags.get("pending"))

    def observe(self, cmd, out):
        """指令執行後的記憶更新（看到的線索、被伏擊的房間）。"""
        g = self.g
        self.last_cmds.append(cmd)
        text = "\n".join(out)
        if cmd == "look":
            self.looked.add(g.room)
            if any(c in text for c in CLUE_ENEMY):
                self.suspicious.add(g.room)
        if cmd.startswith("drop "):
            self.dropped_here.setdefault(g.room, set()).add(cmd[5:])
        if "從你沒注意的地方撲出來" in text:
            self.ambushed.add(g.room)
            self.stats["ambush"] += 1
        nb = text.count("咬進你的肉裡") + text.count("牠咬到你了")
        self.stats["bites"] += nb
        if nb:
            self.bitten = True
        if g.combat:
            self.combat_turns += 1
        else:
            self.combat_turns = 0
        self.stats["fights"] += text.count("戰鬥開始")
        self.stats["spawns"] += text.count("牠們找到你了")
        self.stats["night_attacks"] += text.count("木板被撞得咚咚響") + text.count("你是被一股臭味醒的") + text.count("有東西來了，還在外面")
        self.stats["fled"] += text.count("衝出去")
        if self.noinfect:
            self.p.infection = 0
            for n in g.npcs:
                n.infected = False
        if self.god and not g.over:
            self.p.hp = 100
            self.p.bleeding = False

    def check_anomalies(self, cmd, out):
        g, p, r = self.g, self.p, self.r
        text = "\n".join(out)
        A = []
        if g.combat and not r.enemies:
            A.append("combat flag set but no enemies in room")
        if not g.combat and any(e.dist == 1 for e in r.enemies) and not g.over:
            A.append(f"enemy at distance 1 but no combat ({[e.label() for e in r.enemies]})")
        if p.weapon and not inv_find(p.inv, p.weapon):
            A.append(f"player.weapon={p.weapon} not in inventory")
        if "你醒了" in text and g.combat:
            A.append("slept through combat: '你醒了' printed while g.combat is True")
        if any(line.strip() == "安靜了。" for line in out) and r.enemies:
            A.append("'安靜了' printed but enemies remain")
        if p.hp > 100:
            A.append(f"hp > 100: {p.hp}")
        if p.stamina > p.max_stamina():
            A.append(f"stamina {p.stamina} > max {p.max_stamina()}")
        if len(p.inv) > p.slots:
            A.append(f"inventory {len(p.inv)} > slots {p.slots}")
        for it in p.inv:
            if it.qty <= 0:
                A.append(f"item {it.name} qty {it.qty}")
        for e in r.enemies:
            if e.hp <= 0:
                A.append(f"enemy {e.label()} with hp {e.hp} still in room")
        if g.minute >= 1440 or g.minute < 0:
            A.append(f"minute out of range {g.minute}")
        if "沒打中" in text and "命中率" in text and not r.enemies and not g.over:
            pass
        for a in A:
            self.anomalies.append((self.seed, self.step_no, cmd, a, text[:300]))

    def run(self):
        g = self.g
        tr = open(self.transcript, "w", encoding="utf-8") if self.transcript else None
        try:
            while self.step_no < self.max_steps and not g.over:
                try:
                    cmd = self.decide()
                except Exception:
                    self.errors.append((self.seed, self.step_no, "<bot.decide>", traceback.format_exc()))
                    break
                # 停滯偵測：同一狀態同一指令重複
                sig = (self.signature(), cmd)
                if sig == self.last_sig and not g.combat:
                    self.repeat += 1
                else:
                    self.repeat = 0
                self.last_sig = sig
                # 戰鬥回合本來就不推進時鐘；只有連續非常多回合還打不完才算異常
                if self.combat_turns >= 150:
                    self.softlocks.append((self.seed, self.step_no, cmd, f"combat lasted {self.combat_turns} commands: room={g.room} hp={self.p.hp} stam={self.p.stamina} enemies={[(e.label(), e.dist, e.hp) for e in g.cur.enemies]}"))
                    self.combat_turns = 0
                self.recent.append((cmd, g.day, g.minute))
                if (not g.combat and len(self.recent) == self.recent.maxlen and len({(d, m) for _, d, m in self.recent}) == 1
                        and len({c for c, _, _ in self.recent}) <= 2 and self.repeat < 6):
                    self.softlocks.append((self.seed, self.step_no, cmd, f"bot ping-pong without time passing: {[c for c, _, _ in self.recent]} room={g.room}"))
                    self.recent.clear()
                    self.target = None
                    cmd = "wait 1" if not g.combat else "aim"
                    self.forced_waits += 1
                if self.repeat >= 6 and not g.combat:
                    self.softlocks.append((self.seed, self.step_no, cmd, f"same state+command repeated {self.repeat} times; room={g.room} combat={g.combat} pending={g.flags.get('pending')} hp={self.p.hp} stam={self.p.stamina} enemies={[(e.label(), e.dist, e.hp) for e in g.cur.enemies]}"))
                    cmd = "wait 1"
                    self.forced_waits += 1
                    self.repeat = 0
                    if self.forced_waits > 20:
                        self.softlocks.append((self.seed, self.step_no, cmd, "gave up: too many forced waits"))
                        break
                self.step_no += 1
                self.eng.new_turn()
                before_sig = self.signature()
                try:
                    handle(self.eng, cmd)
                    self.eng.check_death()
                except Exception:
                    self.errors.append((self.seed, self.step_no, cmd, traceback.format_exc()))
                    break
                out = list(self.eng.out)
                self.observe(cmd, out)
                self.max_day = max(self.max_day, g.day)
                if tr:
                    tr.write(f"[{self.step_no}] d{g.day} {g.clock()} {g.room} hp{self.p.hp} > {cmd}\n")
                    for line in out:
                        tr.write("    " + line + "\n")
                if self.verbose:
                    print(f"[{self.step_no}] d{g.day} {g.clock()} {g.room} hp{self.p.hp} > {cmd}")
                    for line in out:
                        print("    " + line)
                try:
                    self.check_anomalies(cmd, out)
                except Exception:
                    self.errors.append((self.seed, self.step_no, cmd, "anomaly check: " + traceback.format_exc()))
                # 無進展偵測
                if self.signature() == before_sig and not g.combat:
                    self.stall += 1
                else:
                    self.stall = 0
                if self.stall >= 25:
                    self.softlocks.append((self.seed, self.step_no, cmd, f"no state change for 25 commands: last={list(self.last_cmds)} room={g.room} combat={g.combat}"))
                    break
                # 存檔往返
                if self.step_no % 50 == 0:
                    try:
                        d = json.loads(json.dumps(to_dict(g), ensure_ascii=False))
                        g2 = from_dict(d)
                        assert to_dict(g2) == to_dict(g), "save roundtrip mismatch"
                        self.g = g = g2
                        self.eng = Engine(g)
                    except Exception:
                        self.errors.append((self.seed, self.step_no, "save/load", traceback.format_exc()))
                        break
        finally:
            if tr:
                tr.close()
        return self.summary()

    def summary(self):
        g = self.g
        return {
            "seed": self.seed, "goal": g.goal, "over": g.over or "running", "day": g.day, "max_day": self.max_day,
            "steps": self.step_no, "kills": g.flags.get("kills", 0), "hp": self.p.hp, "infection": round(self.p.infection),
            "companions_recruited": len(self.recruited), "placed": g.placed, "fort": g.base.fort, "base": g.base.room,
            "errors": len(self.errors), "anomalies": len(self.anomalies), "softlocks": len(self.softlocks),
            "visited": sum(1 for r in g.rooms.values() if r.visited), "rooms": len(g.rooms),
            "has_radio": self.has("收音機"), "has_flare": self.has("訊號彈"), "has_vaccine": self.has("疫苗樣本"),
            "checkpoint_gone": bool(g.flags.get("checkpoint_gone")),
            **{k: self.stats[k] for k in ("bites", "fights", "ambush", "spawns", "night_attacks", "fled")},
        }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    runs = int(args[0]) if len(args) > 0 else 30
    steps = int(args[1]) if len(args) > 1 else 1500
    verbose = "--verbose" in sys.argv
    noinfect = "--noinfect" in sys.argv   # 診斷模式：每步清除感染，用來跑到後期找當機（不是平衡數據）
    god = "--god" in sys.argv             # 診斷模式：每步回滿血＋清除感染，只為了跑到第 14 天的結局程式碼
    seed_arg = None
    transcript = None
    for i, a in enumerate(sys.argv):
        if a == "--seed":
            seed_arg = int(sys.argv[i + 1])
        if a == "--transcript":
            transcript = sys.argv[i + 1]
    rng = random.Random(7)
    seeds = [seed_arg] if seed_arg else [rng.randrange(1, 10 ** 6) for _ in range(runs)]
    results, errors, anomalies, softlocks = [], [], [], []
    for sd in seeds:
        bot = SmartBot(sd, steps, verbose=verbose, transcript=transcript, noinfect=noinfect, god=god)
        res = bot.run()
        results.append(res)
        errors.extend(bot.errors)
        anomalies.extend(bot.anomalies)
        softlocks.extend(bot.softlocks)
        print(f"seed={res['seed']:<7} goal={res['goal']} over={res['over']:<10} day={res['day']:>2} steps={res['steps']:>4} kills={res['kills']:>2} "
              f"hp={res['hp']:>3} inf={res['infection']:>3} comp={res['companions_recruited']} placed={res['placed']} fort={res['fort']} "
              f"visited={res['visited']}/{res['rooms']} radio={int(res['has_radio'])} flare={int(res['has_flare'])} fights={res['fights']} bites={res['bites']} "
              f"err={res['errors']} anom={res['anomalies']} lock={res['softlocks']}")
    n = len(results)
    print("=" * 70)
    print(f"runs={n} steps/run<={steps}")
    overs = Counter(r["over"] for r in results)
    print("endings:", dict(overs))
    days = Counter(r["day"] for r in results)
    print("days reached:", dict(sorted(days.items())))
    print("avg day:", round(sum(r["day"] for r in results) / n, 2))
    print("reached day 7:", sum(1 for r in results if r["day"] >= 7), "/", n)
    print("reached day 14:", sum(1 for r in results if r["day"] >= 14), "/", n)
    print("non-death endings:", sum(1 for r in results if r["over"] not in ("dead", "infection", "running")), "/", n)
    print("avg kills:", round(sum(r["kills"] for r in results) / n, 2))
    for k in ("fights", "bites", "ambush", "spawns", "night_attacks", "fled"):
        print(f"avg {k}:", round(sum(r[k] for r in results) / n, 2))
    print("infection deaths with bites:", dict(Counter(r["bites"] for r in results if r["over"] == "infection")))
    print("avg time/day (commands):", round(sum(r["steps"] for r in results) / max(1, sum(r["day"] for r in results)), 1))
    if god:
        print("(diagnostic --god mode: hp restored and infection cleared every step; not balance data)")
    elif noinfect:
        print("(diagnostic --noinfect mode: infection cleared every step; not balance data)")
    print("avg steps:", round(sum(r["steps"] for r in results) / n, 1))
    print("goals:", dict(Counter(r["goal"] for r in results)))
    by_goal = {}
    for r in results:
        by_goal.setdefault(r["goal"], Counter())[r["over"]] += 1
    print("ending by goal:", {k: dict(v) for k, v in by_goal.items()})
    print(f"errors={len(errors)} anomalies={len(anomalies)} softlocks={len(softlocks)}")
    seen = set()
    for seed, i, cmd, tb in errors:
        key = tb.strip().splitlines()[-1]
        print("-" * 60)
        print(f"ERROR seed={seed} step={i} cmd={cmd}")
        print(tb if key not in seen else key)
        seen.add(key)
    akinds = Counter(a[3].split("(")[0].split(":")[0] for a in anomalies)
    print("anomaly kinds:", dict(akinds))
    shown = set()
    for seed, i, cmd, a, text in anomalies:
        k = a.split("(")[0].split(":")[0]
        if k in shown:
            continue
        shown.add(k)
        print("-" * 60)
        print(f"ANOMALY seed={seed} step={i} cmd={cmd}: {a}")
        print("  output:", text.replace("\n", " | ")[:300])
    for seed, i, cmd, a in softlocks[:20]:
        print("-" * 60)
        print(f"SOFTLOCK seed={seed} step={i} cmd={cmd}: {a}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
