"""
app.py — Streamlit 大樂透智能選號儀表板
執行方式: streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import pandas as pd
import streamlit as st

# 確保可以 import src 套件
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.engine import EnhancedLottoAnalyzer, LottoConfig, RandomForestPredictor
from src.scraper import DATA_PATH, load_history
from src.utils import (
    backtest_combo_hits,
    compute_big_small_stats,
    compute_missing_periods,
    compute_overfrequent_numbers,
    compute_streak_numbers,
    compute_sum_stats,
    simulate_roi,
)

# ── 中文字型設定（避免 matplotlib 亂碼）─────────────────────
def _setup_chinese_font():
    """嘗試設定中文字型；若無可用中文字型，退回英文標題。"""
    candidates = ["Microsoft JhengHei", "Microsoft YaHei", "SimHei", "Noto Sans CJK TC"]
    for name in candidates:
        if any(name.lower() in f.name.lower() for f in fm.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            return True
    plt.rcParams["font.family"] = "DejaVu Sans"
    return False

HAS_CN_FONT = _setup_chinese_font()

# ──────────────────────────────────────────────
# 資料載入（快取，避免每次點選都重新讀檔）
# ──────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_data() -> list:
    return load_history(DATA_PATH)


# ──────────────────────────────────────────────
# 頁面設定
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="台灣大樂透智能選號系統",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 台灣大樂透智能選號系統")
st.caption("資料驅動 · 三層池管理 · 隨機森林 ML 預測")

# ──────────────────────────────────────────────
# 側邊欄控制
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 參數設定")

    num_groups = st.number_input(
        "生成組數", min_value=1, max_value=10, value=6, step=1
    )

    hot_weight = st.slider(
        "冷熱策略權重",
        min_value=1, max_value=10, value=5,
        help="1 = 偏向冷門號，10 = 偏向熱門號，5 = 中性平衡",
    )

    excluded_nums = st.multiselect(
        "手動排除號碼",
        options=list(range(1, 50)),
        default=[],
        help="選擇不希望出現在推薦組合中的號碼",
    )

    st.divider()
    st.subheader("🔄 資料更新")
    if st.button("立即更新資料"):
        with st.spinner("爬取台彩最新資料中..."):
            try:
                from src.scraper import incremental_update
                added = incremental_update()
                if added > 0:
                    st.success(f"已新增 {added} 期資料！")
                    st.cache_data.clear()
                else:
                    st.info("資料已是最新，無需更新。")
            except Exception as e:
                st.error(f"更新失敗：{e}")

    st.divider()
    st.caption(f"資料路徑：`{DATA_PATH}`")

# ──────────────────────────────────────────────
# 主體
# ──────────────────────────────────────────────
history = load_data()

if not history:
    st.warning(
        "歷史資料為空。請先點選側邊欄「立即更新資料」下載資料，"
        "或手動將 CSV 放置於 `data/lotto_history.csv`。"
    )
    st.stop()

# ── 邊界保護 ───────────────────────────────────
if len(excluded_nums) > 43:
    st.warning(
        f"⚠️ 您已排除 {len(excluded_nums)} 個號碼（上限 43 個），"
        "可選號碼不足 6 個，請減少排除數量。"
    )
    st.stop()

st.info(f"已載入 **{len(history)}** 期歷史資料 | 最近一期: {history[-1] if history else 'N/A'}")

# ──────────────────────────────────────────────
# 下期選號參考指標
# ──────────────────────────────────────────────
_streak_nums      = compute_streak_numbers(history, streak=3)
_overfreq_nums    = compute_overfrequent_numbers(history, window=10, z_threshold=1.5)
_sum_stats        = compute_sum_stats(history, periods=50)
_bs_stats         = compute_big_small_stats(history, periods=50)

# 合併建議排除：連續出現 + 近期過熱（去重排序）
_suggested_remove = sorted(set(_streak_nums) | set(_overfreq_nums))

# 長遺漏號碼：遺漏期數 > 15，依遺漏期數由高到低排序
_missing_data = compute_missing_periods(history)
_long_missing = sorted(
    [(n, m) for n, m in _missing_data.items() if m > 15],
    key=lambda x: -x[1],
)

# ── 建議排除號碼橫幅 ─────────────────────────
st.markdown("---")
st.markdown("### 🚫 建議排除號碼")
_excl_cols = st.columns([2, 3])
with _excl_cols[0]:
    st.markdown("**① 連續 3 期出現**")
    st.caption("近 3 期每期都有開出，可能進入冷卻期")
    if _streak_nums:
        st.warning("　".join(f"`{n:02d}`" for n in _streak_nums))
    else:
        st.success("無（近 3 期無號碼連續出現）")

    st.markdown("**② 近 10 期過熱**")
    st.caption("出現頻率超過統計均值 +1.5σ（異常偏高）")
    if _overfreq_nums:
        st.warning("　".join(f"`{n:02d}`" for n in _overfreq_nums))
    else:
        st.success("無（近期無號碼過於頻繁）")

    st.markdown("**③ 長遺漏號碼（> 15 期未出現）**")
    st.caption("長期未出現，統計規律偏離，建議暫時迴避")
    if _long_missing:
        # 顯示：號碼(遺漏期數)，遺漏最多排最前
        st.warning("　".join(f"`{n:02d}`({m}期)" for n, m in _long_missing))
    else:
        st.success("無（所有號碼遺漏均在 15 期以內）")

with _excl_cols[1]:
    st.markdown("**📋 綜合建議排除清單**（①＋②＋③聯集）")
    _suggested_remove_all = sorted(
        set(_suggested_remove) | {n for n, _ in _long_missing}
    )
    if _suggested_remove_all:
        badge_html = " ".join(
            f'<span style="background:#e74c3c;color:white;padding:3px 8px;'
            f'border-radius:12px;font-weight:bold;margin:2px;display:inline-block">'
            f'{n:02d}</span>'
            for n in _suggested_remove_all
        )
        st.markdown(badge_html, unsafe_allow_html=True)
        st.caption(
            f"共 {len(_suggested_remove_all)} 個號碼建議迴避，"
            "可複製至側邊欄「手動排除號碼」欄位使用。"
        )
    else:
        st.success("目前無建議排除號碼，所有號碼可正常使用。")

# ── 選號參考指標 ─────────────────────────────
with st.expander("📊 下期選號參考指標", expanded=False):
    ref_c1, ref_c2, ref_c3 = st.columns(3)

    with ref_c1:
        st.markdown("#### 📐 和值參考範圍")
        st.caption("近 50 期統計，建議選號落在此區間")
        st.metric("Q25 ～ Q75", f"{int(_sum_stats['q25'])} ～ {int(_sum_stats['q75'])}")
        st.caption(f"歷史均值：{_sum_stats['mean']:.1f}　標準差：{_sum_stats['std']:.1f}")

    with ref_c2:
        st.markdown("#### ⚖️ 大小號比例參考")
        st.caption("近 50 期平均大小號分佈（小號 ≤25，大號 >25）")
        col_s, col_b = st.columns(2)
        col_s.metric("小號(≤25)", f"{_bs_stats['avg_small']} 個")
        col_b.metric("大號(>25)", f"{_bs_stats['avg_big']} 個")
        st.caption(
            f"小號建議範圍：{int(_bs_stats['small_q25'])} ～ {int(_bs_stats['small_q75'])} 個"
        )

    with ref_c3:
        st.markdown("#### 🔢 連號規則說明")
        st.caption("系統自動套用以下連號過濾規則")
        st.success("✅ **允許**：最多 1 組二連號（加分）")
        st.error("❌ **自動排除**：3 個以上連號（如 12-13-14）")

# ──────────────────────────────────────────────
# Tab 佈局
# ──────────────────────────────────────────────
tab_gen, tab_charts, tab_missing, tab_backtest = st.tabs(
    ["🎰 號碼生成", "📊 走勢圖表", "📉 遺漏分析", "🔍 回測模擬"]
)

# ═══════════════════════════════════════════════
# Tab 1：號碼生成
# ═══════════════════════════════════════════════
with tab_gen:
    st.subheader("推薦號碼組合")

    col_gen, col_ml = st.columns([2, 1])

    with col_gen:
        if st.button("🎯 生成推薦號碼", type="primary", use_container_width=True):
            with st.spinner(f"正在分析 {len(history)} 期資料並生成 {num_groups} 組號碼..."):
                cfg = LottoConfig(min_score=6)
                analyzer = EnhancedLottoAnalyzer(
                    history=history,
                    config=cfg,
                    excluded=excluded_nums,
                )
                # 將 slider 1-10 對應到 0.2-2.0 的熱號權重
                hw = hot_weight / 5.0
                results = analyzer.generate_enhanced(groups=int(num_groups), hot_weight=hw)

            st.success(f"成功生成 {len(results)} 組推薦號碼！")

            # 組合結果表格
            rows = []
            for i, r in enumerate(results, 1):
                nums_str = "  ".join(f"**{n:02d}**" for n in r.numbers)
                rows.append({
                    "組別": f"第 {i} 組",
                    "號碼": " | ".join(f"{n:02d}" for n in r.numbers),
                    "分數": r.score,
                    "和值": r.sum_value,
                    "連號組": r.consecutive_pairs,
                    "區段覆蓋": r.section_hits,
                    "夥伴對": r.companion_pair_count,
                })

            df_result = pd.DataFrame(rows)
            st.dataframe(
                df_result,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "分數": st.column_config.ProgressColumn(
                        "分數", min_value=0, max_value=35
                    )
                },
            )

            # 存入 session_state 供回測使用
            st.session_state["last_results"] = [r.numbers for r in results]

    with col_ml:
        st.subheader("🤖 ML 預測熱門號")
        if st.button("執行隨機森林預測", use_container_width=True):
            with st.spinner("訓練 49 個隨機森林模型..."):
                rf = RandomForestPredictor()
                rf.train(history)
                top_nums = rf.predict_top_n(n=10)
            st.success("預測完成！")
            st.write("**ML 推薦熱門號碼（由高到低）：**")
            cols = st.columns(5)
            for i, n in enumerate(top_nums):
                cols[i % 5].metric(f"第 {i+1} 名", f"{n:02d}")


# ═══════════════════════════════════════════════
# Tab 2：走勢圖表
# ═══════════════════════════════════════════════
with tab_charts:
    col_c1, col_c2 = st.columns(2)

    # ── 近 50 期和值走勢圖 ──────────────────────
    with col_c1:
        st.subheader("近 50 期和值走勢")
        recent = history[-50:]
        sums = [sum(draw) for draw in recent]
        fig1, ax1 = plt.subplots(figsize=(7, 4))
        ax1.plot(range(1, len(sums)+1), sums, marker="o", markersize=3,
                 linewidth=1.5, color="#1f77b4")
        mean_val = np.mean(sums)
        ax1.axhline(mean_val, color="red", linestyle="--", linewidth=1,
                    label=f"Mean={mean_val:.1f}")
        ax1.set_xlabel("Period (recent →)" if not HAS_CN_FONT else "期次（由舊到新）")
        ax1.set_ylabel("Sum" if not HAS_CN_FONT else "和值")
        ax1.set_title("Sum Trend (Last 50)" if not HAS_CN_FONT else "近 50 期和值走勢")
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        st.pyplot(fig1)
        plt.close(fig1)

    # ── 號碼出現頻率長條圖 ──────────────────────
    with col_c2:
        st.subheader("號碼出現頻率（近 100 期）")
        recent100 = history[-100:]
        freq = {n: 0 for n in range(1, 50)}
        for draw in recent100:
            for n in draw:
                freq[n] = freq.get(n, 0) + 1

        nums = list(range(1, 50))
        counts = [freq[n] for n in nums]
        colors = ["#e74c3c" if c >= np.percentile(counts, 75)
                  else "#3498db" if c <= np.percentile(counts, 25)
                  else "#95a5a6" for c in counts]

        fig2, ax2 = plt.subplots(figsize=(14, 4))
        ax2.bar(nums, counts, color=colors, edgecolor="white", linewidth=0.5)
        ax2.set_xlabel("Number" if not HAS_CN_FONT else "號碼")
        ax2.set_ylabel("Count" if not HAS_CN_FONT else "出現次數")
        ax2.set_title(
            "Number Frequency (Last 100)" if not HAS_CN_FONT else "號碼出現頻率（近 100 期）"
        )
        ax2.set_xticks(nums[::5])
        # 圖例說明
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor="#e74c3c", label="Hot (top 25%)"),
            Patch(facecolor="#3498db", label="Cold (bottom 25%)"),
            Patch(facecolor="#95a5a6", label="Normal"),
        ]
        ax2.legend(handles=legend_elements, loc="upper right")
        ax2.grid(True, alpha=0.3, axis="y")
        st.pyplot(fig2)
        plt.close(fig2)


# ═══════════════════════════════════════════════
# Tab 3：遺漏分析
# ═══════════════════════════════════════════════
with tab_missing:
    st.subheader("號碼遺漏期數分析")

    missing = compute_missing_periods(history)
    df_missing = pd.DataFrame([
        {"號碼": n, "遺漏期數": m,
         "狀態": "🔴 長遺漏(>15)" if m > 15 else "🟡 中遺漏(6-15)" if m >= 6 else "🟢 短遺漏(≤5)"}
        for n, m in sorted(missing.items())
    ])

    col_m1, col_m2, col_m3 = st.columns(3)
    short_cnt = sum(1 for m in missing.values() if m <= 5)
    med_cnt = sum(1 for m in missing.values() if 6 <= m <= 15)
    long_cnt = sum(1 for m in missing.values() if m > 15)
    col_m1.metric("🟢 短遺漏（≤5期）", short_cnt)
    col_m2.metric("🟡 中遺漏（6-15期）", med_cnt)
    col_m3.metric("🔴 長遺漏（>15期）", long_cnt)

    st.dataframe(
        df_missing,
        use_container_width=True,
        hide_index=True,
        column_config={
            "遺漏期數": st.column_config.ProgressColumn(
                "遺漏期數", min_value=0, max_value=max(missing.values(), default=1)
            )
        },
    )

    # 視覺化遺漏熱力條
    st.subheader("遺漏熱力圖")
    missing_arr = np.array([[missing.get(n, 0) for n in range(1, 50)]])
    fig3, ax3 = plt.subplots(figsize=(14, 1.5))
    im = ax3.imshow(missing_arr, cmap="RdYlGn_r", aspect="auto")
    ax3.set_xticks(range(49))
    ax3.set_xticklabels(range(1, 50), fontsize=7)
    ax3.set_yticks([])
    ax3.set_title(
        "Missing Period Heatmap (red=long, green=short)"
        if not HAS_CN_FONT
        else "遺漏期數熱力圖（紅=長遺漏，綠=短遺漏）"
    )
    plt.colorbar(im, ax=ax3, orientation="horizontal", pad=0.3, shrink=0.5)
    st.pyplot(fig3)
    plt.close(fig3)


# ═══════════════════════════════════════════════
# Tab 4：回測模擬
# ═══════════════════════════════════════════════
with tab_backtest:
    st.subheader("歷史回測與 ROI 模擬")

    if "last_results" not in st.session_state:
        st.info("請先在「號碼生成」頁面生成號碼，再執行回測。")
    else:
        results_nums = st.session_state["last_results"]
        periods = st.slider("回測期數", min_value=10, max_value=200, value=100, step=10)

        if st.button("執行回測", type="primary"):
            with st.spinner("回測中..."):
                rows = []
                for i, combo in enumerate(results_nums, 1):
                    hits = backtest_combo_hits(combo, history, periods)
                    rows.append({
                        "組別": f"第 {i} 組",
                        "號碼": " | ".join(f"{n:02d}" for n in combo),
                        "玖獎(3中/100)": hits["3?"],
                        "陸獎(4中/800)": hits["4?"],
                        "肆獎(5中/2萬)": hits["5?"],
                        "貳獎(6中/估算)": hits["6?"],
                    })

                df_bt = pd.DataFrame(rows)
                st.dataframe(df_bt, use_container_width=True, hide_index=True)

                # ROI 模擬
                roi = simulate_roi(results_nums, history, periods)
                col_r1, col_r2, col_r3 = st.columns(3)
                col_r1.metric("總投入", f"NT$ {roi['total_cost']:,}")
                col_r2.metric("總回收", f"NT$ {roi['total_reward']:,}")
                col_r3.metric(
                    "ROI",
                    f"{roi['roi_pct']:+.1f}%",
                    delta=f"淨損益 {roi['net_profit']:+,}",
                )

                st.caption(
                    "⚠️ 本模擬僅供娛樂參考，大樂透為機率事件，頭獎金額以實際彩金為準。"
                )
