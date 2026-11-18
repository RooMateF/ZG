# -*- coding: utf-8 -*-
"""指令解析與執行。"""
from .data import (ITEMS, RECIPES, DIR_ALIAS, DIRS, LOCATIONS, CLUE_ENEMY, CLUE_LOOT, CLUE_EMPTY, GOALS, FACTIONS, ENEMIES)
from .state import inv_find, inv_add, inv_remove, inv_count, new_item, Enemy, inv_take_one, sync_weapon, inv_split


def _name_qty(text):
    """「霰彈 2」-> ("霰彈", 2)；沒寫數量 -> 0（整堆）。"""
    parts = text.split()
    if len(parts) >= 2 and parts[-1].isdigit():
        return " ".join(parts[:-1]), int(parts[-1])
    return text, 0
from . import combat, npc, events

ALIASES = {
    "看": "look", "l": "look", "觀察": "look", "搜": "search", "搜索": "search", "地圖": "map", "m": "map", "狀態": "stat", "st": "stat",
    "背包": "inv", "i": "inv", "拿": "take", "撿": "take", "丟": "drop", "用": "use", "吃": "eat", "喝": "drink",
    "裝備": "equip", "製作": "craft", "說": "talk", "聊": "talk", "交易": "trade", "給": "give", "邀": "ask",
    "命令": "order", "歸隊": "rejoin", "拋下": "leave", "偷翻": "search", "潛行": "search", "檢查": "check", "據點": "claim", "加固": "fortify", "存": "store", "取": "retrieve",
    "睡": "sleep", "等": "wait", "撬": "open", "裝水": "refill", "交付": "deliver", "訊號": "signal",
    "攻擊": "attack", "a": "attack", "瞄準": "aim", "牽制": "pin", "推": "push", "逃": "flee", "f": "flee", "丟擲": "throw", "集火": "focus",
    "日誌": "journal", "幫助": "help", "說明": "help", "?": "help", "離開": "q", "quit": "q", "exit": "q",
    "是": "yes", "y": "yes", "否": "no", "不": "no", "go": "go", "走": "go",
    "看地圖": "map", "看狀態": "stat", "看背包": "inv", "看日誌": "journal",
    "new": "restart", "重開": "restart", "重來": "restart", "新遊戲": "restart",
}

HELP = """移動  n s e w u d in out（或 北南東西上下進出）
      街道用 in 進建築、out 回街上
看    look / look 人名或物品   search 翻找
物品  take 物品|all   drop 物品 [數量]（整堆或幾個）   use/eat/drink 物品   equip 武器
      craft [配方]   refill（有水源的房間裝水）
人    talk 人   trade 人 給1+給2 要（多樣湊價）   give 人 物品   take 隊友 物品（拿回）   ask 人 join
      order 人 search|rest（留守；在據點＝守夜）   leave 人   check 人
據點  claim   fortify   store 物品   retrieve 物品
      sleep [小時]   wait [小時]   open 方向（撬鎖）
戰鬥  attack [編號|head]   aim   push   flee 方向   throw 物品   use 物品   focus 編號（集火，不花回合）
結局  deliver（交付疫苗）   signal（屋頂發訊號）   yes / no 回答事件
提示：噪音到一半以上就會有東西來。多數戰鬥，逃比打好。"""

COMBAT_HELP = """attack [目標]  攻擊（近戰要距離1）   attack head  爆頭（命中低，一擊殺）
aim  瞄準，可疊三次，但牠會靠近（滿了再按是原地等牠）   focus 編號  集火：你和隊友都先打牠   push  推開（或掙脫）
pin  牽制：引開牠們注意，這回合隊友命中 +15～30（越用越熟），但牠們 80% 先撲你   flee 方向  逃跑   throw 物品  引開或燃燒瓶   use 物品
order 人 attack|back|auto  喊隊友上前 / 退後 / 跟著打（不花回合）"""


def has_tool(g, name):
    return inv_count(g.player.inv, name) > 0


