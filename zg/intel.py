# -*- coding: utf-8 -*-
"""NPC 情報：講對這局真的有用的事。目標物品在哪、哪間鎖著的房有好貨、哪區很吵、其他生存者在哪、日程。
信任低的人可能騙你（地點型情報會指到錯的房間，地圖上一樣會標「聞」，搜了才知道）。"""
from .data import ITEMS, LOCATIONS, LOCKED_BONUS, GOALS
from .world import room_floor, floor_label

# 每個地區第一間鎖著的房間有固定好貨，講法
LOCKED_PITCH = {
    "警局": "軍械庫有槍和子彈", "住宅區": "車庫裡有把消防斧和汽油", "醫院": "藥品室有抗生素和急救包",
    "藥局": "倉庫有抗生素", "超市": "倉庫堆滿罐頭和水", "學校": "保健室有急救包", "加油站": "維修間有汽油、鐵撬，還有訊號彈",
    "河岸碼頭": "倉庫有霰彈和燃燒瓶",
}


SKILL_TALK = {
    "戰鬥": "手上有傢伙，也敢用，我看他一個人放倒過兩隻。",
    "醫療": "以前是做醫護的，縫傷口、看咬傷都行。",
    "搜索": "手腳很快，別人翻過的地方他還能翻出東西來。",
    "守夜": "耳朵很靈，一點動靜就醒，晚上有他守門睡得安穩。",
}


TRAIT_WIN = {
    "忠誠": "人很好說話，你幫過他一次他就記一輩子，很快就肯跟你走。",
    "實際": "他只看你靠不靠得住，帶點他缺的東西去，講幾次話就會跟你走。",
    "怯懦": "膽子小，別嚇他，多去幾趟讓他看慣你的臉，他就敢跟你走。",
    "貪婪": "眼睛只看東西，嘴巴很硬，要拿不少好處餵他才肯點頭。",
    "冷酷": "那個人很難搞，什麼都不信，要花很長時間他才肯跟你走。",
}


def where(g, r):
    k = room_floor(r.tags)
    fl = floor_label(k) if k != 1 else ""
    return f"{r.loc}{fl}{'' if '的' in r.name else '的'}{r.name}"


def rooms_with(g, item):
    rs = [r for r in g.rooms.values() if any(it.name == item for it in r.loot) and not r.is_street()]
    return sorted(rs, key=lambda r: (r.id != "辦公大樓·辦公室", r.loc != "加油站", r.id))


def goal_checklist(g):
    """狀態頁用：目標還差什麼。"""
    from .state import inv_count
    p = g.player
    out = []
    if g.goal == "撤離":
        out.append(("收音機", inv_count(p.inv, "收音機") > 0 or any(it.name == "收音機" for it in g.base.storage)))
        out.append(("訊號彈", inv_count(p.inv, "訊號彈") > 0 or any(it.name == "訊號彈" for it in g.base.storage)))
        out.append(("第 14 天 06:00–12:00 站在辦公大樓 4F 屋頂 signal，再撐 3 小時", g.flags.get("signal_at") is not None))
    elif g.goal == "疫苗":
        out.append(("疫苗樣本（醫院 2F 實驗室，鎖著）", inv_count(p.inv, "疫苗樣本") > 0))
        out.append(("第 4 到 10 天之間送到軍方檢查站 deliver（第 11 天就撤了）", False))
    else:
        out.append((f"把 5 個人帶到教堂交給修女（{g.placed}/5），被咬的她不收", g.placed >= 5))
        out.append(("第 14 天 12:00 前", False))
    return [("[v] " if done else "[ ] ") + text for text, done in out]


