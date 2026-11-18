# -*- coding: utf-8 -*-
"""《末日第十四天》入口。python play.py"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zg.console import setup as _console_setup  # noqa: E402
CONSOLE_FONT = _console_setup()
from zg.data import GOALS, BOSS_LOG  # noqa: E402
from zg.world import build_world  # noqa: E402
from zg.engine import Engine  # noqa: E402
from zg.commands import handle, ALIASES, HELP, COMBAT_HELP, do_stat  # noqa: E402
from zg.mapdraw import city_map, floor_map  # noqa: E402
from zg import options, ui  # noqa: E402
from zg.textw import set_ambiguous_wide, set_overrides, PROBE_CHARS  # noqa: E402
from zg.console import probe_widths  # noqa: E402
set_ambiguous_wide(CONSOLE_FONT is not None)   # 傳統主控台 + 中文字型：箭頭等符號佔 2 格
set_overrides(probe_widths(PROBE_CHARS))       # 再實際量一次：像「·」在細明體主控台其實只佔 1 格
from zg.save import save_game, load_game, delete_save, load_meta, save_meta, record_run  # noqa: E402

ENDINGS = {
    "dead": "你死了。",
    "infection": "你變成了牠們的一員。下一個走進這裡的人會看到你。",
    "survived": "第 14 天中午過了。沒有直升機，沒有車，沒有人來。你還活著，但接下來的日子沒有結局。",
    "evac": "直升機拉起來的時候，你看到整座城市。到處都是牠們。你沒有回頭。",
    "evac_vaccine": "直升機拉起來的時候，你抱著那個保溫盒。有人會因為這管東西活下來。也許。",
    "vaccine": "軍方的卡車載著你往北開。後面的城市越來越小。你做到了。",
    "escort": "修女數了數人頭，點了點頭。車來的時候，五個人回頭看你。你帶他們出來了。",
}

HOTKEY_HELP = """快捷鍵（任何時候都能按）
  M 地圖   I 背包   C 製作   P 人物   H 據點   R 休息
  T 狀態與目標   J 最近發生的事   L 看四周   ? 這頁   B 老闆鍵   Q 存檔離開
  數字 選畫面上的選項，子選單裡 0 回上一層   n s e w u d 直接走
  restart 放棄這局重新開始（會保留已探索的地圖和認識的人）
