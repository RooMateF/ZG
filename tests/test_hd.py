# -*- coding: utf-8 -*-
"""HD-2D 版規則的測試（zg/hd/）。純腳本，不需 pytest。
用法：python -X utf8 tests/test_hd.py
失敗時以 exit code 1 結束。每個情境獨立執行並收集失敗。
"""
import io
import json
import os
import random
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from zg.engine import Engine                      # noqa: E402
from zg.hd import containers                      # noqa: E402
from zg.hd.battle import Battle, obey_label       # noqa: E402
from zg.hd.bridge import serve                    # noqa: E402
from zg.hd.rules import band_from_distance, noise_radius   # noqa: E402
from zg.hd.session import Session                 # noqa: E402
from zg.save import SAVE                          # noqa: E402
from zg.state import Enemy, inv_count, new_item   # noqa: E402
from zg.world import build_world                  # noqa: E402

FAILURES = []
PASSES = []
START = "住宅區·客廳"


class Rig:
    """可以指定結果的亂數。roll 是擲 1 到 100 時回的數字（1 一定成功，100 一定失敗）；
    其他範圍回最小值；random() 回 rnd；choice 拿第一個。"""

    def __init__(self, roll=1, rnd=0.99):
        self.roll = roll
        self.rnd = rnd

    def randint(self, a, b):
        return self.roll if (a, b) == (1, 100) else a

    def random(self):
        return self.rnd

    def choice(self, seq):
        return seq[0]

    def choices(self, pop, weights=None):
        return [pop[0]]


def world(seed=1):
    g = build_world(seed, difficulty="normal")
    g.cur.enemies.clear()
    g.cur.hidden.clear()
    return g, Engine(g)


def recruit(g, name, trust=50, fear=30, **kw):
    n = next(x for x in g.npcs if x.name == name)
    n.status = "companion"
    n.trust, n.fear = trust, fear
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def arm(g, name):
    g.player.inv.append(new_item(name))
    g.player.weapon = name


def fight(foes, weapon=None, comps=(), opener="neutral", env=None, roll=100, rnd=0.99, seed=1, setup=None):
    """開一場戰鬥。foes：[(種類, 距離帶, {額外資訊})]。預設所有擲骰都失敗（roll=100），要成功就改 eng.rng.roll。"""
    g, eng = world(seed)
    if weapon:
        arm(g, weapon)
    for c in comps:
        recruit(g, *c[:1], **(c[1] if len(c) > 1 else {}))
    if setup:
        setup(g)
    entries = []
    for f in foes:
        kind, band = f[0], f[1]
        info = dict(f[2]) if len(f) > 2 else {}
        info["band"] = band
        e = Enemy(kind, {"行屍": 30, "疾走者": 22, "腫脹者": 55, "掠奪者": 40, "士兵": 60}[kind], dist=band)
        g.cur.enemies.append(e)
        entries.append((e, g.cur.enemies, info))
    eng.rng = Rig(roll, rnd)
    b = Battle(eng, entries, opener=opener, env=env)
    return g, eng, b


def types(events):
    return [e["t"] for e in events]


def has(events, t, **kw):
    return any(e["t"] == t and all(e.get(k) == v for k, v in kw.items()) for e in events)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def scenario(fn):
    try:
        fn()
        PASSES.append(fn.__name__)
    except Exception:
        FAILURES.append((fn.__name__, traceback.format_exc()))
    return fn


# ================================================================ 聲音和距離
@scenario
def noise_and_bands():
    rs = [noise_radius(a) for a in (0, 0.25, 0.5, 1, 2, 3, 4, 5, 9)]
    check(rs[0] == 0 and rs == sorted(rs), f"聲音半徑要隨音量變大：{rs}")
    check(noise_radius(4) >= 3 * noise_radius(2), "槍聲要比跑步傳得遠很多")
    check([band_from_distance(d) for d in (0.5, 2, 5, 10)] == [1, 2, 3, 4], "實際距離換成距離帶")


# ================================================================ 搜索
@scenario
def loot_total_unchanged():
    g, _ = world(5)
    indoor = [r for r in g.rooms.values() if not r.is_street()]
    before = sum(it.qty for r in indoor for it in r.loot)      # 文字版街道不能搜，街道上的不算
    check(before > 50, "世界裡應該有物資")
    for r in g.rooms.values():
        containers.ensure(g, r)
    check(containers.total_items(g) == before, f"分進容器後總量要一樣：{containers.total_items(g)} vs {before}")
    check(all(not r.loot for r in indoor), "原本的清單要清空，不然同一樣東西拿得到兩次")
    check(all(not g.flags["hd_containers"][r.id] for r in g.rooms.values() if r.is_street()), "街道沒有容器")
    again = containers.total_items(g)
    for r in g.rooms.values():
        containers.ensure(g, r)
    check(containers.total_items(g) == again, "重複呼叫不能再分一次")


@scenario
def containers_same_for_same_seed():
    a, _ = world(7)
    b, _ = world(7)
    for g in (a, b):
        for r in g.rooms.values():
            containers.ensure(g, r)
    check(a.flags["hd_containers"] == b.flags["hd_containers"], "同一個種子要分得一樣")
    kitchen = a.flags["hd_containers"]["住宅區·廚房"]
    check([c["furniture"] for c in kitchen][:1] == ["fridge"], "廚房的容器要對得上家具代號")


