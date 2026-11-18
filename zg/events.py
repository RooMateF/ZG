# -*- coding: utf-8 -*-
"""睡覺、夜襲、掠奪者、隨機事件、是/否事件。"""
from .data import LOCATIONS, LOOT, ITEMS
from .state import Enemy, new_item, inv_add
from .world import weighted
from . import combat


def sleep(eng, hours: int):
    g, p = eng.g, eng.g.player
    if g.combat:
        eng.say("你瘋了嗎？")
        return False
    if g.cur.enemies:
        eng.say("這裡有東西，你睡不著。")
        return False
    if g.cur.hidden and eng.rng.random() < 0.5:
        eng.say("你剛躺下就聽到旁邊有呼吸聲。不是你的。")
        return combat.ambush(eng, g.cur)
    hours = max(1, min(10, hours))
    at_base = g.base.room == g.room
    if at_base:
        eng.say(f"你檢查了門，躺下。（據點加固 {g.base.fort}）")
    else:
        eng.say("你靠著牆閉上眼，不敢睡太熟。這不是據點，什麼都可能發生。")
    for _ in range(hours):
        if eng.advance(60, resting=True) or g.combat or g.over:
            if g.combat:
                g.flags["interrupted"] = "睡到一半被吵醒"
            return True
        if night_check(eng, at_base):
            if g.combat:
                g.flags["interrupted"] = "睡到一半被吵醒"
            return True
        if at_base and g.is_night() and not g.flags.get("pending") and eng.rng.random() < 0.06:
            g.flags["pending"] = "knock"
            eng.say("有人在敲門。小聲的，很急。「拜託，我沒被咬。讓我進去。」要開門嗎？（yes / no）")
            return True
    eng.say(f"你醒了。疲勞 {int(p.fatigue)}。")
    # 貪婪隊友偷東西
    for n in g.companions():
        if n.trait == "貪婪" and n.trust < 50 and eng.rng.random() < 0.12 and p.inv:
            eng.say(f"{n.name}不見了。")
            eng.companion_leaves(n, steal=True)
    return True


