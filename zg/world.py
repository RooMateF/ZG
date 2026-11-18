# -*- coding: utf-8 -*-
"""地圖生成。固定街道骨架，內部房間與物資隨機。"""
import random
from typing import Dict, List

from .data import LOCATIONS, LOOT, LOCKED_BONUS, DIRS, ROOM_FLAVOR, SURVIVORS, FACTIONS, GOALS, ITEMS
from .state import Game, Room, Item, Enemy, NPC, new_item, inv_add

OFFS = {"北": (0, -1), "南": (0, 1), "東": (1, 0), "西": (-1, 0)}


def room_floor(tags) -> int:
    """從標籤看樓層：B1 -> 0，沒寫 -> 1，2F -> 2 ..."""
    for t in tags:
        if len(t) == 2 and t[0] == "B" and t[1].isdigit():
            return 1 - int(t[1])
        if len(t) == 2 and t[1] == "F" and t[0].isdigit():
            return int(t[0])
    return 1


def floor_label(k: int) -> str:
    return f"B{1 - k}" if k <= 0 else f"{k}F"


def rid(loc: str, name: str) -> str:
    return f"{loc}·{name}"


def weighted(rng: random.Random, pool):
    total = sum(w for _, w in pool)
    x = rng.uniform(0, total)
    for name, w in pool:
        x -= w
        if x <= 0:
            return name
    return pool[-1][0]


FOOD_EXTRA = 0.2    # 有食物的物資池，每間有東西的房間額外多一份食物的機率（全地圖食物約 32 → 45）


def gen_loot(rng: random.Random, loc: str, level: int, locked: bool, day: int = 1, food_rng: random.Random = None) -> List[Item]:
    out: List[Item] = []
    pool = LOOT[loc]
    n = max(0, level + rng.choice([-1, 0, 0, 1]))
    for _ in range(n):
        out.append(new_item(weighted(rng, pool), 1, day))
    foods = [(name, w) for name, w in pool if ITEMS[name]["kind"] == "food" and name != "腐壞食物"]
    fr = food_rng or random.Random(f"food-{loc}-{len(out)}")
    if foods and n and fr.random() < FOOD_EXTRA:
        out.append(new_item(weighted(fr, foods), 1, day))
    if locked:
        for name in LOCKED_BONUS.get(loc, []):
            out.append(new_item(name, 1, day))
    # 堆疊合併
    merged: Dict[str, Item] = {}
    res = []
    for it in out:
        if it.stackable:
            if it.name in merged:
                merged[it.name].qty += 1
            else:
                merged[it.name] = it
                res.append(it)
        else:
            res.append(it)
    return res


DENSITY = {"normal": 0.7, "hard": 1.0}


def gen_enemies(rng: random.Random, loc: str, room: Room, danger: int, difficulty: str = "hard"):
    if danger == 0 or "faction" in room.tags:
        return
    if room.is_street():
        n = 1 if rng.random() < 0.15 * danger else 0
        for _ in range(n):
            room.enemies.append(Enemy("行屍", 30, dist=3))
        return
    p = {1: 0.2, 2: 0.4, 3: 0.55}[danger] * DENSITY.get(difficulty, 1.0)
    if rng.random() > p:
        return
    n = rng.randint(1, max(1, danger))
    for _ in range(n):
        kind = "行屍"
        if "dark" in room.tags and loc in ("醫院", "超市") and rng.random() < 0.35:
            kind = "腫脹者"
        e = Enemy(kind, 55 if kind == "腫脹者" else 30, dist=rng.randint(2, 3))
        hidden_p = 0.6 if "dark" in room.tags else 0.35
        if rng.random() < hidden_p:
            e.dist = 1
            room.hidden.append(e)
        else:
            room.enemies.append(e)