@scenario
def search_takes_time_and_gives_items():
    s = Session(seed=3)
    g = s.g
    g.cur.loot.append(new_item("罐頭", 2))
    g.cur.hidden.clear()
    room = s.handle({"cmd": "state"})["room"]
    check(all("items" not in c for c in room["containers"]), "沒翻過的容器不能透露內容")
    t0 = s.state()["minute"]
    found = 0
    for c in room["containers"]:
        out = s.handle({"cmd": "search", "container": c["id"]})
        check(out["ok"], out.get("error"))
        for it in out["container"].get("items", []):
            found += it["qty"]
            check(s.handle({"cmd": "take", "container": c["id"], "item": it["name"]})["ok"], "拿不到翻出來的東西")
    check(found >= 2, "加進去的罐頭要翻得到")
    check(inv_count(g.player.inv, "罐頭") >= 2, "拿了要進背包")
    check(s.state()["minute"] - t0 == sum(c["minutes"] for c in room["containers"]), "搜索的時間是各容器加起來")
    check(not s.handle({"cmd": "take", "container": "fridge", "item": "罐頭"})["ok"], "沒有的東西要回錯誤")


@scenario
def ambush_from_container():
    s = Session(seed=3)
    g = s.g
    g.cur.enemies.clear()
    g.cur.hidden[:] = [Enemy("行屍", 30, dist=2)]
    g.flags.pop("hd_containers", None)
    room = s.handle({"cmd": "state"})["room"]
    hit = None
    for c in room["containers"]:
        out = s.handle({"cmd": "search", "container": c["id"]})
        if has(out["events"], "ambush"):
            hit = out
            break
    check(hit, "藏著的那一隻要在翻某個容器時撲出來")
    check(not g.cur.hidden and g.cur.enemies[0].dist == 1, "牠要出現在貼身的距離")
    foe = next(e for e in hit["events"] if e["t"] == "ambush")["foe"]
    out = s.handle({"cmd": "battle_start", "foes": [{"uid": foe["uid"], "band": 1}], "opener": "enemy"})
    check(out["ok"] and out["battle"]["foes"][0]["band_name"] == "貼身", "接著要能原地開戰")


# ================================================================ 時間
@scenario
def time_follows_distance():
    s = Session(seed=2)
    t0 = s.state()["minute"]
    s.handle({"cmd": "state"})
    s.handle({"cmd": "noise", "action": "door"})
    check(s.state()["minute"] == t0, "站著不動、開門，時鐘不走")
    s.handle({"cmd": "walk", "dist": 7.5})
    check(s.state()["minute"] == t0 + 3, f"走 7.5 個單位是 3 分鐘：{s.state()['minute'] - t0}")
    s.handle({"cmd": "walk", "dist": 17.5})
    check(s.state()["minute"] == t0 + 10 and s.g.minute == t0 + 10, "滿十分鐘規則引擎要跟上")
    hunger = s.g.player.hunger
    s.handle({"cmd": "walk", "dist": 250})
    check(s.g.player.hunger > hunger, "走路會餓")


@scenario
def running_costs_stamina_and_is_loud():
    s = Session(seed=2)
    walk = s.handle({"cmd": "walk", "dist": 5})
    st = s.g.player.stamina
    run = s.handle({"cmd": "walk", "dist": 5, "run": True})
    check(run["radius"] > walk["radius"] * 2, "跑步要比走路大聲很多")
    check(s.g.player.stamina < st, "跑步扣體力")
    recruit(s.g, "老陳")
    check(s.handle({"cmd": "walk", "dist": 1})["noise"] > walk["noise"], "隊友越多腳步聲越大")


# ================================================================ 戰鬥：輪流和距離
@scenario
def who_goes_first():
    g, eng, b = fight([("行屍", 3)], opener="enemy")
    check(b.foes[0].band == 2 and b.waiting.uid == "p", "牠先發現你：牠先走一步才輪到你")
    g, eng, b = fight([("行屍", 3)], opener="player")
    check(b.foes[0].band == 3 and b.waiting.aim == 1, "你先動手：牠還沒動，而且你有瞄準加成")
    g, eng, b = fight([("疾走者", 4)], opener="neutral")
    check(b.foes[0].band == 2, "疾走者比你快，會先動")
    g, eng, b = fight([("腫脹者", 3)], opener="neutral")
    check(b.foes[0].band == 3 and b.waiting.uid == "p", "腫脹者最慢，你先動")


@scenario
def speeds_and_eta():
    g, eng, b = fight([("行屍", 4), ("疾走者", 4), ("腫脹者", 3)], opener="player")
    eta = {f.kind: b.eta(f) for f in b.foes}
    check(eta == {"行屍": 3, "疾走者": 2, "腫脹者": 4}, f"還要幾回合貼上來：{eta}")
    seen = {f.kind: [f.band] for f in b.foes}
    for _ in range(4):
        b.act("p", "wait")
        for f in b.foes:
            seen[f.kind].append(f.band)
    check(seen["行屍"] == [4, 3, 2, 1, 1], f"行屍一回合一段：{seen['行屍']}")
    # 疾走者比你快：第一回合你先動手之後牠走兩段，第二回合牠又搶在你前面再走，所以你只來得及做一件事
    check(seen["疾走者"] == [4, 1, 1, 1, 1], f"疾走者一回合兩段，而且比你先動：{seen['疾走者']}")
    check(seen["腫脹者"] == [3, 3, 2, 2, 1], f"腫脹者兩回合一段：{seen['腫脹者']}")
    v = b.view()
    check(all(f["eta"] == 0 for f in v["foes"]) and v["current"] == "p", "view 要報出誰貼身了、輪到誰")


