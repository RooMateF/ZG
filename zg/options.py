# -*- coding: utf-8 -*-
"""多層數字選單。每個選項是 (顯示文字, 目標)，目標是指令字串或 callable(g) -> Menu。"""
from .data import ITEMS, TRAIT_JOIN, FACTIONS, RECIPES
from .state import inv_count
from .npc import faction_rep_here
from .commands import can_craft
from .combat import aim_bonus, AIM_MAX, hit_chance, flee_chance, escape_chance, rates_after_aim, PUSH_CHANCE, numbered, pick_target, focused, is_bonded, ensure_uids
from .data import QUESTS

MAX_TOP = 9


class Menu:
    def __init__(self, title, entries, parent=None):
        self.title = title
        self.entries = entries   # [(label, target)]
        self.parent = parent


class _Eng:
    def __init__(self, g):
        self.g = g



TIME_MARK = "耗"   # 選項後面的耗時標記。主控台中文字型沒有 ⏱ 這類符號，所以用字


def tc(minutes) -> str:
    """選項用的耗時字樣：耗20分。"""
    return f"{TIME_MARK}{minutes}分"

def _label(r, t):
    return t.loc if t.loc != r.loc else t.name


def _move_min(g, r, t):
    """跟 commands.do_move 同一套算法。"""
    street = t.loc != r.loc
    m = 20 if street else 5
    if street and len(g.companions()) >= 2:
        m += 5
    if g.is_night() and street and not inv_count(g.player.inv, "手電筒"):
        m += 10
    return m


def _open_info(g, t):
    """跟 commands.do_open 同一套：回傳 (成功率, 分鐘, 用什麼)。"""
    p = g.player
    if inv_count(p.inv, "消防斧"):
        return 95, 10, "斧頭"
    if inv_count(p.inv, "鐵撬"):
        return 80, 20, "鐵撬"
    return (15 if t.loot_level >= 3 else 30), 10, "肩膀"


def _hours_to_dawn(g):
    h = g.hour
    return (6 - h) % 24 or 8