def build_world(seed: int, goal: str = None, legacy: dict = None, difficulty: str = "hard") -> Game:
    rng = random.Random(seed)
    food_rng = random.Random(f"food-{seed}")
    g = Game(seed=seed)
    g.flags["difficulty"] = difficulty
    g.goal = goal or rng.choice(list(GOALS.keys()))
    legacy = legacy or {}

    # 建房間
    for loc, spec in LOCATIONS.items():
        g.threat[loc] = float(spec["danger"]) * 0.8
        rooms_here: List[Room] = []
        entrance = None
        locked_bonus_given = False
        for tpl in spec["rooms"]:
            name, level, base_ok = tpl[0], tpl[1], tpl[2]
            tags = list(tpl[3:])
            if "faction" in spec and name in (FACTIONS[spec["faction"]]["room"], "值班室", "收容所", "帳篷", "禮拜堂"):
                tags.append("faction")
            r = Room(id=rid(loc, name), loc=loc, name=name, loot_level=level, base_ok=base_ok, tags=tags)
            r.locked = "locked" in tags
            r.flavor = rng.choice(ROOM_FLAVOR)
            r.loot = gen_loot(rng, loc, level, r.locked and not locked_bonus_given, food_rng=food_rng)
            if r.locked:
                locked_bonus_given = True      # 每個地區只有第一間鎖著的房間有固定好貨
            if "vaccine" in tags:
                r.loot.append(new_item("疫苗樣本"))
            if r.id == "辦公大樓·辦公室":
                r.loot.append(new_item("收音機"))
            gen_enemies(rng, loc, r, spec["danger"], difficulty)
            g.rooms[r.id] = r
            if r.is_street():
                entrance = r
            rooms_here.append(r)
        # 每一層的房間放到自己的小格子上，方向才一致。入口(街道)用「進/出」連到 1F 第一個房間
        floors: Dict[int, List[Room]] = {}
        for r in rooms_here:
            if r is not entrance:
                floors.setdefault(room_floor(r.tags), []).append(r)
        for k, interior in floors.items():
            grid: Dict[tuple, Room] = {}
            for r in interior:
                if not grid:
                    if k == 1:
                        entrance.exits["進"] = r.id
                        r.exits["出"] = entrance.id
                    grid[(0, 0)] = r
                    continue
                placed = False
                candidates = list(grid.items())
                rng.shuffle(candidates)
                for (x, y), pr in candidates:
                    dirs = list(OFFS.keys())
                    rng.shuffle(dirs)
                    for d in dirs:
                        nx, ny = x + OFFS[d][0], y + OFFS[d][1]
                        if (nx, ny) in grid or d in pr.exits:
                            continue
                        pr.exits[d] = r.id
                        r.exits[DIRS[d]] = pr.id
                        grid[(nx, ny)] = r
                        placed = True
                        break
                    if placed:
                        break
                assert placed, f"{loc} 放不下 {r.name}"
        # 樓梯：k 層的 stairs 房（沒標就是第一間）往上接 k+1 層的第一間；地下用 cellar 房往下接
        for k in sorted(floors):
            if k + 1 in floors and k >= 1:
                low = next((r for r in floors[k] if "stairs" in r.tags), floors[k][0])
                high = floors[k + 1][0]
                low.exits["上"] = high.id
                high.exits["下"] = low.id
            if k - 1 in floors and k <= 1:
                up = next((r for r in floors[k] if "cellar" in r.tags), floors[k][0])
                down = floors[k - 1][0]
                up.exits["下"] = down.id
                down.exits["上"] = up.id
    # 街道連接
    for loc, spec in LOCATIONS.items():
        ent = next(r for r in g.rooms.values() if r.loc == loc and r.is_street())
        for d, other in spec["exits"].items():
            oent = next(r for r in g.rooms.values() if r.loc == other and r.is_street())
            ent.exits[d] = oent.id

    # 起點：住宅區客廳，門口有基本物資
    start = g.rooms[rid("住宅區", "客廳")]
    start.enemies.clear()
    start.hidden.clear()
    for name in ("廚房", "臥室"):  # 第一天的隔壁房間不埋伏，被咬的第一口至少要看得到
        g.rooms[rid("住宅區", name)].hidden.clear()
    g.room = start.id
    g.player.inv = [new_item("菜刀"), new_item("瓶裝水"), new_item("餅乾", 2)]
    last = legacy.get("last") or {}
    if last.get("ending") and last["ending"] not in ("dead", "infection", "abandon"):
        # 上一局活下來了：這次多帶一點，算是「有經驗的人」
        g.player.inv.append(new_item("罐頭", 2))
        g.player.inv.append(new_item("繃帶", 1))
        g.flags["legacy_bonus"] = 1
    g.player.weapon = "菜刀"
    start.visited = True

    # 生存者
    for s in SURVIVORS:
        n = NPC(name=s["name"], trait=s["trait"], skill=s["skill"], need=s["need"], loc=s["loc"], room=s["room"],
                hp=s["hp"], max_hp=s["hp"], trust=rng.randint(10, 25), fear=rng.randint(30, 60),
                infected=s.get("infected", False), infect_day=1 if s.get("infected") else 0)
        n.inv = []
        for x in s["inv"]:                     # 同種的疊成一筆（繃帶x2 而不是兩個繃帶x1）
            inv_add(n.inv, new_item(x))
        g.npcs.append(n)
        rm = g.rooms[rid(n.loc, n.room)]
        rm.enemies.clear()
        rm.hidden.clear()
    # 勢力
    for f, spec in FACTIONS.items():
        g.factions[f] = spec["attitude"]

    # 傳承：上一局的屍體
    if legacy.get("deaths"):
        last = legacy["deaths"][-1]
        room = g.rooms.get(last.get("room", ""))
        if room:
            if last.get("cause") == "infection":
                room.enemies.append(Enemy("行屍", 30, dist=2, name="熟悉的面孔"))
                room.flavor = "有個身影背對著你，穿著你上一局穿的那件外套。"
            else:
                room.flavor = "角落有一具屍體，你認得那張臉。"
            for name in [x for x in last.get("items", []) if x != "疫苗樣本"][:4]:
                try:
                    room.items.append(new_item(name))
                except KeyError:
                    pass
            room.items.append(new_item("日記"))
    for key in legacy.get("known_rooms", []):
        if key in g.rooms:
            g.rooms[key].visited = True
    for name in legacy.get("known_traits", []):
        for n in g.npcs:
            if n.name == name:
                n.intro_seen = True
    g.rng_state = None
    return g