@scenario
def weapon_reach():
    def chance(weapon, band):
        g, eng, b = fight([("行屍", band)], weapon=weapon, opener="player")
        return b.hit_chance(b.waiting, b.foes[0])

    check(chance("菜刀", 1) > 0 and chance("菜刀", 2) == 0, "刀只打得到貼身")
    check(0 < chance("消防斧", 2) < chance("消防斧", 1), "斧頭搆得到「近」，但比較不準")
    check(chance("手槍", 4) == 0, "沒子彈的槍打不到遠的")
    g, eng, b = fight([("行屍", 4), ("行屍", 3), ("行屍", 2)], weapon="手槍", opener="player",
                      setup=lambda g: g.player.inv.append(new_item("手槍子彈", 5)))
    a = b.waiting
    c4, c3, c2 = (b.hit_chance(a, f) for f in b.foes)
    check(c3 > c2 > c4 > 0, f"手槍最順手的是「中」：遠{c4} 中{c3} 近{c2}")
    g, eng, b = fight([("行屍", 4), ("行屍", 2)], weapon="霰彈槍", opener="player",
                      setup=lambda g: g.player.inv.append(new_item("霰彈", 5)))
    check(b.hit_chance(b.waiting, b.foes[0]) == 0 and b.hit_chance(b.waiting, b.foes[1]) > 0, "霰彈槍打不到遠")
    atk = next(o for o in b.view()["options"] if o["cmd"] == "attack")
    check([t["foe"] for t in atk["targets"]] == ["e2"] and atk["noise"] == 5, "選單要列出打得到誰、多大聲")


@scenario
def gun_makes_noise_and_uses_ammo():
    g, eng, b = fight([("行屍", 3)], weapon="手槍", opener="player",
                      setup=lambda g: g.player.inv.append(new_item("手槍子彈", 2)))
    threat = g.threat[g.cur.loc]
    eng.rng.roll = 1
    ev = b.act("p", "attack", {"target": "e1"})
    check(inv_count(g.player.inv, "手槍子彈") == 1, "開槍要用掉子彈")
    noise = next(e for e in ev if e["t"] == "noise")
    check(noise["amount"] == 4 and noise["radius"] >= 20, "槍聲要回報很大的半徑")
    check(g.threat[g.cur.loc] > threat, "槍聲加進地區威脅值")


@scenario
def shotgun_hits_two_at_near():
    g, eng, b = fight([("行屍", 2), ("行屍", 2)], weapon="霰彈槍", opener="player",
                      setup=lambda g: g.player.inv.append(new_item("霰彈", 2)))
    eng.rng.roll = 1
    ev = b.act("p", "attack", {"target": "e1"})
    check(has(ev, "attack", mode="splash"), "在「近」一槍要波及第二隻")


# ================================================================ 戰鬥：指令
@scenario
def legs_slow_them_down():
    g, eng, b = fight([("行屍", 1), ("疾走者", 1)], weapon="球棒", opener="player")
    eng.rng.roll = 1
    walker, runner = b.foes
    hp = walker.hp
    b.act("p", "attack", {"target": "e1", "mode": "legs"})
    check(walker.pace() == (1, 2) and hp - walker.hp < 10, "行屍腿被打：兩回合才走一段，傷害低")
    eng.rng.roll = 1
    b.act("p", "attack", {"target": "e2", "mode": "legs"})
    check(runner.pace() == (1, 1), "疾走者腿被打：變成一回合一段")
    walker.band = 4
    check(b.eta(walker) > 3, "腿斷了的行屍要更久才到")


@scenario
def head_helmet_vest():
    g, eng, b = fight([("行屍", 1, {"tags": ["helmet"]}), ("行屍", 1, {"tags": ["vest"]}), ("行屍", 1)],
                      weapon="球棒", opener="player")
    eng.rng.roll = 1
    b.act("p", "attack", {"target": "e1", "mode": "head"})
    check(b.foe("e1") and not b.foe("e1").helmet and b.foe("e1").hp == 30, "第一下只打掉安全帽")
    eng.rng.roll = 1
    b.act("p", "attack", {"target": "e1", "mode": "head"})
    check(b.foe("e1") is None, "安全帽掉了之後打頭一擊斃命")
    eng.rng.roll = 1
    b.act("p", "attack", {"target": "e2"})
    eng.rng.roll = 1
    b.act("p", "attack", {"target": "e3"})
    check(30 - b.foe("e2").hp < 30 - b.foe("e3").hp, "防彈背心讓打身體的傷害減半")
    check(g.flags.get("xp_kills") == 1, "你親手殺的要算熟練度")