def handle(eng, line: str) -> bool:
    g = eng.g
    line = line.strip()
    if not line:
        return False
    parts = line.split()
    cmd = parts[0].lower()
    args = parts[1:]
    if cmd not in ALIASES and cmd not in DIR_ALIAS and not cmd.isascii():
        # 中文指令沒空格：「看小美」「逃南」
        for k in sorted(ALIASES, key=len, reverse=True):
            if not k.isascii() and parts[0].startswith(k) and len(parts[0]) > len(k):
                cmd = k
                args = [parts[0][len(k):]] + parts[1:]
                break
    cmd = ALIASES.get(cmd, cmd)
    if g.flags.get("pending"):
        if cmd == "n":
            cmd = "no"
        if cmd not in ("yes", "no", "help", "stat", "inv", "map", "look", "journal", "q", "b"):
            eng.say("先回答：yes 或 no。")
            return False
    # 純方向
    if cmd in DIR_ALIAS:
        return do_move(eng, DIR_ALIAS[cmd])
    if cmd == "go" and args:
        d = DIR_ALIAS.get(args[0].lower())
        if not d:
            eng.say("哪個方向？")
            return False
        return do_move(eng, d)
    rest = " ".join(args)
    if g.combat and cmd in ("search", "take", "craft", "talk", "trade", "give", "ask", "leave", "check",
                            "claim", "fortify", "store", "retrieve", "sleep", "wait", "open", "refill", "deliver", "signal"):
        eng.say("現在不是時候。牠就在你面前。")
        return False
    if cmd == "yes":
        return events.resolve_pending(eng, True)
    if cmd == "no":
        return events.resolve_pending(eng, False)
    if cmd == "look":
        return do_look(eng, rest)
    if cmd == "search":
        return do_search(eng)
    if cmd == "map":
        do_map(eng)
        return False
    if cmd == "stat":
        do_stat(eng)
        return False
    if cmd == "inv":
        do_inv(eng)
        return False
    if cmd == "journal":
        for t in g.log[-12:]:
            eng.out.append(t)
        return False
    if cmd == "help":
        eng.out.append(COMBAT_HELP if g.combat else HELP)
        return False
    if cmd == "take":
        if args and g.find_npc(args[0]) and not inv_find(g.cur.items, args[0]):
            return npc.request(eng, args[0], " ".join(args[1:]))
        return do_take(eng, rest)
    if cmd == "drop":
        return do_drop(eng, rest)
    if cmd in ("use", "eat", "drink"):
        used = do_use(eng, rest)
        if used and g.combat and g.cur.enemies:
            combat.enemy_turn(eng)
        return used
    if cmd == "equip":
        ok = do_equip(eng, rest)
        if ok and g.combat and g.cur.enemies:
            combat.enemy_turn(eng)
        return ok
    if cmd == "craft":
        return do_craft(eng, rest)
    if cmd == "talk":
        return npc.talk(eng, rest)
    if cmd == "trade":
        return npc.trade(eng, args[0] if args else "", args[1] if len(args) > 1 else "", args[2] if len(args) > 2 else "")
    if cmd == "give":
        if len(args) < 2:
            eng.say("用法：give 人 物品")
            return False
        return npc.give(eng, args[0], args[1])
    if cmd == "ask":
        return npc.ask_join(eng, args[0] if args else "")
    if cmd == "order":
        if len(args) < 2:
            eng.say("用法：order 人 search|rest（留守，在據點就是守夜）")
            return False
        return npc.order(eng, args[0], args[1].lower())
    if cmd == "leave":
        return npc.leave(eng, rest)
    if cmd == "check":
        return npc.check(eng, rest)
    if cmd == "claim":
        return do_claim(eng)
    if cmd == "fortify":
        return do_fortify(eng)
    if cmd == "rejoin":
        if not g.waiting_at(g.room):
            eng.say("這裡沒有留守的人。")
            return False
        eng.rejoin_waiting()
        return False
    if cmd == "store":
        return do_store(eng, rest)
    if cmd == "retrieve":
        return do_retrieve(eng, rest)
    if cmd == "sleep":
        return events.sleep(eng, int(args[0]) if args and args[0].isdigit() else 6)
    if cmd == "wait":
        return do_wait(eng, int(args[0]) if args and args[0].isdigit() else 1)
    if cmd == "open":
        return do_open(eng, DIR_ALIAS.get(args[0].lower()) if args else None)
    if cmd == "refill":
        return do_refill(eng)
    if cmd == "deliver":
        return do_deliver(eng)
    if cmd == "signal":
        return do_signal(eng)
    if cmd == "attack":
        if not g.combat:
            if g.cur.enemies:
                combat.start_combat(eng)
            else:
                eng.say("這裡沒有東西可以打。")
                return False
        head = bool(args) and args[0].lower() in ("head", "頭")
        return combat.player_attack(eng, "" if head else rest, head)
    if cmd == "focus":
        return combat.set_focus(eng, rest)
    if cmd == "aim":
        if not g.combat:
            eng.say("沒有東西需要瞄準。")
            return False
        return combat.player_aim(eng)
    if cmd == "push":
        if not g.combat:
            eng.say("推什麼？")
            return False
        return combat.player_push(eng)
    if cmd == "pin":
        if not g.combat:
            eng.say("沒有東西要牽制。")
            return False
        return combat.player_pin(eng)
    if cmd == "flee":
        if not g.combat:
            eng.say("沒有東西在追你。直接走就好。")
            return False
        d = DIR_ALIAS.get(args[0].lower()) if args else None
        if not d:
            eng.say("往哪逃？flee 方向")
            return False
        return combat.player_flee(eng, d)
    if cmd == "throw":
        if not g.combat:
            eng.say("現在丟東西只是浪費。")
            return False
        return combat.player_throw(eng, rest)
    eng.say("看不懂。輸入 help。")
    return False


