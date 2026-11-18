# -*- coding: utf-8 -*-
"""搜索：從「搜這個房間」改成「搜這樣東西」（設計文件第六節）。

物資總量不變：文字版的規則算出這個房間有什麼（room.loot），這裡只負責把它分到各個容器裡。
容器的資料存在 g.flags["hd_containers"]，是純字典，可以直接存檔。
"""
import random
from dataclasses import asdict

from ..data import ITEMS
from ..state import Item

# 每個房間有哪些可以翻的東西：（代號, 名稱, 對應的家具代號, 分鐘, 音量, 偏好放哪類物品）
# 家具代號和 docs/FIRST_BUILD.md 第二節一致，畫面端靠它把容器接到家具上。
TEMPLATES = {
    "客廳": [
        ("tv_console", "電視櫃的抽屜", "tv_console", 3, 0.25, ("tool", "material")),
        ("shoe_cabinet", "鞋櫃", "shoe_cabinet", 3, 0.25, ("material", "tool")),
        ("coffee_table", "茶几下面", "coffee_table", 2, 0.0, ("food", "water")),
        ("sofa", "沙發的縫", "sofa_seat", 2, 0.0, ()),
        ("moving_box", "搬家紙箱", "moving_box", 5, 0.5, ()),
    ],
    "廚房": [
        ("fridge", "冰箱", "fridge", 3, 0.25, ("food", "water")),
        ("counter_sink", "流理台下面", "counter_sink", 4, 0.5, ("water", "material")),
        ("counter_stove", "瓦斯爐旁的抽屜", "counter_stove", 3, 0.5, ("weapon", "tool")),
        ("dining_table", "餐桌", "dining_table", 2, 0.0, ("food",)),
    ],
    "臥室": [
        ("wardrobe", "衣櫃", "wardrobe", 5, 0.5, ("material",)),
        ("nightstand", "床頭櫃", "nightstand", 2, 0.25, ("med", "tool")),
        ("bed", "床底", "bed_single", 4, 0.25, ()),
    ],
    "車庫": [
        ("garage_shelf", "鐵架", "garage_shelf", 6, 0.5, ("material", "tool")),
        ("workbench", "工作檯", "workbench", 5, 0.5, ("weapon", "tool")),
        ("toolbox", "工具箱", "toolbox", 3, 0.5, ("weapon", "material")),
        ("car", "車子裡", "car", 6, 1.0, ()),
    ],
    "主臥": [
        ("wardrobe", "衣櫃", "wardrobe", 5, 0.5, ("material",)),
        ("dresser", "斗櫃", "dresser", 4, 0.5, ("med", "material")),
        ("nightstand", "床頭櫃", "nightstand", 2, 0.25, ("med", "tool")),
        ("bed", "床底", "bed_double", 4, 0.25, ()),
    ],
    "小孩房": [
        ("desk", "書桌的抽屜", "desk", 3, 0.25, ("tool", "food")),
        ("toy_box", "玩具箱", "toy_box", 3, 0.5, ()),
        ("bookshelf_low", "矮書櫃", "bookshelf_low", 3, 0.25, ()),
        ("bed", "床底", "bed_single", 4, 0.25, ()),
    ],
    "浴室": [
        ("sink_cabinet", "洗手台的櫃子", "sink_cabinet", 3, 0.25, ("med",)),
        ("washing_machine", "洗衣機", "washing_machine", 3, 0.5, ("material",)),
        ("bathtub", "浴缸", "bathtub", 2, 0.0, ("water",)),
    ],
    "閣樓": [
        ("storage_bin", "收納箱", "storage_bin", 4, 0.5, ()),
        ("moving_box", "紙箱堆", "moving_box", 6, 0.5, ()),
    ],
}
GENERIC = [
    ("cabinet", "櫃子", "", 5, 0.5, ()),
    ("drawer", "抽屜", "", 3, 0.25, ()),
    ("corner", "角落", "", 4, 0.25, ()),
]
HIDING = ("bed", "wardrobe", "car", "moving_box", "cabinet")    # 藏得住東西的地方


def _store(g):
    return g.flags.setdefault("hd_containers", {})


def ensure(g, room):
    """第一次進這個房間時，把它的物資分進容器。回傳容器列表（字典）。"""
    store = _store(g)
    if room.id in store:
        return store[room.id]
    if room.is_street():
        store[room.id] = []
        return store[room.id]
    rng = random.Random(f"{g.seed}-containers-{room.id}")
    cons = []
    for cid, name, furniture, minutes, noise, likes in TEMPLATES.get(room.name, GENERIC):
        cons.append({"id": cid, "name": name, "furniture": furniture, "minutes": minutes, "noise": noise,
                     "likes": list(likes), "opened": False, "ambush": False, "items": []})
    for it in room.loot:
        kind = ITEMS[it.name]["kind"]
        liked = [c for c in cons if kind in c["likes"]]
        rng.choice(liked or cons)["items"].append(asdict(it))
    room.loot.clear()
    # 文字版「搜索時撲出來」的那一隻，藏進一個藏得住東西的容器
    spots = [c for c in cons if c["id"] in HIDING] or cons
    for _ in room.hidden:
        free = [c for c in spots if not c["ambush"]]
        if not free:
            break
        rng.choice(free)["ambush"] = True
    store[room.id] = cons
    return cons


def find(g, room, cid):
    return next((c for c in ensure(g, room) if c["id"] == cid), None)


def items_of(con):
    return [Item(**d) for d in con["items"]]


def take(con, name, qty=0):
    """從容器拿出一樣東西。qty 0 是整堆。回傳 Item，沒有就回 None。"""
    for i, d in enumerate(con["items"]):
        if d["name"] == name:
            it = Item(**d)
            if it.stackable and 0 < qty < it.qty:
                d["qty"] = it.qty - qty
                it.qty = qty
            else:
                con["items"].pop(i)
            return it
    return None


def put_back(con, it):
    for d in con["items"]:
        if d["name"] == it.name and it.stackable:
            d["qty"] += it.qty
            return
    con["items"].append(asdict(it))


def view(con, hint=False):
    """給畫面看的。沒翻過的容器不透露內容；hint 是「有搜索技能的隊友在場」，會提示裡面有沒有東西。"""
    d = {"id": con["id"], "name": con["name"], "furniture": con["furniture"], "minutes": con["minutes"],
         "noise": con["noise"], "opened": con["opened"]}
    if con["opened"]:
        d["items"] = [{"name": x["name"], "qty": x["qty"]} for x in con["items"]]
    elif hint:
        d["hint"] = bool(con["items"])
    return d


def total_items(g) -> int:
    return sum(x["qty"] for cons in _store(g).values() for c in cons for x in c["items"])