# ---------------------------------------------------------------- 主選單
def build(g):
    """主選單：情境動作 + 分類。"""
    p = g.player
    r = g.cur
    opts = []
    if g.over:
        return []
    if g.flags.get("pending"):
        return [("是", "yes"), ("否", "no")]

    def add(label, cmd):
        if cmd not in [c for _, c in opts]:
            opts.append((label, cmd))

    if g.combat and r.enemies:
        adj = any(e.dist == 1 for e in r.enemies)
        E = _Eng(g)
        hc, hh = rates_after_aim(E, 0)
        nc, nh = rates_after_aim(E, 1)
        if p.grabbed:
            add(f"掙脫({escape_chance(E)}%)", "push")
        ensure_uids(g)
        wi0 = next((it for it in p.inv if it.name == p.weapon), None)
        reach = ITEMS[wi0.name]["range"] if wi0 else 1
        tgt = pick_target(g, reach)
        tname = f"{tgt.uid}:{tgt.label()}" if tgt else ""
        from .combat import penalty_tags, swing_cost
        pen = penalty_tags(g, cost=swing_cost(E))
        if adj:
            add(f"攻擊 {tname}({hc}%{pen})", "attack")
            add(f"爆頭 {tname}({hh}%{pen}，中了一擊殺)", "attack head")
            if int(p.aimed) < AIM_MAX:
                add(f"瞄準(會挨打；之後攻擊{nc}% 爆頭{nh}%)", "aim")
            if not p.grabbed:
                add(f"推開({PUSH_CHANCE}%，推開後牠停一回合)", "push")
        else:
            if int(p.aimed) < AIM_MAX:
                add(f"瞄準等牠靠近(之後攻擊{nc}% 爆頭{nh}%)", "aim")
            else:
                add(f"保持瞄準等牠靠近(攻擊{hc}% 爆頭{hh}%)", "aim")
            wi = next((it for it in p.inv if it.name == p.weapon), None)
            if wi and ITEMS[wi.name]["range"] > 1:
                add(f"開槍 {tname}({hc}%{pen})", "attack")
        helpers = [n for n in g.companions() if n.stance != "hide"]
        if helpers:
            from .combat import pin_bonus, pin_level, PIN_DRAW
            add(f"牽制(隊友命中+{pin_bonus(g)}，牠們{PIN_DRAW}%先撲你，熟練{pin_level(g)}/3)", "pin")
        for name in ("燃燒瓶", "石頭", "空瓶"):
            if inv_count(p.inv, name):
                add(f"丟{name}", f"throw {name}")
                break
        if p.bleeding and inv_count(p.inv, "繃帶"):
            add("用繃帶", "use 繃帶")
        if p.hp < 40 and inv_count(p.inv, "急救包"):
            add("用急救包", "use 急救包")
        for d, tid in r.exits.items():
            t = g.rooms[tid]
            if not t.locked:
                add(f"逃往{d}({_label(r, t)}) {flee_chance(_Eng(g))}%", f"flee {d}")
        if len(r.enemies) >= 2:
            f = focused(g)
            opts.append((f"集火{'：' + str(f.uid) + ':' + f.label() if f else '(選一隻大家一起打)'}", focus_menu))
        if g.companions():
            opts.append(("指揮隊友(不花回合)", squad_menu))
        return opts

    # ---- 情境動作
    if p.bleeding:
        if inv_count(p.inv, "繃帶"):
            add("用繃帶止血", "use 繃帶")
        elif inv_count(p.inv, "布料") >= 2:
            add("做繃帶(布料x2)", "craft 繃帶")
        else:
            add("撕衣服做布料(扣5血)", "craft 布料")
    if p.hp < 40 and inv_count(p.inv, "急救包"):
        add("用急救包", "use 急救包")
    if r.loc == "教堂" and faction_rep_here(_Eng(g)) == "教堂":
        for n in g.companions():
            tag = "被咬了，會被拒收" if (n.revealed and n.infected) else ("沒被咬" if n.revealed else "沒檢查過")
            add(f"把{n.name}交給修女({tag})", f"leave {n.name}")
    sneak = None
    if r.enemies and not g.combat:
        from .combat import sneak_chance
        sneak = sneak_chance(g, r)
        add("先動手攻擊(牠們還沒發現你，先出手有瞄準時間)", "attack")
    if not r.is_street() and (r.loot or not r.searched):
        dark = ("dark" in r.tags or g.is_night()) and not inv_count(p.inv, "手電筒")
        if sneak is not None:
            who = "一個人最穩" if not g.companions() else f"帶{len(g.companions())}人會吵"
            add(f"偷偷翻東西(成功{sneak}%，{who}，{tc(30 if dark else 20)})", "search")
        else:
            add(f"搜索這裡({tc(30 if dark else 20)}" + ("，很暗" if dark else "") + ")", "search")
    if r.items:
        if len(r.items) == 1:
            add(f"撿起{r.items[0].label()}", "take all")
        else:
            names = "、".join(it.label() for it in r.items)
            if len(names) > 16:
                names = names[:15] + "…"
            opts.append((f"撿東西({len(r.items)}樣：{names})", ground_menu))
    for n in g.npcs_here():
        if n.trust >= TRAIT_JOIN[n.trait] and len(g.companions()) < (4 if g.goal == "護送" else 3):
            add(f"邀{n.name}加入", f"ask {n.name} join")
    f = faction_rep_here(_Eng(g))
    if f == "軍方" and inv_count(p.inv, "疫苗樣本"):
        add("交付疫苗樣本", "deliver")
    if r.id == "辦公大樓·屋頂" and g.day >= 14 and inv_count(p.inv, "訊號彈") and not g.flags.get("signal_at"):
        add("發射訊號彈", "signal")
    if r.base_ok and g.base.room != r.id and not r.hidden:
        add(f"設為據點({tc(5)})", "claim")
    if p.hunger > 50:
        food = next((it for it in p.inv if ITEMS[it.name]["kind"] == "food" and it.name != "腐壞食物"), None)
        if food:
            add(f"吃{food.name}", f"use {food.name}")
    if p.thirst > 50:
        water = next((it for it in p.inv if ITEMS[it.name]["kind"] == "water" and it.name != "髒水"), None)
        if water:
            add(f"喝{water.name}", f"use {water.name}")
    if "water" in r.tags and inv_count(p.inv, "空瓶"):
        add(f"用空瓶裝水({tc(5)})", "refill")
    acts = opts
    # ---- 移動
    moves = []
    for d, tid in r.exits.items():
        t = g.rooms[tid]
        if t.locked:
            ch, mn, how = _open_info(g, t)
            moves.append((f"撬開{d}({t.name}) {how}{ch}% {tc(mn)}" + ("，一定驚動牠們" if sneak is not None else ""), f"open {d}"))
        elif t.loc != r.loc:
            moves.append((f"{d}→[{t.loc}] 跨區 {tc(_move_min(g, r, t))}" + (f" 溜{sneak}%" if sneak is not None else ""), f"go {d}"))
        else:
            moves.append((f"{d}→{t.name} {tc(_move_min(g, r, t))}" + (f" 溜{sneak}%" if sneak is not None else ""), f"go {d}"))
    # ---- 據點（人在據點才出現）
    base = []
    if g.base.room == r.id:
        if not r.enemies:
            if g.hour >= 17 or g.hour < 6:
                base.append((f"睡到天亮({_hours_to_dawn(g)}小時)", f"sleep {_hours_to_dawn(g)}"))
            elif p.fatigue >= 40:
                base.append(("小睡 2 小時", "sleep 2"))
        ok = inv_count(p.inv, "木板") >= 2 and inv_count(p.inv, "釘子") >= 1
        base.append((f"加固({g.base.fort}/5，木板x2 釘子x1{'' if ok else '，材料不夠'}) {tc(60)}", "fortify" if ok else None))
        base.append((f"存東西(背包{len(p.inv)}/{p.slots})", lambda g: Menu("存什麼", [(it.label(), f"store {it.name}") for it in g.player.inv] or [("背包是空的", None)])))
        if g.base.storage:
            base.append((f"取東西(箱裡{len(g.base.storage)}項)", lambda g: Menu("取什麼", [(it.label(), f"retrieve {it.name}") for it in g.base.storage] or [("儲物箱是空的", None)])))
        for n in g.companions():
            base.append((f"留{n.name}守據點(守夜、看家、回血；你走他不跟)", f"order {n.name} rest"))
    # ---- 人物（在場的人、隊友、勢力代表）
    people = []
    for n in g.npcs_here():
        people.append((f"{n.name}：{npc_summary(g, n)}", lambda g, n=n: person_menu(g, n)))
    for n in g.companions():
        if n not in g.npcs_here():
            people.append((f"{n.name}：{npc_summary(g, n)}", lambda g, n=n: person_menu(g, n)))
    if f:
        att = g.factions[f]
        mood = "友好" if att >= 70 else "中立" if att >= 20 else "敵對"
        people.append((f"{FACTIONS[f]['rep']}：{f}·{mood}" + ("，有東西賣" if FACTIONS[f]["shop"] else ""), lambda g, f=f: faction_menu(g, f)))
    # ---- 現在做得出來的東西
    craft = []
    for name, rc in RECIPES.items():
        if name == "布料":
            continue                       # 撕衣服扣血，流血時才在上面提示
        if name == "修理":
            wi0 = next((it for it in p.inv if it.name == p.weapon), None)
            if wi0 and ITEMS[wi0.name]["dur"] < 99 and wi0.dur < ITEMS[wi0.name]["dur"] and can_craft(p, rc):
                craft.append((f"修理{wi0.name}(+4耐久，{tc(20)})", "craft 修理"))
            continue
        if can_craft(p, rc):
            craft.append((f"做{name}({tc(rc['minutes'])})", f"craft {name}"))
    # ---- 組起來；§ 開頭是群組標題，不能選
    out = []
    for title, group in (("這裡能做", acts), ("移動", moves), ("據點", base), ("人物", people), ("可以做", craft)):
        if group:
            out.append((f"§{title}", None))
            out.extend(group)
    return out


