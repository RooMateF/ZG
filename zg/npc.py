# -*- coding: utf-8 -*-
"""生存者與勢力互動。"""
from .data import ITEMS, SURVIVORS, TRAIT_JOIN, TRAIT_TRUST_MULT, FACTIONS, LOCATIONS, QUESTS
from .state import NPC, inv_find, inv_remove, inv_add, new_item, inv_count

NEED_KIND = {"藥": ("med",), "食物": ("food",), "水": ("water",), "武器": ("weapon", "ammo"), "安全": ("weapon", "material")}
# 畫面上「缺X」後面的提示：送這些信任加倍
NEED_HINT = {"藥": "繃帶、抗生素、止痛藥、急救包", "食物": "任何食物", "水": "瓶裝水、汽水",
             "武器": "任何武器、子彈", "安全": "武器，或木板、釘子、鐵絲這類能加固的材料"}


def need_text(n: NPC) -> str:
    return f"缺{n.need}（送{NEED_HINT.get(n.need, n.need)}信任加倍）"
TRAIT_DESC = {
    "忠誠": "他看著你的眼神很直接，像是已經決定要相信誰。",
    "貪婪": "他的視線一直在你的背包上。",
    "怯懦": "他說話很小聲，每句話都在看門口。",
    "冷酷": "他說話像在報數，沒有一個多餘的字。",
    "實際": "他問的第一件事是：你有多少水。",
}
# 還是陌生人、但不是第一次見面：依信任低 / 中 / 高
LOOK_STRANGER = {
    "忠誠": ["他看到你，點了點頭，但手沒離開武器。", "他看到你來，肩膀鬆了一點。「又是你。」", "他看到你就站起來，像是等很久了。"],
    "貪婪": ["他看到你，先看你的背包，再看你的臉。", "他對你笑了一下，笑得不太自然。「帶東西來了？」", "他把藏起來的東西拿出來給你看。「這些我可以分你。」"],
    "怯懦": ["他看到你縮了一下，然後才認出你。", "他看到你，低聲說：「你還活著，太好了。」", "他看到你就跑過來，手抓著你的袖子。"],
    "冷酷": ["他看了你一眼，沒有表情。", "他看到你，問：「還沒死？」然後讓出一個位置給你坐。", "他看到你，點了一根菸遞給你。這是他最親近的表示。"],
    "實際": ["他看到你，問你帶了多少水。", "他看到你，問你外面怎麼樣，聽得很仔細。", "他看到你，把自己的水分了一半給你。「我算過，夠。」"],
}


def cure_chance(g, n: NPC) -> int:
    """一顆抗生素治好被咬隊友的機率：35，隊裡有醫療技能 +30，被咬一天內 +15。"""
    ch = 35
    if any(c.skill == "醫療" and c.status == "companion" for c in g.npcs):
        ch += 30
    if n.infect_day and g.day - n.infect_day <= 1:
        ch += 15
    return min(95, ch)


def try_cure(eng, n: NPC, who: str = "") -> bool:
    """吃一顆抗生素（呼叫端負責扣藥）。治好回 True；沒治好延 2 天。"""
    g = eng.g
    ch = cure_chance(g, n)
    pre = f"{who}" if who else f"{n.name}"
    if eng.rng.randint(1, 100) <= ch:
        n.infected = False
        n.infect_day = 0
        n.revealed = False
        eng.say(f"{pre}把抗生素吞下去。隔了一陣子，{n.name}手臂上的黑邊退了，燒也退了。他好了。（{ch}%）")
        return True
    n.infect_day += 2
    eng.say(f"{pre}把抗生素吞下去。{n.name}還在發燒，但至少沒更糟。（{ch}%，沒治好，多撐 2 天）")
    return False


