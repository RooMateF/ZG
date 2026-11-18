# -*- coding: utf-8 -*-
"""遊戲狀態資料結構與序列化。"""
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import random

from .data import ITEMS


@dataclass(eq=False)
class Item:
    name: str
    qty: int = 1
    dur: int = 0          # 武器耐久
    made_day: int = 0     # 食物製造日，用於腐壞
    ident: bool = True    # 不明藥丸是否鑑定

    @property
    def spec(self):
        return ITEMS[self.name]

    @property
    def stackable(self):
        return self.spec.get("stack", False)

    def label(self):
        s = self.spec
        if s["kind"] == "weapon" and s["dur"] < 99:
            return f"{self.name}({self.dur}/{s['dur']})"
        return f"{self.name}x{self.qty}"      # 一個也寫 x1，數量一目了然


def new_item(name: str, qty: int = 1, day: int = 1) -> Item:
    s = ITEMS[name]
    it = Item(name=name, qty=qty if s.get("stack") else 1, made_day=day)
    if s["kind"] == "weapon":
        it.dur = s["dur"]
    return it


@dataclass(eq=False)
class Enemy:
    kind: str
    hp: int
    dist: int = 3
    distract: int = 0
    name: str = ""
    uid: int = 0               # 戰鬥中的編號，集火用

    def label(self):
        return self.name or self.kind


@dataclass
class Room:
    id: str
    loc: str
    name: str
    exits: Dict[str, str] = field(default_factory=dict)   # 方向 -> room id
    items: List[Item] = field(default_factory=list)     # 地上可見、可拿的
    loot: List[Item] = field(default_factory=list)      # 還沒被搜出來的
    enemies: List[Enemy] = field(default_factory=list)
    hidden: List[Enemy] = field(default_factory=list)       # 搜索時才出現
    loot_level: int = 0
    searched: int = 0        # 已搜索次數
    locked: bool = False
    tags: List[str] = field(default_factory=list)
    visited: bool = False
    base_ok: bool = False
    flavor: str = ""
    rumor: Optional[str] = None  # NPC 情報指向的物品（可能是假的）

    @property
    def full(self):
        return f"{self.loc}·{self.name}"

    def is_street(self):
        return "street" in self.tags


@dataclass
class NPC:
    name: str
    trait: str
    skill: str
    need: str
    loc: str
    room: str
    hp: int
    max_hp: int
    trust: int = 20
    fear: int = 40
    status: str = "stranger"   # stranger companion waiting left dead hostile placed；waiting=留守，在 loc/room 等你
    infected: bool = False
    infect_day: int = 0        # 被感染的那一天（0=未）
    inv: List[Item] = field(default_factory=list)
    unfed_days: int = 0
    revealed: bool = False     # 感染是否被玩家發現
    bandaged: bool = False
    intro_seen: bool = False
    order: str = ""            # guard/rest/''
    stance: str = ""           # 戰鬥姿態：''跟著打 / attack 上前 / back 退後 / hide 躲起來
    quest: str = ""            # 請託：''還沒提 / given 提了 / done 完成
    bonded: bool = False       # 羈絆：完成請託，戰鬥命中 +15、不躲、會擋刀
    wait_day: int = 0          # 開始留守的那一天（waiting 用）
    ate_day: int = 0           # 白天被你餵過食物的那一天（晚上就不用再分他）
    meal_day: int = 0          # 上一次吃到食物的日子；隊友省著吃，食物兩天一份（水每天）
    drank_day: int = 0         # 同上，水


@dataclass
class Player:
    hp: int = 100
    hunger: float = 20
    thirst: float = 20
    fatigue: float = 10
    infection: float = 0
    stamina: int = 100
    bleeding: bool = False
    sick: int = 0              # 食物中毒剩餘小時
    painkiller: int = 0        # 止痛剩餘小時
    antibiotic: int = 0        # 抗生素剩餘小時
    inv: List[Item] = field(default_factory=list)
    weapon: Optional[str] = None   # 裝備武器的 item 索引用 name 找
    slots: int = 10
    aimed: int = 0             # 瞄準次數：1 次 +25，之後每次 +10，最多 3 次 +45
    grabbed: bool = False

    def max_stamina(self):
        return 50 if self.hunger > 70 else 100


@dataclass
class Base:
    room: Optional[str] = None
    fort: int = 0
    storage: List[Item] = field(default_factory=list)