def candidates(g, n):
    """所有還沒講過、而且現在講有意義的情報。回傳 [(key, text, room_id or None, item or None)]，前面的優先。"""
    given = set(g.flags.get("intel_given", []))
    out = []

    def add(key, text, room=None, item=None):
        if key not in given:
            out.append((key, text, room, item))

    # ---- 目標
    if g.goal == "撤離":
        for r in rooms_with(g, "收音機")[:2]:
            add(f"loc:{r.id}:收音機", f"我記得{where(g, r)}有台收音機，之前還會響。你要找直升機就靠那個了。", r.id, "收音機")
        for r in rooms_with(g, "訊號彈")[:2]:
            add(f"loc:{r.id}:訊號彈", f"訊號彈的話……{where(g, r)}應該有" + ("，不過那間鎖著，你得帶鐵撬或斧頭去。" if r.locked else "，我看過。"), r.id, "訊號彈")
        add("evac:time", "聽廣播說直升機第十四天早上來，六點到中午，過了就走。要去辦公大樓屋頂，從樓梯間一路爬到四樓。打了訊號彈之後還得撐三個小時，整棟樓的那些東西都會被引上來，別一個人去。")
    elif g.goal == "疫苗":
        for r in rooms_with(g, "疫苗樣本"):
            add(f"loc:{r.id}:疫苗樣本", f"樣本還在{where(g, r)}，我親眼看他們鎖的門。那層電早就沒了，進去伸手不見五指，記得帶手電筒。", r.id, "疫苗樣本")
        add("vac:window", "檢查站那些兵要第四天才會開始收東西，去早了他們拿槍指著你叫你滾。但別拖，第十一天他們就撤了，到時候只剩一堆沙包。")
        doc = next((s for s in g.npcs if s.name == "林醫師"), None)
        if doc and doc.status == "stranger":
            add("vac:doctor", "醫院員工休息室躲了個穿白袍的，姓林，以前就在實驗室那層上班。她門卡還掛在脖子上，帶著她你連門都不用撬。")
    else:
        for s in g.npcs:
            if s.status == "stranger" and s.name != n.name:
                r = g.rooms.get(f"{s.loc}·{s.room}")
                if r:
                    add(f"npc:{s.name}", f"我碰過一個叫{s.name}的，躲在{where(g, r)}。{SKILL_TALK[s.skill]}{TRAIT_WIN[s.trait]}", r.id)
        add("escort:rule", "修女只收沒被咬的，帶人過去之前先看看他身上有沒有傷口。騙不了她的，她一眼就看得出來，白跑一趟。")
    # ---- 其他生存者（非護送目標時也講，但排後面）
    if g.goal != "護送":
        for s in g.npcs:
            if s.status == "stranger" and s.name != n.name and not s.intro_seen:
                r = g.rooms.get(f"{s.loc}·{s.room}")
                if r:
                    add(f"npc:{s.name}", f"{where(g, r)}還有活人，叫{s.name}。{SKILL_TALK[s.skill]}", r.id)
    # ---- 好貨：每區第一間鎖著的房間
    for loc, pitch in LOCKED_PITCH.items():
        r = next((x for x in g.rooms.values() if x.loc == loc and x.locked and not x.is_street()), None)
        if r and r.loot and loc != g.cur.loc:
            add(f"locked:{loc}", f"{loc}{pitch}，可惜門鎖著。沒鐵撬就別想用肩膀撞，撞半天撞不開，整條街都聽見。", r.id, LOCKED_BONUS[loc][0])
    # ---- 危險
    for loc, t in sorted(g.threat.items(), key=lambda kv: -kv[1]):
        if t >= 5 and loc != g.cur.loc:
            add(f"threat:{loc}:{g.day}", f"{loc}那邊今天一直有聲音，牠們都往那邊擠。你今天別過去，等它靜下來再說。")
            break
    bloat = [r for r in g.rooms.values() if any(e.kind == "腫脹者" for e in r.enemies + r.hidden)]
    if bloat:
        r = bloat[0]
        add("bloater", f"{r.loc}暗的地方有一種胖的，肚子脹得像要破。千萬別拿刀砍，破了那口氣吸到會死人。燒牠，或者開槍，不然就繞遠一點。", r.id)
    # ---- 日程
    if g.day < 3:
        add("water", "水龍頭還有水，但撐不了幾天了。現在看到水龍頭就把瓶子裝滿，之後只剩髒水，得生火煮過才能喝。")
    if g.day < 7:
        add("raiders", "碼頭那群人在看誰家有據點。我聽說一個禮拜左右他們就會挨家挨戶搜。門窗至少釘三層木板他們才懶得撬，不然就留個人守夜。")
    if g.day < 9:
        add("runners", "晚上跑得快的那種越來越多了，再過幾天只會更糟。天黑前一定要回去，真要出門把手電筒帶著。")
    # ---- 機制
    add("noise", "牠們是聽聲音的。動靜一大就有東西來，開一槍等於叫整條街。能逃就逃，打贏了也不划算。")
    add("bite", "被咬了不會馬上怎樣，先是發冷，然後傷口會發黑。抗生素壓得住，但一顆不夠，要連著吃好幾顆。")
    add("aim", "牠從遠處慢慢走過來的時候別急著砍。多瞄幾下，瞄到穩了再往頭上招呼，一下解決，省得挨咬。")
    add("backpack", "警局守衛和碼頭那群人手上有背包，幾罐食物就換得到，背起來能多裝不少東西。")
    return out