def use_on_companion(eng, n: NPC, one) -> bool:
    """你給隊友的東西他會不會當場用掉。會就回 True（東西消耗掉），不會就回 False（收進他背包）。"""
    g = eng.g
    kind = ITEMS[one.name]["kind"]
    if kind == "food" and one.name != "腐壞食物":
        if n.ate_day != g.day:
            n.ate_day = g.day
            n.meal_day = g.day
            n.hp = min(n.max_hp, n.hp + 5)
            eng.say(f"{n.name}當場把{one.name}吃了。（今晚不用再分他食物）")
            return True
        return False
    if kind == "water" and one.name != "髒水":
        if n.drank_day != g.day:
            n.drank_day = g.day
            back = inv_add(g.player.inv, new_item("空瓶"), g.player.slots)
            if not back:
                g.cur.items.append(new_item("空瓶"))
            eng.say(f"{n.name}一口氣喝完，把空瓶" + ("遞還給你" if back else "放在地上（你背包滿了）") + "。（今晚不用再分他水）")
            return True
        return False
    if one.name == "繃帶" and n.hp < n.max_hp:
        n.hp = min(n.max_hp, n.hp + 15)
        eng.say(f"{n.name}把繃帶纏上去。血 {n.hp}/{n.max_hp}。")
        return True
    if one.name == "急救包" and n.hp < n.max_hp * 0.7:
        n.hp = min(n.max_hp, n.hp + 40)
        eng.say(f"{n.name}用急救包處理了傷口。血 {n.hp}/{n.max_hp}。")
        return True
    if one.name == "抗生素" and n.infected:
        if not n.revealed:
            n.revealed = True
            eng.say(f"{n.name}看到抗生素，沉默了一下，把袖子拉起來給你看：一排牙印。")
        try_cure(eng, n)
        return True
    return False


def ration_state(g, n: NPC):
    """隊友的口糧狀態，兩個短句：(食物, 水)。"""
    if n.ate_day == g.day:
        food = "今天吃過"
    elif n.meal_day and g.day - n.meal_day < 2:
        food = "昨天吃過，今晚不用"
    else:
        food = "今晚要吃"
    water = "今天喝過" if n.drank_day == g.day else "今晚要喝"
    return food, water


def fear_word(n: NPC) -> str:
    return "鎮定" if n.fear < 30 else "緊張" if n.fear < 60 else "快崩潰"


def look_tier(n: NPC) -> int:
    from .combat import is_bonded
    if is_bonded(n) or n.trust >= 70:
        return 2
    return 1 if n.trust >= 40 else 0


TALK_LINES = {
    "忠誠": ["「只要你不丟下我，我也不會丟下你。」", "「我以前在這附近上班，我知道哪裡有東西。」"],
    "貪婪": ["「東西分一半，不然免談。」", "「我聽說有人在囤貨。囤得越多，死得越慘。」"],
    "怯懦": ["「晚上不要出去。拜託。」", "「我昨天看到一個跑很快的，牠不是走的，是跑的。」"],
    "冷酷": ["「受傷的人會拖慢你。你知道的。」", "「被咬了就是死了，差別只是什麼時候。」"],
    "實際": ["「水比食物重要。藥比水重要。」", "「別開槍。開一槍，整條街都會來。」"],
}


def spec_of(name):
    return next(s for s in SURVIVORS if s["name"] == name)


def faction_rep_here(eng):
    """目前房間是否有勢力代表，回傳勢力名。"""
    r = eng.g.cur
    for f, spec in FACTIONS.items():
        if spec["loc"] == r.loc and spec["room"] == r.name:
            if f == "軍方" and eng.g.flags.get("checkpoint_gone"):
                return None
            return f
    return None


def resolve_target(eng, text):
    """回傳 (npc, faction)。"""
    n = eng.g.find_npc(text)
    if n:
        return n, None
    f = faction_rep_here(eng)
    if f and (not text or text in FACTIONS[f]["rep"] or FACTIONS[f]["rep"].startswith(text) or text in ("守衛", "修女", "頭目", "軍官")):
        return None, f
    return None, None