# ---------------------------------------------------------------- 子選單
def inventory_menu(g):
    p = g.player
    entries = []
    marked = False
    for it in p.inv:
        tag = ""
        if it.name == p.weapon and not marked:
            tag, marked = "[裝備]", True
        entries.append((f"{tag}{it.label()}  {item_hint(it.name)}", lambda g, it=it: item_menu(g, it)))
    if not entries:
        entries.append(("背包是空的", None))
    return Menu(f"背包 {len(p.inv)}/{p.slots}" + (f"（裝備：{p.weapon}）" if p.weapon else "（徒手）"), entries)


def item_hint(name):
    """一眼看懂的用途，放在背包項目後面。"""
    s = ITEMS[name]
    k = s["kind"]
    if k == "weapon":
        return f"傷{s['dmg'][0]}-{s['dmg'][1]} 中{s['hit']}" + (f" 需{s['ammo']}" if s.get("ammo") else "")
    if k == "food":
        return f"飢-{s['hunger']}" + ("，會壞" if s.get("spoil") else "") + ("，吃了會病" if s.get("sick") else "")
    if k == "water":
        return f"渴-{s['thirst']}" + ("，可能拉肚子" if s.get("sick") else "")
    if k == "med":
        return {"bandage": "止血", "antibiotic": "壓感染12h", "painkiller": "減傷6h", "firstaid": "血+40止血", "unknown": "不明"}[s["effect"]]
    if k == "throw":
        return "引開" if s.get("distract") else "火攻遠處"
    if k == "ammo":
        return "子彈"
    return {"手電筒": "暗處搜索", "收音機": "撤離用/聽廣播", "訊號彈": "第14天屋頂", "打火機": "煮水", "背包": "用了+5格",
            "疫苗樣本": "送軍方", "日記": "可讀", "木板": "加固/釘棒", "釘子": "加固/釘棒", "布料": "繃帶材料",
            "酒精": "清洗傷口/燃燒瓶", "汽油": "燃燒瓶/交易", "鐵絲": "材料", "空瓶": "裝水/引開"}.get(name, "材料")