@scenario
def aim_stacks():
    g, eng, b = fight([("腫脹者", 4)], weapon="球棒")
    base = b.hit_chance(b.waiting, b.foes[0])
    b.foes[0].band = 1
    c0 = b.hit_chance(b.waiting, b.foes[0], "head")
    for _ in range(4):
        b.foes[0].band = 4
        b.act("p", "aim")
    check(b.waiting.aim == 3, "瞄準最多疊三次")
    b.foes[0].band = 1
    check(b.hit_chance(b.waiting, b.foes[0], "head") >= c0 + 45, "瞄準後打頭準很多")
    check(base == 0, "搆不到時命中率是 0")


@scenario
def push_makes_room():
    g, eng, b = fight([("行屍", 1)], opener="player")
    eng.rng.roll = 1
    ev = b.act("p", "push")
    check(has(ev, "push", ok=True), "推開要成功")
    check(has(ev, "foe_wait", why="stagger") and b.foes[0].band == 2, "被推開的那一隻踉蹌一回合，停在「近」")
    check(not b.act("p", "push")[0].get("ok", False) and b.waiting.uid == "p", "沒有貼身的就不能推，也不耗回合")


@scenario
def grab_and_escape():
    g, eng, b = fight([("行屍", 1)], opener="player")
    a = b.waiting
    a.grabbed = True
    check(has(b.act("p", "flee"), "no"), "被抓住時不能逃")
    eng.rng.roll = 1
    ev = b.act("p", "push")
    check(has(ev, "push", escape=True, ok=True), "被抓住時推開是掙脫")


@scenario
def taunt_and_cover():
    g, eng, b = fight([("行屍", 1)], comps=[("阿強",)], opener="player")
    eng.rng.roll = 1
    eng.rng.rnd = 0.0
    b.act("p", "wait")
    ev = b.act("c:阿強", "taunt")
    hit = next(e for e in ev if e["t"] == "foe_attack")
    check(hit["dst"] == "c:阿強", "牽制的人要把牠引過去")
    g, eng, b = fight([("行屍", 1)], comps=[("小美", {"trust": 90})], opener="player")
    hp = g.player.hp
    eng.rng.roll = 1
    b.act("p", "wait")
    ev = b.act("c:小美", "cover", {"target": "p"})
    hit = next(e for e in ev if e["t"] == "foe_attack")
    check(hit["dst"] == "c:小美" and hit["via"] == "cover" and g.player.hp == hp, "掩護的人替你挨打")


@scenario
def back_row_is_safe_until_front_falls():
    g, eng, b = fight([("行屍", 1)], comps=[("阿強",)], opener="player")
    eng.rng.roll = 1
    b.act("p", "row", {"row": "back"})
    ev = b.act("c:阿強", "wait")
    check(next(e for e in ev if e["t"] == "foe_attack")["dst"] == "c:阿強", "貼身的敵人打前排")
    g, eng, b = fight([("行屍", 1)], opener="player")
    eng.rng.roll = 1
    ev = b.act("p", "row", {"row": "back"})
    check(next(e for e in ev if e["t"] == "foe_attack")["dst"] == "p", "前排沒人就打得到後排")


@scenario
def throw_distracts_and_fire_burns():
    g, eng, b = fight([("行屍", 4), ("行屍", 3)], opener="player",
                      setup=lambda g: g.player.inv.extend([new_item("空瓶", 1), new_item("燃燒瓶", 1)]))
    ev = b.act("p", "throw", {"item": "空瓶", "target": "e1"})
    check(has(ev, "foe_wait", foe="e1", why="distract") and b.foe("e1").band == 4, "被引開的那一隻這回合不靠近")
    check(b.foe("e2").band == 2, "沒被引開的照樣逼近")
    ev = b.act("p", "throw", {"item": "燃燒瓶"})
    check(not b.foes and b.over == "won", "燃燒瓶燒到所有還沒貼身的")
    check(inv_count(g.player.inv, "燃燒瓶") == 0, "丟出去就沒了")


@scenario
def meds_in_battle():
    g, eng, b = fight([("腫脹者", 4)], comps=[("小美",)], opener="player",
                      setup=lambda g: g.player.inv.append(new_item("繃帶", 2)))
    g.player.hp, g.player.bleeding = 50, True
    b.act("p", "use", {"item": "繃帶"})
    check(g.player.hp == 60 and not g.player.bleeding, "繃帶止血回血")
    mei = b.ally("c:小美")
    mei.hp = 20
    b.act("c:小美", "wait")
    b.act("p", "use", {"item": "繃帶", "target": "c:小美"})
    check(mei.hp == 30, "可以替隊友包紮")


# ================================================================ 戰鬥：環境
@scenario
def door_holds_them_back():
    env = [{"id": "door_a", "kind": "door", "name": "房門"}]
    g, eng, b = fight([("行屍", 4, {"via": "door_a"})], opener="player", env=env)
    ev = b.act("p", "env", {"env": "door_a", "verb": "close"})
    check(has(ev, "door", state="bash") and b.foes[0].band == 4, "關上門，牠只能在外面撞")
    check(b.view()["foes"][0]["blocked"], "view 要標出牠被門擋住")
    ev = b.act("p", "env", {"env": "door_a", "verb": "brace"})
    hold = b.env["door_a"]["hold"]
    n = 0
    while b.env["door_a"].get("closed") and n < 10:
        ev = b.act("p", "wait")
        n += 1
    check(n == hold and has(ev, "door", state="broken"), f"門撐了 {n} 回合才被撞開（頂住後是 {hold}）")
    b.act("p", "wait")
    check(b.foes[0].band == 3, "門破了之後牠才進來")
    check(has(b.act("p", "env", {"env": "door_a", "verb": "close"}), "no"), "壞掉的門關不起來")


