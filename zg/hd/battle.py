# -*- coding: utf-8 -*-
"""HD-2D 版的戰鬥：每個單位輪流行動、四段距離帶、環境指令、隊友會不聽話。

設計依據：docs/GAME_DESIGN_HD2D.md 第五節。核心是「牠還有幾步會到，我在那之前能做幾件事」。
數值以文字版為起點，不保證相同；都還沒有實際玩過平衡。

用法：
    b = Battle(eng, [(enemy, room.enemies, {"band": 3})], opener="enemy", env=[...])
    b.view()                      # 現在的狀況，含輪到誰、他能下哪些指令
    b.act("p", "attack", {"target": "e1"})   # 回傳這個動作引發的事件，一路算到下一個要下指令的人
"""
from ..combat import AIM_MAX, aim_bonus, companion_weapon, experience, is_bonded, pin_bonus
from ..data import ENEMIES, ITEMS
from ..state import inv_count, inv_remove, new_item
from .rules import BAND_NAME, noise_radius

MELEE_REACH = {1: 0}
# 每把武器在各個距離的命中修正；表上沒有的距離打不到。「最順手」的距離是 0
REACH = {
    "消防斧": {1: 0, 2: -20},
    "霰彈槍": {1: -5, 2: 0, 3: -20},
    "手槍": {1: -10, 2: -5, 3: 0, 4: -20},
}
THROW_BANDS = (2, 3, 4)
FIST = {"name": "拳頭", "dmg": (3, 6), "hit": 50, "noise": 0, "dur": 99, "stam": 6}
CLUB = {"dmg": (4, 9), "hit": 60, "noise": 1, "dur": 99, "stam": 7}     # 沒子彈的槍倒過來握

TAUNT_DRAW = 80          # 牽制時牠們找牽制者的機率（%）
PUSH_CHANCE = 75
DOOR_HOLD = 3            # 關上的門撐得住幾下
DOOR_HOLD_MAX = 6
RISKY = ("front", "taunt", "cover", "choke")      # 信任低時隊友可能不做的指令
INITIATIVE = {"疾走者": 7, "行屍": 3, "腫脹者": 1}

REFUSE_LINES = {
    "怯懦": "我、我不行……我過不去。",
    "貪婪": "要去你自己去，我不幹賠本的事。",
    "冷酷": "我不替別人擋。",
    "實際": "那樣會死人。我照我的判斷來。",
}


def obey_label(chance: int) -> str:
    if chance >= 90:
        return "會聽"
    if chance >= 65:
        return "大概會聽"
    if chance >= 40:
        return "可能不聽"
    return "多半不聽"


class Ally:
    """我方的一個人。數值直接讀寫 Player 或 NPC，戰鬥打完不用再同步。"""

    def __init__(self, ref, is_player: bool):
        self.ref = ref
        self.is_player = is_player
        self.uid = "p" if is_player else "c:" + ref.name
        self.row = "back" if (not is_player and ref.stance == "back") else "front"
        self.aim = 0
        self.grabbed = False
        self._stamina = 100
        self.cover = None        # 正在替誰擋（uid）
        self.taunt = False
        self.in_cover = False    # 躲在家具後面
        self.out = ""            # ""在場 / hid 躲起來了 / dead

    @property
    def name(self):
        return "你" if self.is_player else self.ref.name

    @property
    def hp(self):
        return self.ref.hp

    @hp.setter
    def hp(self, v):
        self.ref.hp = v

    @property
    def max_hp(self):
        return 100 if self.is_player else self.ref.max_hp

    @property
    def stamina(self):
        return self.ref.stamina if self.is_player else self._stamina

    @stamina.setter
    def stamina(self, v):
        v = max(0, min(self.max_stamina, int(v)))
        if self.is_player:
            self.ref.stamina = v
        else:
            self._stamina = v

    @property
    def max_stamina(self):
        return self.ref.max_stamina() if self.is_player else 100

    @property
    def inv(self):
        return self.ref.inv

    @property
    def trait(self):
        return "" if self.is_player else self.ref.trait

    @property
    def skill(self):
        return "" if self.is_player else self.ref.skill

    @property
    def trust(self):
        return 100 if self.is_player else self.ref.trust

    @property
    def fear(self):
        return 0 if self.is_player else self.ref.fear

    @property
    def bonded(self):
        return (not self.is_player) and is_bonded(self.ref)

    def weapon_item(self):
        if self.is_player:
            return next((it for it in self.inv if it.name == self.ref.weapon), None) if self.ref.weapon else None
        return companion_weapon(self.ref)

    def weapon(self):
        """回傳（規格, 物品, 子彈名）。沒武器是拳頭；槍沒子彈就倒過來握，只能打貼身。"""
        it = self.weapon_item()
        if not it:
            s = dict(FIST)
            s["reach"] = MELEE_REACH
            return s, None, None
        s = dict(ITEMS[it.name])
        s["name"] = it.name
        ammo = s.get("ammo")
        if ammo and inv_count(self.inv, ammo) <= 0:
            s.update(CLUB)
            s["name"] = it.name + "的槍托"
            s["reach"] = MELEE_REACH
            return s, it, None
        s["reach"] = REACH.get(it.name, MELEE_REACH)
        return s, it, ammo