# ---------------------------------------------------------------- 移動
def do_move(eng, d):
    g, p = eng.g, eng.g.player
    r = g.cur
    if g.combat:
        eng.say(f"戰鬥中要跑就用 flee {d}。")
        return False
    if d not in r.exits:
        eng.say("那邊沒有路。")
        return False
    t = g.rooms[r.exits[d]]
    if r.enemies and not g.combat:
        # 還沒注意到你的喪屍：溜走有機率被發現
        sneak = combat.sneak_chance(g, r)
        if eng.rng.randint(1, 100) > sneak:
            for e in r.enemies:
                e.dist = min(e.dist, 2)
            combat.start_combat(eng, f"你踩到碎玻璃。牠們轉過頭來。（溜走的機率 {sneak}%）")
            return True
        eng.say(f"你貼著牆慢慢繞過去，牠們沒注意到。（{sneak}%）")
    if t.locked:
        doc = next((n for n in g.companions() if n.name == "林醫師"), None)
        if t.id == "醫院·實驗室" and doc:
            t.locked = False
            eng.say("林醫師從白袍口袋摸出門卡，刷了一下。鎖開了。「我以前就在這層工作。」")
        else:
            eng.say(f"{t.name}的門鎖著。用 open {d} 撬開（有鐵撬或消防斧比較穩，噪音大）。")
            return False
    if t.id == "軍方檢查站·帳篷" and not g.flags.get("checkpoint_gone") and g.factions["軍方"] < 70:
        eng.say("士兵把槍抬起來：「平民不准進。」")
        return False
    street = t.loc != r.loc
    minutes = 20 if street else 5
    if street and len(g.companions()) >= 2:
        minutes += 5
    if g.is_night() and street and not has_tool(g, "手電筒"):
        minutes += 10
    if g.is_night() and street and not combat.confirm_once(eng, "night", "天黑了。夜裡跨區會遇到疾走者，沒手電筒連埋伏都看不到。確定要走就再選一次。"):
        return False
    g.room = t.id
    first = not t.visited
    t.visited = True
    eng.rejoin_waiting()
    if eng.advance(minutes):
        return True
    # 勢力敵對
    f = LOCATIONS[t.loc].get("faction")
    if f and "faction" in t.tags and g.factions.get(f, 50) < 20 and not (f == "軍方" and g.flags.get("checkpoint_gone")):
        label = {"警局": "警員", "教堂": "守門人", "掠奪者": "掠奪者", "軍方": "士兵"}[f]
        kind = "士兵" if f == "軍方" else "掠奪者"
        for _ in range(2):
            t.enemies.append(Enemy(kind, ENEMIES[kind]["hp"], dist=3, name=label))
        combat.start_combat(eng, f"{label}舉起槍：「你還敢來？」")
        return True
    # 記仇的人
    for n in g.npcs:
        if n.status == "left" and n.loc == t.loc and n.room == t.name and g.flags.get(f"grudge_{n.name}") and eng.rng.random() < 0.5:
            n.status = "hostile"
            t.enemies.append(Enemy("掠奪者", n.hp, dist=2, name=n.name))
            combat.start_combat(eng, f"{n.name}從陰影裡走出來，手上多了把槍。「你還記得我嗎？」")
            return True
    # 黑暗房間沒手電筒：看得到的也看不到
    if ("dark" in t.tags or g.is_night()) and not t.is_street() and not has_tool(g, "手電筒"):
        for e in list(t.enemies):
            t.enemies.remove(e)
            e.dist = 1
            t.hidden.append(e)
        if t.enemies == [] and t.hidden and first:
            eng.say("裡面太暗了，你什麼都看不到。")
    if t.enemies and all(e.dist >= 3 for e in t.enemies) and not any(ENEMIES[e.kind].get("human") for e in t.enemies):
        ch = combat.sneak_chance(g, t)
        if t.is_street():
            eng.say("街上有" + "、".join(e.label() for e in t.enemies) + f"，還沒注意到你。可以試著直接走過去（溜過去 {ch}%），或者先動手。")
        else:
            eng.say("房間另一頭有" + "、".join(e.label() for e in t.enemies) + f"，還沒注意到你。可以偷偷翻東西（{ch}%）、先動手，或退出去（{ch}%）。")
    elif t.enemies:
        combat.start_combat(eng, "有東西在這裡。")
    elif street:
        events.street_event(eng)
    eng.say(eng.room_desc(brief=not first))
    return True


# ---------------------------------------------------------------- 看
def do_look(eng, text=""):
    g = eng.g
    if text:
        n = g.find_npc(text)
        if n:
            npc.look_npc(eng, n)
            return False
        it = inv_find(g.player.inv, text) or inv_find(g.cur.items, text)
        if it:
            describe_item(eng, it)
            return False
        f = npc.faction_rep_here(eng)
        if f:
            eng.say(FACTIONS[f]["greet"])
            return False
        eng.say("沒看到那個東西。")
        return False
    r = g.cur
    eng.say(eng.room_desc())
    if r.is_street():
        return False
    # 線索（依房間固定，不隨機跳動）
    h = sum(ord(c) for c in r.id) % 10
    if r.hidden and h < 9:
        eng.say(CLUE_ENEMY[h % len(CLUE_ENEMY)])
    if r.loot:
        eng.say(CLUE_LOOT[h % len(CLUE_LOOT)])
    elif r.searched:
        eng.say(CLUE_EMPTY[h % len(CLUE_EMPTY)])
    if r.rumor:
        eng.say(f"（有人說這裡有{r.rumor}）")
    if "water" in r.tags:
        eng.say("這裡有水龍頭。" + ("（第 3 天起只剩髒水）" if g.day >= 3 else ""))
    if r.base_ok and g.base.room != r.id:
        eng.say("這裡可以當據點（claim）。")
    f = npc.faction_rep_here(eng)
    if f:
        eng.say(f"{FACTIONS[f]['rep']}在這裡。")
    return False