@scenario
def chokepoint_lets_one_through():
    env = [{"id": "hall", "kind": "choke", "name": "門口"}]
    g, eng, b = fight([("行屍", 2), ("行屍", 2), ("行屍", 2)], opener="player", env=env)
    b.act("p", "env", {"env": "hall", "verb": "choke"})
    b.act("p", "wait")
    check(sorted(f.band for f in b.foes) == [1, 2, 2], "守住門口：一次只有一隻貼得上來")
    b.act("p", "row", {"row": "back"})
    b.act("p", "wait")
    check(sorted(f.band for f in b.foes) == [1, 1, 1], "離開門口就擋不住了")


@scenario
def topple_noise_fire_light():
    env = [{"id": "shelf", "kind": "topple", "name": "衣櫃"}, {"id": "radio", "kind": "noise", "name": "收音機"},
           {"id": "stove", "kind": "fire", "name": "瓦斯爐"}, {"id": "sw", "kind": "light", "name": "電燈"},
           {"id": "sofa", "kind": "cover", "name": "沙發"}]
    g, eng, b = fight([("行屍", 2), ("行屍", 3)], opener="player", env=env)
    hp = b.foes[0].hp
    ev = b.act("p", "env", {"env": "shelf", "verb": "topple"})
    check(b.foes[0].hp < hp and has(ev, "noise", amount=3.0), "推倒家具砸到「近」的，而且很大聲")
    check(has(b.act("p", "env", {"env": "shelf", "verb": "topple"}), "no"), "推倒過的不能再推")
    ev = b.act("p", "env", {"env": "radio", "verb": "noise"})
    check(all(f.distract or has(ev, "foe_wait", foe=f.uid, why="distract") for f in b.foes), "弄出聲音把牠們引開")
    check(has(b.act("p", "env", {"env": "stove", "verb": "fire"}), "no"), "沒有打火機點不了火")
    g.player.inv.append(new_item("打火機"))
    for f in b.foes:
        f.band = 2
    b.act("p", "env", {"env": "stove", "verb": "fire"})
    check(b.over == "won", "火燒得死「近」和「中」的")
    g, eng, b = fight([("掠奪者", 3)], opener="player", env=env)
    eng.rng.roll, eng.rng.rnd = 25, 0.0      # 掠奪者在「中」的命中是 30
    ev = b.act("p", "wait")
    check(next(e for e in ev if e["t"] == "foe_attack")["hit"], "掠奪者在「中」開槍打得中站著的人")
    hp = g.player.hp
    b.act("p", "env", {"env": "sofa", "verb": "cover"})
    ev = b.act("p", "env", {"env": "sw", "verb": "light"})
    check(g.player.hp == hp or not [e for e in ev if e["t"] == "foe_attack" and e["hit"]], "躲在家具後面又關了燈，打不中")
    check(b.view()["dark"], "view 要報出燈關了")


@scenario
def bloater_cloud_only_in_melee():
    g, eng, b = fight([("腫脹者", 1)], weapon="球棒", opener="player")
    b.foes[0].hp = 1
    eng.rng.roll = 1
    ev = b.act("p", "attack")
    check(has(ev, "cloud") and g.player.infection == 15, "近身打死腫脹者會吸到毒霧")
    env = [{"id": "stove", "kind": "fire", "name": "瓦斯爐", "lit": True}]
    g, eng, b = fight([("腫脹者", 2)], opener="player", env=env)
    b.foes[0].hp = 1
    ev = b.act("p", "env", {"env": "stove", "verb": "fire"})
    check(not has(ev, "cloud") and g.player.infection == 0 and b.over == "won", "用火燒死才安全")


# ================================================================ 戰鬥：隊友聽不聽
@scenario
def risky_orders_can_be_refused():
    check([obey_label(c) for c in (95, 70, 45, 10)] == ["會聽", "大概會聽", "可能不聽", "多半不聽"], "選單上的說法")
    g, eng, b = fight([("腫脹者", 4)], comps=[("老陳", {"trust": 10, "fear": 60, "stance": "back"})], opener="player")
    chen = b.ally("c:老陳")
    check(chen.row == "back", "退後的隊友從後排開始")
    b.act("p", "wait")
    opts = {(o["cmd"], o.get("args", {}).get("row")): o for o in b.view()["options"]}
    check(opts[("row", "front")]["obey"] < 40 and opts[("attack", None)]["obey"] == 100, "危險的指令才可能不聽，而且選單看得到")
    eng.rng.roll = 100
    ev = b.act("c:老陳", "row", {"row": "front"})
    check(has(ev, "refuse", unit="c:老陳") and chen.row == "back", "怯懦又不信任你：叫他上前他不去")
    g, eng, b = fight([("腫脹者", 4)], comps=[("小美", {"trust": 5, "fear": 90, "stance": "back"})], opener="player")
    b.act("p", "wait")
    ev = b.act("c:小美", "row", {"row": "front"})
    check(has(ev, "row", unit="c:小美", row="front"), "忠誠的人一定聽")
    g, eng, b = fight([("腫脹者", 4)], comps=[("林醫師", {"trust": 80})], opener="player")
    check(b.obey_chance(b.ally("c:林醫師"), "cover") == 0, "冷酷的人不替別人擋")
    g, eng, b = fight([("腫脹者", 4)], comps=[("林醫師", {"trust": 80, "bonded": True})], opener="player")
    check(b.obey_chance(b.ally("c:林醫師"), "cover") == 100, "有羈絆的人什麼都做")


