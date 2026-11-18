# -*- coding: utf-8 -*-
"""HD-2D 版共用的數值。都是起始值，要實際玩過才定。"""

# ---- 時間：走路照距離算（設計文件第三節）
UNITS_PER_MINUTE = 2.5      # 每走 2.5 個場景單位過 1 分鐘
RUN_STAMINA_PER_UNIT = 0.5  # 跑步每個單位扣的體力

# ---- 聲音：規則算出「多大聲」，畫面拿半徑去找誰聽得到（設計文件第四節）
# 音量和文字版的噪音值同一個刻度：0.5 小、1 中小、2 中、3 大、4 以上是槍聲
NOISE_RADIUS = [(0.0, 0.0), (0.25, 1.5), (0.5, 3.0), (1.0, 5.0), (2.0, 8.0), (3.0, 12.0), (4.0, 25.0), (5.0, 40.0)]

# 探索時每個動作的音量
ACTION_NOISE = {
    "walk": 0.25,
    "run": 2.0,
    "door": 0.5,
    "door_slam": 1.0,
    "search": 0.5,
    "pry": 3.0,
    "glass": 3.0,
    "topple": 3.0,
}


def noise_radius(amount: float) -> float:
    """音量換成聽得到的半徑（場景單位），在表上的兩點之間線性內插。"""
    if amount <= 0:
        return 0.0
    prev_a, prev_r = NOISE_RADIUS[0]
    for a, r in NOISE_RADIUS[1:]:
        if amount <= a:
            return round(prev_r + (r - prev_r) * (amount - prev_a) / (a - prev_a), 2)
        prev_a, prev_r = a, r
    return NOISE_RADIUS[-1][1]


def walk_noise(base: float, companions: int, fatigue: float) -> float:
    """腳步聲：隊友越多越大聲，很累的時候拖著腳也比較吵。"""
    return round(base * (1 + 0.25 * companions) * (1.3 if fatigue > 80 else 1.0), 2)


# ---- 距離帶
BAND_NAME = {1: "貼身", 2: "近", 3: "中", 4: "遠"}


def band_from_distance(units: float) -> int:
    """開戰那一刻的實際距離換成距離帶（設計文件第四節「即時和回合怎麼接起來」）。"""
    if units <= 1.5:
        return 1
    if units <= 3.5:
        return 2
    if units <= 6.5:
        return 3
    return 4