def describe_item(eng, it):
    s = ITEMS[it.name]
    k = s["kind"]
    if k == "weapon":
        d = f"傷害{s['dmg'][0]}-{s['dmg'][1]} 命中{s['hit']} 噪音{s['noise']} 射程{s['range']}"
        if s.get("ammo"):
            d += f" 需要{s['ammo']}"
        eng.say(f"{it.label()}：{d}")
    elif k == "food":
        eng.say(f"{it.name}：飢餓 -{s['hunger']}" + (f"，{s['spoil']} 天內要吃" if s.get("spoil") else "") + ("，看起來不太對勁" if s.get("sick") else ""))
    elif k == "water":
        eng.say(f"{it.name}：口渴 -{s['thirst']}" + ("，喝了可能拉肚子" if s.get("sick") else ""))
    elif k == "med":
        eff = {"bandage": "止血", "antibiotic": "減緩感染 12 小時", "painkiller": "減傷 6 小時", "firstaid": "回血 40 並止血", "unknown": "不知道是什麼"}[s["effect"]]
        eng.say(f"{it.name}：{eff}")
    elif k == "throw":
        eng.say(f"{it.name}：" + ("丟出去引開注意" if s.get("distract") else "丟向遠處的敵人，燒牠們"))
    else:
        eng.say(f"{it.name}：" + {"手電筒": "黑暗房間和夜晚搜索用", "收音機": "撤離需要，use 可以聽廣播", "訊號彈": "第 14 天屋頂用",
                                   "打火機": "煮水用", "背包": "use 增加 5 格", "疫苗樣本": "送到軍方檢查站", "日記": "上一個你留下的"}.get(it.name, "材料"))


# ---------------------------------------------------------------- 搜索
def do_search(eng, by=None):
    g, p = eng.g, eng.g.player
    r = g.cur
    if g.combat:
        eng.say("現在？")
        return False
    if r.is_street():
        eng.say("街上沒什麼好翻的，而且太顯眼。")
        return False
    dark = ("dark" in r.tags or g.is_night()) and not has_tool(g, "手電筒")
    minutes = 30 if dark else 20
    if r.enemies:
        # 牠們還沒發現你：偷翻。一個人最穩，人多手雜
        if by is not None:
            eng.say("牠們就在那邊，叫人翻東西太吵。要翻你自己來。")
            return False
        ch = combat.sneak_chance(g, r)
        eng.noise(0.5)
        if eng.rng.randint(1, 100) > ch:
            for e in r.enemies:
                e.dist = min(e.dist, 3)
            combat.start_combat(eng, f"抽屜卡住了，一聲悶響。牠們轉過頭來。（偷翻成功率 {ch}%）")
            return True
        eng.say(f"你壓低身子，一格一格摸過去。（{ch}%）")
    else:
        eng.noise(1.0)
    if r.hidden:
        if by is None:
            return combat.ambush(eng, r)
        e = r.hidden.pop(0)
        e.dist = 2
        r.enemies.append(e)
        eng.say(f"{by.name}尖叫著跳開，一隻{e.kind}從櫃子後面站起來。")
        combat.start_combat(eng)
        return True
    if eng.advance(minutes):
        return True
    r.searched += 1
    if not r.loot:
        h = sum(ord(c) for c in r.id) % len(CLUE_EMPTY)
        eng.say(CLUE_EMPTY[h])
        if r.rumor:
            eng.say(f"沒有情報說的{r.rumor}。那個人騙了你。")
            r.rumor = None
        return True
    n = 1
    if r.searched == 1 and r.loot_level >= 2:
        n += 1
    if by and by.skill == "搜索":
        n += 1
    if dark:
        n = max(1, n - 1)
    found = []
    for _ in range(n):
        if r.loot:
            found.append(r.loot.pop(eng.rng.randrange(len(r.loot))))
    names = []
    for it in found:
        if not inv_add(p.inv, it, p.slots):
            r.items.append(it)
            eng.say(f"背包滿了，{it.label()}放在地上。")
        names.append(it.label())
        if it.name == "疫苗樣本":
            eng.say("一個金屬保溫盒，裡面是一管標著編號的液體。這就是了。")
    eng.say(("你" if by is None else by.name) + "找到：" + "、".join(names))
    if r.rumor:
        if any(it.name == r.rumor for it in found) or any(it.name == r.rumor for it in r.loot):
            eng.say("情報是真的。")
        elif not r.loot:
            eng.say(f"沒有情報說的{r.rumor}。那個人騙了你。")
        r.rumor = None
    if r.loot:
        eng.say("好像還有東西沒翻到。")
    elif r.items:
        eng.say("沒東西可翻了，地上的記得撿。")
    else:
        eng.say("這裡翻乾淨了。")
    return True


# ---------------------------------------------------------------- 物品
def do_take(eng, text):
    g, p = eng.g, eng.g.player
    r = g.cur
    if not r.items:
        eng.say("地上沒東西。")
        return False
    targets = list(r.items) if text in ("all", "全部", "") else [inv_find(r.items, text)]
    if not targets or targets[0] is None:
        eng.say("地上沒有那個。")
        return False
    for it in targets:
        if inv_add(p.inv, it, p.slots):
            r.items[:] = [x for x in r.items if x is not it]
            eng.say(f"拿了{it.label()}。")
            if it.name == "日記":
                eng.say("日記最後一頁：「如果你在看這個，別走我走過的路。」")
        else:
            eng.say(f"背包滿了（{p.slots} 格）。")
            break
    return False