@scenario
def coward_runs_and_comes_back():
    g, eng, b = fight([("行屍", 4), ("行屍", 4), ("行屍", 4)], comps=[("老陳", {"trust": 30, "fear": 80})],
                      opener="player")
    chen = b.ally("c:老陳")
    check(b.view()["allies"][1]["break_kind"] == "flee" and b.view()["allies"][1]["break_chance"] >= 40,
          "view 要先讓玩家看到他可能會跑")
    eng.rng.roll = 1
    ev = b.act("p", "wait")
    check(has(ev, "trait", unit="c:老陳", kind="flee") and chen.out == "hid", "怯懦的人恐懼夠高就自己躲起來")
    check(b.waiting.uid == "p", "他躲起來之後不再輪到他")
    eng.rng.roll = 100
    for f in list(b.foes):
        b._kill(f, b.ally("p"), melee=False)
    b.run()
    check(b.over == "won" and chen.ref.stance == "" and chen.ref.status == "companion", "打完他會回來")


@scenario
def greedy_loots_and_practical_retreats():
    g, eng, b = fight([("掠奪者", 1), ("行屍", 4)], weapon="球棒", comps=[("阿凱", {"trust": 40})], opener="player")
    b.foes[0].hp = 1
    eng.rng.roll = 1
    ev = b.act("p", "attack", {"target": "e1"})
    check(has(ev, "drop") and has(ev, "trait", unit="c:阿凱", kind="loot"), "貪婪的人先去翻屍體")
    kai = next(n for n in g.npcs if n.name == "阿凱")
    check(any(e.get("item") for e in ev if e["t"] == "trait") and not b.drops, "掉的東西進了他的口袋")
    g, eng, b = fight([("行屍", 4)] * 5, comps=[("阿強", {"trust": 40})], opener="player")
    eng.rng.roll = 1
    ev = b.act("p", "wait")
    check(has(ev, "trait", unit="c:阿強", kind="retreat") and b.ally("c:阿強").row == "back", "實際的人看打不贏就自己退後")
    check(kai.status == "companion", "翻屍體不影響他的隊友身分")


@scenario
def companion_death_and_player_death():
    g, eng, b = fight([("行屍", 1)], opener="player",
                      comps=[("小傑", {"hp": 1}), ("阿強", {"trust": 50, "fear": 20, "stance": "back"})])
    eng.rng.roll = 45        # 小傑這回合沒有嚇跑（要 40 以下），行屍打得中（45 以下），但沒咬到
    b.act("p", "row", {"row": "back"})
    b.act("c:阿強", "wait")
    ev = b.act("c:小傑", "wait")
    jie = next(n for n in g.npcs if n.name == "小傑")
    qiang = next(n for n in g.npcs if n.name == "阿強")
    check(has(ev, "death", unit="c:小傑") and jie.status == "dead", "隊友血歸零就死了")
    check(qiang.trust == 45 and qiang.fear >= 35, "其他人看到會動搖")
    g, eng, b = fight([("行屍", 1)], opener="player")
    g.player.hp = 1
    eng.rng.roll = 1
    ev = b.act("p", "wait")
    check(b.over == "dead" and g.over == "dead" and has(ev, "end", result="dead"), "玩家死了戰鬥結束")
    check(not g.combat, "戰鬥結束要把狀態清掉")


@scenario
def flee_and_chasers():
    g, eng, b = fight([("疾走者", 3), ("行屍", 1)], opener="player")
    eng.rng.roll, eng.rng.rnd = 1, 0.0
    ev = b.act("p", "flee", {"exit": "door_back"})
    end = next(e for e in ev if e["t"] == "end")
    check(b.over == "fled" and end["result"] == "fled" and not g.combat, "逃跑成功，戰鬥結束")
    check(sorted(c["foe"] for c in end["chasers"]) == ["e1", "e2"], "追上來的要回報給畫面")
    check(len(g.cur.enemies) == 2, "沒死的敵人還在那個房間")
    g, eng, b = fight([("行屍", 1)], opener="player")
    eng.rng.roll = 100
    ev = b.act("p", "flee")
    check(has(ev, "flee", ok=False) and not b.over, "逃跑失敗要耗掉回合")