class Foe:
    """一隻敵人。血量、距離、分心直接讀寫房間裡的 Enemy。"""

    def __init__(self, e, home, uid, via=None, tags=()):
        self.e = e
        self.home = home         # 牠所在房間的 enemies list，倒下時從裡面拿掉
        self.uid = uid
        self.via = via           # 牠要從哪扇門進來（環境物件的 id）；已經在房間裡就是 None
        self.slow = 0            # 腿被打了幾次
        self.stagger = 0         # 踉蹌，還有幾回合不能動
        self.tick = 0
        self.vest = "vest" in tags       # 防彈背心：打身體傷害減半
        self.helmet = "helmet" in tags   # 安全帽：打頭要先把它打掉
        e.dist = max(1, min(4, int(e.dist)))

    @property
    def kind(self):
        return self.e.kind

    @property
    def spec(self):
        return ENEMIES[self.e.kind]

    @property
    def label(self):
        return self.e.label()

    @property
    def hp(self):
        return self.e.hp

    @hp.setter
    def hp(self, v):
        self.e.hp = v

    @property
    def band(self):
        return self.e.dist

    @band.setter
    def band(self, v):
        self.e.dist = max(1, min(4, int(v)))

    @property
    def distract(self):
        return self.e.distract

    @distract.setter
    def distract(self, v):
        self.e.distract = v

    @property
    def human(self):
        return bool(self.spec.get("human"))

    def pace(self):
        """（一次走幾段, 每幾回合走一次）。腿被打一次少一段，少到沒有就改成隔更多回合才走。"""
        base_period = 2 if self.kind == "腫脹者" else 1
        eff = self.spec["speed"] - self.slow
        if eff >= 1:
            return eff, base_period
        return 1, base_period + (1 - eff)


