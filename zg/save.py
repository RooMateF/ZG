# -*- coding: utf-8 -*-
"""存檔與傳承。"""
import json
import os

from .state import Game, to_dict, from_dict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE = os.path.join(HERE, "save.json")
META = os.path.join(HERE, "meta.json")


def save_game(g: Game, path: str = SAVE):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(to_dict(g), f, ensure_ascii=False)
    os.replace(tmp, path)


def load_game(path: str = SAVE):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return from_dict(json.load(f))


def delete_save(path: str = SAVE):
    if os.path.exists(path):
        os.remove(path)


def load_meta(path: str = META) -> dict:
    if not os.path.exists(path):
        return {"deaths": [], "known_rooms": [], "known_traits": [], "runs": 0, "wins": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_meta(meta: dict, path: str = META):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


def record_run(g: Game, meta: dict):
    meta["runs"] = meta.get("runs", 0) + 1
    known = set(meta.get("known_rooms", []))
    known.update(r.id for r in g.rooms.values() if r.visited)
    meta["known_rooms"] = sorted(known)
    traits = set(meta.get("known_traits", []))
    traits.update(n.name for n in g.npcs if n.intro_seen)
    meta["known_traits"] = sorted(traits)
    if g.over == "abandon":
        return meta
    meta["last"] = {"ending": g.over, "day": g.day, "goal": g.goal}
    if g.over in ("dead", "infection"):
        meta.setdefault("deaths", []).append({
            "day": g.day, "room": g.room, "cause": g.over,
            "items": [it.name for it in g.player.inv],
        })
    else:
        meta.setdefault("wins", []).append({"day": g.day, "ending": g.over, "goal": g.goal})
    return meta