@scenario
def reinforcements_join():
    s = Session(seed=4)
    g = s.g
    g.cur.enemies[:] = [Enemy("行屍", 30, dist=3)]
    g.cur.hidden.clear()
    other = g.rooms["住宅區·廚房"]
    other.enemies[:] = [Enemy("疾走者", 22, dist=3)]
    other.enemies[0].uid = 9
    room = s.handle({"cmd": "state"})["room"]
    out = s.handle({"cmd": "battle_start", "foes": [{"uid": room["enemies"][0]["uid"], "dist": 5}], "opener": "player"})
    check(out["ok"] and out["battle"]["foes"][0]["band_name"] == "中", "開戰距離用實際距離換算")
    check(not s.handle({"cmd": "enter", "room": "住宅區·廚房"})["ok"], "戰鬥中不能直接換房間")
    out = s.handle({"cmd": "battle_join", "room": "住宅區·廚房", "uid": 9, "via": "door_kitchen"})
    check(out["ok"] and has(out["events"], "join") and len(out["battle"]["foes"]) == 2, "隔壁的可以闖進來")
    check(out["battle"]["foes"][1]["band_name"] == "遠" and out["battle"]["foes"][1]["via"] == "door_kitchen",
          "闖進來的從「遠」開始，記得牠走哪扇門")
    check(not s.handle({"cmd": "battle_join", "room": "住宅區·廚房", "uid": 9})["ok"], "同一隻不能加兩次")
    out = s.handle({"cmd": "battle_act", "unit": "p", "act": "wait"})
    check("e2" in [e.get("foe") for e in out["events"] if e["t"] == "move"], "下一回合牠就會動")
    check(out["state"]["in_battle"], "狀態要標出正在戰鬥")


@scenario
def unaware_enemies_stay_out():
    s = Session(seed=4)
    g = s.g
    g.cur.enemies[:] = [Enemy("行屍", 30), Enemy("行屍", 30)]
    g.cur.hidden.clear()
    room = s.handle({"cmd": "state"})["room"]
    out = s.handle({"cmd": "battle_start", "foes": [{"uid": room["enemies"][0]["uid"], "band": 3}], "opener": "player"})
    out = s.handle({"cmd": "battle_act", "unit": "p", "act": "wait"})
    check(len(out["battle"]["foes"]) == 1 and not has(out["events"], "intrusion"), "沒發現你的那一隻不會自己加入戰鬥")
    g.cur.enemies.append(Enemy("疾走者", 22, dist=4))      # 模擬打到一半規則引擎又叫來一隻
    out = s.handle({"cmd": "battle_act", "unit": "p", "act": "wait"})
    check(has(out["events"], "intrusion") and len(out["battle"]["foes"]) == 1, "新來的只通知畫面，由畫面決定牠何時加入")
    out = s.handle({"cmd": "battle_act", "unit": "p", "act": "wait"})
    check(not has(out["events"], "intrusion"), "同一隻只通知一次")


@scenario
def police_sprite_gets_vest():
    s = Session(seed=4)
    g = s.g
    g.cur.enemies[:] = [Enemy("行屍", 30), Enemy("行屍", 30)]
    g.cur.hidden.clear()
    room = s.handle({"cmd": "state"})["room"]
    foes = [{"uid": room["enemies"][0]["uid"], "band": 3, "sprite": "walker_police_01"},
            {"uid": room["enemies"][1]["uid"], "band": 3, "sprite": "walker_dock_02"}]
    out = s.handle({"cmd": "battle_start", "foes": foes})
    f = out["battle"]["foes"]
    check(f[0]["vest"] and not f[0]["helmet"] and f[1]["helmet"], "警察有防彈背心，碼頭工人有安全帽")


# ================================================================ 窗口
@scenario
def bridge_speaks_json_lines():
    lines = [{"cmd": "state"}, {"cmd": "hello"}, {"cmd": "new", "seed": 11}, {"cmd": "walk", "dist": 5},
             {"cmd": "nonsense"}, {"cmd": "enter", "room": "不存在"}, {"cmd": "quit"}, {"cmd": "state"}]
    out = io.StringIO()
    serve(io.StringIO("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\nnot json\n"), out)
    replies = [json.loads(x) for x in out.getvalue().splitlines()]
    check(len(replies) == 7, f"每個指令一行回覆，quit 之後不再回：{len(replies)}")
    check(not replies[0]["ok"], "還沒開局就送指令要回錯誤")
    check(replies[1]["protocol"] == 1, "hello 回報協定版本")
    check(replies[2]["ok"] and replies[2]["state"]["room"] == START and replies[2]["room"]["containers"], "new 回整個狀態")
    check(replies[3]["ok"] and "radius" in replies[3], "walk 回腳步聲半徑")
    check(not replies[4]["ok"] and not replies[5]["ok"] and "error" in replies[5], "錯的指令回錯誤，不會當掉")
    check(replies[5]["state"]["room"] == START, "指令不成立時狀態不變")


@scenario
def bridge_survives_broken_input():
    out = io.StringIO()
    serve(io.StringIO('{"cmd": "new"}\nnot json\n{"cmd": "state"}\n'), out)
    replies = [json.loads(x) for x in out.getvalue().splitlines()]
    check(len(replies) == 3 and not replies[1]["ok"] and replies[2]["ok"], "壞掉的一行不能讓整個程式停下來")