def do_drop(eng, text):
    g, p = eng.g, eng.g.player
    name, qty = _name_qty(text)
    it = inv_find(p.inv, name)
    if not it:
        eng.say("你沒有那個。")
        return False
    one = inv_split(p.inv, it, qty)
    inv_add(g.cur.items, one)            # 地上同種的會疊在一起
    sync_weapon(p)
    eng.say(f"丟下{one.label()}。")
    return False


def do_equip(eng, text):
    p = eng.g.player
    it = inv_find(p.inv, text)
    if not it or ITEMS[it.name]["kind"] != "weapon":
        eng.say("那不是武器。")
        return False
    p.weapon = it.name
    eng.say(f"你握緊{it.name}。")
    return True


def do_use(eng, text):
    g, p = eng.g, eng.g.player
    it = inv_find(p.inv, text)
    if not it:
        eng.say("你沒有那個。")
        return False
    s = ITEMS[it.name]
    k = s["kind"]
    if k == "weapon":
        return do_equip(eng, text)
    consumed = False
    if k == "food":
        inv_remove(p.inv, it.name, 1)
        consumed = True
        p.hunger = max(0, p.hunger - s["hunger"])
        p.thirst = max(0, min(100, p.thirst - s.get("thirst", 0)))
        p.fatigue = max(0, p.fatigue + s.get("fatigue", 0))
        if s.get("sick") and eng.rng.random() < 0.7:
            p.sick = 6
            eng.say(f"你吃了{it.name}。味道不對，但你吃完了。半小時後你開始後悔。")
        else:
            eng.say(f"你吃了{it.name}。飢餓 {int(p.hunger)}。")
    elif k == "water":
        inv_remove(p.inv, it.name, 1)
        consumed = True
        p.thirst = max(0, p.thirst - s["thirst"])
        if it.name != "髒水":
            inv_add(p.inv, new_item("空瓶"), p.slots)
        if s.get("sick") and eng.rng.random() < 0.5:
            p.sick = 5
            eng.say(f"你喝了{it.name}。有股味道。")
        else:
            eng.say(f"你喝了{it.name}。口渴 {int(p.thirst)}。")
    elif k == "med":
        eff = s["effect"]
        inv_remove(p.inv, it.name, 1)
        consumed = True
        if eff == "bandage":
            if p.bleeding:
                p.bleeding = False
                p.hp = min(100, p.hp + 10)
                eng.say("你綁緊繃帶，血止住了。")
            else:
                p.hp = min(100, p.hp + 10)
                eng.say("你沒在流血，但還是包了一下。")
        elif eff == "antibiotic":
            p.antibiotic = 12
            p.infection = max(0, p.infection - 25)
            eng.say("你吞了抗生素。如果你被感染了，這會壓下去一些，但一顆不夠。")
        elif eff == "painkiller":
            p.painkiller = 6
            p.hp = min(100, p.hp + 5)
            eng.say("止痛藥。接下來幾小時你會比較耐打。")
        elif eff == "firstaid":
            p.hp = min(100, p.hp + 40)
            p.bleeding = False
            eng.say(f"你花了十分鐘處理傷口。血量 {p.hp}。")
            eng.advance(10)
        elif eff == "unknown":
            roll = eng.rng.random()
            if roll < 0.4:
                p.antibiotic = 12
                p.infection = max(0, p.infection - 10)
                eng.say("藥丸是苦的。幾小時後你覺得身體沒那麼燙了。（是抗生素）")
            elif roll < 0.7:
                eng.say("什麼感覺都沒有。（大概是維他命）")
            else:
                p.sick = 4
                eng.say("十分鐘後你開始吐。（不是好東西）")
    elif k == "tool":
        if it.name == "收音機":
            do_radio(eng)
        elif it.name == "背包":
            inv_remove(p.inv, "背包", 1)
            p.slots += 5
            eng.say(f"你把東西重新塞過。背包格數變成 {p.slots}。")
        elif it.name == "訊號彈":
            return do_signal(eng)
        else:
            eng.say(f"{it.name}帶著就會自動用到。")
    elif k == "throw":
        if g.combat:
            return combat.player_throw(eng, it.name)
        eng.say("現在丟只是浪費。")
    elif it.name == "酒精":
        if p.infection > 0 or p.bleeding:
            inv_remove(p.inv, "酒精", 1)
            before = p.infection
            p.infection = max(0, p.infection - 15)
            consumed = True
            eng.say("你咬著牙把酒精倒在傷口上。痛到眼前發白，但乾淨多了。" + ("" if before > 15 else "（傷口大致處理好了）"))
            eng.advance(10)
        else:
            eng.say("身上沒有傷口。留著做燃燒瓶或換東西。")
    elif it.name == "日記":
        eng.say("「第 3 天水停了。第 6 天阿凱偷走了我的罐頭。第 9 天我在超市被咬。別睡在沒加固的地方。」")
    else:
        eng.say("那個沒辦法直接用。可能是製作材料（craft）。")
    return consumed