def trust_gain(n: NPC, amount: float):
    n.trust = int(min(100, n.trust + amount * TRAIT_TRUST_MULT[n.trait]))


# ---------------------------------------------------------------- look
def look_npc(eng, n: NPC):
    """觀察一個人。第一次見面講外表；之後依關係（陌生人／隊友）和信任高低講他現在對你的樣子。"""
    from .data import LOOK_COMPANION
    s = spec_of(n.name)
    tier = look_tier(n)
    if not n.intro_seen:
        eng.say(s["intro"])
        eng.say(TRAIT_DESC[n.trait])
    elif n.status == "companion":
        eng.say(LOOK_COMPANION.get(n.name, ["", "", ""])[tier] or s["intro"])
    else:
        eng.say(LOOK_STRANGER[n.trait][tier])
    n.intro_seen = True
    word = "高" if n.trust >= 60 else "中" if n.trust >= 35 else "低"
    eng.say(f"（性格：{n.trait}，擅長：{n.skill}，{need_text(n)}，信任{word}" + ("，羈絆" if tier == 2 and n.bonded else "") + "）")
    if n.status == "companion":
        g = eng.g
        eng.say(f"血量 {n.hp}/{n.max_hp}。" + ("看起來不太好。" if n.hp < n.max_hp * 0.5 else ""))
        food, water = ration_state(g, n)
        nf = sum(it.qty for it in n.inv if ITEMS[it.name]["kind"] == "food" and it.name != "腐壞食物")
        nw = sum(it.qty for it in n.inv if ITEMS[it.name]["kind"] == "water" and it.name != "髒水")
        eng.say(f"口糧：食物{food}，水{water}。身上有食物 {nf} 份、水 {nw} 份" + ("，晚上會自己吃。" if nf or nw else "。")
                + (f" 已經 {n.unfed_days} 天沒吃飽。" if n.unfed_days else ""))
        eng.say(f"情緒：{fear_word(n)}。" + ("他的手一直在抖，不敢看門口以外的地方。" if n.fear >= 70 else ""))
        if n.unfed_days >= 1:
            eng.say("他餓著肚子，眼神有點飄。")
        if n.quest == "given":
            eng.say(f"他還在等你幫他找{QUESTS[n.name]['want']}。")
        if n.revealed and n.infected:
            eng.say("他被咬了，你已經知道。")
        elif n.infected and n.infect_day and eng.g.day - n.infect_day >= 1:
            eng.say("他一直用外套遮著手臂。")


# ---------------------------------------------------------------- talk
def talk(eng, text):
    g = eng.g
    n, f = resolve_target(eng, text)
    if f:
        eng.say(FACTIONS[f]["greet"])
        from .intel import faction_tell
        faction_tell(eng, f)
        eng.advance(30)
        return True
    if not n:
        eng.say("這裡沒有這個人。")
        return False
    if not n.intro_seen:
        look_npc(eng, n)
    eng.say(eng.rng.choice(TALK_LINES[n.trait]))
    trust_gain(n, 5)
    # 情報：目標物品、好貨、危險、其他生存者、日程。信任低可能騙你。
    from .intel import tell
    tell(eng, n, max_items=2 if n.status == "companion" or n.trust >= 35 else 1)
    # 請託：熟一點才會開口
    q = QUESTS.get(n.name)
    if q and n.quest == "" and (n.status == "companion" or n.trust >= 25):
        n.quest = "given"
        eng.say(f"{n.name}壓低聲音：「{q['text']}」（請託：{q['want']}，完成會有回禮和羈絆）")
    if n.status == "stranger":
        need_join = TRAIT_JOIN[n.trait]
        if n.trust >= need_join:
            eng.say(f"{n.name}看起來願意跟你走了。（ask {n.name} join）")
        else:
            eng.say(f"{n.name}還在觀望你。（{need_text(n)}）")
    eng.advance(60)
    return True