def ground_menu(g):
    r = g.cur
    e = [(f"全部撿起（背包 {len(g.player.inv)}/{g.player.slots}）", "take all")]
    for it in r.items:
        e.append((f"撿{it.label()}  {item_hint(it.name)}", f"take {it.name}"))
    return Menu("地上的東西", e)


def item_menu(g, it):
    p = g.player
    s = ITEMS[it.name]
    k = s["kind"]
    e = []
    if k == "food":
        e.append(("吃", f"use {it.name}"))
    elif k == "water":
        e.append(("喝", f"use {it.name}"))
    elif k == "med":
        e.append(((f"使用({tc(10)})" if it.name == "急救包" else "使用"), f"use {it.name}"))
    elif k == "weapon":
        e.append(("裝備", f"equip {it.name}"))
    elif k == "tool":
        e.append(("使用", f"use {it.name}"))
    elif it.name == "酒精":
        e.append((f"清洗傷口(感染-15，{tc(10)})" if (g.player.infection > 0 or g.player.bleeding) else "清洗傷口(現在沒傷口)", f"use {it.name}"))
    elif k == "throw" and g.combat:
        e.append(("丟出去", f"throw {it.name}"))
    elif it.name == "日記":
        e.append(("讀", f"use {it.name}"))
    e.append(("查看說明", f"look {it.name}"))
    if not g.combat:
        many = it.stackable and it.qty > 1
        if g.base.room == g.room:
            e.append((f"存入儲物箱{'(全部x' + str(it.qty) + ')' if many else ''}", f"store {it.name}"))
            if many:
                e.append(("存入儲物箱(一個)", f"store {it.name} 1"))
        for n in g.npcs_here() + g.companions():
            e.append((f"給{n.name}", f"give {n.name} {it.name}"))
        f = faction_rep_here(_Eng(g))
        if f:
            e.append((f"給{FACTIONS[f]['rep']}", f"give {FACTIONS[f]['rep']} {it.name}"))
        e.append((f"丟在地上{'(全部x' + str(it.qty) + ')' if many else ''}", f"drop {it.name}"))
        if many:
            e.append(("丟在地上(一個)", f"drop {it.name} 1"))
    return Menu(it.label(), e)


