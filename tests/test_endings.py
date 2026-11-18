# -*- coding: utf-8 -*-
"""結局可達性與 14 天時程測試（純腳本，不需 pytest）。
用法：python -X utf8 tests/test_endings.py
失敗時以 exit code 1 結束。每個情境獨立執行並收集失敗，不會因為一個失敗就中斷其他情境。
"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from zg.world import build_world          # noqa: E402
from zg.engine import Engine              # noqa: E402
from zg.commands import handle            # noqa: E402
from zg.state import new_item, inv_count  # noqa: E402
from zg.data import DAY_EVENTS            # noqa: E402
from zg.save import record_run            # noqa: E402

ROOF = "辦公大樓·屋頂"
CHECKPOINT = "軍方檢查站·路障"
CHURCH = "教堂·前庭"
START = "住宅區·客廳"

FAILURES = []
PASSES = []


def run(eng, cmd):
    """執行一個指令並回傳輸出文字。"""
    eng.new_turn()
    handle(eng, cmd)
    eng.check_death()
    return "\n".join(eng.out)


def fresh(seed=1, goal=None):
    g = build_world(seed, goal=goal)
    eng = Engine(g)
    return g, eng


def teleport(g, room_id, clear=True):
    """把玩家直接放到某房間（測試用狀態操作）。"""
    assert room_id in g.rooms, f"房間不存在：{room_id}"
    g.room = room_id
    if clear:
        g.cur.enemies.clear()
        g.cur.hidden.clear()
    g.cur.visited = True
    g.combat = False


def set_time(g, day, hh, mm=0):
    g.day = day
    g.minute = hh * 60 + mm


def give(g, name, qty=1, day=1):
    g.player.inv.append(new_item(name, qty, day))


def clear_enemies(g):
    g.cur.enemies.clear()
    g.cur.hidden.clear()
    g.combat = False
    g.player.grabbed = False


def scenario(name):
    def deco(fn):
        def wrapper():
            try:
                fn()
            except Exception as ex:  # AssertionError 或程式例外都算失敗
                FAILURES.append((name, f"{type(ex).__name__}: {ex}", traceback.format_exc()))
                print(f"[FAIL] {name}: {type(ex).__name__}: {ex}")
            else:
                PASSES.append(name)
                print(f"[ok]   {name}")
        wrapper.__name__ = fn.__name__
        return wrapper
    return deco


# ===================================================================== 1. 撤離
def holdout(g, eng, max_waits=8):
    """signal 之後反覆 wait 1；遇到戰鬥就用蠻力清場。回傳 (波數, 戰鬥中 wait 是否被拒絕)。"""
    waves = 0
    wait_refused_in_combat = False
    for _ in range(max_waits):
        run(eng, "wait 1")
        if g.over:
            break
        if g.combat:
            assert g.cur.enemies, "combat 旗標為真但房間沒有敵人"
            waves += 1
            out = run(eng, "wait 1")
            if "現在等只會被咬" in out or "現在不是時候" in out:
                wait_refused_in_combat = True
            clear_enemies(g)
    return waves, wait_refused_in_combat


@scenario("1a evac：第 14 天 06:00 屋頂 signal + 撐 3 小時 -> evac")
def t_evac():
    g, eng = fresh(1)
    set_time(g, 14, 6, 0)
    teleport(g, ROOF)
    give(g, "訊號彈")
    give(g, "收音機")
    start_minute = g.minute
    out = run(eng, "signal")
    assert g.flags.get("signal_at") == 14 * 1440 + 6 * 60, f"signal_at 沒記錄：{g.flags} / {out}"
    assert inv_count(g.player.inv, "訊號彈") == 0, "訊號彈沒被消耗"
    assert not g.over
    waves, refused = holdout(g, eng)
    assert g.over == "evac", f"結局應為 evac，實際 {g.over!r}（day {g.day} {g.clock()}）"
    assert waves >= 1, "整點應該至少湧入一波敵人並設定 combat"
    assert refused, "戰鬥中 wait 應被拒絕（必須先清場才能繼續等）"
    assert g.day == 14 and g.minute - start_minute >= 180, f"應至少撐滿 180 分鐘，實際 {g.clock()}"
    assert g.minute - start_minute <= 240, f"撐太久：{g.clock()}"


@scenario("1b evac_vaccine：帶著疫苗樣本撤離 -> evac_vaccine")
def t_evac_vaccine():
    g, eng = fresh(2)
    set_time(g, 14, 7, 30)
    teleport(g, ROOF)
    give(g, "訊號彈")
    give(g, "收音機")
    give(g, "疫苗樣本")
    run(eng, "signal")
    assert g.flags.get("signal_at")
    holdout(g, eng)
    assert g.over == "evac_vaccine", f"結局應為 evac_vaccine，實際 {g.over!r}"


@scenario("1c signal 前置條件：不在屋頂 / 不是第 14 天 / 時段不對 / 缺道具 都要失敗")
def t_signal_preconditions():
    g, eng = fresh(3)
    give(g, "訊號彈")
    give(g, "收音機")
    # 不在屋頂
    set_time(g, 14, 8)
    run(eng, "signal")
    assert not g.flags.get("signal_at")
    # 不是第 14 天
    teleport(g, ROOF)
    set_time(g, 13, 8)
    run(eng, "signal")
    assert not g.flags.get("signal_at")
    # 時段不對（12:00 以後）
    set_time(g, 14, 12)
    run(eng, "signal")
    assert not g.flags.get("signal_at")
    # 缺收音機
    set_time(g, 14, 8)
    g.player.inv = [it for it in g.player.inv if it.name != "收音機"]
    run(eng, "signal")
    assert not g.flags.get("signal_at")
    assert inv_count(g.player.inv, "訊號彈") == 1, "失敗的 signal 不該消耗訊號彈"
    # 補齊之後成功
    give(g, "收音機")
    run(eng, "signal")
    assert g.flags.get("signal_at")


@scenario("1d 死守期間：12:00 不會誤判 survived（11:30 發訊號，撐到 14:30）")
def t_signal_past_noon():
    g, eng = fresh(4)
    set_time(g, 14, 11, 30)
    teleport(g, ROOF)
    give(g, "訊號彈")
    give(g, "收音機")
    run(eng, "signal")
    assert g.flags.get("signal_at")
    holdout(g, eng)
    assert g.over == "evac", f"11:30 發訊號後應能在 14:30 撤離，實際 {g.over!r} at {g.clock()}"


@scenario("1e 死守必須待在屋頂：發訊號後離開屋頂不該還能撤離（設計漏洞檢查）")
def t_signal_offroof():
    g, eng = fresh(5)
    set_time(g, 14, 6, 0)
    teleport(g, ROOF)
    give(g, "訊號彈")
    give(g, "收音機")
    run(eng, "signal")
    # 跑去別的地方等 3 小時
    teleport(g, "辦公大樓·辦公室")
    waves, _ = holdout(g, eng)
    assert waves == 0, "不在屋頂不該有整點湧入"
    assert g.over != "evac", "玩家不在屋頂卻拿到 evac 結局：直升機不該在別處接人（engine.hourly 只檢查 elapsed，不檢查位置）"


# ===================================================================== 2. 疫苗
@scenario("2a vaccine：第 11 天前把疫苗樣本送到檢查站 -> vaccine")
def t_vaccine():
    g, eng = fresh(6, goal="疫苗")
    set_time(g, 8, 10)
    teleport(g, CHECKPOINT)
    # 沒樣本：拒收
    run(eng, "deliver")
    assert g.over == "", "沒樣本時不該結束"
    give(g, "疫苗樣本")
    out = run(eng, "deliver")
    assert g.over == "vaccine", f"結局應為 vaccine，實際 {g.over!r} / {out}"


@scenario("2b vaccine：第 11 天跨日後檢查站撤離，deliver 失敗")
def t_vaccine_late():
    g, eng = fresh(7, goal="疫苗")
    set_time(g, 10, 23, 50)
    teleport(g, CHECKPOINT)
    give(g, "疫苗樣本")
    out = run(eng, "wait 1")
    assert g.day == 11, f"應該跨到第 11 天，實際 {g.day}"
    assert g.flags.get("checkpoint_gone") == 1, f"checkpoint_gone 沒設：{g.flags}"
    assert g.factions["軍方"] == 0
    assert DAY_EVENTS[11] in out, "第 11 天事件訊息沒有輸出"
    teleport(g, CHECKPOINT)
    out = run(eng, "deliver")
    assert g.over == "", f"檢查站撤離後 deliver 不該成功：{g.over!r} / {out}"
    assert inv_count(g.player.inv, "疫苗樣本") == 1
    # 不在檢查站也不能交
    g2, eng2 = fresh(8, goal="疫苗")
    give(g2, "疫苗樣本")
    run(eng2, "deliver")
    assert g2.over == ""


# ===================================================================== 3. 護送
NON_INFECTED = ["小美", "阿強", "老陳", "阿凱", "林醫師", "阿芳", "大鬍子"]


def npc_by(g, name):
    return next(n for n in g.npcs if n.name == name)


def recruit(g, eng, name):
    n = npc_by(g, name)
    teleport(g, f"{n.loc}·{n.room}")
    assert n in g.npcs_here(), f"{name} 不在 {g.room}"
    # 信任不夠要被拒
    n.trust = 0
    run(eng, f"ask {name} join")
    assert n.status == "stranger", f"{name} 信任 0 不該加入"
    n.trust = 100
    out = run(eng, f"ask {name} join")
    assert n.status == "companion", f"{name} 沒加入：{out}"
    return n


@scenario("3a escort：招募 4+1 人、在教堂 leave -> placed 累計到 5 -> escort")
def t_escort():
    g, eng = fresh(9, goal="護送")
    names = NON_INFECTED[:5]
    placed_expect = 0
    for batch in (names[:4], names[4:]):
        for nm in batch:
            recruit(g, eng, nm)
        assert len(g.companions()) == len(batch)
        # 第五個人要被拒（護送目標最多 4 人；其他目標 3 人）
        if len(batch) == 4:
            extra = npc_by(g, names[4])
            teleport(g, f"{extra.loc}·{extra.room}")
            extra.trust = 100
            run(eng, f"ask {extra.name} join")
            assert extra.status == "stranger", "超過 4 名隊友還能加入"
        # 不在教堂 leave：不算數
        teleport(g, CHURCH)
        for nm in batch:
            n = npc_by(g, nm)
            before = g.placed
            out = run(eng, f"leave {nm}")
            assert n.status == "placed", f"{nm} 沒被收容：{out}"
            assert g.placed == before + 1, f"placed 沒增加：{g.placed}"
            placed_expect += 1
            if placed_expect < 5:
                assert g.over == "", f"才 {g.placed} 人就結束了：{g.over!r}"
    assert g.placed == 5
    assert g.over == "escort", f"結局應為 escort，實際 {g.over!r}"


@scenario("3b escort：不在教堂 leave 不算收容，且信任下降 / 記仇")
def t_leave_elsewhere():
    g, eng = fresh(10, goal="護送")
    n = recruit(g, eng, "阿凱")  # 貪婪
    teleport(g, "商店街·騎樓")
    t0 = n.trust
    run(eng, "leave 阿凱")
    assert n.status == "left"
    assert g.placed == 0
    assert n.trust < t0
    assert g.flags.get("grudge_阿凱") == 1


@scenario("3c escort：被感染的小傑在教堂會被修女拒收")
def t_escort_infected():
    g, eng = fresh(11, goal="護送")
    n = recruit(g, eng, "小傑")
    assert n.infected
    teleport(g, CHURCH)
    att = g.factions["教堂"]
    out = run(eng, "leave 小傑")
    assert n.status != "placed" and g.placed == 0, f"感染者被收容了：{out}"
    assert n.revealed, "修女檢查後應標記 revealed"
    assert g.factions["教堂"] == att - 10
    assert "不收" in out


@scenario("3d escort：已被玩家發現（revealed）的感染者也必須被修女拒收")
def t_escort_infected_revealed():
    g, eng = fresh(12, goal="護送")
    n = recruit(g, eng, "小傑")
    # 用急救包 check 讓感染曝光
    give(g, "急救包")
    out = run(eng, "check 小傑")
    assert n.revealed, f"check 沒揭露感染：{out}"
    teleport(g, CHURCH)
    out = run(eng, "leave 小傑")
    assert n.status != "placed" and g.placed == 0, (
        f"已知感染的小傑被修女收容了（npc.leave 只在 not revealed 時檢查）：{out}")


# ===================================================================== 4. survived
@scenario("4 survived：第 14 天 12:00 沒達成任何目標 -> survived")
def t_survived():
    g, eng = fresh(13)
    set_time(g, 13, 23, 50)
    out = run(eng, "wait 1")
    assert g.day == 14, f"應跨到第 14 天：{g.day}"
    assert "第 14 天到了" in out, f"final_day 訊息沒出現：{out}"
    assert g.flags.get("final_day") == 1
    assert g.over == "", "剛到第 14 天不該結束"
    set_time(g, 14, 11, 50)
    run(eng, "wait 1")
    assert g.over == "survived", f"結局應為 survived，實際 {g.over!r} at {g.clock()}"
    # 11:00 以前不該觸發
    g2, eng2 = fresh(14)
    set_time(g2, 14, 9, 50)
    run(eng2, "wait 1")
    assert g2.over == "", "第 14 天 10:00 就被判定 survived"


# ===================================================================== 5. 死亡
@scenario("5a dead：血量歸零 -> dead")
def t_dead():
    g, eng = fresh(15)
    g.player.hp = 2
    g.player.bleeding = True
    run(eng, "wait 1")
    assert g.player.hp <= 0
    assert g.over == "dead", f"結局應為 dead，實際 {g.over!r}"


@scenario("5b infection：感染到 100 -> infection")
def t_infection():
    g, eng = fresh(16)
    g.player.infection = 99.5
    run(eng, "wait 1")
    assert g.player.infection >= 100
    assert g.over == "infection", f"結局應為 infection，實際 {g.over!r}"
    # 抗生素減緩：99.5 + 0.4/h 不會在 1 小時內到 100
    g2, eng2 = fresh(17)
    g2.player.infection = 99.5
    g2.player.antibiotic = 12
    run(eng2, "wait 1")
    assert g2.over == "", "抗生素作用中感染仍然立刻致死"


# ===================================================================== 6. 日程
def roll_to_day(g, eng, day):
    """從 (day-1) 23:50 等 1 小時跨到 day。"""
    set_time(g, day - 1, 23, 50)
    teleport(g, START)  # 避免湧入打斷
    g.player.fatigue = 0
    out = run(eng, "wait 1")
    assert g.day == day, f"沒跨到第 {day} 天：{g.day} / {out}"
    return out


@scenario("6a 日程：第 3 天訊息、第 7 天 raiders_active、第 11 天 checkpoint_gone + 軍方 0")
def t_schedule():
    g, eng = fresh(18)
    out = roll_to_day(g, eng, 3)
    assert "=== 第 3 天 ===" in out
    assert DAY_EVENTS[3] in out, f"第 3 天訊息沒輸出：{out}"
    assert not g.flags.get("raiders_active")
    out = roll_to_day(g, eng, 7)
    assert DAY_EVENTS[7] in out
    assert g.flags.get("raiders_active") == 1, g.flags
    assert not g.flags.get("checkpoint_gone")
    assert g.factions["軍方"] == 50
    out = roll_to_day(g, eng, 11)
    assert DAY_EVENTS[11] in out
    assert g.flags.get("checkpoint_gone") == 1, g.flags
    assert g.factions["軍方"] == 0


@scenario("6b 日程：麵包（spoil 3）在第 4 天變成腐壞食物；罐頭不會壞")
def t_spoil():
    g, eng = fresh(19)
    g.player.inv = [new_item("麵包", 1, 1), new_item("罐頭", 2, 1)]
    roll_to_day(g, eng, 3)
    assert inv_count(g.player.inv, "麵包") == 1, "第 3 天麵包就壞了"
    roll_to_day(g, eng, 4)
    assert inv_count(g.player.inv, "麵包") == 0, "第 4 天麵包沒壞"
    assert inv_count(g.player.inv, "腐壞食物") == 1, [it.name for it in g.player.inv]
    assert inv_count(g.player.inv, "罐頭") == 2
    # 據點儲物箱裡的也會壞
    g.base.room = START
    g.base.storage = [new_item("麵包", 1, 4)]
    roll_to_day(g, eng, 7)
    assert [it.name for it in g.base.storage] == ["腐壞食物"]


@scenario("6c 日程：跨日時隊友從背包吃掉一份食物一份水；沒得吃信任下降，連續缺糧會離隊")
def t_feed():
    g, eng = fresh(20)
    n = npc_by(g, "小美")
    n.status = "companion"
    n.trust = 80
    n.hp = 50
    g.player.inv = [new_item("罐頭", 2, 1), new_item("瓶裝水", 2, 1)]
    out = roll_to_day(g, eng, 2)
    assert "小美吃了一份食物和水" in out, out
    assert inv_count(g.player.inv, "罐頭") == 1
    assert inv_count(g.player.inv, "瓶裝水") == 1
    assert inv_count(g.player.inv, "空瓶") == 1, "隊友晚上喝掉你背包的水，空瓶應留在你背包"
    assert n.unfed_days == 0 and n.hp == 60 and n.meal_day == 1
    # 第二晚：食物省著（兩天一份），只喝水
    out = roll_to_day(g, eng, 3)
    assert "喝了水，食物省著" in out and inv_count(g.player.inv, "罐頭") == 1 and inv_count(g.player.inv, "瓶裝水") == 0, out
    # 第三晚要食物了；腐壞食物和髒水不算
    g.player.inv = [new_item("腐壞食物", 1, 1), new_item("髒水", 1, 1)]
    t0 = n.trust
    out = roll_to_day(g, eng, 4)
    assert "沒東西吃" in out, out
    assert n.unfed_days == 1 and n.trust == t0 - 12
    assert inv_count(g.player.inv, "腐壞食物") == 1
    # 忠誠者連續 3 天沒吃才走
    roll_to_day(g, eng, 5)
    assert n.status == "companion" and n.unfed_days == 2
    roll_to_day(g, eng, 6)
    assert n.status == "left", f"忠誠隊友連續 3 天沒吃應離隊：{n.status}"
    assert len(g.companions()) == 0


@scenario("6d 日程：據點儲物箱也能餵隊友（只在人在據點時）")
def t_feed_from_storage():
    g, eng = fresh(21)
    n = npc_by(g, "阿強")
    n.status = "companion"
    g.base.room = START
    g.base.storage = [new_item("罐頭", 1, 1), new_item("瓶裝水", 1, 1)]
    g.player.inv = []
    out = roll_to_day(g, eng, 2)  # roll_to_day 把玩家放在 START = 據點
    assert "阿強吃了一份食物和水" in out, out
    assert [it.name for it in g.base.storage] == ["空瓶"], [it.name for it in g.base.storage]   # 水喝掉，空瓶留在箱裡


# ===================================================================== 7. 傳承
@scenario("7 legacy：死亡後 record_run + build_world(legacy) 在死亡房間放日記與遺物")
def t_legacy():
    seed = 22
    g, eng = fresh(seed)
    death_room = "商店街·五金行"
    teleport(g, death_room)
    g.rooms["十字路口·路口"].visited = True
    npc_by(g, "小美").intro_seen = True
    g.player.inv = [new_item("鐵撬"), new_item("罐頭", 2), new_item("疫苗樣本"), new_item("繃帶"), new_item("木板"), new_item("手電筒")]
    g.player.hp = 0
    eng.check_death()
    assert g.over == "dead"
    meta = {"deaths": [], "known_rooms": [], "known_traits": [], "runs": 0, "wins": []}
    meta = record_run(g, meta)
    assert meta["runs"] == 1
    assert meta["deaths"][-1]["room"] == death_room
    assert meta["deaths"][-1]["cause"] == "dead"
    assert "十字路口·路口" in meta["known_rooms"]
    assert "小美" in meta["known_traits"]
    g2 = build_world(seed, legacy=meta)
    r = g2.rooms[death_room]
    names = [it.name for it in r.items]
    assert "日記" in names, names
    assert "鐵撬" in names and "罐頭" in names and "繃帶" in names, names
    assert "疫苗樣本" not in names, "疫苗樣本不該傳承"
    # 規則是「略過樣本後取前 4 件」：木板是第 4 件遺物，手電筒是第 5 件不會出現
    assert "木板" in names and "手電筒" not in names, names
    assert len(names) == 5, names  # 4 件遺物 + 日記
    assert g2.rooms["十字路口·路口"].visited
    assert npc_by(g2, "小美").intro_seen
    assert "屍體" in r.flavor
    # 新局可以把日記撿起來讀
    eng2 = Engine(g2)
    teleport(g2, death_room)
    out = run(eng2, "take 日記")
    assert "日記最後一頁" in out, out
    out = run(eng2, "use 日記")
    assert "第 3 天水停了" in out
    # 感染死亡：房間裡有「熟悉的面孔」
    g3, eng3 = fresh(23)
    teleport(g3, "超市·辦公室")
    g3.player.infection = 100
    g3.player.hp = 0
    eng3.check_death()
    assert g3.over == "infection"
    meta = record_run(g3, {"deaths": [], "known_rooms": [], "known_traits": [], "runs": 0, "wins": []})
    g4 = build_world(23, legacy=meta)
    r4 = g4.rooms["超市·辦公室"]
    assert any(e.name == "熟悉的面孔" for e in r4.enemies), [e.label() for e in r4.enemies]
    assert any(it.name == "日記" for it in r4.items)
    # 勝利不記死亡
    g5, _ = fresh(24)
    g5.over = "evac"
    meta = record_run(g5, {"deaths": [], "known_rooms": [], "known_traits": [], "runs": 0, "wins": []})
    assert meta["deaths"] == [] and meta["wins"][-1]["ending"] == "evac"


# ===================================================================== 8. 真實走位
PLAY_SEED = 2   # 用 build_world(seed) 掃描挑出的種子：這條路線沒有街道喪屍、沒有事件提問、沒有埋伏
PLAY_PATH = [
    ("out", "住宅區·巷口", 5),
    ("s", "十字路口·路口", 20),
    ("s", "商店街·騎樓", 20),
    ("in", "商店街·五金行", 5),
    ("search", "商店街·五金行", 20),
    ("out", "商店街·騎樓", 5),
    ("n", "十字路口·路口", 20),
    ("n", "住宅區·巷口", 20),
    ("in", "住宅區·客廳", 5),
]


@scenario("8 真實走位：客廳 -> 街 -> 十字路口 -> 商店街五金行 搜索 -> 回客廳，不動狀態")
def t_playthrough():
    g, eng = fresh(PLAY_SEED)
    for r in g.rooms.values():
        r.enemies.clear()
        r.hidden.clear()
    assert g.room == START
    assert g.day == 1 and g.minute == 8 * 60
    minute = g.minute
    inv_before = sum(it.qty for it in g.player.inv)
    for cmd, room, cost in PLAY_PATH:
        out = run(eng, cmd)
        assert not g.over, f"[{cmd}] 遊戲結束：{g.over}"
        assert not g.combat, f"[{cmd}] 進入戰鬥：{out}"
        assert not g.flags.get("pending"), f"[{cmd}] 有待回答事件：{out}"
        assert g.room == room, f"[{cmd}] 應該在 {room}，實際 {g.room}：{out}"
        assert g.minute == minute + cost, f"[{cmd}] 時間應 +{cost}，實際 {g.clock()}（前 {minute}）"
        minute = g.minute
        if cmd == "search":
            assert "找到" in out, f"搜索沒有找到東西：{out}"
            assert g.cur.searched == 1
    assert g.minute == 8 * 60 + 120, g.clock()
    assert sum(it.qty for it in g.player.inv) > inv_before or g.cur.items, "搜索應該有拿到東西"
    assert g.rooms["商店街·五金行"].visited
    # 錯誤方向與街上搜索都被擋（客廳有「上」通二樓，但沒有「下」）
    assert "下" not in g.cur.exits
    out = run(eng, "d")
    assert g.room == START and "沒有路" in out, out
    out = run(eng, "out")
    assert g.room == "住宅區·巷口", out
    out = run(eng, "search")
    assert "街上" in out and g.cur.searched == 0, out


@scenario("9 製作：背包滿時不能撕布料（不扣血、不消失）；騰出格子後才做得出來；用光的材料會空出格子")
def t_craft_full():
    g, eng = fresh(PLAY_SEED)
    p = g.player
    for n in ("罐頭", "手電筒", "打火機", "鐵撬", "球棒", "木板", "釘子"):
        p.inv.append(new_item(n))
    assert len(p.inv) == p.slots == 10
    hp = p.hp
    out = run(eng, "craft 布料")
    assert "背包滿" in out and p.hp == hp and not any(it.name == "布料" for it in p.inv), out
    p.inv.remove(next(it for it in p.inv if it.name == "罐頭"))
    out = run(eng, "craft 布料")
    assert "做好了" in out and p.hp == hp - 5 and any(it.name == "布料" and it.qty == 2 for it in p.inv), out
    # 背包又滿了（10 格），但繃帶會用光布料那一格，所以做得出來
    assert len(p.inv) == 10
    out = run(eng, "craft 繃帶")
    assert "做好了" in out and any(it.name == "繃帶" for it in p.inv) and not any(it.name == "布料" for it in p.inv), out


# ===================================================================== main
def main():
    tests = [t_evac, t_evac_vaccine, t_signal_preconditions, t_signal_past_noon, t_signal_offroof,
             t_vaccine, t_vaccine_late,
             t_escort, t_leave_elsewhere, t_escort_infected, t_escort_infected_revealed,
             t_survived, t_dead, t_infection,
             t_schedule, t_spoil, t_feed, t_feed_from_storage,
             t_legacy, t_playthrough, t_craft_full, t_wait_behind, t_sneak_search, t_pin, t_mini_floors, t_look_npc, t_cure, t_food_supply]
    for t in tests:
        t()
    print()
    print(f"{len(PASSES)} passed, {len(FAILURES)} failed")
    for name, msg, tb in FAILURES:
        print("-" * 60)
        print(f"FAIL {name}\n  {msg}")
        if "AssertionError" not in msg:
            print(tb)
    # 不留垃圾檔
    for junk in ("save.json", "meta.json", "error.log", "save.json.tmp"):
        p = os.path.join(ROOT, junk)
        if os.path.exists(p):
            print(f"警告：測試後專案根目錄出現 {junk}")
    sys.exit(1 if FAILURES else 0)


@scenario("10 留守：留在據點不跟著走、每小時回血、你回來歸隊；留在外面一天沒回去退回據點；有人在家掠奪者撬不開門")
def t_wait_behind():
    g, eng = fresh(seed=2)
    teleport(g, START)
    run(eng, "claim")
    n = g.npcs[0]
    n.status = "companion"
    n.hp = max(1, n.max_hp - 30)
    n.loc, n.room = g.cur.loc, g.cur.name
    hp0 = n.hp
    out = run(eng, f"order {n.name} rest")
    assert n.status == "waiting" and "留守" in out, out
    assert n not in g.companions()
    st = eng.status_line()
    assert "留守" in st and "客廳" in st, st
    # 走到隔壁：他不跟
    d = next(d for d, t in g.cur.exits.items() if not g.rooms[t].is_street() and not g.rooms[t].locked)
    tgt = g.cur.exits[d]
    g.rooms[tgt].enemies.clear()
    g.rooms[tgt].hidden.clear()
    run(eng, f"go {d}")
    assert g.room == tgt and n.status == "waiting", (g.room, n.status)
    set_time(g, g.day, 10)
    g.cur.enemies.clear()
    g.rooms[START].enemies.clear()
    eng.new_turn()
    eng.advance(180)
    assert n.hp > hp0, (n.hp, hp0)
    # 回去：歸隊
    back = next(d2 for d2, t2 in g.cur.exits.items() if t2 == START)
    out = run(eng, f"go {back}")
    assert n.status == "companion" and "歸隊" in out, out
    # 留在外面，過一天沒回去：退回據點
    teleport(g, tgt)
    run(eng, f"order {n.name} rest")
    g.room = CHURCH
    g.cur.enemies.clear()
    g.cur.hidden.clear()
    n.wait_day = g.day - 1
    eng.new_turn()
    eng.waiting_daily()
    assert f"{n.loc}·{n.room}" == START, (n.loc, n.room)
    # 掠奪者：留守在家、加固 0 → 撬不開門，儲物不掉
    from zg import events
    g.base.fort = 0
    g.base.storage.append(new_item("罐頭"))
    g.flags["raiders_active"] = True
    g.factions["掠奪者"] = 10
    eng.new_turn()
    eng.rng.random = lambda: 0.1
    events.raid_check(eng)
    out = "\n".join(eng.out)
    assert "撬了很久" in out and any(it.name == "罐頭" for it in g.base.storage) and g.base.fort == 0, out
    # 同一間房叫他歸隊
    teleport(g, START)
    out = run(eng, "rejoin")
    assert n.status == "companion" and "歸隊" in out, out
    # 守夜 = 留守據點；你在據點睡覺時他算守夜（night_check 的 guards）
    n.skill = "守夜"
    out = run(eng, f"order {n.name} guard")
    assert n.status == "waiting" and "門邊" in out, out
    g.threat[g.cur.loc] = 10
    set_time(g, g.day, 23)
    eng.new_turn()
    eng.rng.random = lambda: 0.0        # 一定觸發夜襲
    events.night_check(eng, at_base=True)
    out = "\n".join(eng.out)
    assert "搖醒你" in out, out


@scenario("11 潛行搜索：距離 3 以上的喪屍不會發現你；一個人成功率最高，每多一個隊友 -12；失敗就開打；叫隊友翻不行")
def t_sneak_search():
    from zg.state import Enemy
    from zg.combat import sneak_chance
    g, eng = fresh(seed=3)
    teleport(g, START)
    room = g.rooms["住宅區·廚房"] if "住宅區·廚房" in g.rooms else g.rooms[g.cur.exits[next(iter(g.cur.exits))]]
    d = next(dd for dd, t in g.cur.exits.items() if t == room.id)
    room.enemies = [Enemy("行屍", 30, dist=3)]
    room.hidden.clear()
    room.loot = [new_item("餅乾")]
    room.searched = 0
    set_time(g, 2, 10)
    out = run(eng, f"go {d}")
    assert not g.combat and "還沒注意到你" in out, out
    solo = sneak_chance(g, room)
    for n in g.npcs[:3]:
        n.status = "companion"
    assert sneak_chance(g, room) == solo - 36, (solo, sneak_chance(g, room))
    for n in g.npcs[:3]:
        n.status = "stranger"
    # 叫隊友翻：不行
    g.npcs[0].status = "companion"
    out = run(eng, f"order {g.npcs[0].name} search")
    assert "太吵" in out and not g.combat, out
    g.npcs[0].status = "stranger"
    # 成功：拿到東西、沒開打
    eng.new_turn()
    eng.rng.randint = lambda a, b: 1
    eng.rng.random = lambda: 0.99     # 不讓遊蕩觸發
    handle(eng, "search")
    out = "\n".join(eng.out)
    assert not g.combat and "餅乾" in out and inv_count(g.player.inv, "餅乾") >= 1, out
    # 失敗：開打，牠從距離 3 過來（有瞄準時間）
    room.loot = [new_item("罐頭")]
    eng.new_turn()
    eng.rng.randint = lambda a, b: 100
    handle(eng, "search")
    out = "\n".join(eng.out)
    assert g.combat and "轉過頭來" in out and all(e.dist >= 3 for e in room.enemies), out


@scenario("12 牽制：要有隊友；隊友命中 +15 起、每 3 次升級到 +30；牠們 80% 撲你、羈絆隊友不擋；沒隊友不能用")
def t_pin():
    from zg.state import Enemy
    from zg import combat
    g, eng = fresh(seed=4)
    teleport(g, START)
    out = run(eng, "pin")
    assert "沒有東西要牽制" in out, out
    g.cur.enemies = [Enemy("行屍", 300, dist=1)]
    g.combat = True
    out = run(eng, "pin")
    assert "白白挨打" in out and not g.flags.get("pin_uses"), out
    n = g.npcs[0]
    n.status = "companion"
    n.hp = n.max_hp
    n.bonded = True
    n.inv = []
    hp0 = g.player.hp
    eng.new_turn()
    eng.rng.random = lambda: 0.5          # 牽制中：0.5*100 < 80 → 撲你；不牽制時 0.5 不會選隊友前排(無)、0.5 ≥ 0.3 不選隊友
    eng.rng.randint = lambda a, b: a      # 一定命中、最低傷害
    handle(eng, "pin")
    out = "\n".join(eng.out)
    assert g.flags["pin"] == g.turn and g.flags["pin_uses"] == 1, out
    assert "命中 +15" in out and "你" in out and n.hp == n.max_hp and g.player.hp < hp0, out
    assert combat.pin_bonus(g) == 15
    g.flags["pin_uses"] = 9
    assert combat.pin_level(g) == 3 and combat.pin_bonus(g) == 30
    # 牽制中隊友命中 = 50 + 15(羈絆) + 30：randint 回傳 95 也要打中
    eng.new_turn()
    eng.rng.randint = lambda a, b: 95 if (a, b) == (1, 100) else a
    g.cur.enemies[0].hp = 300
    handle(eng, "pin")
    out = "\n".join(eng.out)
    assert "打中" in out or "解決" in out, out


@scenario("13 右欄小地圖：所有樓層由上往下、你在的那層加 [ ]、沒去過的房間是？？、每行不超過 45 格、行數上限會收成一行")
def t_mini_floors():
    from zg import mapdraw
    from zg.textw import w
    g, eng = fresh(seed=1)
    teleport(g, "辦公大樓·辦公室")
    lines = mapdraw.mini_floor(g)
    txt = "\n".join(lines)
    assert "[2F] 你在這層" in txt and "3F" in txt and "1F" in txt and "？？" in txt, txt
    assert all(w(x) <= 45 for x in lines), [x for x in lines if w(x) > 45]
    assert lines.index(next(x for x in lines if x.startswith("3F"))) < lines.index(next(x for x in lines if x.startswith("[2F]"))), txt
    short = mapdraw.mini_floor(g, max_lines=16)      # 你這層 12 行 + 抬頭 + 圖例 + 其他樓層一行 = 15
    assert len(short) <= 16 and any(x.startswith("其他樓層") for x in short) and "[2F] 你在這層" in "\n".join(short), short


@scenario("14 觀察人：第一次是外表；之後陌生人／隊友、信任低中高各有不同敘述，不再重複初見面那段")
def t_look_npc():
    g, eng = fresh(seed=1)
    n = next(x for x in g.npcs if x.name == "小美")
    teleport(g, f"{n.loc}·{n.room}")
    first = run(eng, "look 小美")
    assert "剪刀" in first and "比你還怕" in first, first
    again = run(eng, "look 小美")
    assert "比你還怕" not in again and "信任低" in again, again
    n.trust = 50
    mid = run(eng, "look 小美")
    assert mid != again and "信任中" in mid, mid
    n.status = "companion"
    n.trust = 20
    low = run(eng, "look 小美")
    assert "準備往反方向跑" in low and "血量" in low, low
    n.trust = 80
    high = run(eng, "look 小美")
    assert "幫你看背後" in high, high
    n.unfed_days = 1
    assert "餓著肚子" in run(eng, "觀察 小美")


@scenario("15 治療與餵食：給抗生素有機率治好（醫療隊友 +30）；白天餵過晚上不扣口糧；給繃帶當場包紮；醫療隊友每天自動用抗生素治被咬隊友")
def t_cure():
    from zg.npc import cure_chance
    g, eng = fresh(seed=5)
    teleport(g, START)
    n = npc_by(g, "小傑")                       # 開局就被咬，infect_day=1
    n.status = "companion"
    n.loc, n.room = g.cur.loc, g.cur.name
    assert n.infected and cure_chance(g, n) == 35 + 15, cure_chance(g, n)     # 第 1 天：被咬一天內
    doc = npc_by(g, "小美")
    doc.status = "companion"
    doc.loc, doc.room = g.cur.loc, g.cur.name
    assert cure_chance(g, n) == 80
    # 給抗生素：先揭穿再治；強制失敗 → 延 2 天
    g.player.inv = [new_item("抗生素", 2), new_item("繃帶", 1), new_item("罐頭", 1), new_item("瓶裝水", 1)]
    eng.new_turn()
    eng.rng.randint = lambda a, b: 100
    handle(eng, "give 小傑 抗生素")
    out = "\n".join(eng.out)
    assert n.revealed and n.infected and n.infect_day == 3 and "沒治好" in out, out
    # 強制成功 → 治好
    eng.new_turn()
    eng.rng.randint = lambda a, b: 1
    handle(eng, "give 小傑 抗生素")
    out = "\n".join(eng.out)
    assert not n.infected and "他好了" in out and inv_count(g.player.inv, "抗生素") == 0, out
    # 繃帶：受傷才會當場用
    n.hp = n.max_hp - 30
    out = run(eng, "give 小傑 繃帶")
    assert n.hp == n.max_hp - 15 and "纏上去" in out and inv_count(n.inv, "繃帶") == 0, out
    # 餵食：今天吃過喝過 → 晚上不扣
    out = run(eng, "give 小傑 罐頭")
    assert "當場" in out and n.ate_day == g.day, out
    out = run(eng, "give 小傑 瓶裝水")
    assert n.drank_day == g.day and "空瓶" in out and inv_count(g.player.inv, "空瓶") == 1, out
    g.player.inv = [new_item("罐頭", 1), new_item("瓶裝水", 1)]
    doc.ate_day = doc.drank_day = g.day
    g.player.hunger = g.player.thirst = g.player.fatigue = 0
    g.player.hp = 100
    set_time(g, g.day, 22)
    eng.new_turn()
    eng.rng.random = lambda: 0.99
    eng.rng.randint = lambda a, b: 1
    eng.advance(3 * 60)
    out = "\n".join(eng.out)
    assert inv_count(g.player.inv, "罐頭") == 1 and n.unfed_days == 0 and doc.unfed_days == 0, out
    # 醫療隊友自動治：阿強被咬、玩家有抗生素 → 隔天醫師餵藥
    s = npc_by(g, "阿強")
    s.status = "companion"
    s.loc, s.room = g.cur.loc, g.cur.name
    s.infected, s.infect_day = True, g.day
    g.player.inv = [new_item("抗生素", 1), new_item("罐頭", 3), new_item("瓶裝水", 3)]
    g.player.hunger = g.player.thirst = g.player.fatigue = 0
    g.player.hp = 100
    set_time(g, g.day, 22)
    eng.new_turn()
    eng.rng.random = lambda: 0.99
    eng.rng.randint = lambda a, b: 1
    eng.advance(3 * 60)
    out = "\n".join(eng.out)
    assert not s.infected and "小美" in out and inv_count(g.player.inv, "抗生素") == 0, out


@scenario("16 口糧：修女每收一人給罐頭+水；全地圖食物平均 ≥ 42 份；17:00 提示分開算食物與水")
def t_food_supply():
    from zg.data import ITEMS
    g, eng = fresh(seed=7, goal="護送")
    n = g.npcs[0]
    n.status = "companion"
    n.infected = False
    teleport(g, CHURCH)
    n.loc, n.room = g.cur.loc, g.cur.name
    g.player.inv = []
    out = run(eng, f"leave {n.name}")
    assert "收容所的口糧" in out and inv_count(g.player.inv, "罐頭") == 1 and inv_count(g.player.inv, "瓶裝水") == 1, out
    tot = []
    for seed in range(1, 21):
        w = build_world(seed)
        tot.append(sum(it.qty for r in w.rooms.values() for it in r.loot + r.items if ITEMS[it.name]["kind"] == "food" and it.name != "腐壞食物"))
    avg = sum(tot) / len(tot)
    assert avg >= 42, avg
    # 提示：兩個隊友，一個今天吃過
    g, eng = fresh(seed=7)
    teleport(g, START)
    a, b = g.npcs[0], g.npcs[1]
    a.status = b.status = "companion"
    g.day = 3
    a.meal_day = 2                  # 昨天剛吃，今晚不用
    nf, nw, food, water = eng.rations()
    assert nf == 1 and nw == 2, (nf, nw)


if __name__ == "__main__":
    main()