class Battle:
    def __init__(self, eng, foes, opener="neutral", env=None, tick=None):
        """foes：[(Enemy, 牠所在房間的 enemies list, {"band": 3, "via": "door_a", "tags": ["vest"]})]
        opener："enemy" 牠先發現你 / "player" 你先動手 / "neutral"
        env：這個房間裡能用的東西，見 docs/RULES_BRIDGE.md
        tick：每過一回合呼叫一次 tick(1)，讓外面推進時鐘"""
        self.eng = eng
        self.g = g = eng.g
        self.tick = tick
        self.allies = [Ally(g.player, True)] + [Ally(n, False) for n in g.companions() if n.stance != "hide"]
        self.foes = []
        self._n = 0
        self.env = {d["id"]: dict(d) for d in (env or [])}
        self.opener = opener
        self.round = 0
        self.queue = []
        self.waiting = None      # 正在等玩家下指令的那個人
        self.events = []
        self.over = ""           # "" / won / fled / dead
        self.taunter = None
        self.choke = None        # 守住門口的人
        self.dark = False
        self.drops = []
        self.corpses = 0         # 還沒被翻過的屍體，貪婪的人會去翻
        self.chasers = []
        self.start = {"hp": g.player.hp, "kills": g.flags.get("kills", 0), "bites": g.flags.get("bites", 0)}
        g.combat = True
        g.flags["fights"] = g.flags.get("fights", 0) + 1
        g.player.aimed = 0
        g.player.grabbed = False
        for e, home, info in foes:
            self._add(e, home, info or {})
        if opener == "player":
            for a in self.allies:
                a.aim = 1
        opening = {"enemy": "牠們先發現了你。", "player": "你先動手。牠們還沒反應過來。"}.get(opener, "戰鬥開始。")
        self.ev("start", opening, opener=opener)
        self._new_round()
        self.run()

    # ------------------------------------------------------------ 基礎
    @property
    def rng(self):
        return self.eng.rng

    def ev(self, t, text="", **kw):
        d = {"t": t}
        if text:
            d["text"] = text
            log = self.g.log             # 只記進紀錄，不進 eng.out：事件本身就會送到畫面
            log.append(text)
            if len(log) > 60:
                del log[:-60]
        d.update(kw)
        self.events.append(d)

    def drain(self):
        out, self.events = self.events, []
        return out

    def noise(self, amount):
        if amount and amount > 0:
            self.eng.noise(amount)
            self.ev("noise", amount=amount, radius=noise_radius(amount))

    def active(self):
        return [a for a in self.allies if not a.out]

    def ally(self, uid):
        return next((a for a in self.allies if a.uid == uid), None)

    def foe(self, uid):
        return next((f for f in self.foes if f.uid == uid), None)

    def _add(self, e, home, info):
        self._n += 1
        if "band" in info:
            e.dist = info["band"]
        f = Foe(e, home, "e%d" % self._n, via=info.get("via"), tags=info.get("tags", ()))
        e.uid = self._n
        self.foes.append(f)
        return f

    def join(self, e, home, info=None):
        """戰鬥中闖進來的敵人。預設從「遠」開始。"""
        info = dict(info or {})
        info.setdefault("band", 4)
        f = self._add(e, home, info)
        self.ev("join", f"{f.label}闖了進來。", foe=f.uid, band=f.band, via=f.via)
        return f

    def _init(self, u):
        if isinstance(u, Ally):
            v = 6 if u.is_player else 5 + (1 if u.skill == "戰鬥" else 0)
            if self.round == 1 and self.opener == "player":
                v += 10
        else:
            v = INITIATIVE.get(u.kind, 5)
            if self.round == 1 and self.opener == "enemy":
                v += 10
        return v

    def _new_round(self):
        self.round += 1
        if self.round > 1 and self.tick:
            self.tick(1)
        units = self.active() + list(self.foes)
        order = sorted(enumerate(units), key=lambda iu: (-self._init(iu[1]), iu[0]))
        self.queue = [u for _, u in order]
        self.ev("round", n=self.round, order=[u.uid for u in self.queue])

    def _check_end(self) -> bool:
        if self.over:
            return True
        if self.g.over or self.g.player.hp <= 0:
            self.eng.check_death()
            self._finish("dead")
        elif not self.foes:
            self._finish("won")
        return bool(self.over)

    def _finish(self, result):
        g, p = self.g, self.g.player
        self.over = result
        self.waiting = None
        g.combat = False
        p.aimed = 0
        p.grabbed = False
        for a in self.allies:
            if a.out == "hid":
                a.ref.stance = ""
        for it in self.drops:
            g.cur.items.append(it)
        kills = g.flags.get("kills", 0) - self.start["kills"]
        lost = max(0, self.start["hp"] - p.hp)
        bites = g.flags.get("bites", 0) - self.start["bites"]
        text = {"won": "安靜了。", "fled": "你們衝了出去。", "dead": ""}[result]
        if result != "dead":
            text += f"這場：殺 {kills}，掉 {lost} 血，被咬 {bites} 次。"
        self.ev("end", text, result=result, kills=kills, hp_lost=lost, bites=bites,
                drops=[it.name for it in self.drops], chasers=list(self.chasers))

    def run(self):
        """一路算下去，直到輪到一個要玩家下指令的人，或戰鬥結束。"""
        for _ in range(1000):
            if self._check_end():
                return
            if not self.queue:
                self._new_round()
                continue
            u = self.queue[0]
            if isinstance(u, Foe):
                self.queue.pop(0)
                if u in self.foes:
                    self._foe_turn(u)
                continue
            if u.out:
                self.queue.pop(0)
                continue
            if self._ally_turn_start(u):
                self.waiting = u
                self.ev("turn", unit=u.uid)
                return
            self.queue.pop(0)
        raise RuntimeError("戰鬥沒有結束")

    def _end_turn(self, a):
        self.waiting = None
        if self.queue and self.queue[0] is a:
            self.queue.pop(0)

    # ------------------------------------------------------------ 敵人的回合
    def eta(self, f) -> int:
        """照牠現在的速度，還要幾個回合才會貼上來。不算門和被擋住的情況。0 是已經貼身。"""
        band, tick, wait = f.band, f.tick, f.stagger + f.distract
        steps, period = f.pace()
        n = 0
        while band > 1 and n < 30:
            n += 1
            if wait > 0:
                wait -= 1
                continue
            tick += 1
            if tick % period == 0:
                band = max(1, band - steps)
        return n

    def _blocking_door(self, f):
        if f.via and f.band == 4:
            d = self.env.get(f.via)
            if d and d.get("closed"):
                return d
        return None

    def _choke_full(self, f) -> bool:
        holder = self.ally(self.choke) if self.choke else None
        if not holder or holder.out or holder.row != "front" or holder.grabbed:
            return False
        return any(o is not f and o.band == 1 for o in self.foes)

    def _foe_turn(self, f):
        spec = f.spec
        if f.stagger > 0:
            f.stagger -= 1
            self.ev("foe_wait", foe=f.uid, why="stagger")
            return
        if f.distract > 0:
            f.distract -= 1
            self.ev("foe_wait", foe=f.uid, why="distract")
            return
        door = self._blocking_door(f)
        if door:
            door["hold"] = door.get("hold", DOOR_HOLD) - 1
            self.noise(0.5)
            if door["hold"] <= 0:
                door["closed"] = False
                door["broken"] = True
                self.ev("door", "門被撞開了。", env=door["id"], state="broken", foe=f.uid)
            else:
                self.ev("door", f"{f.label}在撞門。門還撐得住 {door['hold']} 下。", env=door["id"], state="bash",
                        foe=f.uid, hold=door["hold"])
            return
        if spec.get("ranged") and f.band <= 3 and self.rng.random() < 0.6:
            self._foe_shoot(f)
            return
        if f.band > 1:
            self._foe_move(f)
            return
        self._foe_bite(f)

    def _foe_move(self, f):
        f.tick += 1
        steps, period = f.pace()
        if f.tick % period:
            self.ev("foe_wait", foe=f.uid, why="slow")
            return
        new = max(1, f.band - steps)
        if new == 1 and self._choke_full(f):
            new = 2
        if new == f.band:
            self.ev("foe_wait", f"{f.label}被擋在門口，擠不進來。", foe=f.uid, why="choke")
            return
        f.band = new
        text = f"{f.label}撲到面前。" if new == 1 else f"{f.label}逼近到「{BAND_NAME[new]}」。"
        self.ev("move", text, foe=f.uid, band=new)

    def _pick_target(self, ranged=False):
        act = self.active()
        pool = act if ranged else ([a for a in act if a.row == "front"] or act)
        if self.taunter in pool and self.rng.random() * 100 < TAUNT_DRAW:
            return self.taunter
        weights = [2.0 if a.is_player else 1.5 if a.skill == "戰鬥" else 1.0 for a in pool]
        return self.rng.choices(pool, weights)[0]

    def _redirect(self, t):
        """有人替他擋嗎？回傳（實際挨打的人, 原因）。"""
        cov = next((a for a in self.active() if a.cover == t.uid and a is not t and not a.grabbed), None)
        if cov:
            return cov, "cover"
        if t.is_player and not t.taunt and not t.grabbed:
            shield = [a for a in self.active() if a.bonded and a.row == "front" and a.hp > 10]
            if shield and self.rng.random() < 0.25:
                return self.rng.choice(shield), "shield"
        return t, ""

    def _foe_bite(self, f):
        spec = f.spec
        t = self._pick_target()
        chance = spec["hit"] + (20 if t.grabbed else 0) + (10 if t.taunt else 0)
        if self.rng.randint(1, 100) > chance:
            self.ev("foe_attack", f"{f.label}撲向{t.name}，撲空了。", foe=f.uid, dst=t.uid, hit=False)
            return
        t, how = self._redirect(t)
        self._hurt(f, t, self.rng.randint(*spec["dmg"]), how)

    def _foe_shoot(self, f):
        spec = f.spec
        t = self._pick_target(ranged=True)
        chance = spec["hit"] - 10 * (f.band - 1) - (25 if t.in_cover else 0) - (20 if self.dark else 0)
        self.noise(2)
        if self.rng.randint(1, 100) > chance:
            self.ev("foe_attack", f"{f.label}開槍，打偏了。", foe=f.uid, dst=t.uid, hit=False, shot=True)
            return
        t, how = self._redirect(t)
        self._hurt(f, t, self.rng.randint(*spec["dmg"]), how, shot=True)

    def _hurt(self, f, t, dmg, how="", shot=False):
        g, p, spec = self.g, self.g.player, f.spec
        if t.is_player and p.painkiller:
            dmg = int(dmg * 0.7)
        t.hp -= dmg
        lead = {"cover": f"{t.name}擋在前面。", "shield": f"{t.name}擋在你前面，替你挨了這一下。"}.get(how, "")
        res = "hit"
        if shot:
            text = f"{f.label}開槍，打中{t.name}。-{dmg}"
            if t.is_player and self.rng.random() < 0.3:
                p.bleeding = True
                res = "bleed"
        else:
            bite = spec["bite"] * (2 if t.grabbed else 1)
            if bite and self.rng.randint(1, 100) <= bite:
                res = "bite"
                if t.is_player:
                    p.infection += self.rng.randint(20, 35)
                    p.bleeding = True
                    g.flags["bites"] = g.flags.get("bites", 0) + 1
                    text = f"{f.label}咬進你的肉裡。-{dmg} 你在流血。"
                else:
                    if not t.ref.infected:
                        t.ref.infected = True
                        t.ref.infect_day = g.day
                    text = f"{f.label}咬住了{t.name}的手臂。-{dmg}"
                for o in self.active():
                    if o is not t and not o.is_player and o.trait != "冷酷":
                        o.ref.fear = min(100, o.ref.fear + 5)
            elif spec["grab"] and not t.grabbed and self.rng.randint(1, 100) <= spec["grab"]:
                t.grabbed = True
                res = "grab"
                text = f"{f.label}抓住了{t.name}。-{dmg} 要先掙脫。"
            else:
                text = f"{f.label}抓傷了{t.name}。-{dmg}"
                if t.is_player and self.rng.random() < 0.25:
                    p.bleeding = True
                    res = "bleed"
                    text += " 傷口在流血。"
        self.ev("foe_attack", lead + text, foe=f.uid, dst=t.uid, hit=True, dmg=dmg, result=res, via=how, shot=shot)
        if t.hp <= 0:
            self._ally_down(t)

    def _ally_down(self, t):
        if t.is_player:
            self.eng.check_death()
            return
        t.out = "dead"
        t.ref.status = "dead"
        self.ev("death", f"{t.name}倒下了，沒有再起來。", unit=t.uid)
        for o in self.active():
            if not o.is_player and o.trait != "冷酷":
                o.ref.trust -= 5
                o.ref.fear = min(100, o.ref.fear + 15)

    # ------------------------------------------------------------ 我方的回合
    def _ally_turn_start(self, a) -> bool:
        """輪到他。回傳 True 表示等玩家下指令；False 表示他自己做了別的事，這回合沒了。"""
        a.stamina = a.stamina + 5
        if a.taunt:
            a.taunt = False
            if self.taunter is a:
                self.taunter = None
        a.cover = None
        if a.is_player:
            return True
        chance, kind = self.break_chance(a)
        if not chance or self.rng.randint(1, 100) > chance:
            return True
        if kind == "flee":
            a.out = "hid"
            a.ref.stance = "hide"
            if self.choke == a.uid:
                self.choke = None
            self.ev("trait", f"{a.name}退到門外，躲了起來。「我不行，我真的不行……」", unit=a.uid, kind=kind)
        elif kind == "loot":
            self.corpses -= 1
            if self.drops:
                it = self.drops.pop(0)
                a.inv.append(it)
                self.ev("trait", f"{a.name}蹲下去翻屍體，把{it.name}塞進自己口袋。", unit=a.uid, kind=kind, item=it.name)
            else:
                self.ev("trait", f"{a.name}蹲下去翻屍體，什麼也沒翻到。", unit=a.uid, kind=kind)
        elif kind == "retreat":
            a.row = "back"
            a.in_cover = False
            if self.choke == a.uid:
                self.choke = None
            self.ev("trait", f"{a.name}往後退。「這樣打不贏，我不陪你送死。」", unit=a.uid, kind=kind)
        else:
            self.ev("trait", f"{a.name}沒有等你開口，自己動了。", unit=a.uid, kind=kind)
            self._auto(a)
        return False

    def break_chance(self, a):
        """性格發作：這回合他自己行動、不等指令的機率，和會做什麼。（機率, 種類）"""
        if a.is_player or a.bonded or a.trait == "忠誠":
            return 0, ""
        foes, allies = len(self.foes), len(self.active())
        if a.trait == "怯懦" and (a.hp < a.max_hp * 0.5 or foes >= 3 or a.fear >= 70):
            return min(90, 40 + max(0, a.fear - 50) // 2), "flee"
        if a.trait == "貪婪" and self.corpses > 0:
            return 35, "loot"
        if a.trait == "實際" and a.row == "front" and (foes > allies * 2 or a.hp < a.max_hp * 0.4):
            return 50, "retreat"
        if a.trust < 15:
            return 15, "own"
        return 0, ""

    def obey_chance(self, a, cmd) -> int:
        """他會不會照做。只有危險的指令才可能不做。"""
        if a.is_player or a.bonded or a.trait == "忠誠" or cmd not in RISKY:
            return 100
        if cmd == "cover" and a.trait == "冷酷":
            return 0
        c = 55 + a.trust * 0.5 - max(0, a.fear - 40) * 0.5 - 25
        if a.trait == "怯懦":
            c -= 20
        return int(max(5, min(100, c)))

    def _risk_name(self, cmd, args):
        if cmd == "row":
            return "front" if args.get("row") == "front" else "back"
        if cmd == "env":
            d = self.env.get(args.get("env", ""))
            return "choke" if d and d.get("kind") == "choke" else "env"
        return cmd

    def act(self, uid, cmd, args=None):
        """對輪到的人下指令。回傳事件列表。指令不成立時只有一則 t=no 的事件，不耗回合。"""
        args = args or {}
        a = self.waiting
        if self.over:
            self.ev("no", "戰鬥已經結束。")
            return self.drain()
        if not a or a.uid != uid:
            self.ev("no", "還沒輪到他。")
            return self.drain()
        fn = getattr(self, "_do_" + cmd, None)
        if not fn:
            self.ev("no", "沒有這個指令。")
            return self.drain()
        risk = self._risk_name(cmd, args)
        chance = self.obey_chance(a, risk)
        if chance < 100 and self.rng.randint(1, 100) > chance:
            line = REFUSE_LINES.get(a.trait, "我做不到。")
            self.ev("refuse", f"{a.name}：「{line}」", unit=a.uid, cmd=cmd, chance=chance)
            self._auto(a)
            done = True
        else:
            done = fn(a, args)
        if done:
            self._end_turn(a)
            self.run()
        return self.drain()

    def _no(self, text):
        self.ev("no", text)
        return False

    def hit_chance(self, a, f, mode="body", spent=0) -> int:
        """命中率。打不到回傳 0。spent 是這一擊要花的體力，預覽時先扣掉才準。"""
        w, _, _ = a.weapon()
        if f.band not in w["reach"]:
            return 0
        c = w["hit"] + w["reach"][f.band] + aim_bonus(a.aim)
        if a.is_player:
            p, xp = self.g.player, experience(self.g)
            c += xp["hit"] + (xp["head"] if mode == "head" else 0)
            if p.stamina - spent < 15:
                c -= 20
            if p.fatigue > 80:
                c -= 20
            if p.thirst > 70:
                c -= 15
            if p.sick:
                c -= 10
        else:
            c += (10 if a.skill == "戰鬥" else 0) + (10 if a.trait == "冷酷" else 0) + (15 if a.bonded else 0)
        if a.grabbed:
            c -= 20
        if self.taunter and self.taunter is not a:
            c += pin_bonus(self.g)
        if mode == "head":
            c -= 30 + (0 if a.aim else 20)
        elif mode == "legs":
            c -= 10
        return max(5, min(95, c))

    def swing_cost(self, a) -> int:
        w, _, ammo = a.weapon()
        cost = w["stam"]
        if a.is_player and not ammo:
            cost = max(1, cost - experience(self.g)["stam"])
        return cost

    def _auto(self, a):
        """他自己判斷：搆得到就打最近的，搆不到就瞄準或等。"""
        w, _, _ = a.weapon()
        reach = [f for f in self.foes if f.band in w["reach"]]
        if reach and not a.grabbed:
            self._do_attack(a, {"target": min(reach, key=lambda f: f.band).uid})
        elif a.grabbed:
            self._do_push(a, {})
        elif a.aim < AIM_MAX and a.stamina >= 3:
            self._do_aim(a, {})
        else:
            self._do_wait(a, {})

    def _target(self, a, args):
        w, _, _ = a.weapon()
        if args.get("target"):
            return self.foe(args["target"])
        reach = [f for f in self.foes if f.band in w["reach"]]
        return min(reach, key=lambda f: f.band) if reach else None

    def _do_attack(self, a, args):
        mode = args.get("mode", "body")
        if mode not in ("body", "head", "legs"):
            return self._no("沒有這種打法。")
        f = self._target(a, args)
        if not f:
            return self._no("沒有搆得到的目標。")
        w, it, ammo = a.weapon()
        if f.band not in w["reach"]:
            return self._no(f"{f.label}在「{BAND_NAME[f.band]}」，{w['name']}打不到那裡。")
        cost = self.swing_cost(a)
        if a.stamina < cost:
            a.stamina = a.stamina + 10
            self.ev("winded", f"{a.name}喘不過氣，只能先護住頭。", unit=a.uid)
            return True
        if ammo:
            inv_remove(a.inv, ammo, 1)
            self.noise(w["noise"])
        chance = self.hit_chance(a, f, mode, spent=cost)
        a.stamina = a.stamina - cost
        a.aim = 0
        where = {"head": "往頭部", "legs": "往腿"}.get(mode, "")
        if self.rng.randint(1, 100) > chance:
            self.ev("attack", f"{a.name}用{w['name']}{where}揮去，沒打中。（{chance}%）", unit=a.uid, foe=f.uid,
                    mode=mode, hit=False, chance=chance)
            if not ammo:
                self.noise(w["noise"] * 0.5)
            return True
        dmg = self.rng.randint(*w["dmg"])
        if not a.is_player and a.skill == "戰鬥":
            dmg += 3
        note = ""
        if mode == "head":
            if f.helmet:
                f.helmet = False
                dmg = 0
                note = "安全帽被打飛了。"
            else:
                dmg = 999
        elif mode == "legs":
            dmg = max(1, dmg // 2)
            f.slow += 1
            note = "牠的腿斷了，拖著走。"
        elif f.vest:
            dmg = (dmg + 1) // 2
            note = "防彈背心擋掉一半。"
        f.hp -= dmg
        if not ammo:
            self.noise(w["noise"] * 0.5)
        if it and ITEMS[it.name]["dur"] < 99:
            it.dur -= 1
            if it.dur <= 0:
                a.inv.remove(it)
                if a.is_player:
                    a.ref.weapon = None
                self.ev("break", f"{it.name}斷了。", unit=a.uid, item=it.name)
        shown = dmg if dmg < 999 else None
        self.ev("attack", f"{a.name}打中{f.label}{where}。" + (f"-{dmg} " if shown else "") + note, unit=a.uid,
                foe=f.uid, mode=mode, hit=True, dmg=shown, chance=chance)
        if f.hp <= 0:
            self._kill(f, a, melee=not ammo, head=(mode == "head"))
        if ammo == "霰彈" and f.band == 2:
            other = next((o for o in self.foes if o is not f and o.band == 2), None)
            if other:
                splash = max(1, dmg // 2 if dmg < 999 else self.rng.randint(*w["dmg"]) // 2)
                other.hp -= splash
                self.ev("attack", f"散開的彈丸也打到{other.label}。-{splash}", unit=a.uid, foe=other.uid, mode="splash",
                        hit=True, dmg=splash)
                if other.hp <= 0:
                    self._kill(other, a, melee=False)
        return True

    def _kill(self, f, by, melee=True, head=False):
        g = self.g
        if f in self.foes:
            self.foes.remove(f)
        if f.e in f.home:
            f.home.remove(f.e)
        if by and by.is_player:
            g.flags["xp_kills"] = g.flags.get("xp_kills", 0) + 1
        g.flags["kills"] = g.flags.get("kills", 0) + 1
        self.corpses += 1
        text = f"{f.label}的頭炸開了。牠不動了。" if head else f"{f.label}倒下了，不再動。"
        self.ev("kill", text, foe=f.uid, by=by.uid if by else None, head=head)
        if f.spec.get("cloud") and melee and by:
            if by.is_player:
                g.player.infection += 15
                self.ev("cloud", "牠的身體裂開，噴出一團黃綠色的霧。你吸進去了一些。", unit=by.uid)
            else:
                if not by.ref.infected and self.rng.random() < 0.5:
                    by.ref.infected = True
                    by.ref.infect_day = g.day
                self.ev("cloud", f"牠的身體裂開，噴出一團黃綠色的霧，罩住了{by.name}。", unit=by.uid)
        if f.human:
            drop = self.rng.choice(["霰彈", "手槍子彈", "罐頭", "汽油", "繃帶"])
            self.drops.append(new_item(drop, 3 if drop in ("霰彈", "手槍子彈") else 1, g.day))
            self.ev("drop", f"他身上掉出了{drop}。", item=drop)

    def _do_aim(self, a, args):
        if a.stamina < 3:
            a.stamina = a.stamina + 5
            self.ev("winded", f"{a.name}太喘了，只能先穩住。", unit=a.uid)
            return True
        if a.aim < AIM_MAX:
            a.stamina = a.stamina - 3
            a.aim += 1
        self.ev("aim", f"{a.name}穩住呼吸，盯著牠。（瞄準 {a.aim}/{AIM_MAX}）", unit=a.uid, level=a.aim)
        return True

    def _do_wait(self, a, args):
        a.stamina = a.stamina + 5
        self.ev("wait", f"{a.name}喘了口氣。", unit=a.uid)
        return True

    def _do_push(self, a, args):
        if a.grabbed:
            chance = 55 + (20 if a.stamina > 50 else 0)
            a.stamina = a.stamina - 10
            ok = self.rng.randint(1, 100) <= chance
            if ok:
                a.grabbed = False
            self.ev("push", f"{a.name}掙脫了。" if ok else f"牠抓得很緊，{a.name}掙不開。", unit=a.uid, escape=True, ok=ok)
            return True
        f = self.foe(args["target"]) if args.get("target") else next((x for x in self.foes if x.band == 1), None)
        if not f or f.band != 1:
            return self._no("沒有東西靠得夠近可以推。")
        if a.stamina < 10:
            return self._no(f"{a.name}沒力氣推了。")
        a.stamina = a.stamina - 10
        ok = self.rng.randint(1, 100) <= PUSH_CHANCE
        if ok:
            f.band = 2
            f.stagger = 1
        self.ev("push", f"{a.name}把{f.label}推開，牠踉蹌了一下。" if ok else f"{a.name}推了一下，{f.label}紋絲不動。",
                unit=a.uid, foe=f.uid, ok=ok)
        return True

    def _do_taunt(self, a, args):
        if a.row != "front":
            return self._no("要站在前排才能牽制。")
        if len(self.active()) < 2:
            return self._no("沒有別人能趁機出手，牽制只是白白挨打。")
        if a.stamina < 4:
            return self._no(f"{a.name}太喘了，吼不出聲。")
        a.stamina = a.stamina - 4
        a.taunt = True
        self.taunter = a
        if a.is_player:
            self.g.flags["pin_uses"] = self.g.flags.get("pin_uses", 0) + 1
        self.noise(1.0)
        self.ev("taunt", f"{a.name}大吼一聲，拿武器敲牆。牠們全轉了過來。（其他人命中 +{pin_bonus(self.g)}）", unit=a.uid,
                bonus=pin_bonus(self.g))
        return True

    def _do_cover(self, a, args):
        t = self.ally(args.get("target", ""))
        if not t or t is a or t.out:
            return self._no("要指定替誰擋。")
        if a.grabbed:
            return self._no(f"{a.name}被抓住了，動不了。")
        a.cover = t.uid
        self.ev("cover", f"{a.name}站到{t.name}前面。", unit=a.uid, dst=t.uid)
        return True

    def _do_row(self, a, args):
        row = args.get("row")
        if row not in ("front", "back") or row == a.row:
            return self._no("他已經在那一排了。")
        if a.grabbed:
            return self._no(f"{a.name}被抓住了，動不了。")
        a.row = row
        a.in_cover = False
        if self.choke == a.uid:
            self.choke = None
        self.ev("row", f"{a.name}{'上前' if row == 'front' else '退到後面'}。", unit=a.uid, row=row)
        return True

    def _do_throw(self, a, args):
        name = args.get("item", "")
        if inv_count(a.inv, name) <= 0:
            return self._no("他身上沒有那個東西。")
        spec = ITEMS[name]
        if spec["kind"] == "throw" and spec.get("fire"):
            near = any(f.band == 1 for f in self.foes)
            inv_remove(a.inv, name, 1)
            self.noise(spec["noise"])
            self.ev("throw", "玻璃碎了，火燒了起來。", unit=a.uid, item=name, fire=True)
            for f in [x for x in self.foes if x.band >= 2]:
                f.hp -= self.rng.randint(*spec["fire"])
                if f.hp <= 0:
                    self._kill(f, a, melee=False)
            if near:
                a.hp -= 8
                self.ev("burn", f"太近了，火燎到{a.name}。-8", unit=a.uid, dmg=8)
                if a.hp <= 0:
                    self._ally_down(a)
            return True
        cands = [f for f in self.foes if f.distract == 0 and not f.human and f.band in THROW_BANDS]
        f = self.foe(args["target"]) if args.get("target") else (self.rng.choice(cands) if cands else None)
        inv_remove(a.inv, name, 1)
        self.noise(0.5)
        if f and f in cands:
            f.distract = 2
            self.ev("throw", f"{name}砸在角落。{f.label}轉頭朝聲音走去。", unit=a.uid, item=name, foe=f.uid)
        else:
            self.ev("throw", f"{a.name}把{name}丟出去，但沒有東西理它。", unit=a.uid, item=name)
        return True

    def _do_use(self, a, args):
        name = args.get("item", "")
        if inv_count(a.inv, name) <= 0:
            return self._no("他身上沒有那個東西。")
        eff = ITEMS[name].get("effect")
        t = self.ally(args.get("target", "")) or a
        if t.out:
            return self._no("他不在場。")
        if eff == "bandage":
            t.hp = min(t.max_hp, t.hp + 10)
            if t.is_player:
                t.ref.bleeding = False
            else:
                t.ref.bandaged = True
            text = f"{a.name}替{'自己' if t is a else t.name}綁緊繃帶。"
        elif eff == "firstaid":
            t.hp = min(t.max_hp, t.hp + 40)
            if t.is_player:
                t.ref.bleeding = False
            text = f"{a.name}打開急救包，處理{'自己' if t is a else t.name}的傷口。"
        elif eff == "painkiller" and t.is_player:
            t.ref.painkiller = 6
            t.hp = min(100, t.hp + 5)
            text = "你吞了止痛藥。接下來幾小時比較耐打。"
        else:
            return self._no("這個東西現在用不了。")
        inv_remove(a.inv, name, 1)
        self.ev("use", text, unit=a.uid, item=name, dst=t.uid)
        return True

    def flee_chance(self) -> int:
        p = self.g.player
        c = 75 - 12 * len([f for f in self.foes if f.band == 1])
        if p.fatigue > 80:
            c -= 20
        if p.thirst > 70:
            c -= 10
        if p.stamina < 15:
            c -= 15
        return max(10, c)

    def _do_flee(self, a, args):
        if any(x.grabbed for x in self.active()):
            return self._no("有人被抓住了，要先掙脫。")
        chance = self.flee_chance()
        a.stamina = a.stamina - 15
        if self.rng.randint(1, 100) > chance:
            self.ev("flee", f"你們被擋住了，沒能跑掉。（{chance}%）", unit=a.uid, ok=False, chance=chance)
            return True
        for f in self.foes:
            if f.kind == "疾走者" and self.rng.random() < 0.5:
                self.chasers.append({"foe": f.uid, "band": 2})
            elif f.kind == "行屍" and f.band == 1 and self.rng.random() < 0.3:
                self.chasers.append({"foe": f.uid, "band": 3})
        self.ev("flee", f"你們衝了出去。（{chance}%）", unit=a.uid, ok=True, chance=chance, exit=args.get("exit"))
        self._finish("fled")
        return True

    def _do_env(self, a, args):
        d = self.env.get(args.get("env", ""))
        if not d:
            return self._no("這裡沒有那樣東西。")
        kind, verb = d.get("kind"), args.get("verb", "")
        name = d.get("name", "那個")
        if a.grabbed:
            return self._no(f"{a.name}被抓住了，動不了。")
        if kind == "door":
            if d.get("broken"):
                return self._no("門已經被撞壞了。")
            if verb == "close" and not d.get("closed"):
                d["closed"] = True
                d["hold"] = d.get("hold", DOOR_HOLD)
                self.noise(0.5)
                self.ev("env", f"{a.name}把{name}關上。", unit=a.uid, env=d["id"], verb=verb, hold=d["hold"])
                return True
            if verb == "brace" and d.get("closed"):
                d["hold"] = min(DOOR_HOLD_MAX, d.get("hold", DOOR_HOLD) + 2)
                self.ev("env", f"{a.name}用肩膀頂住{name}。（撐得住 {d['hold']} 下）", unit=a.uid, env=d["id"], verb=verb,
                        hold=d["hold"])
                return True
            if verb == "open" and d.get("closed"):
                d["closed"] = False
                self.ev("env", f"{a.name}把{name}打開。", unit=a.uid, env=d["id"], verb=verb)
                return True
            return self._no("門現在不能這樣做。")
        if kind in ("topple", "noise", "fire") and d.get("used"):
            return self._no("那個已經用過了。")
        if kind == "topple":
            if a.stamina < 12:
                return self._no(f"{a.name}沒力氣推倒它。")
            a.stamina = a.stamina - 12
            d["used"] = True
            self.noise(3.0)
            hit = [f for f in self.foes if f.band == 2]
            self.ev("env", f"{a.name}把{name}推倒。", unit=a.uid, env=d["id"], verb="topple")
            if hit:
                for f in hit:
                    dmg = self.rng.randint(8, 16)
                    f.hp -= dmg
                    f.stagger = max(f.stagger, 1)
                    self.ev("attack", f"{name}砸在{f.label}身上。-{dmg}", unit=a.uid, foe=f.uid, mode="env", hit=True,
                            dmg=dmg)
                    if f.hp <= 0:
                        self._kill(f, a, melee=False)
            else:
                for f in self.foes:
                    if f.band >= 3:
                        f.stagger = max(f.stagger, 1)
                self.ev("env", "路被擋住了，牠們要繞過來。", env=d["id"], verb="block")
            return True
        if kind == "cover":
            a.in_cover = True
            self.ev("env", f"{a.name}躲到{name}後面。", unit=a.uid, env=d["id"], verb="cover")
            return True
        if kind == "choke":
            if a.row != "front":
                return self._no("要站在前排才能守住門口。")
            self.choke = a.uid
            self.ev("env", f"{a.name}守住{name}。一次只有一隻擠得過來。", unit=a.uid, env=d["id"], verb="choke")
            return True
        if kind == "noise":
            d["used"] = True
            self.noise(3.0)
            lured = [f for f in self.foes if f.band >= 2 and not f.human and f.distract == 0]
            for f in lured:
                f.distract = 2
            self.ev("env", f"{a.name}弄響了{name}。" + ("牠們朝聲音轉過去。" if lured else ""), unit=a.uid, env=d["id"],
                    verb="noise", foes=[f.uid for f in lured])
            return True
        if kind == "fire":
            if not d.get("lit") and not any(inv_count(x.inv, "打火機") for x in self.active()):
                return self._no("沒有東西可以點火。")
            d["used"] = True
            near = any(f.band == 1 for f in self.foes)
            self.noise(3.0)
            self.ev("env", f"{a.name}點著了{name}。火一下子竄起來。", unit=a.uid, env=d["id"], verb="fire")
            for f in [x for x in self.foes if x.band in (2, 3)]:
                f.hp -= self.rng.randint(30, 50)
                if f.hp <= 0:
                    self._kill(f, a, melee=False)
            if near:
                a.hp -= 8
                self.ev("burn", f"太近了，火燎到{a.name}。-8", unit=a.uid, dmg=8)
                if a.hp <= 0:
                    self._ally_down(a)
            return True
        if kind == "light":
            self.dark = not self.dark
            self.ev("env", f"{a.name}把燈{'關掉' if self.dark else '打開'}。", unit=a.uid, env=d["id"], verb="light",
                    dark=self.dark)
            return True
        return self._no("那個東西現在派不上用場。")

    # ------------------------------------------------------------ 給畫面看的
    def options(self, a):
        """輪到的人現在能下哪些指令，連同命中率、體力、聲音、他聽不聽。"""
        w, _, ammo = a.weapon()
        cost = self.swing_cost(a)
        gun_noise = w["noise"] if ammo else w["noise"] * 0.5
        targets = [f for f in self.foes if f.band in w["reach"]]
        out = []

        def add(cmd, label, ok=True, why="", **kw):
            risk = self._risk_name(cmd, kw.get("args", {}))
            ch = self.obey_chance(a, risk)
            d = {"cmd": cmd, "label": label, "ok": bool(ok), "obey": ch, "obey_label": obey_label(ch)}
            if why and not ok:
                d["why"] = why
            d.update(kw)
            out.append(d)

        for mode, label in (("body", "攻擊"), ("head", "打頭"), ("legs", "打腿")):
            add("attack", label, ok=bool(targets) and a.stamina >= cost, why="搆不到" if not targets else "體力不夠",
                args={"mode": mode}, stamina=cost, noise=gun_noise,
                targets=[{"foe": f.uid, "chance": self.hit_chance(a, f, mode, spent=cost)} for f in targets])
        add("aim", "瞄準", ok=a.aim < AIM_MAX and a.stamina >= 3, why="已經最穩" if a.aim >= AIM_MAX else "體力不夠",
            stamina=3, noise=0, level=a.aim)
        if a.grabbed:
            add("push", "掙脫", stamina=10, noise=0, chance=55 + (20 if a.stamina > 50 else 0))
        else:
            adj = [f.uid for f in self.foes if f.band == 1]
            add("push", "推開", ok=bool(adj) and a.stamina >= 10, why="沒有貼身的" if not adj else "體力不夠", stamina=10,
                noise=0, chance=PUSH_CHANCE, targets=[{"foe": u} for u in adj])
        add("taunt", "牽制", ok=a.row == "front" and len(self.active()) > 1 and a.stamina >= 4, why="現在不行",
            stamina=4, noise=1.0)
        others = [x.uid for x in self.active() if x is not a]
        add("cover", "掩護", ok=bool(others) and not a.grabbed, why="沒有人可以掩護", allies=others, noise=0)
        to = "back" if a.row == "front" else "front"
        add("row", "後退" if to == "back" else "上前", ok=not a.grabbed, why="被抓住了", args={"row": to}, noise=0)
        throwable = [it.name for it in a.inv if ITEMS[it.name]["kind"] == "throw" or it.name == "空瓶"]
        add("throw", "丟東西", ok=bool(throwable), why="沒有東西可以丟", items=throwable, noise=0.5)
        meds = [it.name for it in a.inv if ITEMS[it.name].get("effect") in ("bandage", "firstaid", "painkiller")]
        add("use", "用物品", ok=bool(meds), why="沒有能用的", items=meds, noise=0)
        for d in self.env.values():
            verbs = self._env_verbs(a, d)
            for verb, label in verbs:
                add("env", label, args={"env": d["id"], "verb": verb}, noise=3.0 if d["kind"] in ("topple", "noise", "fire") else
                    0.5 if verb == "close" else 0)
        add("flee", "逃跑", ok=not any(x.grabbed for x in self.active()), why="有人被抓住了", stamina=15,
            chance=self.flee_chance(), noise=0)
        add("wait", "喘口氣", noise=0)
        return out

    def _env_verbs(self, a, d):
        kind, name = d.get("kind"), d.get("name", "")
        if kind == "door":
            if d.get("broken"):
                return []
            return [("brace", f"頂住{name}"), ("open", f"打開{name}")] if d.get("closed") else [("close", f"關上{name}")]
        if kind in ("topple", "noise", "fire") and d.get("used"):
            return []
        return {"topple": [("topple", f"推倒{name}")], "cover": [("cover", f"躲到{name}後面")],
                "choke": [("choke", f"守住{name}")], "noise": [("noise", f"弄響{name}")],
                "fire": [("fire", f"點燃{name}")], "light": [("light", "開關燈")]}.get(kind, [])

    def view(self):
        g = self.g
        allies = []
        for a in self.allies:
            w, _, ammo = a.weapon()
            chance, kind = self.break_chance(a) if not a.out else (0, "")
            allies.append({
                "uid": a.uid, "name": a.name, "hp": a.hp, "max_hp": a.max_hp, "stamina": a.stamina, "row": a.row,
                "aim": a.aim, "grabbed": a.grabbed, "out": a.out, "weapon": w["name"],
                "ammo": inv_count(a.inv, ammo) if ammo else None, "cover": a.cover, "taunt": a.taunt,
                "in_cover": a.in_cover, "break_chance": chance, "break_kind": kind,
            })
        foes = []
        for f in self.foes:
            steps, period = f.pace()
            foes.append({
                "uid": f.uid, "kind": f.kind, "label": f.label, "hp": f.hp, "band": f.band,
                "band_name": BAND_NAME[f.band], "steps": steps, "period": period, "eta": self.eta(f), "slow": f.slow,
                "stagger": f.stagger, "distract": f.distract, "via": f.via,
                "blocked": bool(self._blocking_door(f)), "vest": f.vest, "helmet": f.helmet, "human": f.human,
            })
        cur = self.waiting
        return {
            "round": self.round, "over": self.over, "current": cur.uid if cur else None,
            "order": [u.uid for u in self.queue], "allies": allies, "foes": foes,
            "env": list(self.env.values()), "dark": self.dark, "choke": self.choke,
            "taunter": self.taunter.uid if self.taunter else None,
            "threat": round(g.threat.get(g.cur.loc, 0), 2),
            "options": self.options(cur) if cur else [],
        }
