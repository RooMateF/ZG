# -*- coding: utf-8 -*-
"""自動測試機器人：隨機指令跑很多局，抓例外；順便做存檔往返測試。
用法：python tests/bot.py [局數] [每局步數]
"""
import os
import sys
import random
import traceback
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from zg.world import build_world
from zg.engine import Engine
from zg.commands import handle
from zg.state import to_dict, from_dict
from zg.data import LOCATIONS

CMDS = ["n", "s", "e", "w", "u", "d", "in", "out", "in", "out", "look", "search", "search", "search", "map", "stat", "inv", "take all", "pin",
        "sleep 6", "sleep 2", "wait 1", "wait 3", "claim", "fortify", "craft", "craft 繃帶", "craft 淨水", "refill",
        "attack", "attack head", "aim", "push", "flee n", "flee s", "flee e", "flee w", "flee out", "flee in", "throw 石頭", "throw 燃燒瓶",
        "use 繃帶", "use 罐頭", "use 瓶裝水", "use 抗生素", "use 不明藥丸", "use 急救包", "use 收音機", "use 背包",
        "equip 鐵撬", "equip 球棒", "equip 消防斧", "equip 手槍", "drop 石頭", "store 木板", "retrieve 木板",
        "talk 小美", "talk 阿強", "talk 老陳", "talk 阿凱", "talk 林醫師", "talk 小傑", "talk 阿芳", "talk 大鬍子",
        "talk 守衛", "talk 修女", "talk 頭目", "talk 軍官", "trade 修女", "trade 修女 罐頭 繃帶", "trade 小美 餅乾 繃帶",
        "give 小美 餅乾", "give 老陳 餅乾", "give 阿強 菜刀", "ask 小美 join", "ask 老陳 join", "ask 阿強 join", "ask 阿芳 join",
        "order 小美 search", "order 小美 guard", "order 老陳 rest", "leave 小美", "leave 老陳", "check 小傑", "check 小美",
        "open n", "open s", "open e", "open w", "deliver", "signal", "yes", "no", "help", "journal", "look 小美", "look 菜刀",
        "亂打", "go 北", "北", "搜", "拿 全部"]


def run_one(seed, steps, rng, verbose=False):
    g = build_world(seed)
    eng = Engine(g)
    errors = []
    max_day = 1
    for i in range(steps):
        cmd = rng.choice(CMDS)
        eng.new_turn()
        try:
            handle(eng, cmd)
            eng.check_death()
        except Exception:
            errors.append((seed, i, cmd, traceback.format_exc()))
            break
        max_day = max(max_day, g.day)
        if verbose:
            print(f"[{cmd}]", " | ".join(eng.out)[:200])
        if g.over:
            break
        # 每 25 步做一次存檔往返
        if i % 25 == 0:
            try:
                d = json.loads(json.dumps(to_dict(g), ensure_ascii=False))
                g2 = from_dict(d)
                assert to_dict(g2) == to_dict(g), "save roundtrip mismatch"
                g = g2
                eng = Engine(g)
            except Exception:
                errors.append((seed, i, "save/load", traceback.format_exc()))
                break
    return errors, g, max_day


def check_map(seed):
    g = build_world(seed)
    # 雙向出口一致
    for r in g.rooms.values():
        for d, tid in r.exits.items():
            t = g.rooms[tid]
            assert tid in g.rooms, f"{r.id} -> {tid} 不存在"
            back = {"北": "南", "南": "北", "東": "西", "西": "東", "上": "下", "下": "上", "進": "出", "出": "進"}[d]
            assert t.exits.get(back) == r.id, f"{r.id} {d}-> {tid} 沒有回路 ({t.exits})"
    # 全部連通
    seen = {g.room}
    stack = [g.room]
    while stack:
        cur = stack.pop()
        for tid in g.rooms[cur].exits.values():
            if tid not in seen:
                seen.add(tid)
                stack.append(tid)
    assert len(seen) == len(g.rooms), f"有 {len(g.rooms) - len(seen)} 個房間不連通: {set(g.rooms) - seen}"
    assert any(it.name == "疫苗樣本" for r in g.rooms.values() for it in r.loot), "沒有疫苗樣本"


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    rng = random.Random(1)
    all_errors = []
    overs = {}
    days = []
    for k in range(runs):
        seed = rng.randrange(1, 10 ** 6)
        try:
            check_map(seed)
        except AssertionError as ex:
            all_errors.append((seed, -1, "map", str(ex)))
            continue
        errs, g, max_day = run_one(seed, steps, rng)
        all_errors.extend(errs)
        overs[g.over or "running"] = overs.get(g.over or "running", 0) + 1
        days.append(max_day)
    print(f"局數 {runs}，每局 {steps} 步")
    print("結局分布：", overs)
    if days:
        print("平均撐到第幾天：", round(sum(days) / len(days), 1), "最高", max(days))
    print(f"錯誤數：{len(all_errors)}")
    seen = set()
    for seed, i, cmd, tb in all_errors:
        key = tb.strip().splitlines()[-1]
        if key in seen:
            continue
        seen.add(key)
        print("-" * 60)
        print(f"seed={seed} step={i} cmd={cmd}")
        print(tb)
    sys.exit(1 if all_errors else 0)


if __name__ == "__main__":
    main()