def do_radio(eng):
    g = eng.g
    from .data import RADIO
    eng.say("你轉著頻道。大部分是雜訊。")
    if g.day + 1 in RADIO:
        eng.say("緊急廣播：「" + RADIO[g.day + 1] + "」")
    hot = [loc for loc, t in g.threat.items() if t >= 6]
    if hot:
        eng.say("「……" + "、".join(hot) + "一帶偵測到大量移動，請避開……」")
    if g.goal == "撤離":
        eng.say("「……第 14 天……辦公大樓……0600 到 1200……」")
    elif g.goal == "疫苗":
        eng.say("「……檢查站將於第 11 天撤離……生物樣本優先……」")
    else:
        eng.say("「……教堂……收容……車輛……第 14 天……」")
    if g.day < 11:
        eng.say(f"「……北方檢查站仍在運作……重複，第 11 天前……」")
    else:
        eng.say("北方頻道只剩雜訊。")


def do_craft(eng, text):
    g, p = eng.g, eng.g.player
    if not text:
        for name, rc in RECIPES.items():
            need = "+".join(f"{k}x{v}" if v else k for k, v in rc["need"].items()) or rc.get("note", "")
            if rc.get("tool"):
                need += f"（需要{rc['tool']}）"
            ok = can_craft(p, rc)
            eng.out.append(f"  {'可' if ok else '　'} {name}：{need}")
        eng.out.append("用法：craft 配方名")
        return False
    name = next((k for k in RECIPES if k.startswith(text)), None)
    if not name:
        eng.say("沒有這個配方。")
        return False
    rc = RECIPES[name]
    if not can_craft(p, rc):
        eng.say("材料不夠。")
        return False
    if name == "修理":
        wi = next((it for it in p.inv if it.name == p.weapon), None)
        s = ITEMS[wi.name] if wi else None
        if not wi or s["dur"] >= 99:
            eng.say("手上要拿著近戰武器才能修。")
            return False
        if wi.dur >= s["dur"]:
            eng.say(f"{wi.name}還很好，不用修。")
            return False
        inv_remove(p.inv, "鐵絲", 1)
        inv_remove(p.inv, "布料", 1)
        wi.dur = min(s["dur"], wi.dur + 4)
        eng.say(f"你用鐵絲把{wi.name}重新綁緊。耐久 {wi.dur}/{s['dur']}。")
        return not eng.advance(rc["minutes"])
    need = rc["need"]
    if not all(inv_count(p.inv, k) >= v for k, v in need.items()) and rc.get("alt"):
        need = rc["alt"]
    out, qty = rc["out"]
    # 先確認放得下：產物能疊進現有的堆，或扣掉材料後有空格。放不下就什麼都不做（以前會扣血扣材料然後東西消失）
    fits = new_item(out, qty, g.day).stackable and inv_count(p.inv, out) > 0
    if not fits:
        freed = sum(1 for k, v in need.items() if v and inv_count(p.inv, k) == v)
        fits = len(p.inv) - freed < p.slots
    if not fits:
        eng.say(f"背包滿了（{p.slots} 格），{out}沒地方放。先丟點東西再做。")
        return False
    for k, v in need.items():
        if v:
            inv_remove(p.inv, k, v)
    if rc.get("hp"):
        p.hp += rc["hp"]
    inv_add(p.inv, new_item(out, qty, g.day), p.slots)
    eng.say(f"做好了：{out}x{qty}。")
    return not eng.advance(rc["minutes"])


def can_craft(p, rc):
    if rc.get("tool") and inv_count(p.inv, rc["tool"]) <= 0:
        return False
    ok = all(inv_count(p.inv, k) >= v for k, v in rc["need"].items() if v)
    if not ok and rc.get("alt"):
        ok = all(inv_count(p.inv, k) >= v for k, v in rc["alt"].items())
    return ok


def do_refill(eng):
    g, p = eng.g, eng.g.player
    r = g.cur
    if "water" not in r.tags:
        eng.say("這裡沒有水源。")
        return False
    if inv_count(p.inv, "空瓶") <= 0:
        eng.say("你需要空瓶。")
        return False
    inv_remove(p.inv, "空瓶", 1)
    clean = g.day < 3 and r.loc not in ("公園", "加油站")
    inv_add(p.inv, new_item("瓶裝水" if clean else "髒水"), p.slots)
    eng.say("你裝了一瓶" + ("水。" if clean else "髒水。煮過再喝（craft 淨水）。"))
    eng.advance(5)
    return True


# ---------------------------------------------------------------- 據點
def do_claim(eng):
    g = eng.g
    r = g.cur
    if not r.base_ok:
        eng.say("這裡不適合當據點。")
        return False
    if r.enemies or r.hidden:
        eng.say("先把這裡清乾淨。" if r.enemies else "你總覺得這裡有東西。先搜過再說。")
        return False
    if g.base.room == r.id:
        eng.say("這裡已經是你的據點了。")
        return False
    if g.base.room:
        old = g.rooms[g.base.room]
        old.items.extend(g.base.storage)
        g.base.storage = []
        eng.say(f"你放棄了{old.full}。留在那裡的東西還在地上。")
    g.base.room = r.id
    g.base.fort = 0
    eng.say(f"你把{r.name}當成據點。可以 store 東西、sleep 回復、fortify 加固。")
    return False