# ---------------------------------------------------------------- trade
def value_for(n: NPC, item_name: str) -> float:
    v = ITEMS[item_name]["value"]
    if ITEMS[item_name]["kind"] in NEED_KIND.get(n.need, ()):
        v *= 2
    return v


def faction_by_rep(who: str):
    return next((f for f, s in FACTIONS.items() if s["rep"] == who or (who and s["rep"].startswith(who))), None)


def unit_value(g, who: str, name: str) -> float:
    """對方眼中這樣東西一個值多少。who 是人名或勢力代表。"""
    n = g.find_npc(who)
    if n:
        mult = {"貪婪": 0.6, "冷酷": 0.8}.get(n.trait, 1.0) * (1.2 if n.trust >= 60 else 1.0)
        return value_for(n, name) * mult
    f = faction_by_rep(who)
    if f:
        spec = FACTIONS[f]
        att = g.factions.get(f, 50)
        return ITEMS[name]["value"] * (2 if name in spec["wants"] else 1) * (0.6 if f == "掠奪者" else 1.0) * (1.3 if att >= 70 else 1.0)
    return ITEMS[name]["value"]


def offer_total(g, who: str, give: dict) -> float:
    return sum(unit_value(g, who, name) * cnt for name, cnt in give.items())


def parse_gives(p, give_text: str):
    """「餅乾+餅乾+繃帶」-> {"餅乾": 2, "繃帶": 1}；沒有的東西回傳 (None, 名字)。"""
    give = {}
    for part in [x for x in give_text.replace("，", "+").replace(",", "+").split("+") if x]:
        it = inv_find(p.inv, part)
        if not it:
            return None, part
        give[it.name] = give.get(it.name, 0) + 1
    for name, cnt in give.items():
        if inv_count(p.inv, name) < cnt:
            return None, name
    return give, None


def take_gives(p, give: dict):
    """從背包拿出這些東西，回傳 Item 清單（每個一單位）。"""
    from .state import inv_take_one, sync_weapon
    out = []
    for name, cnt in give.items():
        for _ in range(cnt):
            it = inv_find(p.inv, name)
            if it:
                out.append(inv_take_one(p.inv, it))
    sync_weapon(p)
    return out


def trade(eng, text, give_text="", want_text=""):
    """trade 人 給的（可用 + 串多樣，例如 餅乾+餅乾+繃帶） 要的。"""
    g, p = eng.g, eng.g.player
    n, f = resolve_target(eng, text)
    if f:
        return trade_faction(eng, f, give_text, want_text)
    if not n:
        eng.say("這裡沒有這個人。")
        return False
    if not give_text or not want_text:
        inv = "、".join(it.label() for it in n.inv) or "沒東西"
        eng.say(f"{n.name}有：{inv}。{need_text(n)}。")
        eng.say(f"用法：trade {n.name} 你給的（多樣用 + 串）你要的")
        return False
    give, missing = parse_gives(p, give_text)
    if give is None:
        eng.say(f"你沒有那麼多{missing}。")
        return False
    want = inv_find(n.inv, want_text)
    if not want:
        eng.say(f"{n.name}沒有那個東西。")
        return False
    offer = offer_total(g, n.name, give)
    ask = ITEMS[want.name]["value"]
    if offer >= ask:
        from .state import inv_take_one
        given = take_gives(p, give)
        wi = inv_take_one(n.inv, want)
        for gi in given:
            inv_add(n.inv, gi)
        if not inv_add(p.inv, wi, p.slots):
            g.cur.items.append(wi)
            eng.say("背包滿了，東西放在地上。")
        trust_gain(n, 3)
        names = "、".join(f"{k}x{v}" if v > 1 else k for k, v in give.items())
        eng.say(f"{n.name}收下{names}，把{wi.name}給了你。")
        g.flags.pop("basket", None)
        eng.advance(10)
        return True
    eng.say(f"{n.name}搖頭：「不夠。」（出 {offer:g}，他要 {ask}）")
    return False


