"""
engine.py — 核心分析引擎
大樂透三層池管理、多因子評分、隨機森林預測
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from .utils import (
    PRIMES,
    build_partner_map,
    compute_frequency_weight,
    compute_missing_periods,
    compute_sum_stats,
    encode_ml_one_hot,
)


# ──────────────────────────────────────────────
# 設定 Dataclass
# ──────────────────────────────────────────────
@dataclass
class LottoConfig:
    num_range: Tuple[int, int] = (1, 49)
    combo_size: int = 6
    min_score: int = 8
    max_attempts: int = 50_000
    companion_pairs_period: int = 500
    companion_pairs_top: int = 150
    adaptive_mode: bool = True          # 嘗試失敗後放寬條件
    vector_analysis_enabled: bool = True
    enable_diversity_check: bool = True
    enable_backtest: bool = True
    enable_roi_simulation: bool = True


# ──────────────────────────────────────────────
# 結果 Dataclass
# ──────────────────────────────────────────────
@dataclass
class ComboResult:
    numbers: List[int]
    score: float = 0.0
    sum_value: int = 0
    consecutive_pairs: int = 0          # 二連號組數
    section_hits: int = 0               # 覆蓋區段數
    companion_pair_count: int = 0
    backtest_hits: Dict[str, int] = field(default_factory=dict)
    prediction_match: bool = False
    diversity_score: float = 0.0
    tail_distribution: List[int] = field(default_factory=list)


# ──────────────────────────────────────────────
# 三層號碼池管理員
# ──────────────────────────────────────────────
class MultiLevelNumberPoolManager:
    """
    三層循環池管理：
      Pool1 (精選池) → 用畢移入 Pool2 → 用畢移入 Pool3
    安全機制：任一層不足 combo_size 時自動補充。
    """

    def __init__(self, pool1: List[int], config: LottoConfig):
        self.config = config
        self.pool1: List[int] = list(pool1)
        self.pool2: List[int] = []
        self.pool3: List[int] = []
        self._used1: List[int] = []
        self._used2: List[int] = []

    # ── 內部：取得各層可用號碼 ──────────────────
    def _available1(self) -> List[int]:
        return list(self.pool1)

    def _available2(self) -> List[int]:
        return list(self.pool2)

    def _available3(self) -> List[int]:
        return list(self.pool3)

    # ── 觸發循環補充 ────────────────────────────
    def _maybe_recycle(self):
        size = self.config.combo_size
        # [Fix] Pool1 剩餘 ≤ combo_size 時，將已用號碼移入 Pool2
        if len(self.pool1) <= size and self._used1:
            self.pool2.extend(self._used1)
            self._used1.clear()

        # [Fix] Pool2 剩餘 ≤ combo_size 時，將已用號碼移入 Pool3
        if len(self.pool2) <= size and self._used2:
            self.pool3.extend(self._used2)
            self._used2.clear()

    # ── 安全補充：從 1-49 填充至足夠數量 ──────
    def _emergency_refill(self, pool: List[int]) -> List[int]:
        """[Fix] 防崩潰：池不足時從 1-49 自動補充。"""
        all_nums = list(range(1, 50))
        missing_nums = [n for n in all_nums if n not in pool]
        random.shuffle(missing_nums)
        pool = pool + missing_nums
        return pool

    def get(self, n: int = 6) -> List[int]:
        """從可用池取出 n 個號碼（不重複）。"""
        self._maybe_recycle()
        combined = list(dict.fromkeys(
            self._available1() + self._available2() + self._available3()
        ))
        # [Fix] 安全補充
        if len(combined) < n:
            combined = self._emergency_refill(combined)
        return random.sample(combined, min(n, len(combined)))

    def confirm_use(self, numbers: List[int]):
        """標記號碼已被使用，從池中移除並記錄。"""
        for n in numbers:
            if n in self.pool1:
                self.pool1.remove(n)
                self._used1.append(n)
            elif n in self.pool2:
                self.pool2.remove(n)
                self._used2.append(n)
            elif n in self.pool3:
                self.pool3.remove(n)

    def get_status(self) -> Dict[str, int]:
        return {
            "pool1_available": len(self.pool1),
            "pool2_available": len(self.pool2),
            "pool3_available": len(self.pool3),
            "used1": len(self._used1),
            "used2": len(self._used2),
        }


# ──────────────────────────────────────────────
# 區段向量分析（10 區段，每段 5 號）
# ──────────────────────────────────────────────
class SectionVectorAnalyzer:
    """
    將 1-49 分成 10 區段（1-5, 6-10, ..., 46-49）。
    分析歷史最常見的區段分佈模式。
    """

    NUM_SECTIONS = 10
    SECTION_SIZE = 5

    def __init__(self, history: List[List[int]]):
        self.history = history

    def _section_of(self, n: int) -> int:
        return min((n - 1) // self.SECTION_SIZE, self.NUM_SECTIONS - 1)

    def get_section_vector(self, combo: List[int]) -> Tuple[int, ...]:
        """回傳 10 維二進位向量，命中的區段標 1。"""
        vec = [0] * self.NUM_SECTIONS
        for n in combo:
            vec[self._section_of(n)] = 1
        return tuple(vec)

    def analyze_vector_patterns(self, period: int = 500) -> Counter:
        counter: Counter = Counter()
        for draw in self.history[-period:]:
            counter[self.get_section_vector(draw)] += 1
        return counter

    def get_top_section_vectors(self, period: int = 500, top: int = 150) -> List[Tuple]:
        return [v for v, _ in self.analyze_vector_patterns(period).most_common(top)]

    def check_vector_match(self, combo: List[int], top_vectors: List[Tuple]) -> bool:
        return self.get_section_vector(combo) in top_vectors

    def section_hit_count(self, combo: List[int]) -> int:
        return sum(self.get_section_vector(combo))


# ──────────────────────────────────────────────
# 隨機森林預測器
# ──────────────────────────────────────────────
class RandomForestPredictor:
    """
    49 個獨立 RandomForestClassifier，每個號碼一個。
    特徵：前期 one-hot(49) + 遺漏期數(49) + 近30期冷熱加權(49)
    """

    def __init__(self):
        self._models = {}
        self._is_trained = False

    def train(self, history: List[List[int]]):
        from sklearn.ensemble import RandomForestClassifier

        X_onehot, y = encode_ml_one_hot(history, max_periods=200)
        n = len(history)

        # 額外特徵：遺漏期數 + 冷熱加權（對訓練集每個時間點動態計算）
        missing_feat = np.zeros((len(X_onehot), 49), dtype=np.float32)
        freq_feat = np.zeros((len(X_onehot), 49), dtype=np.float32)

        history_slice = history[-200:] if len(history) > 200 else history
        for i in range(len(X_onehot)):
            sub = history_slice[:i+1]
            mp = compute_missing_periods(sub)
            fw = compute_frequency_weight(sub, periods=30)
            for num in range(1, 50):
                missing_feat[i, num-1] = mp.get(num, 0) / 50.0  # 正規化
                freq_feat[i, num-1] = fw.get(num, 0.0)

        X = np.hstack([X_onehot, missing_feat, freq_feat])  # shape: (n, 147)

        for num in range(1, 50):
            clf = RandomForestClassifier(
                n_estimators=50,
                max_depth=6,
                random_state=42,
                n_jobs=-1,
            )
            clf.fit(X, y[:, num-1])
            self._models[num] = clf

        self._last_X = X[-1:].copy()  # 最後一筆用於預測下一期
        self._is_trained = True

    def predict_top_n(self, n: int = 10) -> List[int]:
        if not self._is_trained:
            return list(range(1, n+1))
        probs = {}
        for num, clf in self._models.items():
            proba = clf.predict_proba(self._last_X)[0]
            # [Fix] 若訓練資料中該號碼從未出現（只有 class 0），則機率為 0
            if 1 in clf.classes_:
                idx = list(clf.classes_).index(1)
                probs[num] = proba[idx]
            else:
                probs[num] = 0.0
        return sorted(probs, key=probs.get, reverse=True)[:n]


# ──────────────────────────────────────────────
# 主分析引擎
# ──────────────────────────────────────────────
class EnhancedLottoAnalyzer:
    """
    大樂透號碼分析與生成主引擎。
    整合三層池、多因子評分、遺漏分析、ML 預測。
    """

    def __init__(
        self,
        history: List[List[int]],
        config: Optional[LottoConfig] = None,
        excluded: Optional[List[int]] = None,
    ):
        self.history = history
        self.config = config or LottoConfig()
        self.excluded: Set[int] = set(excluded or [])
        self._section_analyzer = SectionVectorAnalyzer(history)
        self._partner_map = build_partner_map(
            history, top_n=self.config.companion_pairs_top
        )
        self._sum_stats = compute_sum_stats(history, periods=50)
        self._missing = compute_missing_periods(history)
        self._freq = compute_frequency_weight(history, periods=30)
        self._top_vectors = self._section_analyzer.get_top_section_vectors()
        self._history_sets = [set(d) for d in history]

    # ── 遺漏分析 ───────────────────────────────
    def get_missing_analysis(self) -> Dict[str, List[int]]:
        """將號碼依遺漏期數分成短/中/長期三類。"""
        short, medium, long_ = [], [], []
        for n, m in self._missing.items():
            if n in self.excluded:
                continue
            if m <= 5:
                short.append(n)
            elif m <= 15:
                medium.append(n)
            else:
                long_.append(n)
        return {"short": short, "medium": medium, "long": long_}

    # ── 生成精選池 ─────────────────────────────
    def _build_pool1(self) -> List[int]:
        """
        精選池：熱號 + 中遺漏候選，排除長遺漏與被排除號碼。
        """
        missing_info = self.get_missing_analysis()
        hot = [n for n, f in sorted(self._freq.items(), key=lambda x: -x[1])
               if n not in self.excluded and n not in missing_info["long"]][:20]
        medium = [n for n in missing_info["medium"] if n not in self.excluded]
        short = [n for n in missing_info["short"] if n not in self.excluded]

        pool = list(dict.fromkeys(hot + medium + short))

        # [Fix] 安全：若池不足 30 號，補充未排除的所有號碼
        if len(pool) < 30:
            all_nums = [n for n in range(1, 50) if n not in self.excluded]
            for n in all_nums:
                if n not in pool:
                    pool.append(n)
        return pool

    # ── 連號計數 ───────────────────────────────
    @staticmethod
    def _count_consecutive(combo: List[int]) -> Tuple[int, int]:
        """
        回傳 (二連號組數, 三連號以上組數)。
        用於連號規則判斷。
        """
        s = sorted(combo)
        pairs2 = pairs3 = 0
        i = 0
        while i < len(s) - 1:
            run = 1
            while i + run < len(s) and s[i + run] == s[i] + run:
                run += 1
            if run == 2:
                pairs2 += 1
            elif run >= 3:
                pairs3 += 1
            i += run
        return pairs2, pairs3

    # ── 理性過濾 ───────────────────────────────
    def is_reasonable(self, combo: List[int]) -> bool:
        """
        基本過濾：排除歷史重複、三連號以上、排除號碼、和值範圍。
        """
        combo_set = set(combo)

        # 排除包含被排除號碼
        if combo_set & self.excluded:
            return False

        # 排除歷史已出現組合
        if combo_set in self._history_sets:
            return False

        # [Fix] 連號規則：三連號以上強制排除
        _, trips = self._count_consecutive(combo)
        if trips > 0:
            return False

        # 和值範圍（±1.5 倍標準差）
        s = sum(combo)
        mean = self._sum_stats["mean"]
        std = self._sum_stats["std"]
        if not (mean - 1.5 * std <= s <= mean + 1.5 * std):
            return False

        # 至少覆蓋 3 個區段
        if self._section_analyzer.section_hit_count(combo) < 3:
            return False

        return True

    # ── 多因子評分 ─────────────────────────────
    def score(self, combo: List[int]) -> float:
        """
        多因子評分，滿分約 35 分。
        """
        s = sorted(combo)
        total = 0.0

        # 1. 和值（3 分）
        sv = sum(s)
        q25 = self._sum_stats["q25"]
        q75 = self._sum_stats["q75"]
        if q25 <= sv <= q75:
            total += 3

        # 2. 奇偶分佈（3 分）：奇 3 偶 3 最佳
        odd_count = sum(1 for n in s if n % 2 == 1)
        if odd_count == 3:
            total += 3
        elif odd_count in (2, 4):
            total += 1.5

        # 3. 大小分佈（3 分）：小(≤25) 3 個最佳
        small_count = sum(1 for n in s if n <= 25)
        if small_count == 3:
            total += 3
        elif small_count in (2, 4):
            total += 1.5

        # 4. 熱號命中（4 分）
        hot_top10 = sorted(self._freq, key=self._freq.get, reverse=True)[:10]
        hot_hits = sum(1 for n in s if n in hot_top10)
        total += min(hot_hits * 1.0, 4.0)

        # 5. 質數數量（3 分）：2~3 個最佳
        prime_count = sum(1 for n in s if n in PRIMES)
        if 2 <= prime_count <= 3:
            total += 3
        elif prime_count == 1:
            total += 1

        # 6. 尾數多樣性（3 分）：尾數不重複最佳
        tails = [n % 10 for n in s]
        tail_unique = len(set(tails))
        total += min(tail_unique * 0.5, 3.0)

        # 7. 區段覆蓋（5 分）
        sec_hits = self._section_analyzer.section_hit_count(combo)
        total += min(sec_hits * 0.8, 5.0)

        # 8. 夥伴號碼（3 分）
        pair_count = 0
        for a in s:
            for b in s:
                if a != b and b in self._partner_map.get(a, set()):
                    pair_count += 1
        pair_count //= 2
        total += min(pair_count * 1.0, 3.0)

        # [Fix] 9. 連號加分：1 組二連號 +2；三連號以上已被 is_reasonable 排除
        pairs2, _ = self._count_consecutive(combo)
        if pairs2 == 1:
            total += 2.0

        # 10. 遺漏加分（3 分）：納入 2~3 個中遺漏號碼加分
        medium_missing = [n for n, m in self._missing.items() if 6 <= m <= 15]
        medium_hits = sum(1 for n in s if n in medium_missing)
        total += min(medium_hits * 1.0, 3.0)

        return round(total, 2)

    # ── 生成組合 ───────────────────────────────
    def generate_enhanced(
        self,
        groups: int = 6,
        hot_weight: float = 1.0,
    ) -> List[ComboResult]:
        """
        生成 groups 組號碼，使用三層池管理。

        Parameters
        ----------
        groups    : 要生成的組數
        hot_weight: 1.0=中性；>1.0偏熱號；<1.0偏冷號（調整精選池排序權重）
        """
        pool1_nums = self._build_pool1()

        # 依 hot_weight 重排 pool1
        if hot_weight != 1.0:
            pool1_nums = sorted(
                pool1_nums,
                key=lambda n: self._freq.get(n, 0) * hot_weight,
                reverse=True,
            )

        pool_mgr = MultiLevelNumberPoolManager(pool1_nums, self.config)
        results: List[ComboResult] = []
        seen: List[Set[int]] = list(self._history_sets)

        adaptive = False
        attempts = 0
        while len(results) < groups and attempts < self.config.max_attempts:
            attempts += 1
            candidates = pool_mgr.get(self.config.combo_size)
            if len(candidates) < self.config.combo_size:
                continue
            combo = sorted(candidates)

            # 相似組去重（≥4 個相同號碼）
            too_similar = any(len(set(combo) & s) >= 4 for s in seen[-50:])
            if too_similar:
                continue

            if not self.is_reasonable(combo):
                # adaptive mode：嘗試次數過多時放寬條件
                if self.config.adaptive_mode and attempts > self.config.max_attempts // 2:
                    adaptive = True
                continue

            sc = self.score(combo)
            min_score = (self.config.min_score * 0.7) if adaptive else self.config.min_score
            if sc < min_score:
                continue

            pool_mgr.confirm_use(combo)
            seen.append(set(combo))

            pairs2, _ = self._count_consecutive(combo)
            result = ComboResult(
                numbers=combo,
                score=sc,
                sum_value=sum(combo),
                consecutive_pairs=pairs2,
                section_hits=self._section_analyzer.section_hit_count(combo),
                companion_pair_count=sum(
                    1 for a in combo for b in combo
                    if a != b and b in self._partner_map.get(a, set())
                ) // 2,
            )
            results.append(result)

        # [Fix] 安全：若仍不足，用低分組補齊
        while len(results) < groups:
            fallback = sorted(random.sample(
                [n for n in range(1, 50) if n not in self.excluded], 6
            ))
            pairs2, _ = self._count_consecutive(fallback)
            results.append(ComboResult(
                numbers=fallback,
                score=self.score(fallback),
                sum_value=sum(fallback),
                consecutive_pairs=pairs2,
                section_hits=self._section_analyzer.section_hit_count(fallback),
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:groups]