def do_fortify(eng):
    g, p = eng.g, eng.g.player
    if g.base.room != g.room:
        eng.say("只能加固據點。")
        return False
    if g.base.fort >= 5:
        eng.say("已經釘得不能再釘了。")
        return False
    if inv_count(p.inv, "木板") < 2 or inv_count(p.inv, "釘子") < 1:
        eng.say("需要木板x2、釘子x1。")
        return False
    inv_remove(p.inv, "木板", 2)
    inv_remove(p.inv, "釘子", 1)
    g.base.fort += 1
    eng.noise(2)
    eng.say(f"你把木板釘上門窗。加固等級 {g.base.fort}/5。敲打聲傳得很遠。")
    return not eng.advance(60)


def do_store(eng, text):
    g, p = eng.g, eng.g.player
    if g.base.room != g.room:
        eng.say("只能在據點儲物。")
        return False
    name, qty = _name_qty(text)
    it = inv_find(p.inv, name)
    if not it:
        eng.say("你沒有那個。")
        return False
    one = inv_split(p.inv, it, qty)
    inv_add(g.base.storage, one)
    sync_weapon(p)
    eng.say(f"放進儲物箱：{one.label()}。")
    return False


def do_retrieve(eng, text):
    g, p = eng.g, eng.g.player
    if g.base.room != g.room:
        eng.say("只能在據點取物。")
        return False
    if not text:
        eng.say("儲物箱：" + ("、".join(it.label() for it in g.base.storage) or "空的"))
        return False
    name, qty = _name_qty(text)
    it = inv_find(g.base.storage, name)
    if not it:
        eng.say("儲物箱裡沒有那個。")
        return False
    one = inv_split(g.base.storage, it, qty)
    if not inv_add(p.inv, one, p.slots):
        inv_add(g.base.storage, one)
        eng.say("背包滿了。")
        return False
    eng.say(f"拿出{one.label()}。")
    return False


def do_wait(eng, hours):
    g = eng.g
    if g.combat:
        eng.say("現在等只會被咬。")
        return False
    hours = max(1, min(12, hours))
    eng.say(f"你等了{hours}小時。")
    eng.advance(hours * 60)
    if g.combat:
        g.flags["interrupted"] = "等待被打斷"
    return True


def do_open(eng, d):
    g, p = eng.g, eng.g.player
    r = g.cur
    if not d or d not in r.exits:
        eng.say("撬哪邊？open 方向")
        return False
    t = g.rooms[r.exits[d]]
    if t.locked and not combat.confirm_once(eng, "open", "撬鎖噪音很大，這一區的喪屍會聚過來；沒工具用肩膀成功率很低。確定要撬就再選一次。"):
        return False
    if not t.locked:
        eng.say("那邊沒鎖。")
        return False
    if g.combat:
        eng.say("現在撬門？")
        return False
    if has_tool(g, "消防斧"):
        chance, noise, minutes, how = 95, 3, 10, "斧頭"
    elif has_tool(g, "鐵撬"):
        chance, noise, minutes, how = 80, 3, 20, "鐵撬"
    else:
        chance, noise, minutes, how = (15 if t.loot_level >= 3 else 30), 4, 10, "肩膀"
    eng.noise(noise)
    if t.id == "警局·軍械庫" and g.factions["警局"] >= 20:
        g.factions["警局"] -= 50
        eng.say("你剛動手，就聽到背後拉槍機的聲音。警局的人不會原諒這個。")
    if eng.rng.randint(1, 100) <= chance:
        t.locked = False
        eng.say(f"你用{how}撬開了{t.name}的門。聲音很大。")
    else:
        eng.say(f"你用{how}弄了半天，門還是沒開。聲音很大。")
    if r.enemies and not g.combat:
        for e in r.enemies:
            e.dist = min(e.dist, 3)
        combat.start_combat(eng, "撬門的聲音在房裡迴盪。牠們轉過頭來。")
        return True
    return not eng.advance(minutes)


def do_deliver(eng):
    g, p = eng.g, eng.g.player
    f = npc.faction_rep_here(eng)
    if f != "軍方":
        eng.say("這裡沒有人收。")
        return False
    if inv_count(p.inv, "疫苗樣本") <= 0:
        eng.say("軍官：「沒有樣本就滾。」")
        return False
    if g.day < 4:
        eng.say("軍官看著保溫盒：「指揮部還沒下令接收。第 4 天之後再來，別弄丟它。」")
        return False
    g.over = "vaccine"
    eng.say("軍官看了一眼保溫盒上的編號，對無線電說了幾句。鐵絲網打開了。")
    return True