def trade_faction(eng, f, give_text, want_text):
    g, p = eng.g, eng.g.player
    spec = FACTIONS[f]
    att = g.factions[f]
    if att < 20:
        eng.say("他們不跟你交易。")
        return False
    if not spec["shop"]:
        eng.say("他們沒有東西可以賣。")
        return False
    if not give_text or not want_text:
        eng.say(f"{spec['rep']}可以賣：{'、'.join(dict.fromkeys(spec['shop']))}。他們想要：{'、'.join(spec['wants'])}。")
        eng.say(f"用法：trade {spec['rep']} 你給的（多樣用 + 串）你要的")
        return False
    give, missing = parse_gives(p, give_text)
    want = next((x for x in spec["shop"] if x.startswith(want_text)), None)
    if give is None:
        eng.say(f"你沒有那麼多{missing}。")
        return False
    if not want:
        eng.say("他們沒有賣那個。")
        return False
    offer = offer_total(g, spec["rep"], give)
    ask = ITEMS[want]["value"]
    if offer >= ask:
        take_gives(p, give)
        g.flags.pop("basket", None)
        qty = 3 if ITEMS[want]["kind"] == "ammo" else 1
        wi = new_item(want, qty, g.day)
        if not inv_add(p.inv, wi, p.slots):
            g.cur.items.append(wi)
            eng.say("背包滿了，東西放在地上。")
        g.factions[f] = min(100, att + 3)
        eng.say(f"成交。你拿到{wi.label()}。")
        eng.advance(10)
        return True
    eng.say(f"{spec['rep']}：「不夠。」（出 {offer:g}，要 {ask}；他們想要的東西算兩倍價）")
    return False


# ---------------------------------------------------------------- give
def give(eng, text, item_text):
    g, p = eng.g, eng.g.player
    n, f = resolve_target(eng, text)
    it = inv_find(p.inv, item_text)
    if not it:
        eng.say("你沒有那個東西。")
        return False
    from .state import inv_take_one, sync_weapon
    if f:
        spec = FACTIONS[f]
        one = inv_take_one(p.inv, it)
        sync_weapon(p)
        gain = ITEMS[one.name]["value"] * (2 if one.name in spec["wants"] else 1) * 0.6
        g.factions[f] = int(min(100, g.factions[f] + gain))
        eng.say(f"{spec['rep']}收下了{one.name}。他們對你的態度好了一點。")
        return True
    if not n:
        eng.say("這裡沒有這個人。")
        return False
    one = inv_take_one(p.inv, it)
    sync_weapon(p)
    q = QUESTS.get(n.name)
    if q and n.quest == "given" and one.name == q["want"]:
        n.quest = "done"
        n.bonded = True
        n.trust = min(100, n.trust + 25)
        rname, rqty = q["reward"]
        reward = new_item(rname, rqty, g.day)
        if not inv_add(p.inv, reward, p.slots):
            g.cur.items.append(reward)
            eng.say("背包滿了，回禮放在地上。")
        eng.say(f"{n.name}接過{one.name}，愣了一下，然後把{reward.label()}塞給你。「記住，你有事我會擋在前面。」")
        eng.say(f"（{n.name}跟你有了羈絆：戰鬥命中 +15、不會躲、有機會替你擋刀）")
        if n.status == "stranger" and n.trust >= TRAIT_JOIN[n.trait]:
            eng.say(f"{n.name}看起來願意跟你走了。（ask {n.name} join）")
        return True
    gain = value_for(n, one.name) * 0.8
    if ITEMS[one.name]["kind"] in NEED_KIND.get(n.need, ()):
        eng.say(f"{n.name}接過{one.name}，眼睛亮了一下。「這正是我需要的。」")
    used = use_on_companion(eng, n, one)
    if not used:
        if ITEMS[one.name]["kind"] not in NEED_KIND.get(n.need, ()):
            eng.say(f"{n.name}收下{one.name}。")
        inv_add(n.inv, one)
    trust_gain(n, min(20, gain))
    if n.status == "stranger" and n.trust >= TRAIT_JOIN[n.trait]:
        eng.say(f"{n.name}看起來願意跟你走了。（ask {n.name} join）")
    return True


