# -*- coding: utf-8 -*-
"""畫面端和規則之間唯一的窗口：送一個指令進來，拿回事件和新的狀態。

格式寫在 docs/RULES_BRIDGE.md。畫面端不直接讀規則內部，所以可以用假資料獨立開發，
將來要換掉 Python 也只要重做這一層。
"""
import json
import os

from ..combat import ensure_uids
from ..commands import handle as text_handle
from ..data import ITEMS
from ..engine import Engine
from ..save import META, SAVE
from ..state import from_dict, inv_add, inv_find, to_dict
from ..world import build_world
from . import containers
from .battle import Battle
from .rules import (ACTION_NOISE, RUN_STAMINA_PER_UNIT, UNITS_PER_MINUTE, band_from_distance, noise_radius,
                    walk_noise)

# 敵人的外觀（畫面用哪一張圖）會帶來的規則差異。設計文件第五節「敵人種類」，提案。
SPRITE_TAGS = (("police", "vest"), ("dock", "helmet"))


class RuleError(Exception):
    """指令不成立（房間不存在、東西不在那裡）。回給畫面端當錯誤訊息，不改變狀態。"""


class Session:
    def __init__(self, seed=1, difficulty="normal", goal=None, game=None):
        self.g = game or build_world(int(seed), goal=goal, difficulty=difficulty)
        self.eng = Engine(self.g)
        self.battle = None
        self.events = []
        self._seen = set()       # 開戰時畫面已經知道的敵人

    # ------------------------------------------------------------ 進出口
    def handle(self, msg: dict) -> dict:
        fn = getattr(self, "cmd_" + str(msg.get("cmd", "")), None)
        if not fn:
            return {"ok": False, "error": "沒有這個指令：%s" % msg.get("cmd"), "events": []}
        self.eng.new_turn()
        self.events = []
        try:
            extra = fn(msg) or {}
        except RuleError as e:
            return {"ok": False, "error": str(e), "events": [], "state": self.state()}
        self._after()
        out = {"ok": True, "events": self.events, "state": self.state()}
        out.update(extra)
        if self.battle:
            out["battle"] = self.battle.view()
            if self.battle.over:
                self.battle = None
        return out

    def ev(self, t, text="", **kw):
        d = {"t": t}
        if text:
            d["text"] = text
        d.update(kw)
        self.events.append(d)

    def _after(self):
        """規則引擎自己說的話（整點事件、死亡）變成事件；文字版式的「直接開打」改成通知畫面有東西來了。"""
        g = self.g
        for line in self.eng.out:
            self.ev("say", line)
        self.eng.out = []
        if self.battle and not self.battle.over:
            # 打到一半規則引擎又加了敵人（整點的遊走、湧入）：只通知畫面，牠們什麼時候走進戰鬥圈由畫面決定。
            # 開戰時就在房間裡、但沒被拉進戰鬥的那些不算，牠們還沒發現玩家。
            new = [e for e in g.cur.enemies if id(e) not in self._seen]
            if new:
                ensure_uids(g)
                self._seen.update(id(e) for e in new)
                self.ev("intrusion", foes=[self._enemy_view(e) for e in new])
        elif g.combat and not self.battle:
            g.combat = False
            ensure_uids(g)
            self.ev("intrusion", foes=[self._enemy_view(e) for e in g.cur.enemies])

    def tick(self, minutes: float):
        """推進時鐘。規則引擎以十分鐘為一步，零頭先記著。"""
        g = self.g
        pend = g.flags.get("hd_pending", 0.0) + minutes
        while pend >= 10 and not g.over:
            pend -= 10
            self.eng.advance(10)
        g.flags["hd_pending"] = round(pend, 3)

    # ------------------------------------------------------------ 給畫面看的狀態
    def _item_view(self, it):
        return {"name": it.name, "qty": it.qty, "kind": ITEMS[it.name]["kind"], "label": it.label(), "dur": it.dur}

    def _enemy_view(self, e):
        return {"uid": e.uid, "kind": e.kind, "label": e.label(), "hp": e.hp}

    def state(self) -> dict:
        g, p = self.g, self.g.player
        minute = g.minute + int(g.flags.get("hd_pending", 0))
        return {
            "day": g.day, "minute": minute, "clock": "%02d:%02d" % (minute // 60 % 24, minute % 60),
            "phase": g.phase(), "night": g.is_night(), "room": g.room, "loc": g.cur.loc, "over": g.over,
            "goal": g.goal, "threat": round(g.threat.get(g.cur.loc, 0), 2), "in_battle": bool(self.battle),
            "player": {
                "hp": p.hp, "hunger": round(p.hunger), "thirst": round(p.thirst), "fatigue": round(p.fatigue),
                "infection": round(p.infection), "stamina": p.stamina, "max_stamina": p.max_stamina(),
                "bleeding": p.bleeding, "sick": p.sick, "painkiller": p.painkiller, "weapon": p.weapon,
                "slots": p.slots, "inv": [self._item_view(it) for it in p.inv],
            },
            "companions": [
                {"name": n.name, "hp": n.hp, "max_hp": n.max_hp, "trust": n.trust, "fear": n.fear, "trait": n.trait,
                 "skill": n.skill, "stance": n.stance, "bonded": bool(n.bonded), "sick_known": bool(n.revealed)}
                for n in g.companions()
            ],
            "base": {"room": g.base.room, "fort": g.base.fort},
        }

    def room_view(self, room=None) -> dict:
        g = self.g
        r = room or g.cur
        cons = containers.ensure(g, r)
        hint = any(n.skill == "搜索" for n in g.companions())
        if r is g.cur:
            ensure_uids(g)
        return {
            "id": r.id, "loc": r.loc, "name": r.name, "tags": list(r.tags), "locked": r.locked,
            "base_ok": r.base_ok, "exits": dict(r.exits),
            "items": [self._item_view(it) for it in r.items],
            "containers": [containers.view(c, hint) for c in cons],
            "enemies": [self._enemy_view(e) for e in r.enemies],
            "people": [{"name": n.name, "met": n.intro_seen} for n in g.npcs_here()] if r is g.cur else [],
        }

    # ------------------------------------------------------------ 探索
    def cmd_state(self, msg):
        return {"room": self.room_view()}

    def cmd_enter(self, msg):
        """玩家走進一個房間。畫面端自己管位置，這裡只記「現在在哪一間」。"""
        g = self.g
        rid = msg.get("room", "")
        if rid not in g.rooms:
            raise RuleError("沒有這個房間：%s" % rid)
        r = g.rooms[rid]
        if r.locked:
            raise RuleError("門是鎖的。")
        if self.battle:
            raise RuleError("戰鬥中不能換房間，要用逃跑。")
        g.room = rid
        r.visited = True
        return {"room": self.room_view()}

    def cmd_walk(self, msg):
        """回報走了多遠。時間照距離走；跑步扣體力、聲音大。回傳這段路的腳步聲半徑。"""
        g, p = self.g, self.g.player
        dist = max(0.0, float(msg.get("dist", 0)))
        run = bool(msg.get("run"))
        if run:
            cost = dist * RUN_STAMINA_PER_UNIT + g.flags.get("hd_run", 0.0)
            p.stamina = max(0, p.stamina - int(cost))
            g.flags["hd_run"] = round(cost - int(cost), 3)
        self.tick(dist / UNITS_PER_MINUTE)
        amount = walk_noise(ACTION_NOISE["run" if run else "walk"], len(g.companions()), p.fatigue)
        return {"noise": amount, "radius": noise_radius(amount), "can_run": p.stamina > 0}

    def cmd_noise(self, msg):
        """探索時弄出聲音（開門、打破玻璃）。加進地區威脅值，回傳半徑讓畫面找誰聽得到。"""
        amount = float(msg["amount"]) if "amount" in msg else ACTION_NOISE.get(msg.get("action", ""), 0.0)
        if amount >= 0.5:
            self.eng.noise(amount)
        return {"noise": amount, "radius": noise_radius(amount)}

    def cmd_search(self, msg):
        g = self.g
        if self.battle:
            raise RuleError("現在？")
        r = g.cur
        con = containers.find(g, r, msg.get("container", ""))
        if not con:
            raise RuleError("這裡沒有那樣東西。")
        if con["opened"]:
            return {"container": containers.view(con)}
        dark = ("dark" in r.tags or g.is_night()) and not inv_find(g.player.inv, "手電筒")
        minutes = con["minutes"] * (1.5 if dark else 1.0)
        if con["noise"] >= 0.5:
            self.eng.noise(con["noise"])
        extra = {"noise": con["noise"], "radius": noise_radius(con["noise"]), "minutes": minutes}
        if con["ambush"] and r.hidden:
            con["ambush"] = False
            e = r.hidden.pop(0)
            e.dist = 1
            r.enemies.append(e)
            ensure_uids(g)
            self.ev("ambush", f"一隻{e.kind}從{con['name']}撲出來！", container=con["id"], foe=self._enemy_view(e))
            return extra
        self.tick(minutes)
        con["opened"] = True
        names = "、".join(f"{x['name']}x{x['qty']}" for x in con["items"])
        self.ev("search", f"你翻了{con['name']}。" + (f"找到：{names}" if names else "什麼都沒有。"), container=con["id"],
                items=[{"name": x["name"], "qty": x["qty"]} for x in con["items"]])
        extra["container"] = containers.view(con)
        return extra

    def cmd_take(self, msg):
        """從翻過的容器或地上拿東西。container 不給就是拿地上的。"""
        g, p = self.g, self.g.player
        r = g.cur
        name, qty = msg.get("item", ""), int(msg.get("qty", 0))
        if msg.get("container"):
            con = containers.find(g, r, msg["container"])
            if not con or not con["opened"]:
                raise RuleError("要先翻過才拿得到。")
            it = containers.take(con, name, qty)
            if not it:
                raise RuleError("裡面沒有那個。")
            if not inv_add(p.inv, it, p.slots):
                containers.put_back(con, it)
                raise RuleError("背包滿了。")
        else:
            it = next((x for x in r.items if x.name == name), None)
            if not it:
                raise RuleError("地上沒有那個。")
            if not inv_add(p.inv, it, p.slots):
                raise RuleError("背包滿了。")
            r.items.remove(it)
        self.ev("take", f"你拿了{it.label()}。", item=it.name, qty=it.qty)
        return {"room": self.room_view()}

    def cmd_text(self, msg):
        """還沒改成 HD-2D 專用指令的規則（吃東西、加固、睡覺、交談、製作……），先借用文字版的指令。"""
        if self.battle:
            raise RuleError("戰鬥中不能做這個。")
        text_handle(self.eng, str(msg.get("line", "")))
        self.eng.check_death()
        return {"room": self.room_view()}

    # ------------------------------------------------------------ 戰鬥
    def _foe_entry(self, d):
        g = self.g
        room = g.rooms.get(d.get("room", g.room))
        if not room:
            raise RuleError("沒有這個房間。")
        if room is g.cur:
            ensure_uids(g)
        e = next((x for x in room.enemies if x.uid == d.get("uid")), None)
        if not e:
            raise RuleError("那裡沒有這隻敵人：%s" % d.get("uid"))
        info = {"via": d.get("via")}
        if "band" in d:
            info["band"] = int(d["band"])
        elif "dist" in d:
            info["band"] = band_from_distance(float(d["dist"]))
        tags = list(d.get("tags", []))
        sprite = str(d.get("sprite", ""))
        tags += [tag for key, tag in SPRITE_TAGS if key in sprite]
        info["tags"] = tags
        return e, room.enemies, info

    def cmd_battle_start(self, msg):
        """開戰。foes 是畫面端判定「發現了玩家、在戰鬥圈內」的敵人，距離用開戰那一刻的實際距離。"""
        if self.battle:
            raise RuleError("已經在戰鬥中。")
        foes = [self._foe_entry(d) for d in msg.get("foes", [])]
        if not foes:
            raise RuleError("沒有敵人。")
        self._seen = {id(e) for e in self.g.cur.enemies}
        self.battle = Battle(self.eng, foes, opener=msg.get("opener", "neutral"), env=msg.get("env"), tick=self.tick)
        self.events.extend(self.battle.drain())

    def cmd_battle_join(self, msg):
        """戰鬥圈外的敵人聽到聲音走進來。"""
        if not self.battle:
            raise RuleError("現在沒有戰鬥。")
        e, home, info = self._foe_entry(msg)
        if any(f.e is e for f in self.battle.foes):
            raise RuleError("牠已經在戰鬥裡了。")
        self.battle.join(e, home, info)
        self.events.extend(self.battle.drain())

    def cmd_battle_act(self, msg):
        if not self.battle:
            raise RuleError("現在沒有戰鬥。")
        self.events.extend(self.battle.act(msg.get("unit", ""), msg.get("act", ""), msg.get("args") or {}))

    def cmd_battle_view(self, msg):
        if not self.battle:
            raise RuleError("現在沒有戰鬥。")

    # ------------------------------------------------------------ 存檔
    def _path(self, msg):
        path = os.path.abspath(str(msg.get("path", "")))
        if not msg.get("path"):
            raise RuleError("要給存檔的路徑。")
        if os.path.normcase(path) in (os.path.normcase(SAVE), os.path.normcase(META)):
            raise RuleError("那是文字版的存檔，不能用。")
        return path

    def cmd_save(self, msg):
        if self.battle:
            raise RuleError("戰鬥中不能存檔。")
        path = self._path(msg)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(to_dict(self.g), f, ensure_ascii=False)
        os.replace(tmp, path)
        self.ev("saved", path=path)

    def cmd_load(self, msg):
        path = self._path(msg)
        if not os.path.exists(path):
            raise RuleError("沒有這個存檔。")
        with open(path, encoding="utf-8") as f:
            self.g = from_dict(json.load(f))
        self.eng = Engine(self.g)
        self.battle = None
        self.g.combat = False
        return {"room": self.room_view()}