def tell(eng, n, max_items=2):
    """講 1～2 條情報。信任低的人地點型情報有機會是假的。"""
    g = eng.g
    cands = candidates(g, n)
    if not cands:
        eng.say(f"{n.name}想了想：「該講的都跟你講過了，剩下的你自己小心。」")
        return
    given = g.flags.setdefault("intel_given", [])
    picks = cands[:1]
    rest = cands[1:]
    if rest and max_items > 1:
        picks.append(eng.rng.choice(rest[:4]))
    for key, text, room_id, item in picks:
        given.append(key)
        truthful = eng.rng.random() < (0.55 + n.trust / 200)
        if room_id and not truthful:
            # 騙你：指到別的房間
            wrong = [r for r in g.rooms.values() if not r.is_street() and r.id != room_id and r.loc != g.cur.loc]
            if wrong:
                r = eng.rng.choice(wrong)
                text = f"我聽人說{where(g, r)}" + ("有" + item + "，你去看看。" if item else "那邊有你要找的東西。")
                if item:
                    r.rumor = item
        elif room_id and item:
            g.rooms[room_id].rumor = item
        eng.say(f"{n.name}：「{text}」")


def faction_tell(eng, f):
    """勢力代表講的話：跟他們有關的、跟目標有關的。"""
    g = eng.g
    att = g.factions[f]
    if f == "軍方":
        if g.goal == "疫苗":
            eng.say("軍官：「第 5 天到第 10 天，樣本拿來，我們送你走。第 11 天我們就不在了。」")
        else:
            eng.say("軍官：「第 11 天撤。想走就自己想辦法，直升機不接平民。」")
    elif f == "教堂":
        eng.say(f"修女：「目前收容了 {g.placed} 個你帶來的人。被咬的我不收，對其他人不公平。」")
        if g.goal == "護送":
            eng.say("修女：「第 14 天中午前湊滿五個，車就會來。」")
    elif f == "警局":
        eng.say("守衛：「軍械庫別碰，碰了我們就是敵人。想要子彈，拿罐頭、藥、汽油來換，這些我們算雙倍。」")
    elif f == "掠奪者":
        eng.say("頭目：「汽油、酒精、子彈、抗生素，拿來，什麼都能談。」" + ("「第 7 天之後別讓我們找到你的據點。」" if g.day < 7 else ""))
    if att >= 70:
        eng.say("他們對你很客氣。")
    elif att < 30:
        eng.say("他們對你沒什麼好臉色。再得罪下去就不是說話能解決的。")