def craft_menu(g):
    p = g.player
    e = []
    for name, rc in RECIPES.items():
        need = "+".join(f"{k}x{v}" if v else k for k, v in rc["need"].items()) or rc.get("note", "")
        if rc.get("tool"):
            need += f"(需{rc['tool']})"
        ok = can_craft(p, rc)
        e.append((f"{'可' if ok else '缺'} {name}：{need} {tc(rc['minutes'])}", f"craft {name}" if ok else f"look {rc['out'][0]}"))
    return Menu("製作", e)


def trust_word(n):
    return "高" if n.trust >= 60 else "中" if n.trust >= 35 else "低"


def npc_summary(g, n):
    """一行看懂這個人：身分、血、信任、性格技能、缺什麼、現在在幹嘛。"""
    from .combat import STANCE_NAME
    parts = []
    if n.status == "companion":
        parts.append("隊友")
    elif n.status == "placed":
        parts.append("已送到教堂")
    else:
        parts.append("陌生人")
    hurt = "重傷" if n.hp < n.max_hp * 0.5 else ""
    parts.append(f"血{n.hp}/{n.max_hp}{hurt}")
    if n.status == "stranger":
        gap = TRAIT_JOIN[n.trait] - n.trust
        parts.append(f"信任{trust_word(n)}" + ("，可邀加入" if gap <= 0 else f"，再+{gap}可邀"))
    else:
        parts.append(f"信任{trust_word(n)}")
    if n.intro_seen:
        parts.append(f"{n.skill}·{n.trait}")
    else:
        parts.append("性格技能？(觀察)")
    from .npc import NEED_HINT
    parts.append(f"缺{n.need}({NEED_HINT.get(n.need, '').split('、')[0].split('，')[0]}…)")
    if n.status == "companion":
        if g.combat and n.stance:
            parts.append(STANCE_NAME.get(n.stance, ""))
        elif n.order == "guard":
            parts.append("守夜中")
        from .npc import ration_state
        food, water = ration_state(g, n)
        parts.append(f"食物{food}" if food != "今晚要吃" else "今晚要吃")
        parts.append(water)
        if n.unfed_days >= 1:
            parts.append(f"{n.unfed_days}天沒吃")
        if n.revealed and n.infected:
            parts.append("已感染!")
    if n.quest == "given":
        parts.append(f"請託:{QUESTS[n.name]['want']}")
    if is_bonded(n):
        parts.append("羈絆")
    return " | ".join(parts)


def people_menu(g):
    e = []
    for n in g.npcs_here():
        e.append((f"{n.name}  {npc_summary(g, n)}", lambda g, n=n: person_menu(g, n)))
    for n in g.companions():
        if n not in g.npcs_here():
            e.append((f"{n.name}  {npc_summary(g, n)}", lambda g, n=n: person_menu(g, n)))
    for n in g.waiting():
        rid = f"{n.loc}·{n.room}"
        if rid == g.room:
            e.append((f"{n.name}  在這裡留守，血{n.hp}/{n.max_hp}：叫他歸隊", "rejoin"))
        else:
            e.append((f"{n.name}  留守在{'據點' if rid == g.base.room else rid}，血{n.hp}/{n.max_hp}，走進那間房他就歸隊", None))
    f = faction_rep_here(_Eng(g))
    if f:
        att = g.factions[f]
        mood = "友好" if att >= 70 else "中立" if att >= 20 else "敵對"
        e.append((f"{FACTIONS[f]['rep']}  {f}·{mood}" + ("，有東西賣" if FACTIONS[f]["shop"] else ""), lambda g, f=f: faction_menu(g, f)))
    if not e:
        e.append(("這裡沒有人，也沒有隊友", None))
    return Menu("人物", e)