# ---------------------------------------------------------------- join
def ask_join(eng, text):
    g = eng.g
    n = g.find_npc(text)
    if not n:
        eng.say("這裡沒有這個人。")
        return False
    if n.status == "companion":
        eng.say(f"{n.name}已經跟著你了。")
        return False
    if len(g.companions()) >= (4 if g.goal == "護送" else 3):
        eng.say("你帶不了更多人了（最多 3 個）。")
        return False
    need = TRAIT_JOIN[n.trait]
    if n.trust < need:
        eng.say(f"{n.name}：「我不認識你。」（信任不夠，多聊天或送他缺的東西）")
        return False
    n.status = "companion"
    n.order = ""
    eng.say(f"{n.name}收拾了東西，跟在你後面。")
    if n.trait == "冷酷":
        eng.say(f"{n.name}：「先說好，誰被咬了我就走。」")
    return True


# ---------------------------------------------------------------- order
def order(eng, text, what):
    g = eng.g
    n = g.find_npc(text)
    if not n or n.status != "companion":
        eng.say("他不是你的隊友。")
        return False
    if g.combat:
        from .combat import STANCE_NAME
        stances = {"attack": "attack", "上前": "attack", "back": "back", "退後": "back",
                   "auto": "", "follow": "", "跟著": "", "跟著打": ""}
        if what not in stances:
            eng.say("戰鬥中只能喊：order 人 attack（上前）/ back（退後）/ auto（跟著打）。")
            return False
        st = stances[what]
        if n.stance == "hide":
            if eng.rng.random() < 0.5:
                n.stance = st
                eng.say(f"{n.name}咬著牙從門後出來了。（{STANCE_NAME[st]}）")
            else:
                eng.say(f"{n.name}縮在門後，不理你。")
            return False
        n.stance = st
        line = {"attack": f"{n.name}往前跨了一步。牠們會先盯上他。",
                "back": f"{n.name}退到你身後。他不會被打到，有槍會開火，有石頭會丟。",
                "": f"{n.name}跟在你旁邊，誰靠近打誰。"}[st]
        eng.say(line)
        return False
    if what in ("search", "搜索"):
        from .commands import do_search
        eng.say(f"{n.name}開始翻找。")
        return do_search(eng, by=n)
    if what in ("guard", "守夜") and g.base.room != g.room:
        eng.say("只能在據點守夜。別的地方用 rest 留他休息。")
        return False
    if what in ("guard", "守夜", "rest", "休息", "stay", "留守"):
        n.status = "waiting"
        n.order = ""
        n.stance = ""
        n.loc, n.room = g.cur.loc, g.cur.name
        n.wait_day = g.day
        g.flags.pop(f"wait_news_{n.name}", None)
        if g.base.room == g.room:
            eng.say(f"{n.name}拿了椅子坐到門邊。「你回來我就在這，順便幫你看著東西。」"
                    + ("他有守夜的經驗，聽得到很遠的聲音。" if n.skill == "守夜" else "")
                    + "（留守據點＝守夜：每小時回血；你在這睡覺時夜襲機率降、有東西來會先叫醒你；你不在時掠奪者撬不開門）")
        else:
            eng.say(f"{n.name}靠著牆坐下。「你回來我就在這。」（留守：每小時回血，牠們走進來他只能躲；一天後你還沒回來，他會自己退回據點等你）")
        return True
    eng.say("可以下的命令：search / guard / rest（留守）")
    return False