"""

# 快捷鍵 -> 子選單
MENU_KEYS = {"i": options.inventory_menu, "c": options.craft_menu, "p": options.people_menu,
             "h": options.base_menu, "r": options.rest_menu}


def ask_difficulty():
    ui.clear()
    print(ui.rule("難度"))
    print("1 普通：感染速度 0.7 倍、喪屍數量 0.7 倍。先用這個摸熟路線。")
    print("2 硬核：原本的數值。")
    print(ui.rule())
    try:
        ans = input("選 1 或 2（Enter = 普通）> ").strip()
    except (EOFError, KeyboardInterrupt):
        ans = ""
    return "hard" if ans.startswith("2") else "normal"


def new_game(meta):
    seed = random.randrange(1, 10 ** 9)
    return build_world(seed, legacy=meta, difficulty=ask_difficulty())


def review_lines(g):
    """結束回顧。"""
    f = g.flags
    lines = [f"活了 {g.day} 天（{g.clock()}），難度{'普通' if f.get('difficulty') == 'normal' else '硬核'}，目標：{g.goal}。",
             f"打了 {f.get('fights', 0)} 場，擊殺 {f.get('kills', 0)}（親手 {f.get('xp_kills', 0)}），被咬 {f.get('bites', 0)} 次。",
             f"走過 {sum(1 for r in g.rooms.values() if r.visited)}/{len(g.rooms)} 個房間，隊友 {len(g.companions())} 人"
             + (f"，據點在{g.rooms[g.base.room].full}" if g.base.room else "，沒有據點") + "。"]
    if g.over in ("dead", "infection"):
        lines.append("最後發生的事：")
        lines.extend("  " + t for t in g.log[-6:])
    return lines


def intro_text(g, meta):
    lines = []
    if meta.get("runs"):
        last = meta.get("last") or {}
        names = {"survived": "撐到了第 14 天", "evac": "搭上了直升機", "evac_vaccine": "帶著疫苗搭上了直升機",
                 "vaccine": "把疫苗送到了", "escort": "把人送到了教堂"}
        if last.get("ending") in names:
            lines.append(f"這是你的第 {meta['runs'] + 1} 次。上一次你{names[last['ending']]}。這次多帶了罐頭x2 和繃帶。")
        elif meta.get("deaths"):
            lines.append(f"這是你的第 {meta['runs'] + 1} 次。上一次死在第 {meta['deaths'][-1]['day']} 天。")
        else:
            lines.append(f"這是你的第 {meta['runs'] + 1} 次。")
    if sys.platform == "win32" and not CONSOLE_FONT:
        lines.append("（如果看到方塊亂碼：在視窗標題列按右鍵 > 內容 > 字型，選「細明體」或 NSimSun）")
    lines.append("")
    lines.append("你在一棟透天厝的客廳醒來。外面很安靜，安靜得不對。")
    lines.append(f"目標：{g.goal}。{GOALS[g.goal]}")
    lines.append("")
    lines.append(HOTKEY_HELP)
    return lines


def status_text(eng):
    keep = eng.out
    eng.out = []
    do_stat(eng)
    text = list(eng.out)
    eng.out = keep
    return text


def help_text(g):
    return [HOTKEY_HELP, "", "指令（也可以直接打字）", COMBAT_HELP if g.combat else HELP]


def start(g, meta, first=False):
    """建立引擎並顯示開場。回傳 engine。"""
    eng = Engine(g)
    eng.out = []
    if first:
        ui.view("末日第十四天", intro_text(g, meta), prompt="按 Enter 開始 ")
    eng.say(eng.room_desc())
    return eng


def run_turn(eng, line, label=None):
    eng.new_turn()
    if label:
        eng.out.append(f"> {label}")
    try:
        handle(eng, line)
    except Exception as ex:  # 不讓一個 bug 毀掉存檔
        eng.say(f"[程式錯誤：{type(ex).__name__}: {ex}] 已自動存檔，請回報。")
        import traceback
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "error.log"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
    eng.check_death()


def main():
    meta = load_meta()
    try:
        g = load_game()
    except Exception:
        g = None
    if g and not g.over:
        eng = start(g, meta)
        eng.out.insert(0, "讀取存檔。")
    else:
        g = new_game(meta)
        eng = start(g, meta, first=True)
    menu = None     # 目前所在的子選單
    hint = ""       # 畫面上的一行提示（選錯、不是時候…）
    last_line = ""  # 上一個真的執行過的指令，空白 Enter 重複用
    while True:
        entries = menu.entries if menu else options.build(g)
        ui.draw(eng, menu, entries, hint)
        hint = ""
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            save_game(g)
            print("\n已存檔。")
            return
        text = line.strip()
        label = None
        if not text:
            if last_line and not menu:
                text = last_line              # 空白 Enter = 重複上一個指令
                line = last_line
                label = f"重複 {last_line}"
            else:
                continue
        low = text.lower()
        # ---- 數字：選選項 / 進子選單 / 0 返回。「3 抗生素」= 選 3 再在子選單裡挑含「抗生素」的那項
        words0 = text.split()
        if words0[0].isdigit():
            idx = int(words0[0])
            arg = " ".join(words0[1:])
            if idx == 0:
                menu = menu.parent if menu else None
                continue
            choices = ui.selectable(entries)
            if not (1 <= idx <= len(choices)):
                hint = "沒有這個選項。"
                continue
            label, target = choices[idx - 1]
            if target is None:
                continue
            # 一路往下：有參數就在子選單裡找符合的項目
            while callable(target):
                sub = target(g)
                if sub.parent is None:
                    sub.parent = menu
                menu = sub
                if not arg:
                    break
                hits = [e for e in ui.selectable(sub.entries) if e[1] is not None and arg in e[0]]
                if len(hits) != 1:
                    hint = f"「{arg}」在這層" + ("沒有符合的" if not hits else f"有 {len(hits)} 個符合，選一下")
                    arg = ""
                    break
                label, target = hits[0]
            if callable(target) or target is None:
                continue
            line = target
            menu = None
        else:
            menu = None
        words = line.strip().split()
        head = ALIASES.get(words[0].lower(), words[0].lower())
        single = len(words) == 1
        # ---- 全畫面檢視
        if single and head == "map":
            # 雙欄模式右邊已經有建築平面圖，M 只看全區域；單欄模式才一起顯示
            ui.view("地圖", city_map(g) if ui.wide_mode() else city_map(g) + "\n\n" + floor_map(g))
            continue
        if single and (head == "stat" or low == "t"):
            ui.view("狀態與目標", status_text(eng))
            continue
        if single and (head == "journal" or low == "j"):
            ui.view("最近發生的事", list(g.log[-25:]) or ["還沒有事發生。"])
            continue
        if single and head == "help":
            ui.view("說明", help_text(g))
            continue
        if single and head == "b":
            ui.clear()
            print(BOSS_LOG)
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                save_game(g)
                return
            # 回來時提醒做到哪
            recent = next((t for t in eng.out if not t.startswith("> ")), "")
            hint = "回來了。" + (f"上一步：{last_line}" if last_line else "還沒動過") + (f"｜{recent[:30]}" if recent else "")
            continue
        if single and head == "q":
            save_game(g)
            ui.clear()
            print("已存檔。下次直接 python play.py 繼續。")
            return
        if single and head == "restart":
            try:
                ans = input(f"確定放棄這局（第 {g.day} 天）重新開始？(y/n) ")
            except (EOFError, KeyboardInterrupt):
                continue
            if not ans.strip().lower().startswith("y"):
                hint = "繼續這局。"
                continue
            g.over = "abandon"
            meta = record_run(g, meta)
            save_meta(meta)
            delete_save()
            g = new_game(meta)
            eng = start(g, meta, first=True)
            menu = None
            continue
        # ---- 快捷鍵 / 沒帶參數的指令 -> 子選單
        opener = None
        if single and low in MENU_KEYS:
            opener = MENU_KEYS[low]
        elif single and head == "inv":
            opener = options.inventory_menu
        elif single and head in options.BARE and options.BARE[head]:
            opener = options.BARE[head]
        if opener:
            if g.flags.get("pending"):
                hint = "先回答：是或否。"
            elif g.combat and g.cur.enemies and opener is not options.inventory_menu:
                hint = "現在不是時候。牠就在你面前。"
            else:
                menu = opener(g)
                menu.parent = None
            continue
        # ---- 真正的指令
        run_turn(eng, line, label)
        last_line = line.strip()
        if g.over:
            ui.draw(eng, None, [], "")
            print()
            print("=" * ui.WIDTH)
            print(ENDINGS.get(g.over, "結束。"))
            for t in review_lines(g):
                print(t)
            print("=" * ui.WIDTH)
            meta = record_run(g, meta)
            save_meta(meta)
            delete_save()
            try:
                ans = input("再來一局？(y/n) ")
            except (EOFError, KeyboardInterrupt):
                return
            if ans.strip().lower().startswith("y"):
                g = new_game(meta)
                eng = start(g, meta, first=True)
                menu = None
                continue
            return
        save_game(g)


if __name__ == "__main__":
    main()