def person_menu(g, n):
    e = [(npc_summary(g, n), None)]
    bag = "、".join(it.label() for it in n.inv) or "沒東西"
    e.append((f"身上：{bag}", None))
    e.append(("說話(1小時，加信任、問情報)", f"talk {n.name}"))
    e.append(("觀察他(現在對你的態度、性格技能、有沒有被咬的線索)", f"look {n.name}"))
    e.append(("給東西", lambda g, n=n: give_menu(g, n.name)))
    e.append((f"交易({tc(10)})", lambda g, n=n: trade_menu(g, n)))
    if n.status == "stranger":
        e.append(("邀加入" + ("" if n.trust >= TRAIT_JOIN[n.trait] else "(信任還不夠)"), f"ask {n.name} join"))
    else:
        e.append((f"拿回他身上的東西({len(n.inv)}樣)", lambda g, n=n: Menu(
            f"{n.name}身上", [(it.label(), f"take {n.name} {it.name}") for it in n.inv] or [("他身上沒東西", None)])))
        dark = ("dark" in g.cur.tags or g.is_night()) and not inv_count(g.player.inv, "手電筒")
        e.append((f"命令：搜索這裡({tc(30 if dark else 20)}" + ("，搜索技能找更多" if n.skill == "搜索" else "") + ")", f"order {n.name} search"))
        if g.base.room == g.room:
            e.append(("留守據點(＝守夜：看家、回血；你走他不跟，回來歸隊)", f"order {n.name} rest"))
        else:
            e.append(("留他在這裡休息(你走他不跟，回血，回來歸隊；一天沒回他退回據點)", f"order {n.name} rest"))
        e.append((f"檢查有沒有被咬({tc(15)})", f"check {n.name}"))
        e.append((("交給修女" if g.cur.loc == "教堂" else "拋下他"), f"leave {n.name}"))
    return Menu(n.name, e)


def focus_menu(g):
    e = []
    for uid, en in numbered(g):
        e.append((f"{uid}:{en.label()} 血{max(0, en.hp)} 距{en.dist}", f"focus {uid}"))
    return Menu("集火哪一隻（不花回合）", e)


def squad_menu(g):
    from .combat import STANCE_NAME, companion_weapon
    e = []
    for n in g.companions():
        w = companion_weapon(n)
        e.append((f"{n.name}（{STANCE_NAME.get(n.stance, '')}，血{n.hp}，{w.name if w else '徒手'}）", lambda g, n=n: stance_menu(g, n)))
    return Menu("指揮隊友", e)


def stance_menu(g, n):
    e = [("上前攻擊：連距離2的也打，但牠們會先盯上他", f"order {n.name} attack"),
         ("退後掩護：不會被打，有槍會開火、有石頭會丟", f"order {n.name} back"),
         ("跟著打：誰靠近打誰（預設）", f"order {n.name} auto")]
    return Menu(f"叫{n.name}", e)


def give_menu(g, who):
    n = g.find_npc(who)
    e = []
    for it in g.player.inv:
        hint = ""
        if n and n.status == "companion":
            kind = ITEMS[it.name]["kind"]
            if kind == "food" and it.name != "腐壞食物":
                hint = "→他會當場吃掉，今晚不用再分他" if n.ate_day != g.day else "→他今天吃過了，會收著"
            elif kind == "water" and it.name != "髒水":
                hint = "→他會當場喝掉，今晚不用再分他" if n.drank_day != g.day else "→他今天喝過了，會收著"
            elif it.name == "繃帶":
                hint = "→他會馬上包紮(+15血)" if n.hp < n.max_hp else "→他沒受傷，會收著備用"
            elif it.name == "急救包":
                hint = "→他會馬上處理傷口(+40血)" if n.hp < n.max_hp * 0.7 else "→傷不重，會收著備用"
            elif it.name == "抗生素":
                from .npc import cure_chance
                hint = f"→治感染，{cure_chance(g, n)}%治好" if n.revealed and n.infected else "→他會收著，真被咬了會自己吃"
        e.append((it.label() + hint, f"give {who} {it.name}"))
    if not e:
        e.append(("背包是空的", None))
    return Menu(f"給{who}什麼", e)