# ---------------------------------------------------------------- leave
def leave(eng, text):
    g = eng.g
    n = g.find_npc(text)
    if not n or n.status != "companion":
        eng.say("他不是你的隊友。")
        return False
    r = g.cur
    if r.loc == "教堂":
        if n.infected:
            if n.revealed:
                eng.say(f"修女看了一眼{n.name}的手臂。「你明知道他被咬了還帶來？」")
            else:
                eng.say(f"修女檢查了{n.name}的手臂，臉色變了。「他被咬了。我們不收。」")
            n.revealed = True
            eng.say(f"{n.name}看著你，什麼都沒說。")
            n.status = "left"
            n.loc, n.room = r.loc, r.name
            g.factions["教堂"] -= 10
            return True
        n.status = "placed"
        g.placed += 1
        g.factions["教堂"] = min(100, g.factions["教堂"] + 8)
        eng.say(f"修女帶{n.name}進了收容所。「這是第 {g.placed} 個。」")
        for rname in ("罐頭", "瓶裝水"):
            gift = new_item(rname, 1, g.day)
            if not inv_add(g.player.inv, gift, g.player.slots):
                g.cur.items.append(gift)
        eng.say("修女回頭塞給你一罐罐頭和一瓶水：「收容所的口糧，路上吃。」" + ("（背包滿了，放在地上）" if any(it.name in ("罐頭", "瓶裝水") for it in g.cur.items) else ""))
        if g.goal == "護送" and g.placed >= 5:
            g.over = "escort"
        return True
    n.status = "left"
    n.loc, n.room = r.loc, r.name
    n.trust -= 30
    eng.say(f"你告訴{n.name}走到這裡就好。")
    if n.trait in ("冷酷", "貪婪"):
        eng.say(f"{n.name}沒說話，但你知道他記住了。")
        g.flags[f"grudge_{n.name}"] = 1
    elif n.trait == "怯懦":
        eng.say(f"{n.name}求你別走，你沒回頭。")
    for o in g.companions():
        if o.trait == "忠誠":
            o.trust -= 8
            eng.say(f"{o.name}看了你一眼。")
    return True


# ---------------------------------------------------------------- check
def request(eng, who, item_text):
    """跟隊友拿回東西：take 人 物品。隊友的東西本來就是大家的，只有貪婪的人信任不夠會不給。"""
    g, p = eng.g, eng.g.player
    n = g.find_npc(who)
    if not n or n.status != "companion":
        eng.say("他不是你的隊友，要用 trade 換。")
        return False
    if not item_text:
        eng.say(f"{n.name}身上有：" + ("、".join(it.label() for it in n.inv) or "沒東西") + "。用法：take 人 物品")
        return False
    it = inv_find(n.inv, item_text)
    if not it:
        eng.say(f"{n.name}身上沒有那個。")
        return False
    if n.trait == "貪婪" and n.trust < 60:
        eng.say(f"{n.name}把{it.name}往懷裡一收：「給了就是我的。」（信任夠高他才肯）")
        return False
    from .state import inv_take_one
    one = inv_take_one(n.inv, it)
    if not inv_add(p.inv, one, p.slots):
        g.cur.items.append(one)
        eng.say("背包滿了，東西放在地上。")
    else:
        eng.say(f"{n.name}把{one.name}遞給你。")
    return False


def check(eng, text):
    g, p = eng.g, eng.g.player
    n = g.find_npc(text)
    if not n:
        eng.say("這裡沒有這個人。")
        return False
    has_med = any(c.skill == "醫療" and c is not n for c in g.companions()) or inv_count(p.inv, "急救包") > 0
    if not has_med:
        eng.say("你不懂怎麼看。需要有醫療技能的隊友，或一個急救包。")
        return False
    eng.advance(15)
    if n.infected:
        n.revealed = True
        eng.say(f"{n.name}手臂上有一排牙印，邊緣已經發黑。他沒有說，你也沒問為什麼。")
        days = 3 - (g.day - n.infect_day)
        eng.say(f"照這樣下去，大概還有 {max(0, days)} 天。給他一顆抗生素有 {cure_chance(g, n)}% 治好，沒治好也能多撐 2 天。")
    else:
        eng.say(f"{n.name}身上有擦傷，但沒有咬痕。")
    return True
