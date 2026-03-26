"""
utils.py — 工具函式與常數
大樂透分析系統共用工具
"""
from __future__ import annotations

import itertools
from collections import Counter, defaultdict
from typing import Dict, List, Set, Tuple

import numpy as np
import pandas as pd

# ──────────────────────────────────────────────
# 常數
# ──────────────────────────────────────────────
PRIMES: Set[int] = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47}

PRIZE_TABLE: Dict[str, int] = {
    "6?": 8_000_000,   # 頭獎（萬元起跳，這裡用固定值示意）
    "5?": 20_000,
    "4?": 2_000,
    "3?": 400,
}

COST_PER_COMBO: int = 50  # 每注 50 元


# ──────────────────────────────────────────────
# 1. 號碼配對分析
# ──────────────────────────────────────────────
def build_partner_map(
    history: List[List[int]],
    top_n: int = 150,
) -> defaultdict:
    """
    統計歷史資料中每個號碼最常搭配的夥伴號碼，回傳 top_n 對的 mapping。

    Returns
    -------
    defaultdict[int, set]
        key: 號碼, value: 常搭配的夥伴號碼集合
    """
    pair_counter: Counter = Counter()
    for draw in history:
        for a, b in itertools.combinations(sorted(draw), 2):
            pair_counter[(a, b)] += 1

    partner_map: defaultdict = defaultdict(set)
    for (a, b), _ in pair_counter.most_common(top_n):
        partner_map[a].add(b)
        partner_map[b].add(a)
    return partner_map


# ──────────────────────────────────────────────
# 2. 回測命中分析
# ──────────────────────────────────────────────
def backtest_combo_hits(
    combo: List[int],
    history: List[List[int]],
    periods: int = 100,
) -> Dict[str, int]:
    """
    統計 combo 在最近 periods 期內各命中等級的次數。

    Returns
    -------
    dict  {"3?": n, "4?": n, "5?": n, "6?": n}
    """
    result = {"3?": 0, "4?": 0, "5?": 0, "6?": 0}
    combo_set = set(combo)
    for draw in history[-periods:]:
        hits = len(combo_set & set(draw))
        if hits >= 3:
            result[f"{hits}?"] += 1
    return result


# ──────────────────────────────────────────────
# 3. ROI 模擬
# ──────────────────────────────────────────────
def simulate_roi(
    results: List[List[int]],
    history: List[List[int]],
    periods: int = 100,
) -> Dict[str, float]:
    """
    對多組號碼模擬 ROI（假設每期每注都投入）。

    Returns
    -------
    dict  {"total_cost": ..., "total_reward": ..., "roi_pct": ...}
    """
    total_cost = len(results) * COST_PER_COMBO * periods
    total_reward = 0
    for combo in results:
        hits_summary = backtest_combo_hits(combo, history, periods)
        for key, count in hits_summary.items():
            total_reward += PRIZE_TABLE.get(key, 0) * count

    roi_pct = (total_reward - total_cost) / total_cost * 100 if total_cost else 0
    return {
        "total_cost": total_cost,
        "total_reward": total_reward,
        "roi_pct": round(roi_pct, 2),
        "net_profit": total_reward - total_cost,
    }


# ──────────────────────────────────────────────
# 4. 尾數分佈分析
# ──────────────────────────────────────────────
def analyze_tail_distribution(
    history: List[List[int]],
    periods: int = 500,
) -> Counter:
    """
    統計最近 periods 期每個末位數字（0~9）的出現頻率。
    用於驗證生成組合的末位多樣性。
    """
    counter: Counter = Counter()
    for draw in history[-periods:]:
        for n in draw:
            counter[n % 10] += 1
    return counter


# ──────────────────────────────────────────────
# 5. ML 特徵編碼
# ──────────────────────────────────────────────
def encode_ml_one_hot(
    history: List[List[int]],
    max_periods: int = 200,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    將歷史資料編碼為 one-hot 矩陣，供隨機森林訓練使用。

    X[i]  = 第 i 期的 49 維 one-hot 向量（作為特徵，預測下一期）
    y[i]  = 第 i+1 期的 49 維 one-hot 向量（作為標籤）

    Returns
    -------
    X : np.ndarray  shape (n-1, 49)
    y : np.ndarray  shape (n-1, 49)
    """
    data = history[-max_periods:]
    n = len(data)
    X = np.zeros((n, 49), dtype=np.float32)
    for i, draw in enumerate(data):
        for num in draw:
            if 1 <= num <= 49:
                X[i, num - 1] = 1.0
    # X[i] 預測 X[i+1]
    return X[:-1], X[1:]


# ──────────────────────────────────────────────
# 6. 遺漏期數計算
# ──────────────────────────────────────────────
def compute_missing_periods(history: List[List[int]]) -> Dict[int, int]:
    """
    計算每個號碼（1-49）距今已遺漏幾期。
    遺漏 0 表示最近一期有出現。
    """
    missing = {n: 0 for n in range(1, 50)}
    for i, draw in enumerate(reversed(history)):
        for n in range(1, 50):
            if n not in draw:
                if missing[n] == 0:
                    # 還沒開始計，從第 1 期未出現算起
                    missing[n] = i + 1
    # 最後一期出現的號碼遺漏期數為 0
    if history:
        for n in history[-1]:
            missing[n] = 0
    return missing


# ──────────────────────────────────────────────
# 7. 近 N 期冷熱加權
# ──────────────────────────────────────────────
def compute_frequency_weight(
    history: List[List[int]],
    periods: int = 30,
) -> Dict[int, float]:
    """
    計算每個號碼在近 periods 期內的出現比例（0.0~1.0）。
    熱號比例高，冷號比例低。
    """
    counter: Counter = Counter()
    recent = history[-periods:]
    for draw in recent:
        for n in draw:
            counter[n] += 1
    total = len(recent) if recent else 1
    return {n: counter.get(n, 0) / total for n in range(1, 50)}


# ──────────────────────────────────────────────
# 8. 和值計算
# ──────────────────────────────────────────────
def compute_sum_stats(history: List[List[int]], periods: int = 50) -> Dict[str, float]:
    """回傳近 periods 期和值的統計摘要（mean, std, q25, q75）。"""
    sums = [sum(draw) for draw in history[-periods:]]
    if not sums:
        return {"mean": 150, "std": 30, "q25": 120, "q75": 180}
    arr = np.array(sums)
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "q25": float(np.percentile(arr, 25)),
        "q75": float(np.percentile(arr, 75)),
    }