def night_check(eng, at_base: bool) -> bool:
    g = eng.g
    r = g.cur
    guards = [n for n in g.companions() if n.order == "guard"] + (g.waiting_at(g.base.room) if at_base else [])
    watch = any(n.skill == "守夜" for n in guards)
    threat = g.threat.get(r.loc, 0)
    if at_base:
        chance = threat * 1.5 + g.day * 0.6 - g.base.fort * 6 - len(guards) * 8
        chance = max(1, min(25, chance))
    else:
        chance = 8 + LOCATIONS[r.loc]["danger"] * 5 + threat * 2 - len(guards) * 8
        chance = max(2, min(45, chance))
    if not g.is_night():
        chance *= 0.5
    if eng.rng.random() * 100 >= chance:
        return False
    n = 1 + (1 if g.day >= 7 else 0) + (1 if eng.rng.random() < 0.3 else 0)
    n = max(1, n - g.base.fort // 2) if at_base else n
    dist = 3 if watch else (2 if at_base else 1)
    kinds = ["行屍"] * 3 + (["疾走者"] * (3 if g.day >= 9 else 1) if g.is_night() else [])
    for _ in range(n):
        k = eng.rng.choice(kinds)
        r.enemies.append(Enemy(k, 22 if k == "疾走者" else 30, dist=dist))
    if watch:
        eng.say(f"{guards[0].name}搖醒你：「有東西來了，還在外面。」")
    elif dist == 2:
        eng.say("木板被撞得咚咚響。你抓起武器的時候，牠們已經擠進來了。")
    else:
        eng.say("你是被一股臭味醒的。牠就站在你旁邊。")
        combat.ambush_free_hit(eng, r.enemies[0])
    combat.start_combat(eng)
    return True


def raid_check(eng):
    """每日凌晨掠奪者檢查。"""
    g = eng.g
    if not g.flags.get("raiders_active") or not g.base.room:
        return
    if g.factions.get("掠奪者", 0) >= 45:
        return
    if eng.rng.random() > 0.25:
        return
    base_room = g.rooms[g.base.room]
    at_base = g.room == g.base.room
    guards = [n for n in g.companions() if n.order == "guard"] if at_base else []
    guards += g.waiting_at(g.base.room)
    if g.base.fort >= 3 or guards:
        eng.say("夜裡有人在撬你的門，撬了很久，罵了幾句，走了。")
        eng.noise(2, base_room.loc)
        return
    if at_base and eng.rng.random() < 0.3:
        eng.say("門被踹開了。兩個拿槍的人走進來：「東西，全部。」")
        for _ in range(2):
            base_room.enemies.append(Enemy("掠奪者", 40, dist=3))
        combat.start_combat(eng)
        return
    lost = []
    for it in list(g.base.storage):
        if eng.rng.random() < 0.4:
            g.base.storage.remove(it)
            lost.append(it.label())
    g.base.fort = max(0, g.base.fort - 1)
    if at_base:
        eng.say("你早上醒來發現儲物箱被翻過。你睡得太死了。")
    else:
        eng.say("你回到據點時發現門是開的。")
    if lost:
        eng.say("少了：" + "、".join(lost))
    else:
        eng.say("他們沒找到什麼，但把門弄壞了。")


# ---------------------------------------------------------------- 街道事件
def street_event(eng):
    g, p = eng.g, eng.g.player
    if g.flags.get("pending") or eng.rng.random() > 0.18:
        return
    roll = eng.rng.random()
    comps = g.companions()
    if roll < 0.2:
        loc = eng.rng.choice(list(LOCATIONS.keys()))
        g.threat[loc] = min(10, g.threat.get(loc, 0) + 2)
        eng.say(f"遠處傳來槍聲，大概在{loc}那邊。那裡接下來不會太平靜。")
    elif roll < 0.4:
        name = weighted(eng.rng, LOOT[g.cur.loc])
        g.cur.items.append(new_item(name, 1, g.day))
        eng.say(f"路邊有一具屍體，背包半開。裡面有{name}。")
    elif roll < 0.6:
        g.flags["pending"] = "help"
        eng.say("附近有人在喊救命，聲音很近。要過去看嗎？（yes / no）")
    elif roll < 0.75 and len(comps) >= 2:
        a, b = eng.rng.sample(comps, 2)
        bad = a if a.trait in ("冷酷", "貪婪") else b
        other = b if bad is a else a
        bad.trust -= 4
        other.fear += 6
        eng.say(f"{a.name}和{b.name}吵了起來，為了誰拿的水比較多。{bad.name}先動的手。")
    else:
        eng.say("一隻行屍在街尾慢慢走，背對著你。牠沒注意到你，你也沒讓牠注意到。")


def resolve_pending(eng, answer: bool):
    g, p = eng.g, eng.g.player
    kind = g.flags.pop("pending", None)
    if not kind:
        eng.say("現在沒有要回答的問題。")
        return False
    if kind == "help":
        if not answer:
            eng.say("你裝作沒聽到。聲音又喊了兩次，然後停了。")
            for n in g.companions():
                if n.trait == "忠誠":
                    n.trust -= 3
            return True
        eng.advance(20)
        if eng.rng.random() < 0.5:
            eng.say("轉角沒有人，只有兩個拿槍的人從車後面站起來。「背包放下。」")
            for _ in range(2):
                g.cur.enemies.append(Enemy("掠奪者", 40, dist=2))
            combat.start_combat(eng)
        else:
            eng.say("你找到的時候已經太遲了。他旁邊有個背包。")
            for _ in range(2):
                name = weighted(eng.rng, LOOT[g.cur.loc])
                it = new_item(name, 1, g.day)
                if not inv_add(p.inv, it, p.slots):
                    g.cur.items.append(it)
                eng.say(f"你拿了{name}。")
        return True
    if kind == "knock":
        if not answer:
            eng.say("敲門聲停了。你聽到腳步聲走遠。")
            for n in g.companions():
                if n.trait == "忠誠":
                    n.trust -= 3
            return True
        if eng.rng.random() < 0.6:
            eng.say("一個渾身是泥的男人衝進來，蹲在角落喘了半小時。走之前他留下兩樣東西，說謝謝。")
            for name in (eng.rng.choice(["罐頭", "餅乾", "泡麵"]), eng.rng.choice(["瓶裝水", "汽水"])):
                it = new_item(name, 1, g.day)
                if not inv_add(p.inv, it, p.slots):
                    g.cur.items.append(it)
                eng.say(f"得到{name}。")
        else:
            eng.say("一個渾身是泥的男人衝進來，倒在角落。你太累了，沒檢查他。")
            g.flags["knock_turn"] = 1
            eng.say("早上你是被他的呼吸聲吵醒的。不對，那不是呼吸。")
            g.cur.enemies.append(Enemy("行屍", 30, dist=1, name="昨晚的男人"))
            combat.start_combat(eng)
        return True
    return False