def trade_menu(g, n):
    """先選要什麼，再勾選用哪些東西湊。"""
    e = []
    for want in n.inv:
        e.append((f"要{want.label()}（價值{ITEMS[want.name]['value']}）", lambda g, w=want: basket_menu(g, n.name, w.name, reset=True)))
    if not e:
        e.append((f"{n.name}沒有東西可換", None))
    from .npc import NEED_HINT
    return Menu(f"跟{n.name}交易（他缺{n.need}：{NEED_HINT.get(n.need, '')}算兩倍）", e)


def basket_menu(g, who, want, reset=False):
    """交易籃：勾選多樣東西湊到對方要的價值。狀態放在 g.flags['basket']。"""
    from .npc import unit_value, offer_total
    b = g.flags.get("basket")
    if reset or not isinstance(b, dict) or b.get("who") != who or b.get("want") != want:
        b = {"who": who, "want": want, "give": {}}
        g.flags["basket"] = b
    give = b["give"]
    p = g.player
    # 清掉已經沒有的東西
    for name in list(give):
        have = inv_count(p.inv, name)
        if have <= 0:
            give.pop(name)
        elif give[name] > have:
            give[name] = have
    total = offer_total(g, who, give)
    ask = ITEMS[want]["value"]
    e = []
    if give and total >= ask:
        gives = "+".join(name for name, cnt in give.items() for _ in range(cnt))
        e.append((f"成交：出 {'、'.join(f'{k}x{v}' if v > 1 else k for k, v in give.items())}", f"trade {who} {gives} {want}"))
    elif give:
        e.append((f"還差 {ask - total:g}，再勾一點", None))
    else:
        e.append(("勾選下面的東西湊到對方要的價值（再按一次取消）", None))
    for it in p.inv:
        uv = unit_value(g, who, it.name)
        if uv <= 0:
            continue
        cnt = give.get(it.name, 0)
        if it.qty > 1:
            mark = f"[{cnt}/{it.qty}]"
        else:
            mark = "[v]" if cnt else "[ ]"
        e.append((f"{mark} {it.label()}（值{uv:g}）", lambda g, name=it.name: _basket_toggle(g, who, want, name)))
    return Menu(f"換{want}：對方要 {ask}，你出 {total:g}", e)


def _basket_toggle(g, who, want, name):
    b = g.flags.get("basket") or {"who": who, "want": want, "give": {}}
    give = b["give"]
    have = inv_count(g.player.inv, name)
    cnt = give.get(name, 0) + 1
    if cnt > have:
        cnt = 0
    if cnt:
        give[name] = cnt
    else:
        give.pop(name, None)
    m = basket_menu(g, who, want)
    # 返回鍵回到「要什麼」那層，而不是上一次勾選
    n = g.find_npc(who)
    if n:
        m.parent = trade_menu(g, n)
    else:
        from .npc import faction_by_rep
        f = faction_by_rep(who)
        m.parent = faction_trade_menu(g, f) if f else None
    return m


def faction_menu(g, f):
    spec = FACTIONS[f]
    rep = spec["rep"]
    e = [(f"說話({tc(30)})", f"talk {rep}"), ("給東西", lambda g, rep=rep: give_menu(g, rep))]
    if spec["shop"]:
        e.append((f"交易({tc(10)})", lambda g, f=f: faction_trade_menu(g, f)))
    if f == "軍方" and inv_count(g.player.inv, "疫苗樣本"):
        e.append(("交付疫苗樣本", "deliver"))
    if f == "教堂":
        e.append((f"§收容所（已收 {g.placed}/5，被咬的她不收）", None))
        comps = g.companions()
        if not comps:
            e.append(("你沒有帶人來", None))
        for n in comps:
            if n.revealed and n.infected:
                note = "他被咬了，修女會拒收"
            elif n.revealed:
                note = "檢查過，沒被咬"
            else:
                note = "沒檢查過，被咬的話會被拒收"
            e.append((f"把{n.name}交給修女（{note}）", f"leave {n.name}"))
    return Menu(rep, e)


