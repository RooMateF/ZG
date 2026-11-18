# -*- coding: utf-8 -*-
"""規則端的程式進入點：一行 JSON 進來，一行 JSON 出去。

    python -X utf8 -m zg.hd.bridge

Godot 把它開成子程序，從標準輸入送指令、從標準輸出讀回覆。格式見 docs/RULES_BRIDGE.md。
第一個指令要是 new（開新局）或 load（讀檔）。送 {"cmd": "quit"} 或關掉輸入就結束。
"""
import json
import sys
import traceback

from .session import RuleError, Session

PROTOCOL = 1


def serve(stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    session = None

    def reply(d):
        stdout.write(json.dumps(d, ensure_ascii=False) + "\n")
        stdout.flush()

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            cmd = msg.get("cmd")
            if cmd == "quit":
                reply({"ok": True, "events": []})
                return
            if cmd == "hello":
                reply({"ok": True, "protocol": PROTOCOL, "events": []})
                continue
            if cmd == "new":
                session = Session(seed=msg.get("seed", 1), difficulty=msg.get("difficulty", "normal"),
                                  goal=msg.get("goal"))
                msg = {"cmd": "state"}
            elif cmd == "load":
                if session is None:
                    session = Session(seed=0)
            elif session is None:
                reply({"ok": False, "error": "要先送 new 或 load。", "events": []})
                continue
            reply(session.handle(msg))
        except RuleError as e:
            reply({"ok": False, "error": str(e), "events": []})
        except Exception:                     # 規則出錯不能讓畫面端卡住等回覆
            reply({"ok": False, "error": "規則端出錯", "trace": traceback.format_exc(), "events": []})


if __name__ == "__main__":
    for s in (sys.stdin, sys.stdout):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    serve()