@dataclass
class Game:
    seed: int
    day: int = 1
    minute: int = 8 * 60       # 從 08:00 開始
    goal: str = "撤離"
    room: str = ""
    rooms: Dict[str, Room] = field(default_factory=dict)
    threat: Dict[str, float] = field(default_factory=dict)   # loc -> 0..10
    npcs: List[NPC] = field(default_factory=list)
    factions: Dict[str, int] = field(default_factory=dict)   # 態度
    player: Player = field(default_factory=Player)
    base: Base = field(default_factory=Base)
    log: List[str] = field(default_factory=list)
    flags: Dict[str, int] = field(default_factory=dict)      # 各種旗標/計數
    placed: int = 0            # 已送到教堂的人數
    over: str = ""             # 結局代碼
    combat: bool = False
    turn: int = 0
    rng_state: Optional[list] = None

    # ---- 便利方法
    @property
    def cur(self) -> Room:
        return self.rooms[self.room]

    @property
    def hour(self) -> int:
        return (self.minute // 60) % 24

    def clock(self) -> str:
        return f"{self.minute // 60:02d}:{self.minute % 60:02d}"

    def phase(self) -> str:
        h = self.hour
        if 6 <= h <= 11:
            return "早上"
        if 12 <= h <= 17:
            return "下午"
        if 18 <= h <= 21:
            return "傍晚"
        return "深夜"

    def is_night(self) -> bool:
        return self.hour >= 22 or self.hour < 6

    def companions(self) -> List[NPC]:
        return [n for n in self.npcs if n.status == "companion"]

    def waiting(self) -> List[NPC]:
        return [n for n in self.npcs if n.status == "waiting"]

    def waiting_at(self, room_id: str) -> List[NPC]:
        return [n for n in self.waiting() if f"{n.loc}·{n.room}" == room_id]

    def npcs_here(self) -> List[NPC]:
        r = self.cur
        return [n for n in self.npcs if n.status == "stranger" and n.loc == r.loc and n.room == r.name]

    def find_npc(self, text: str) -> Optional[NPC]:
        text = text.strip()
        if not text:
            return None
        for n in self.companions() + self.npcs_here():
            if n.name == text or n.name.startswith(text):
                return n
        return None


# ---------------------------------------------------------------- 序列化
def _item_from(d):
    return Item(**d)


def _enemy_from(d):
    return Enemy(**d)


def to_dict(g: Game) -> dict:
    d = asdict(g)
    return d


def from_dict(d: dict) -> Game:
    rooms = {}
    for rid, rd in d["rooms"].items():
        rd = dict(rd)
        rd["items"] = [_item_from(x) for x in rd["items"]]
        rd["loot"] = [_item_from(x) for x in rd["loot"]]
        rd["enemies"] = [_enemy_from(x) for x in rd["enemies"]]
        rd["hidden"] = [_enemy_from(x) for x in rd["hidden"]]
        rooms[rid] = Room(**rd)
    npcs = []
    for nd in d["npcs"]:
        nd = dict(nd)
        nd["inv"] = [_item_from(x) for x in nd["inv"]]
        npcs.append(NPC(**nd))
    pd = dict(d["player"])
    pd["inv"] = [_item_from(x) for x in pd["inv"]]
    player = Player(**pd)
    bd = dict(d["base"])
    bd["storage"] = [_item_from(x) for x in bd["storage"]]
    base = Base(**bd)
    g = Game(seed=d["seed"])
    for k, v in d.items():
        if k in ("rooms", "npcs", "player", "base"):
            continue
        setattr(g, k, v)
    g.rooms, g.npcs, g.player, g.base = rooms, npcs, player, base
    return g


# ---------------------------------------------------------------- 背包工具
def inv_find(inv: List[Item], text: str) -> Optional[Item]:
    """用名稱或名稱前綴找物品。"""
    text = text.strip()
    if not text:
        return None
    for it in inv:
        if it.name == text:
            return it
    for it in inv:
        if it.name.startswith(text):
            return it
    return None


def inv_count(inv: List[Item], name: str) -> int:
    return sum(it.qty for it in inv if it.name == name)


def inv_add(inv: List[Item], item: Item, slots: int = 999) -> bool:
    """放進背包，超過格數回傳 False。"""
    if item.stackable:
        for it in inv:
            if it.name == item.name:
                it.qty += item.qty
                return True
    if len(inv) >= slots:
        return False
    inv.append(item)
    return True


def inv_remove(inv: List[Item], name: str, qty: int = 1) -> bool:
    for it in list(inv):
        if it.name == name:
            if it.stackable:
                if it.qty < qty:
                    return False
                it.qty -= qty
                if it.qty <= 0:
                    inv.remove(it)
                return True
            inv.remove(it)
            return True
    return False


def sync_weapon(p) -> None:
    """裝備的武器已不在背包時清掉。"""
    if p.weapon and not any(it.name == p.weapon for it in p.inv):
        p.weapon = None


def inv_split(inv: List[Item], it: Item, qty: int = 0) -> Item:
    """從背包拿出 qty 個（0 或大於數量 = 整堆）。回傳拿出來的 Item。"""
    if not it.stackable or qty <= 0 or qty >= it.qty:
        inv.remove(it)
        return it
    it.qty -= qty
    return Item(name=it.name, qty=qty, dur=it.dur, made_day=it.made_day, ident=it.ident)


def inv_take_one(inv: List[Item], it: Item) -> Item:
    """從堆疊中拿出一個，回傳新的單件 Item。"""
    if it.stackable and it.qty > 1:
        it.qty -= 1
        return Item(name=it.name, qty=1, dur=it.dur, made_day=it.made_day, ident=it.ident)
    inv.remove(it)
    return it