def faction_trade_menu(g, f):
    spec = FACTIONS[f]
    rep = spec["rep"]
    e = []
    for want in dict.fromkeys(spec["shop"]):
        e.append((f"要{want}（價值{ITEMS[want]['value']}）", lambda g, w=want: basket_menu(g, rep, w, reset=True)))
    return Menu(f"{rep}（他們想要 {'、'.join(spec['wants'])}，算兩倍）", e)


def base_menu(g):
    r = g.cur
    if g.base.room != r.id:
        e = []
        if g.base.room:
            keep = g.waiting_at(g.base.room)
            e.append((f"你的據點在{g.rooms[g.base.room].full}（加固{g.base.fort}/5，儲物{len(g.base.storage)}項" + (f"，{'、'.join(n.name for n in keep)}留守" if keep else "") + "）", None))
        else:
            e.append(("還沒有據點。找一間能當據點的房間（住家、辦公室之類）", None))
        if r.base_ok and not r.hidden:
            e.append(("把這裡設為據點", "claim"))
        elif r.is_street():
            e.append(("街上不能當據點", None))
        else:
            e.append(("這裡不適合當據點", None))
        return Menu("據點", e)
    e = [(f"睡到天亮({_hours_to_dawn(g)}小時)", f"sleep {_hours_to_dawn(g)}"), ("睡 4 小時", "sleep 4"), ("睡 2 小時", "sleep 2")]
    p = g.player
    ok = inv_count(p.inv, "木板") >= 2 and inv_count(p.inv, "釘子") >= 1
    e.append((f"加固({g.base.fort}/5，木板x2 釘子x1{'' if ok else '，材料不夠'}) {tc(60)}", "fortify" if ok else None))
    e.append(("存東西", lambda g: Menu("存什麼", [(it.label(), f"store {it.name}") for it in g.player.inv] or [("背包是空的", None)])))
    e.append((f"取東西（儲物箱 {len(g.base.storage)} 項）", lambda g: Menu("取什麼", [(it.label(), f"retrieve {it.name}") for it in g.base.storage] or [("儲物箱是空的", None)])))
    for n in g.companions():
        e.append((f"留{n.name}守據點(守夜、看家、回血；你走他不跟)", f"order {n.name} rest"))
    return Menu("據點", e)


def rest_menu(g):
    e = [("等 1 小時", "wait 1"), ("等 3 小時", "wait 3")]
    if g.base.room == g.room:
        e.insert(0, (f"睡到天亮({_hours_to_dawn(g)}小時)", f"sleep {_hours_to_dawn(g)}"))
    elif not g.cur.is_street():
        e.append(("就地睡 4 小時(不在據點，危險)", "sleep 4"))
    if g.cur.is_street():
        e.append(("街上不能睡", None))
    return Menu("休息", e)


def info_menu(g):
    return Menu("資訊", [("地圖", "map"), ("狀態與目標", "stat"), ("背包", "inv"), ("最近發生的事", "journal"), ("指令說明", "help")])


# 沒帶參數的指令 -> 子選單
BARE = {
    "use": inventory_menu, "eat": inventory_menu, "drink": inventory_menu, "equip": inventory_menu, "drop": inventory_menu,
    "inv": None, "craft": craft_menu, "talk": people_menu, "give": people_menu, "ask": people_menu, "order": people_menu,
    "leave": people_menu, "check": people_menu, "trade": people_menu, "store": base_menu, "retrieve": base_menu,
    "sleep": rest_menu, "wait": rest_menu, "throw": inventory_menu,
}


# ---------------------------------------------------------------- 顯示
def render(entries, width=64, back=False):
    lines = []
    cur = ""
    pieces = [f"{i}.{label}" for i, (label, _) in enumerate(entries, 1)]
    if back:
        pieces.append("0.返回")
    for piece in pieces:
        if cur and _w(cur) + _w(piece) + 2 > width:
            lines.append(cur)
            cur = piece
        else:
            cur = piece if not cur else cur + "  " + piece
    if cur:
        lines.append(cur)
    return "\n".join(lines)


from .textw import w as _w  # noqa: E402