def do_signal(eng):
    g, p = eng.g, eng.g.player
    if g.room != "辦公大樓·屋頂":
        eng.say("要在辦公大樓的屋頂。")
        return False
    if g.day < 14:
        eng.say("還沒到第 14 天。現在放只是浪費，還會引來東西。")
        return False
    if not (6 <= g.hour < 12):
        eng.say("直升機只在 06:00 到 12:00 之間來。")
        return False
    if inv_count(p.inv, "訊號彈") <= 0:
        eng.say("你沒有訊號彈。")
        return False
    if inv_count(p.inv, "收音機") <= 0:
        eng.say("沒有收音機，他們聽不到你確認位置。")
        return False
    if g.flags.get("signal_at"):
        eng.say("已經放了，撐住。")
        return False
    inv_remove(p.inv, "訊號彈", 1)
    g.flags["signal_at"] = g.day * 1440 + g.minute
    eng.noise(5)
    eng.say("紅色的光拖著煙升上天空。收音機裡：「看到了，三小時。守住屋頂。」")
    eng.say("整棟樓都聽到了。樓梯間開始有聲音。")
    return True


# ---------------------------------------------------------------- 資訊
def do_map(eng):
    from .mapdraw import city_map, floor_map
    g = eng.g
    eng.out.append(city_map(g))
    eng.out.append("")
    eng.out.append(floor_map(g))


def do_stat(eng):
    g, p = eng.g, eng.g.player
    from .intel import goal_checklist
    lines = [f"目標：{g.goal}。{GOALS[g.goal]}"]
    lines.extend("  " + x for x in goal_checklist(g))
    lines.append(f"血量 {p.hp}/100  飢餓 {int(p.hunger)}  口渴 {int(p.thirst)}  疲勞 {int(p.fatigue)}  體力 {p.stamina}/{p.max_stamina()}")
    cond = []
    if p.bleeding:
        cond.append("流血中")
    if p.sick:
        cond.append(f"腹痛（{p.sick}h）")
    if p.antibiotic:
        cond.append(f"抗生素（{p.antibiotic}h）")
    if p.painkiller:
        cond.append(f"止痛（{p.painkiller}h）")
    if p.infection > 60:
        cond.append("傷口發黑")
    elif p.infection > 30:
        cond.append("發冷")
    elif p.infection > 0:
        cond.append("有傷口")
    lines.append("狀態：" + ("、".join(cond) or "正常"))
    for n in g.companions():
        extra = f"，{n.trait}，{n.skill}" if n.intro_seen else ""
        if n.order == "guard":
            extra += "，守夜"
        if n.revealed and n.infected:
            from .npc import cure_chance
            extra += f"，已感染（還 {max(0, 3 - (g.day - n.infect_day))} 天轉化；抗生素 {cure_chance(g, n)}% 治好）"
        if n.quest == "given":
            from .data import QUESTS
            extra += f"，請託：{QUESTS[n.name]['want']}"
        from .combat import is_bonded
        if is_bonded(n):
            extra += "，羈絆"
        lines.append(f"隊友 {n.name}：血 {n.hp}/{n.max_hp}，信任 {'高' if n.trust >= 60 else '中' if n.trust >= 35 else '低'}{extra}")
    for n in g.waiting():
        rid = f"{n.loc}·{n.room}"
        lines.append(f"留守 {n.name}：在{'據點' if rid == g.base.room else rid}，血 {n.hp}/{n.max_hp}，第 {n.wait_day} 天留下的（走進那間房他就歸隊）")
    lines.append("勢力：" + "  ".join(f"{f}{'友好' if a >= 70 else '中立' if a >= 20 else '敵對'}" for f, a in g.factions.items()))
    if g.base.room:
        lines.append(f"據點：{g.rooms[g.base.room].full}，加固 {g.base.fort}/5，儲物 {len(g.base.storage)} 項")
    nf, nw, food, water = eng.rations()
    if nf or nw:
        lines.append(f"今晚隊友口糧：要 {nf} 份食物 {nw} 份水（食物兩天一份），手邊食物 {food} 水 {water}" + ("" if food >= nf and water >= nw else "（不夠，沒吃的人信任會掉）"))
    if g.goal == "護送":
        lines.append(f"已送到教堂：{g.placed}/5")
    from .combat import experience, STANCE_NAME
    xp = experience(g)
    lines.append(f"戰鬥經驗：{xp['label']}（親手擊殺 {g.flags.get('xp_kills', 0)}，合計 {g.flags.get('kills', 0)}）"
                 + (f"，命中 +{xp['hit']}" if xp["hit"] else "") + (f"，爆頭另 +{xp['head']}" if xp["head"] else "")
                 + ("，近戰省體力" if xp["stam"] else ""))
    from .combat import pin_level, pin_bonus
    if g.flags.get("pin_uses"):
        lines.append(f"牽制熟練：{pin_level(g)}/3（用過 {g.flags['pin_uses']} 次，牽制時隊友命中 +{pin_bonus(g)}）")
    if g.combat and g.companions():
        lines.append("隊友姿態：" + "  ".join(f"{n.name}{STANCE_NAME.get(n.stance, '')}" for n in g.companions()))
    eng.out.extend(lines)


def do_inv(eng):
    p = eng.g.player
    if not p.inv:
        eng.out.append("背包是空的。")
        return
    parts = []
    marked = False
    for it in p.inv:
        tag = ""
        if it.name == p.weapon and not marked:
            tag, marked = "[裝備]", True
        parts.append(tag + it.label())
    eng.out.append(f"背包（{len(p.inv)}/{p.slots}）：" + "、".join(parts))