@scenario
def save_never_touches_text_save():
    s = Session(seed=6)
    check(not s.handle({"cmd": "save", "path": SAVE})["ok"], "不能寫到文字版的存檔")
    check(not s.handle({"cmd": "save"})["ok"], "沒給路徑不能存")
    s.handle({"cmd": "state"})
    s.handle({"cmd": "walk", "dist": 12})
    s.g.player.inv.append(new_item("罐頭", 3))
    path = os.path.join(tempfile.mkdtemp(prefix="zg_hd_"), "hd_save.json")
    check(s.handle({"cmd": "save", "path": path})["ok"], "存到別的路徑要成功")
    t = Session(seed=99)
    out = t.handle({"cmd": "load", "path": path})
    check(out["ok"] and out["state"]["minute"] == s.state()["minute"], "讀回來時間要一樣")
    check(inv_count(t.g.player.inv, "罐頭") == inv_count(s.g.player.inv, "罐頭"), "背包要一樣")
    check(t.g.flags["hd_containers"] == s.g.flags["hd_containers"], "容器裡的東西要一樣")
    os.remove(path)


@scenario
def text_commands_still_work():
    s = Session(seed=6)
    g = s.g
    g.player.inv.append(new_item("罐頭", 1))
    g.player.hunger = 60
    out = s.handle({"cmd": "text", "line": "use 罐頭"})
    check(out["ok"] and g.player.hunger < 60 and has(out["events"], "say"), "吃東西先借用文字版的指令")
    g.cur.enemies.append(Enemy("行屍", 30, dist=3))
    g.combat = True                      # 模擬規則引擎自己判定「牠們找到你了」
    out = s.handle({"cmd": "state"})
    check(has(out["events"], "intrusion") and not g.combat, "文字版式的直接開打，要改成通知畫面有東西來了")


# ================================================================ 亂按也不能壞
@scenario
def random_play_never_breaks():
    names = ["小美", "阿強", "老陳", "阿凱", "林醫師", "小傑", "阿芳", "大鬍子"]
    weapons = [None, "菜刀", "球棒", "消防斧", "手槍", "霰彈槍"]
    kinds = ["行屍", "行屍", "疾走者", "腫脹者", "掠奪者"]
    env = [{"id": "d", "kind": "door", "name": "門"}, {"id": "t", "kind": "topple", "name": "櫃子"},
           {"id": "c", "kind": "cover", "name": "沙發"}, {"id": "k", "kind": "choke", "name": "門口"},
           {"id": "n", "kind": "noise", "name": "收音機"}, {"id": "f", "kind": "fire", "name": "瓦斯爐"},
           {"id": "l", "kind": "light", "name": "電燈"}]
    results = {}
    for seed in range(120):
        rnd = random.Random(seed)
        s = Session(seed=seed % 7 + 1)
        g = s.g
        g.cur.hidden.clear()
        g.cur.enemies[:] = [Enemy(k, 30) for k in rnd.choices(kinds, k=rnd.randint(1, 5))]
        for n in rnd.sample(names, rnd.randint(0, 3)):
            recruit(g, n, trust=rnd.randint(0, 100), fear=rnd.randint(0, 100))
        w = rnd.choice(weapons)
        if w:
            arm(g, w)
            g.player.inv.extend([new_item("手槍子彈", 4), new_item("霰彈", 3)])
        g.player.inv.extend([new_item("空瓶", 2), new_item("燃燒瓶", 1), new_item("繃帶", 2), new_item("打火機")])
        room = s.handle({"cmd": "state"})["room"]
        foes = [{"uid": e["uid"], "dist": rnd.uniform(0.5, 12), "via": rnd.choice([None, "d"])} for e in room["enemies"]]
        out = s.handle({"cmd": "battle_start", "foes": foes, "opener": rnd.choice(["enemy", "player", "neutral"]),
                        "env": env})
        check(out["ok"], out.get("error"))
        steps = 0
        while out.get("battle") and not out["battle"]["over"]:
            steps += 1
            check(steps < 400, f"種子 {seed}：戰鬥打不完")
            b = out["battle"]
            check(b["current"], f"種子 {seed}：沒有結束卻沒有人輪到")
            opts = [o for o in b["options"] if o["ok"]]
            o = rnd.choice(opts)
            args = dict(o.get("args", {}))
            if o.get("targets"):
                args["target"] = rnd.choice(o["targets"])["foe"]
            if o.get("allies"):
                args["target"] = rnd.choice(o["allies"])
            if o.get("items"):
                args["item"] = rnd.choice(o["items"])
            out = s.handle({"cmd": "battle_act", "unit": b["current"], "act": o["cmd"], "args": args})
            check(out["ok"], f"種子 {seed}：{o['cmd']} {args} → {out.get('error')} {out.get('trace', '')}")
            json.dumps(out, ensure_ascii=False)
        res = out["battle"]["over"]
        results[res] = results.get(res, 0) + 1
        check(not g.combat and not s.battle, "打完狀態要清乾淨")
        check(all(e.hp > 0 for r in g.rooms.values() for e in r.enemies), "死掉的敵人不能留在房間裡")
    check(set(results) <= {"won", "fled", "dead"} and len(results) >= 2, f"結果要有輸有贏：{results}")
    print("  亂按 120 場的結果：", results)


if __name__ == "__main__":
    for name, tb in FAILURES:
        print("FAIL", name)
        print(tb)
    print(f"{len(PASSES)} passed, {len(FAILURES)} failed")
    sys.exit(1 if FAILURES else 0)
