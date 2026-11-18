# -*- coding: utf-8 -*-
"""回合制戰鬥。"""
from .data import ITEMS, ENEMIES, DIRS
from .state import Enemy, inv_count, inv_remove, new_item


def weapon_item(eng):
    p = eng.g.player
    if not p.weapon:
        return None
    return next((it for it in p.inv if it.name == p.weapon), None)


def experience(g):
    """戰鬥熟練度：只看這局的擊殺數。命中最多 +10，爆頭最多再 +9，10 殺後近戰省 1 體力。"""
    k = g.flags.get("xp_kills", 0)     # 只算你親手殺的，隊友殺的不算
    label = "生手" if k < 5 else "熟手" if k < 15 else "老手" if k < 30 else "殺手"
    return {"hit": min(10, k // 5 * 2), "head": min(9, k // 10 * 3), "stam": 1 if k >= 10 else 0, "label": label}


AIM_MAX = 3


def aim_bonus(level) -> int:
    """瞄準加成：第 1 次 +25，第 2 次 +35，第 3 次 +45。"""
    level = min(AIM_MAX, int(level))
    return 0 if level <= 0 else 25 + 10 * (level - 1)


def hit_chance(eng, base: int, head=False) -> int:
    p = eng.g.player
    xp = experience(eng.g)
    c = base + xp["hit"]
    if head:
        c += xp["head"]
    c += aim_bonus(p.aimed)
    if p.stamina < 15:
        c -= 20
    if p.fatigue > 80:
        c -= 20
    if p.thirst > 70:
        c -= 15
    if p.grabbed:
        c -= 20
    if p.sick:
        c -= 10
    if head:
        c -= 30
        if not p.aimed:
            c -= 20
    return max(5, min(95, c))


def swing_cost(eng) -> int:
    """揮一下要扣的體力（跟 player_attack 一樣算）。預覽命中率時先扣掉，顯示的才是真正出手那一刻的數字。"""
    g = eng.g
    wi = weapon_item(eng)
    spec = ITEMS[wi.name] if wi else None
    stam = spec["stam"] if spec else 6
    if not (spec and spec.get("ammo")):
        stam = max(1, stam - experience(g)["stam"])
    return stam


def penalty_tags(g, cost=0) -> str:
    """現在命中率被什麼拖低：喘(體力<15 −20) 累(疲勞>80 −20) 渴(口渴>70 −15) 被抓(−20) 病(−10)。沒有就回空字串。
    cost：預覽時先扣掉這次揮擊的體力。"""
    p = g.player
    tags = []
    if p.stamina - cost < 15:
        tags.append("喘-20")
    if p.fatigue > 80:
        tags.append("累-20")
    if p.thirst > 70:
        tags.append("渴-15")
    if p.grabbed:
        tags.append("被抓-20")
    if p.sick:
        tags.append("病-10")
    return "，" + " ".join(tags) if tags else ""


def flee_chance(eng) -> int:
    g, p = eng.g, eng.g.player
    adj = len([e for e in g.cur.enemies if e.dist == 1])
    chance = 75 - 12 * adj
    if p.fatigue > 80:
        chance -= 20
    if p.thirst > 70:
        chance -= 10
    if p.stamina < 15:
        chance -= 15
    return max(10, chance)


def escape_chance(eng) -> int:
    """被抓住時掙脫的機率。"""
    return 55 + (20 if eng.g.player.stamina > 50 else 0)


PUSH_CHANCE = 75


def rates_after_aim(eng, levels=1):
    """再瞄準 levels 次之後，普通攻擊與爆頭的命中率。"""
    p = eng.g.player
    wi = weapon_item(eng)
    base = ITEMS[wi.name]["hit"] if wi else 50
    keep, keep_stam = p.aimed, p.stamina
    p.aimed = min(AIM_MAX, int(p.aimed) + levels)
    p.stamina = p.stamina - swing_cost(eng)        # 出手那一刻體力已經扣掉了
    try:
        return hit_chance(eng, base), hit_chance(eng, base, head=True)
    finally:
        p.aimed, p.stamina = keep, keep_stam


def is_bonded(n) -> bool:
    return bool(getattr(n, "bonded", False)) or n.trust >= 90


def ensure_uids(g):
    """給場上每隻敵人一個不重複的編號（1 開始），畫面和 focus 用。"""
    used = {e.uid for e in g.cur.enemies if e.uid}
    nxt = 1
    for e in g.cur.enemies:
        if not e.uid:
            while nxt in used:
                nxt += 1
            e.uid = nxt
            used.add(nxt)


def numbered(g):
    """[(編號, enemy)] 依編號排序。"""
    ensure_uids(g)
    return sorted(((e.uid, e) for e in g.cur.enemies), key=lambda x: x[0])


def focused(g):
    uid = g.flags.get("focus")
    return next((e for e in g.cur.enemies if e.uid == uid), None) if uid else None


def pick_target(g, reach, text=""):
    """選目標：指定的編號/名字 > 集火目標（搆得到的話）> 最近的。"""
    r = g.cur
    if text:
        if text.isdigit():
            e = next((e for e in r.enemies if e.uid == int(text)), None)
            if e:
                return e
        for e in r.enemies:
            if e.label().startswith(text) or e.kind.startswith(text):
                return e
        return None
    f = focused(g)
    if f and f.dist <= reach:
        return f
    in_range = [e for e in r.enemies if e.dist <= reach]
    return min(in_range, key=lambda e: e.dist) if in_range else min(r.enemies, key=lambda e: e.dist)


def set_focus(eng, text):
    g = eng.g
    if not g.combat or not g.cur.enemies:
        eng.say("沒有東西需要集火。")
        return False
    ensure_uids(g)
    e = pick_target(g, 9, text) if text else None
    if not e:
        eng.say("集火哪一隻？用編號：focus 1")
        return False
    g.flags["focus"] = e.uid
    eng.say(f"集火 {e.uid}:{e.label()}。你和隊友都會優先打牠。（不花回合）")
    return False


def sneak_chance(g, r=None) -> int:
    """牠們還沒發現你時，偷翻東西或溜走不被發現的機率。一個人最高；每多一個隊友 -12，每多一隻 -8，
    有牠在距離 3 以內 -10，疲勞過 80 -15，晚上牠們看不清 +10。10～90。"""
    r = r or g.cur
    zs = [e for e in r.enemies]
    ch = 75 - 12 * len(g.companions()) - 8 * max(0, len(zs) - 1)
    if any(e.dist <= 3 for e in zs):
        ch -= 10
    if g.player.fatigue > 80:
        ch -= 15
    if g.is_night():
        ch += 10
    return max(10, min(90, ch))


def confirm_once(eng, key, warning) -> bool:
    """高風險動作第一次做時先提醒，再做一次才執行；之後這局不再問。回傳 True = 可以執行。"""
    g = eng.g
    done = g.flags.setdefault("warned", [])
    if key in done:
        return True
    if g.flags.get("confirm") == key:
        g.flags.pop("confirm", None)
        done.append(key)
        return True
    g.flags["confirm"] = key
    eng.say("※ " + warning)
    return False


def start_combat(eng, reason=""):
    g = eng.g
    if g.cur.enemies and not g.combat:
        g.combat = True
        eng.rejoin_waiting()
        g.flags["fights"] = g.flags.get("fights", 0) + 1
        g.flags["fight_start"] = {"hp": g.player.hp, "kills": g.flags.get("kills", 0), "bites": g.flags.get("bites", 0)}
        ensure_uids(g)
        g.player.aimed = 0
        if reason:
            eng.say(reason)
        eng.say("戰鬥開始。輸入 help 看戰鬥指令。")


def end_combat(eng):
    g = eng.g
    g.combat = False
    g.player.aimed = 0
    g.player.grabbed = False
    g.flags.pop("focus", None)
    for n in g.companions():
        n.stance = ""
    fs = g.flags.pop("fight_start", None)
    if fs:
        eng.say(f"安靜了。這場：殺 {g.flags.get('kills', 0) - fs['kills']}，掉 {max(0, fs['hp'] - g.player.hp)} 血，被咬 {g.flags.get('bites', 0) - fs['bites']} 次。")
    else:
        eng.say("安靜了。")


def player_attack(eng, target_text="", head=False):
    g, p = eng.g, eng.g.player
    r = g.cur
    if not r.enemies:
        eng.say("這裡沒有可以攻擊的東西。")
        return False
    wi = weapon_item(eng)
    spec = ITEMS[wi.name] if wi else None
    rng_ = spec["range"] if spec else 1
    ammo_name = spec.get("ammo") if spec else None
    # 選目標：編號 / 名字 / 集火 / 最近
    ensure_uids(g)
    target = pick_target(g, rng_, target_text)
    if target is None:
        eng.say("沒有那個目標。用編號：attack 1")
        return False
    if target.dist > rng_:
        if rng_ == 1:
            eng.say(f"{target.label()}還在距離{target.dist}，你搆不到。可以 aim 等牠靠近，或 flee。")
        else:
            eng.say(f"{target.label()}太遠了（射程{rng_}）。")
        return False
    stam = spec["stam"] if spec else 6
    if rng_ == 1:
        stam = max(1, stam - experience(g)["stam"])
    if p.stamina < stam:
        p.stamina = min(p.max_stamina(), p.stamina + 10)
        eng.say(f"你喘不過氣，只能先護住頭。（體力 {p.stamina}，這把武器要 {stam}）")
        enemy_turn(eng)
        return True
    if ammo_name and inv_count(p.inv, ammo_name) <= 0:
        if target.dist > 1:
            eng.say(f"沒有{ammo_name}了。只能等牠靠近用槍托砸。")
            return False
        spec = dict(spec, dmg=(4, 9), hit=60, noise=1, stam=7)
        ammo_name = None
        eng.say("沒子彈了，你把槍倒過來握。")
    if ammo_name and not confirm_once(eng, "shoot", f"開槍噪音 +{spec['noise']}，等於叫整條街過來。確定要開就再按一次。"):
        return False
    if ammo_name:
        inv_remove(p.inv, ammo_name, 1)
        eng.noise(spec["noise"])
    p.stamina -= stam
    base = spec["hit"] if spec else 50
    chance = hit_chance(eng, base, head)
    roll = eng.rng.randint(1, 100)
    p.aimed = 0
    wname = wi.name if wi else "拳頭"
    if roll > chance:
        eng.say(f"你用{wname}{'往頭部' if head else ''}揮去，沒打中。（命中率{chance}%{penalty_tags(g)}）")
        if spec and spec["noise"] and not ammo_name:
            eng.noise(spec["noise"] * 0.5)
    else:
        lo, hi = spec["dmg"] if spec else (3, 6)
        dmg = eng.rng.randint(lo, hi)
        if head:
            dmg = 999
        target.hp -= dmg
        if spec and not ammo_name:
            eng.noise(spec["noise"] * 0.5)
        if wi and spec["dur"] < 99:
            wi.dur -= 1
            if wi.dur <= 0:
                eng.say(f"{wi.name}斷了。")
                p.inv.remove(wi)
                p.weapon = None
        if target.hp <= 0:
            kill(eng, target, melee=(rng_ == 1), head=head)
        else:
            eng.say(f"你打中{target.label()}，{dmg} 點傷害。牠還在動。")
    enemy_turn(eng)
    return True


def kill(eng, e: Enemy, melee=True, head=False, by_player=True):
    g, p = eng.g, eng.g.player
    g.cur.enemies.remove(e)
    if g.flags.get("focus") == e.uid:
        g.flags.pop("focus", None)
    if by_player:
        g.flags["xp_kills"] = g.flags.get("xp_kills", 0) + 1
    spec = ENEMIES[e.kind]
    if head:
        eng.say(f"{e.label()}的頭炸開了。牠不動了。")
    else:
        eng.say(f"{e.label()}倒下了，不再動。")
    if spec.get("cloud") and melee:
        p.infection += 15
        eng.say("牠的身體裂開，噴出一團黃綠色的霧。你吸進去了一些。")
    if spec.get("human"):
        drop = eng.rng.choice(["霰彈", "手槍子彈", "罐頭", "汽油", "繃帶"])
        g.cur.items.append(new_item(drop, 1 if drop not in ("霰彈", "手槍子彈") else 3, g.day))
        eng.say(f"他身上掉出了{drop}。")
    g.flags["kills"] = g.flags.get("kills", 0) + 1
    if not g.cur.enemies:
        end_combat(eng)


def player_aim(eng):
    p = eng.g.player
    if p.stamina < 3:
        eng.say("你太喘了，只能先穩住。")
        p.stamina += 5
        enemy_turn(eng)
        return True
    if int(p.aimed) >= AIM_MAX:
        eng.say("你保持瞄準，等牠再靠近一點。")
        enemy_turn(eng)
        return True
    p.stamina = max(0, p.stamina - 3)
    p.aimed = int(p.aimed) + 1
    hc, hh = rates_after_aim(eng, 0)
    if p.aimed == 1:
        eng.say(f"你穩住呼吸，等牠靠近。現在攻擊 {hc}%、爆頭 {hh}%。")
    else:
        eng.say(f"你繼續盯著牠，呼吸放慢。現在攻擊 {hc}%、爆頭 {hh}%" + ("（已經最穩）。" if p.aimed >= AIM_MAX else "。"))
    enemy_turn(eng)
    return True


PIN_DRAW = 80          # 牽制時牠們撲你的機率（%）


def pin_level(g) -> int:
    """牽制熟練 0～3：每用 3 次升一級。"""
    return min(3, g.flags.get("pin_uses", 0) // 3)


def pin_bonus(g) -> int:
    """牽制這回合隊友命中加成：15/20/25/30。"""
    return 15 + 5 * pin_level(g)


def pinning(g) -> bool:
    return g.flags.get("pin") == g.turn


def player_pin(eng):
    """牽制：吼叫、敲打，把牠們的注意力全引到你身上。這回合隊友命中 +pin_bonus，牠們 80% 撲你、咬你更準，羈絆隊友也不會替你擋。
    用越多越熟練（flags pin_uses）。"""
    g, p = eng.g, eng.g.player
    comps = [n for n in g.companions() if n.stance != "hide"]
    if not comps:
        eng.say("沒有隊友能趁機出手，牽制牠們只是白白挨打。")
        return False
    if p.stamina < 4:
        eng.say("你太喘了，吼不出聲。")
        p.stamina += 5
        enemy_turn(eng)
        return True
    p.stamina = max(0, p.stamina - 4)
    before = pin_level(g)
    g.flags["pin_uses"] = g.flags.get("pin_uses", 0) + 1
    g.flags["pin"] = g.turn
    bonus = pin_bonus(g)
    eng.noise(1.0)
    eng.say(f"你大吼一聲，拿武器敲牆。牠們的眼睛全轉向你。（隊友這回合命中 +{bonus}，牠們 {PIN_DRAW}% 先撲你）")
    if pin_level(g) > before:
        eng.say(f"你越來越會抓牠們的注意力了。（牽制熟練 {pin_level(g)}/3，隊友命中 +{pin_bonus(g)}）")
    enemy_turn(eng)
    return True


def player_push(eng):
    g, p = eng.g, eng.g.player
    r = g.cur
    if p.grabbed:
        chance = escape_chance(eng)
        p.stamina = max(0, p.stamina - 10)
        if eng.rng.randint(1, 100) <= chance:
            p.grabbed = False
            eng.say("你掙脫了。")
        else:
            eng.say("牠抓得很緊，你掙不開。")
        enemy_turn(eng)
        return True
    adj = [e for e in r.enemies if e.dist == 1]
    if not adj:
        eng.say("沒有東西靠得夠近可以推。")
        return False
    if p.stamina < 10:
        eng.say("你沒力氣推了。")
        return False
    p.stamina -= 10
    e = adj[0]
    if eng.rng.randint(1, 100) <= PUSH_CHANCE:
        e.dist = 2
        e.distract = 1      # 踉蹌：這回合動不了，下回合才走回來（給你一回合瞄準）
        eng.say(f"你把{e.label()}推開，牠踉蹌了一下。趁現在瞄準。")
    else:
        eng.say(f"你推了一下，{e.label()}紋絲不動。")
    enemy_turn(eng)
    return True


def player_flee(eng, d: str):
    g, p = eng.g, eng.g.player
    r = g.cur
    if d not in r.exits:
        eng.say("那個方向沒有路。")
        return False
    target = g.rooms[r.exits[d]]
    if target.locked:
        eng.say("那扇門是鎖的，你撞了一下，沒開。")
        enemy_turn(eng)
        return True
    if p.grabbed:
        eng.say("你被抓住了，先 push 掙脫。")
        return False
    chance = flee_chance(eng)
    p.stamina = max(0, p.stamina - 15)
    if eng.rng.randint(1, 100) <= chance:
        eng.say(f"你往{d}衝出去。（成功率{chance}%）")
        chasers = []
        for e in r.enemies:
            if e.kind == "疾走者" and eng.rng.random() < 0.5:
                e.dist = 2
                chasers.append(e)
            elif e.kind == "行屍" and e.dist == 1 and eng.rng.random() < 0.3:
                e.dist = 3      # 行屍慢，跟進來時還在遠處
                chasers.append(e)
        for e in chasers:
            r.enemies[:] = [x for x in r.enemies if x is not e]
            e.distract = 0
            target.enemies.append(e)
        g.combat = False
        p.aimed = 0
        g.room = target.id
        target.visited = True
        if chasers:
            kinds = sorted({e.kind for e in chasers})
            eng.say("、".join(kinds) + ("追了上來。" if "疾走者" in kinds else "拖著腳跟了進來。"))
            start_combat(eng)
        elif target.enemies:
            start_combat(eng, "你跑進了另一個麻煩。")
        else:
            eng.say("你甩掉了牠們。")
        return True
    eng.say(f"你被絆了一下，沒能跑掉。（成功率{chance}%）")
    enemy_turn(eng)
    return True


def player_throw(eng, item_text: str):
    g, p = eng.g, eng.g.player
    from .state import inv_find
    it = inv_find(p.inv, item_text)
    if not it:
        eng.say("你沒有那個東西。")
        return False
    spec = ITEMS[it.name]
    r = g.cur
    if spec["kind"] == "throw" and spec.get("fire"):
        inv_remove(p.inv, it.name, 1)
        eng.noise(spec["noise"])
        far = [e for e in r.enemies if e.dist >= 2]
        near = [e for e in r.enemies if e.dist == 1]
        eng.say("玻璃碎了，火燒了起來。")
        for e in list(far):
            dmg = eng.rng.randint(*spec["fire"])
            e.hp -= dmg
            if e.hp <= 0:
                kill(eng, e, melee=False)
        if near:
            p.hp -= 8
            eng.say("太近了，火燎到你自己。")
        if g.combat:
            enemy_turn(eng)
        return True
    # 任何物品都能丟去引開注意；石頭和空瓶最適合
    inv_remove(p.inv, it.name, 1)
    cands = [e for e in r.enemies if e.distract == 0 and not ENEMIES[e.kind].get("human")]
    if not cands:
        eng.say("你丟出去了，但沒人理你。")
    else:
        e = eng.rng.choice(cands)
        e.distract = 2
        eng.say(f"{it.name}砸在角落。{e.label()}轉頭朝聲音走去。")
    enemy_turn(eng)
    return True


STANCE_NAME = {"": "跟著打", "attack": "上前", "back": "退後", "hide": "躲著"}


def companion_weapon(n):
    """隊友身上最好的武器：有子彈的槍優先，其次傷害最高的近戰武器。"""
    best = None
    for it in n.inv:
        s = ITEMS[it.name]
        if s["kind"] != "weapon":
            continue
        if s.get("ammo"):
            if inv_count(n.inv, s["ammo"]) > 0:
                return it
            continue
        if best is None or s["dmg"][1] > ITEMS[best.name]["dmg"][1]:
            best = it
    return best


def companion_turn(eng):
    """每個隊友每回合做一件事，全部濃縮成一行「隊友：…」。"""
    g = eng.g
    r = g.cur
    notes = []

    def flush():
        if notes:
            eng.say("隊友：" + "，".join(notes) + "。")
            notes.clear()

    for n in g.companions():
        if not r.enemies:
            break
        if n.stance == "hide":
            continue
        if n.trait == "怯懦" and not is_bonded(n) and n.stance != "back" and (n.hp < n.max_hp * 0.5 or len(r.enemies) >= 3) and eng.rng.random() < 0.4:
            n.stance = "hide"
            notes.append(f"{n.name}躲到了門後，不肯出來")
            continue
        wi = companion_weapon(n)
        spec = ITEMS[wi.name] if wi else None
        skilled = n.skill == "戰鬥"
        pin = pin_bonus(g) if pinning(g) else 0
        hit = (70 if skilled else 50) + (10 if n.trait == "冷酷" else 0) + (15 if is_bonded(n) else 0) + pin
        # ---- 有槍：任何姿態都會開火（退後的也會）
        if spec and spec.get("ammo"):
            targets = [e for e in r.enemies if e.dist <= spec["range"]]
            if targets:
                f = focused(g)
                e = f if f in targets else min(targets, key=lambda e: e.dist)
                inv_remove(n.inv, spec["ammo"], 1)
                eng.noise(spec["noise"])
                gun_hit = spec["hit"] + (10 if skilled else 0) + (10 if n.trait == "冷酷" else 0) - 10 + pin
                if eng.rng.randint(1, 100) <= gun_hit:
                    dmg = eng.rng.randint(*spec["dmg"])
                    e.hp -= dmg
                    if e.hp <= 0:
                        notes.append(f"{n.name}開槍打倒{e.label()}")
                        flush()
                        kill(eng, e, melee=False, by_player=False)
                    else:
                        notes.append(f"{n.name}開槍打中{e.label()}(-{dmg})")
                else:
                    notes.append(f"{n.name}開槍打偏")
                continue
        # ---- 近戰：跟著打只打距離 1，上前的連距離 2 也打，退後的不打
        reach = {"attack": 2, "back": 0}.get(n.stance, 1)
        adj = [e for e in r.enemies if e.dist <= reach]
        if adj:
            f = focused(g)
            e = f if f in adj else min(adj, key=lambda e: e.dist)
            if eng.rng.randint(1, 100) <= hit:
                if spec:
                    dmg = eng.rng.randint(*spec["dmg"]) + (3 if skilled else 0)
                else:
                    dmg = eng.rng.randint(10, 16) if skilled else eng.rng.randint(6, 12)
                e.hp -= dmg
                if e.hp <= 0:
                    notes.append(f"{n.name}解決了{e.label()}")
                    flush()
                    kill(eng, e, melee=True, by_player=False)
                else:
                    notes.append(f"{n.name}打中{e.label()}(-{dmg})")
            else:
                notes.append(f"{n.name}揮空")
            continue
        # ---- 沒人搆得到：丟東西引開、或報一下位置
        far = [e for e in r.enemies if e.dist >= 2 and e.distract == 0 and not ENEMIES[e.kind].get("human")]
        thr = next((it for it in n.inv if it.name in ("石頭", "空瓶")), None)
        if far and thr and n.stance != "attack" and eng.rng.random() < 0.6:
            inv_remove(n.inv, thr.name, 1)
            e = eng.rng.choice(far)
            e.distract = 2
            notes.append(f"{n.name}丟{thr.name}引開{e.label()}")
        elif n.stance == "back":
            notes.append(f"{n.name}退在你後面")
        elif n.stance == "attack":
            notes.append(f"{n.name}衝上前找目標")
        else:
            notes.append(f"{n.name}握緊{wi.name if wi else '拳頭'}等牠靠近")
    flush()


def enemy_turn(eng):
    g, p = eng.g, eng.g.player
    if not g.combat:
        return
    companion_turn(eng)
    r = g.cur
    if not r.enemies:
        return
    for e in list(r.enemies):
        spec = ENEMIES[e.kind]
        if e.distract > 0:
            e.distract -= 1
            continue
        if spec.get("ranged") and e.dist <= 3 and eng.rng.random() < 0.6:
            chance = spec["hit"] - 10 * (e.dist - 1)
            if eng.rng.randint(1, 100) <= chance:
                dmg = eng.rng.randint(*spec["dmg"])
                p.hp -= dmg
                eng.say(f"{e.label()}開槍，打中你。-{dmg}")
                if eng.rng.random() < 0.3:
                    p.bleeding = True
            else:
                eng.say(f"{e.label()}開槍，打偏了。")
            eng.noise(2)
            continue
        if e.dist > 1:
            e.dist = max(1, e.dist - spec["speed"])
            if e.dist == 1:
                eng.say(f"{e.label()}撲到你面前。")
            else:
                eng.say(f"{e.label()}逼近到距離{e.dist}。")
            continue
        # 攻擊
        comps = [n for n in g.companions() if n.stance not in ("hide", "back")]
        front = [n for n in comps if n.stance == "attack"]
        guard = [n for n in comps if n.skill == "戰鬥"]
        target_comp = None
        pinned = pinning(g)
        if pinned:
            if comps and eng.rng.random() * 100 >= PIN_DRAW:
                target_comp = eng.rng.choice(comps)
        elif front and eng.rng.random() < 0.6:
            target_comp = eng.rng.choice(front)
        elif comps and eng.rng.random() < (0.45 if guard else 0.3):
            target_comp = eng.rng.choice(comps)
        chance = spec["hit"]
        if p.grabbed and target_comp is None:
            chance += 20
        if pinned and target_comp is None:
            chance += 10
        if eng.rng.randint(1, 100) > chance:
            eng.say(f"{e.label()}撲空了。")
            continue
        dmg = eng.rng.randint(*spec["dmg"])
        if target_comp:
            target_comp.hp -= dmg
            if not target_comp.infected and spec["bite"] and eng.rng.randint(1, 100) <= spec["bite"]:
                target_comp.infected = True
                target_comp.infect_day = g.day
                eng.say(f"{e.label()}咬住了{target_comp.name}的手臂。-{dmg}")
            else:
                eng.say(f"{e.label()}抓傷了{target_comp.name}。-{dmg}")
            if target_comp.hp <= 0:
                target_comp.status = "dead"
                eng.say(f"{target_comp.name}倒下了，沒有再起來。")
                for o in g.companions():
                    if o.trait != "冷酷":
                        o.trust -= 5
                        o.fear += 15
            continue
        shield = [n for n in g.companions() if is_bonded(n) and n.stance not in ("hide", "back") and n.hp > 10]
        if shield and not p.grabbed and not pinned and eng.rng.random() < 0.25:
            s = eng.rng.choice(shield)
            s.hp -= dmg
            eng.say(f"{s.name}擋在你前面，替你挨了這一下。-{dmg}")
            if spec["bite"] and not s.infected and eng.rng.randint(1, 100) <= spec["bite"]:
                s.infected = True
                s.infect_day = g.day
            continue
        if p.painkiller:
            dmg = int(dmg * 0.7)
        p.hp -= dmg
        bite = spec["bite"] * (2 if p.grabbed else 1)
        if bite and eng.rng.randint(1, 100) <= bite:
            inf = eng.rng.randint(20, 35)
            p.infection += inf
            p.bleeding = True
            g.flags["bites"] = g.flags.get("bites", 0) + 1
            eng.say(f"{e.label()}咬進你的肉裡。-{dmg} 你在流血。")
        elif spec["grab"] and not p.grabbed and eng.rng.randint(1, 100) <= spec["grab"]:
            p.grabbed = True
            eng.say(f"{e.label()}抓住了你。-{dmg} 用 push 掙脫。")
        else:
            eng.say(f"{e.label()}抓傷了你。-{dmg}")
            if eng.rng.random() < 0.25:
                p.bleeding = True
                eng.say("傷口在流血。")
    if p.stamina < p.max_stamina():
        p.stamina = min(p.max_stamina(), p.stamina + 5)
    eng.check_death()


def ambush_free_hit(eng, e: Enemy):
    p = eng.g.player
    spec = ENEMIES[e.kind]
    if eng.rng.randint(1, 100) <= spec["hit"] * 0.7:
        dmg = eng.rng.randint(*spec["dmg"])
        p.hp -= dmg
        if eng.rng.randint(1, 100) <= spec["bite"]:
            p.infection += eng.rng.randint(20, 35)
            p.bleeding = True
            eng.g.flags["bites"] = eng.g.flags.get("bites", 0) + 1
            eng.say(f"牠咬到你了。-{dmg}")
        else:
            eng.say(f"牠抓傷你。-{dmg}")


def ambush(eng, room):
    """搜索時觸發藏匿的敵人。"""
    g, p = eng.g, eng.g.player
    if not room.hidden:
        return False
    e = room.hidden.pop(0)
    e.dist = 1
    room.enemies.append(e)
    eng.say(f"一隻{e.kind}從你沒注意的地方撲出來！")
    ambush_free_hit(eng, e)
    start_combat(eng)
    return True
