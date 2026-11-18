# -*- coding: utf-8 -*-
"""時間推進、生存數值、威脅與湧入、死亡判定。"""
import random
from typing import List

from .data import ITEMS, DAY_EVENTS, LOCATIONS, ENEMIES
from .state import Game, Enemy, Item, inv_remove, inv_count, inv_add, new_item


class Engine:
    def __init__(self, g: Game):
        self.g = g
        self.out: List[str] = []
        self.rng = random.Random(f"{g.seed}-{g.turn}")

    # ---------------------------------------------------------- 輸出
    def say(self, text: str):
        if text:
            self.out.append(text)
            self.g.log.append(text)
            if len(self.g.log) > 60:
                del self.g.log[:-60]

    def new_turn(self):
        self.g.turn += 1
        self.rng = random.Random(f"{self.g.seed}-{self.g.turn}")
        self.out = []
        self.g.flags.pop("interrupted", None)
        if self.g.flags.get("confirm") and not self.g.combat:
            pass   # 確認狀態留到下一個指令判斷

    # ---------------------------------------------------------- 噪音
    def noise(self, amount: float, loc: str = None):
        loc = loc or self.g.cur.loc
        self.g.threat[loc] = min(10.0, self.g.threat.get(loc, 0) + amount)

    def noise_bar(self) -> str:
        t = self.g.threat.get(self.g.cur.loc, 0)
        n = int(round(t / 2))
        return "[" + "#" * n + "." * (5 - n) + "]"

    # ---------------------------------------------------------- 時間
    def advance(self, minutes: int, resting: bool = False) -> bool:
        """推進時間。回傳 True 表示被打斷（戰鬥或昏倒）。"""
        g, p = self.g, self.g.player
        remaining = minutes
        while remaining > 0:
            step = min(10, remaining)
            remaining -= step
            prev_hour = g.minute // 60
            g.minute += step
            frac = step / 60.0
            # 基本消耗
            p.hunger = min(100, p.hunger + 2.2 * frac * (0.6 if resting else 1))
            p.thirst = min(100, p.thirst + 3.0 * frac * (0.6 if resting else 1))
            if resting:
                in_base = g.base.room == g.room
                p.fatigue = max(0, p.fatigue - (12 if in_base else 8) * frac)
            else:
                p.fatigue = min(100, p.fatigue + 2.5 * frac)
            if not g.combat:
                p.stamina = min(p.max_stamina(), p.stamina + int(10 * frac * 2))
            # 流血
            if p.bleeding:
                p.hp -= 3
                if self.rng.random() < 0.03 * (step / 10):
                    p.bleeding = False
                    self.say("血止住了。")
            # 感染
            if p.infection > 0:
                rate = 1.0 if p.antibiotic <= 0 else 0.3
                if g.flags.get("difficulty") == "normal":
                    rate *= 0.7
                p.infection = min(100, p.infection + rate * frac)
            # 整點事件
            if g.minute // 60 != prev_hour:
                self.hourly()
                if p.hp <= 0:
                    pass
                elif resting and not p.bleeding and p.hunger < 80 and p.thirst < 80 and p.hp < 100:
                    p.hp = min(100, p.hp + (3 if g.base.room == g.room else 1))
                elif not resting and not p.bleeding and p.hunger < 50 and p.thirst < 50 and p.hp < 100:
                    p.hp = min(100, p.hp + 1)  # 吃飽喝足時清醒也慢慢回血
                if g.combat or g.over:
                    return True
            # 跨日
            if g.minute >= 24 * 60:
                g.minute -= 24 * 60
                g.day += 1
                self.daily()
                if g.combat or g.over:
                    return True
            if self.check_death():
                return True
            # 湧入
            if not g.combat and self.spawn_check(step):
                return True
            if not resting and p.fatigue >= 100:
                self.say("你眼前一黑，倒了下去。")
                self.faint()
                return True
        return False

    def needs_food_tonight(self, n) -> bool:
        """隊友省著吃：食物兩天一份。白天你餵過的今晚不用。"""
        g = self.g
        if n.ate_day == g.day:
            return False
        return n.meal_day == 0 or g.day - n.meal_day >= 2

    def rations(self):
        """今晚隊友要吃多少、手邊有多少。回傳 (要幾份食物, 要幾份水, 手邊食物, 手邊水)。據點箱裡的只有人在據點時算。"""
        g = self.g
        invs = [g.player.inv] + [n.inv for n in g.companions()]
        if g.base.room == g.room:
            invs.append(g.base.storage)
        food = sum(it.qty for inv in invs for it in inv if ITEMS[it.name]["kind"] == "food" and it.name != "腐壞食物")
        water = sum(it.qty for inv in invs for it in inv if ITEMS[it.name]["kind"] == "water" and it.name != "髒水")
        nf = sum(1 for n in g.companions() if self.needs_food_tonight(n))
        nw = sum(1 for n in g.companions() if n.drank_day != g.day)
        return nf, nw, food, water

    def hourly(self):
        g, p = self.g, self.g.player
        for loc in g.threat:
            g.threat[loc] = max(LOCATIONS[loc]["danger"] * 0.5, g.threat[loc] - 1.0)
        # 天黑天亮
        if g.hour == 17:
            self.say("天快黑了。晚上有跑得快的，沒手電筒在外面什麼都看不到。")
            nf, nw, food, water = self.rations()
            if nf or nw:
                lack = "" if food >= nf and water >= nw else "，不夠"
                self.say(f"今晚隊友要吃 {nf} 份食物和 {nw} 份水（食物兩天一份），手邊有食物 {food}、水 {water}{lack}。")
        elif g.hour == 6:
            self.say("天亮了。")
        # 飢渴警示（過 70 提醒一次，降回 60 以下才會再提醒）
        if p.hunger >= 70 and not g.flags.get("warn_hunger"):
            g.flags["warn_hunger"] = 1
            self.say("你餓得頭昏。到 100 就開始掉血。")
        elif p.hunger < 60:
            g.flags.pop("warn_hunger", None)
        if p.thirst >= 70 and not g.flags.get("warn_thirst"):
            g.flags["warn_thirst"] = 1
            self.say("你的嘴唇乾裂，口渴比餓更快殺人。到 100 每小時掉 5 血。")
        elif p.thirst < 60:
            g.flags.pop("warn_thirst", None)
        if p.hunger >= 100:
            p.hp -= 3
            self.say("你餓到胃在絞痛。")
        if p.thirst >= 100:
            p.hp -= 5
            self.say("你的嘴唇裂開了，喉嚨像在燒。")
        if p.sick > 0:
            p.sick -= 1
            p.hp -= 2
            p.thirst = min(100, p.thirst + 4)
        if p.painkiller > 0:
            p.painkiller -= 1
        if p.antibiotic > 0:
            p.antibiotic -= 1
        if p.infection >= 100 - 1e-6:
            p.infection = 100
            p.hp = 0
        # 訊號彈之後的死守
        if g.flags.get("signal_at") and not g.over:
            elapsed = (g.day * 1440 + g.minute) - g.flags["signal_at"]
            if elapsed >= 180:
                if g.room == "辦公大樓·屋頂":
                    g.over = "evac_vaccine" if inv_count(p.inv, "疫苗樣本") else "evac"
                    self.say("螺旋槳的聲音蓋過了一切。繩梯垂下來。")
                else:
                    self.say("你聽到直升機在屋頂上方盤旋了一陣。沒看到人，它飛走了。")
                    g.flags.pop("signal_at", None)
                return
            if g.room == "辦公大樓·屋頂":
                n = self.rng.randint(2, 4)
                for _ in range(n):
                    k = self.rng.choice(["行屍", "行屍", "疾走者"])
                    g.cur.enemies.append(Enemy(k, 22 if k == "疾走者" else 30, dist=self.rng.randint(3, 4)))
                self.say(f"樓梯間傳來撞門聲。又一波上來了，還剩 {180 - elapsed} 分鐘。")
                from .combat import start_combat
                start_combat(self)
            else:
                self.say("你不在屋頂。直升機來的時候找不到人就會走。")
        # 第 14 天中午沒走成
        if g.day >= 14 and g.hour >= 12 and not g.over and not g.flags.get("signal_at"):
            g.over = "survived"
        # 喪屍遊走
        self.waiting_tick()
        self.wander()
        # 感染提示（不顯示數值）
        if p.infection > 0 and self.rng.random() < 0.25:
            if p.infection > 60:
                self.say("你的傷口邊緣發黑了，而且不痛，這才是最可怕的。")
            elif p.infection > 30:
                self.say("你覺得有點發冷，手在抖。")
        # 隊友流血/感染（簡化：隊友只有血量和感染旗標）
        for n in g.companions():
            if n.infected and n.infect_day and g.day - n.infect_day >= 2 and self.rng.random() < 0.15 and not n.revealed:
                self.say(f"{n.name}一直在咳嗽，眼睛有點發黃。")

    def waiting_tick(self):
        """留守的人每小時：房裡沒喪屍就回血；有喪屍就看運氣，被抓到掉血、可能被咬。消息等他歸隊時再講。"""
        g = self.g
        for n in list(g.waiting()):
            r = g.rooms.get(f"{n.loc}·{n.room}")
            if not r:
                continue
            zs = [e for e in r.enemies if not ENEMIES[e.kind].get("human")]
            news = g.flags.setdefault(f"wait_news_{n.name}", [])
            if not zs:
                n.hp = min(n.max_hp, n.hp + 4)
                n.fear = max(0, n.fear - 2)
                continue
            dodge = 0.75 if n.skill == "戰鬥" else 0.5
            if self.rng.random() < dodge:
                continue
            n.hp -= 8
            if not n.infected and self.rng.random() < 0.25:
                n.infected = True
                n.infect_day = g.day
            if n.hp <= 0:
                n.status = "dead"
                r.items.extend(n.inv)
                n.inv = []
                news.append(f"{n.name}沒撐過去。牠們進來的時候他一個人。")
            elif not any("進來過" in x for x in news):
                news.append(f"{n.name}身上多了傷：你不在的時候牠們進來過。")

    def waiting_daily(self):
        """留守在據點以外、過了一天你還沒回那區：有據點就自己退回據點等，沒據點就繼續待著。"""
        g = self.g
        if not g.base.room:
            return
        base = g.rooms[g.base.room]
        for n in g.waiting():
            at_base = f"{n.loc}·{n.room}" == g.base.room
            if at_base or g.day - n.wait_day < 1 or g.cur.loc == n.loc:
                continue
            n.loc, n.room = base.loc, base.name
            g.flags.setdefault(f"wait_news_{n.name}", []).append(f"{n.name}等不到你，自己摸回據點了。")

    def rejoin_waiting(self):
        """走進留守的人所在的房間：他歸隊，順便把你不在時發生的事講出來。死在那裡的人只講一次。"""
        g = self.g
        for n in g.waiting_at(g.room):
            n.status = "companion"
            for line in g.flags.pop(f"wait_news_{n.name}", []):
                self.say(line)
            self.say(f"{n.name}站起來歸隊。血 {n.hp}/{n.max_hp}。")
        for n in g.npcs:
            if n.status == "dead" and f"{n.loc}·{n.room}" == g.room and not g.flags.get(f"seen_dead_{n.name}"):
                g.flags[f"seen_dead_{n.name}"] = True
                for line in g.flags.pop(f"wait_news_{n.name}", []):
                    self.say(line)
                self.say(f"角落躺著{n.name}。他的東西散在地上。")

    def wander(self) -> bool:
        """每小時每隻喪屍有 6% 機率走到同棟相鄰的房間（不進街道、據點、勢力房、鎖著的門），一天下來約七成會換過位置。
        走進你所在的房間就開戰，牠從距離 4 進來。人類敵人不遊走。"""
        g = self.g
        if g.over:
            return False
        moved_in = []
        for r in list(g.rooms.values()):
            if r.is_street() or not r.enemies or r.id == g.room or r.id == g.base.room or "faction" in r.tags:
                continue
            for e in list(r.enemies):
                if ENEMIES[e.kind].get("human") or self.rng.random() >= 0.06:
                    continue
                exits = [g.rooms[t] for d, t in r.exits.items() if d not in ("進", "出")]
                exits = [t for t in exits if not t.locked and not t.is_street() and t.id != g.base.room and "faction" not in t.tags]
                if not exits:
                    continue
                t = self.rng.choice(exits)
                r.enemies.remove(e)
                e.dist = 4
                e.distract = 0
                t.enemies.append(e)
                if t.id == g.room:
                    moved_in.append(e)
        if moved_in and not g.combat:
            from .combat import start_combat
            start_combat(self, "門被推開了。有東西從隔壁走了進來。")
            return True
        return False

    def daily(self):
        g = self.g
        self.say(f"=== 第 {g.day} 天 ===")
        self.waiting_daily()
        if g.day in DAY_EVENTS:
            self.say(DAY_EVENTS[g.day])
        if g.day == 11:
            g.flags["checkpoint_gone"] = 1
            g.factions["軍方"] = 0
        if g.day == 6 and g.base.room:
            self.say("你的據點門口有不是你的腳印。碼頭那群人在打量這裡。明天起他們會動手：加固到 3 或留人守夜才擋得住。")
        if g.day == 7:
            g.flags["raiders_active"] = 1
        # 食物腐壞
        for inv in [g.player.inv, g.base.storage] + [r.items for r in g.rooms.values()] + [r.loot for r in g.rooms.values()]:
            for it in list(inv):
                sp = ITEMS[it.name].get("spoil", 0)
                if sp and g.day - it.made_day >= sp:
                    inv.remove(it)
                    inv.append(Item("腐壞食物", it.qty))
        # 隊友吃飯
        self.feed_companions()
        # 掠奪者
        from .events import raid_check
        raid_check(self)
        # 感染的隊友轉化
        for n in g.companions():
            if n.infected and n.infect_day and g.day - n.infect_day >= 3:
                self.say(f"{n.name}在夜裡沒了呼吸，然後又站了起來。")
                n.status = "dead"
                g.cur.enemies.append(Enemy("行屍", 30, dist=1, name=f"{n.name}（已轉化）"))
                g.flags["turned_companion"] = g.flags.get("turned_companion", 0) + 1
                from .combat import start_combat
                start_combat(self)
        if g.day >= 14 and g.over == "":
            self.final_day()

    def final_day(self):
        g = self.g
        if g.goal == "撤離":
            self.say("第 14 天到了。收音機裡傳來：直升機 06:00 到 12:00 會在辦公大樓屋頂等。在那裡用 signal 發訊號。")
        elif g.goal == "疫苗":
            self.say("第 14 天到了。檢查站早就撤了，樣本只能靠你自己帶出去。辦公大樓屋頂也許還有直升機。")
        else:
            self.say(f"第 14 天到了。目前送到教堂的人數：{g.placed}/5。修女說車 12:00 前會到。")
        g.flags["final_day"] = 1

    # ---------------------------------------------------------- 隊友吃飯
    def _take_antibiotic(self, patient):
        """從病人自己、玩家、其他隊友、據點儲物箱（人在據點）找一顆抗生素扣掉。有就回 True。"""
        g = self.g
        pools = [patient.inv, g.player.inv] + [n.inv for n in g.companions() if n is not patient]
        if g.base.room == g.room:
            pools.append(g.base.storage)
        for inv in pools:
            if inv_count(inv, "抗生素"):
                inv_remove(inv, "抗生素", 1)
                return True
        return False

    def medic_care(self):
        """醫療技能的隊友每天：幫你換藥壓感染；看出被咬的隊友，有抗生素就餵他（有機會治好）。"""
        from .npc import try_cure
        g, p = self.g, self.g.player
        doc = next((n for n in g.companions() if n.skill == "醫療"), None)
        if not doc:
            return
        if p.infection > 0:
            p.infection = max(0, p.infection - 8)
            self.say(f"{doc.name}幫你換了藥，傷口看起來好一點。")
        for n in list(g.companions()):
            if not n.infected:
                continue
            if not self._take_antibiotic(n):
                if not n.revealed:
                    n.revealed = True
                    self.say(f"{doc.name}看了{n.name}的手臂一眼，把你拉到旁邊：「他被咬了。沒有抗生素我沒辦法。」")
                else:
                    self.say(f"{doc.name}：「{n.name}需要抗生素，快。」")
                continue
            if not n.revealed:
                n.revealed = True
                self.say(f"{doc.name}看了{n.name}的手臂一眼，什麼都沒說，塞給他一顆抗生素。")
            try_cure(self, n, who=f"{doc.name}讓{n.name}")

    def companion_self_care(self):
        """隊友每天會自己用背包裡的東西：被咬的偷偷吃抗生素、受傷的換繃帶或用急救包。"""
        from .npc import try_cure
        g = self.g
        for n in list(g.companions()):
            if n.infected and inv_count(n.inv, "抗生素"):
                inv_remove(n.inv, "抗生素", 1)
                if n.revealed:
                    try_cure(self, n)
                else:
                    ok = self._quiet_cure(n)
                    self.say(f"你注意到{n.name}背包裡的抗生素少了一顆。" + ("他今天氣色好多了。" if ok else "他沒提。"))
            if n.hp < n.max_hp * 0.5 and inv_count(n.inv, "急救包"):
                inv_remove(n.inv, "急救包", 1)
                n.hp = min(n.max_hp, n.hp + 40)
                self.say(f"{n.name}自己用掉了急救包。血 {n.hp}/{n.max_hp}。")
            elif n.hp < n.max_hp * 0.6 and inv_count(n.inv, "繃帶"):
                inv_remove(n.inv, "繃帶", 1)
                n.hp = min(n.max_hp, n.hp + 15)
                self.say(f"{n.name}自己換了繃帶。血 {n.hp}/{n.max_hp}。")

    def _quiet_cure(self, n) -> bool:
        """沒被揭穿的隊友偷偷吃藥：不印治療句子，只回有沒有治好。"""
        from .npc import cure_chance
        if self.rng.randint(1, 100) <= cure_chance(self.g, n):
            n.infected = False
            n.infect_day = 0
            return True
        n.infect_day += 2
        return False

    def feed_companions(self):
        g = self.g
        self.companion_self_care()
        self.medic_care()
        yesterday = g.day - 1
        for n in g.companions():
            fed = False
            # 食物兩天一份（省著吃）；白天你餵過的，晚上那份就省了
            need_food = n.ate_day != yesterday and (n.meal_day == 0 or yesterday - n.meal_day >= 2)
            need_water = n.drank_day != yesterday
            if n.ate_day == yesterday:
                n.meal_day = yesterday
            if not need_food and not need_water:
                fed = True
            for inv in (n.inv, g.base.storage if g.base.room == g.room else [], g.player.inv):
                if fed:
                    break
                food = None if not need_food else next((it for it in inv if ITEMS[it.name]["kind"] == "food" and it.name != "腐壞食物"), None)
                water = None if not need_water else next((it for it in inv if ITEMS[it.name]["kind"] == "water" and it.name != "髒水"), None)
                if (food or not need_food) and (water or not need_water):
                    if food:
                        inv_remove(inv, food.name, 1)
                        n.meal_day = yesterday
                    if water:
                        inv_remove(inv, water.name, 1)
                        if water.name != "髒水":            # 空瓶留在水原本放的地方
                            inv_add(inv, new_item("空瓶"), g.player.slots if inv is g.player.inv else 999)
                    fed = True
                    break
            if fed:
                n.unfed_days = 0
                n.hp = min(n.max_hp, n.hp + 10)
                if need_food and need_water:
                    self.say(f"{n.name}吃了一份食物和水。")
                elif need_water:
                    self.say(f"{n.name}喝了水，食物省著，明天再吃。")
                elif need_food:
                    self.say(f"{n.name}吃了一份食物。")
            else:
                n.unfed_days += 1
                n.trust -= 12
                n.fear += 10
                self.say(f"{n.name}今天沒東西吃，臉色很難看。")
                limit = 3 if n.trait == "忠誠" else 2
                if n.unfed_days >= limit:
                    self.say(f"{n.name}受夠了，趁你不注意走了。")
                    self.companion_leaves(n, steal=(n.trait == "貪婪"))

    def companion_leaves(self, n, steal=False):
        g = self.g
        n.status = "left"
        n.loc, n.room = g.cur.loc, g.cur.name
        if steal and g.player.inv:
            victim = self.rng.choice(g.player.inv)
            g.player.inv.remove(victim)
            from .state import sync_weapon
            sync_weapon(g.player)
            self.say(f"{n.name}順手拿走了你的{victim.label()}。")

    # ---------------------------------------------------------- 湧入
    def spawn_check(self, step: int) -> bool:
        g = self.g
        loc = g.cur.loc
        if "faction" in g.cur.tags and g.factions.get(LOCATIONS[loc].get("faction", ""), 0) > 20:
            return False
        t = g.threat.get(loc, 0)
        if t < 6:
            return False
        p = (t - 5) * 0.02 * (step / 10)
        if g.is_night():
            p *= 1.5
        if g.room == g.base.room:
            p *= max(0.2, 1 - g.base.fort * 0.15)
        if self.rng.random() < p:
            n = 1 + (1 if t >= 8 else 0) + (1 if self.rng.random() < 0.3 else 0)
            kinds = ["行屍"] * 3
            if g.is_night():
                kinds += ["疾走者"] * (3 if g.day >= 9 else 1)
            for _ in range(n):
                k = self.rng.choice(kinds)
                g.cur.enemies.append(Enemy(k, 22 if k == "疾走者" else 30, dist=self.rng.randint(2, 4)))
            g.threat[loc] = max(2, t - 3)
            self.say("你聽到腳步聲，不只一個。牠們找到你了。")
            g.combat = True
            return True
        return False

    def faint(self):
        g, p = self.g, self.g.player
        p.fatigue = 60
        hours = self.rng.randint(3, 6)
        for _ in range(hours):
            g.minute += 60
            self.hourly()
            if g.minute >= 24 * 60:
                g.minute -= 24 * 60
                g.day += 1
                self.daily()
            if g.combat or g.over:
                return
        p.hunger = min(100, p.hunger + hours * 2)
        p.thirst = min(100, p.thirst + hours * 3)
        if self.rng.random() < 0.5 + 0.1 * LOCATIONS[g.cur.loc]["danger"]:
            self.say(f"你醒來時已經過了 {hours} 小時，有東西正在啃你的腳。")
            p.hp -= 20
            p.bleeding = True
            p.infection += 20
            g.cur.enemies.append(Enemy("行屍", 30, dist=1))
            g.combat = True
        else:
            self.say(f"你醒來時已經過了 {hours} 小時。運氣好，什麼都沒來。")

    # ---------------------------------------------------------- 死亡
    def check_death(self) -> bool:
        p = self.g.player
        if self.g.over:
            return True
        if p.hp <= 0:
            if p.infection >= 100:
                self.g.over = "infection"
                self.say("你的視線變灰，然後你不再覺得餓了。不，你覺得餓，但不是那種餓。")
            else:
                self.g.over = "dead"
                self.say("你倒在地上，最後聽到的是自己的血滴在地板上的聲音。")
            return True
        return False

    # ---------------------------------------------------------- 顯示
    def status_line(self) -> str:
        g, p = self.g, self.g.player
        base = g.rooms[g.base.room].full if g.base.room else "無"
        comps = " ".join(f"{n.name}({'傷' if n.hp < n.max_hp * 0.5 else '健'})" for n in g.companions()) or "無"
        w = p.weapon or "徒手"
        wi = next((it for it in p.inv if it.name == p.weapon), None)
        wl = wi.label() if wi else w
        from .world import room_floor, floor_label
        from .combat import experience
        r = g.cur
        where = f"{r.loc}·{r.name}" + ("" if r.is_street() else f" {floor_label(room_floor(r.tags))}")
        line1 = f"第{g.day}天 {g.phase()} {g.clock()} | {where}"
        line2 = (f"血{p.hp:>3} 飢{int(p.hunger):>3} 渴{int(p.thirst):>3} 疲{int(p.fatigue):>3} 體{p.stamina:>3} | "
                 f"噪音{self.noise_bar()} | {wl} | {experience(g)['label']}")
        line3 = f"據點 {base} | 隊友 {comps}"
        if g.waiting():
            line3 += " | 留守 " + " ".join(
                f"{n.name}@{'據點' if f'{n.loc}·{n.room}' == g.base.room else n.loc}" for n in g.waiting())
        cond = self.condition_line()
        if cond:
            line3 += " | " + cond
        return line1 + "\n" + line2 + "\n" + line3

    def condition_line(self) -> str:
        """身上的狀態，一行；沒事就回傳空字串。畫面上放在「這裡」下面。"""
        p = self.g.player
        from .combat import aim_bonus
        flags = []
        if self.g.flags.get("interrupted"):
            flags.append("！" + self.g.flags["interrupted"] + "，敵人在這裡")
        if p.bleeding:
            flags.append("流血")
        if p.sick:
            flags.append(f"腹痛{p.sick}h")
        if p.grabbed:
            flags.append("被抓住")
        if p.aimed:
            from .combat import rates_after_aim
            hc, hh = rates_after_aim(self, 0)
            flags.append(f"瞄準中(攻{hc}%/頭{hh}%)")
        if p.painkiller:
            flags.append(f"止痛{p.painkiller}h")
        if p.antibiotic:
            flags.append(f"抗生素{p.antibiotic}h")
        if p.infection > 60:
            flags.append("傷口發黑")
        elif p.infection > 30:
            flags.append("發冷")
        return " ".join(flags)

    def room_desc(self, brief=False) -> str:
        g = self.g
        r = g.cur
        lines = []
        if r.is_street():
            lines.append(f"你在{r.loc}的{r.name}。{LOCATIONS[r.loc]['desc']}")
        else:
            from .world import room_floor, floor_label
            k = room_floor(r.tags)
            where = f"{r.loc}{floor_label(k)}的{r.name}" if k != 1 else f"{r.loc}的{r.name}"
            lines.append(f"你在{where}。" + ("" if brief else r.flavor))
        if r.enemies:
            lines.append("這裡有：" + "、".join(f"{e.label()}(距離{e.dist})" for e in r.enemies))
        # 地上的東西、在場的人、出口固定顯示在畫面的「這裡」那行，這裡不重複
        return "\n".join(lines)
