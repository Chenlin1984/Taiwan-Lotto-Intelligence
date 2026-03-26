"""
scraper.py — 台彩大樂透爬蟲
從台彩官方 JSON API 抓取歷史開獎資料，並增量更新 CSV。
直接執行：python src/scraper.py           （增量更新）
         python src/scraper.py --backfill 36  （補抓過去 36 個月）
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests

# ── 路徑設定 ────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "lotto_history.csv"

CSV_COLUMNS = ["期別", "日期", "第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "特別號"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# 台彩大樂透 JSON API
# 正確格式：?period&month=YYYY-MM&pageSize=31
JSON_API = "https://api.taiwanlottery.com/TLCAPIWeB/Lottery/Lotto649Result"


# ──────────────────────────────────────────────
# 1. 抓取單月資料
# ──────────────────────────────────────────────
def fetch_month(year: int, month: int) -> List[dict]:
    """
    抓取指定年月的大樂透開獎記錄。
    大樂透每月最多 5 次開獎（週二/週五），pageSize=31 足夠覆蓋。
    """
    try:
        resp = requests.get(
            JSON_API,
            params={"period": "", "month": f"{year}-{month:02d}", "pageSize": 31},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        items = (data.get("content") or {}).get("lotto649Res") or []
        records = [r for item in items if (r := _parse_item(item)) is not None]
        print(f"[scraper] {year}-{month:02d}：取得 {len(records)} 筆")
        return records
    except Exception as e:
        print(f"[scraper] {year}-{month:02d} 失敗: {e}", file=sys.stderr)
        return []


def _parse_item(item: dict) -> Optional[dict]:
    """解析 API 單筆記錄。"""
    try:
        draw_no = str(item.get("period", "")).strip()
        raw_date = str(item.get("lotteryDate", ""))[:10]   # "YYYY-MM-DD"
        nums = item.get("drawNumberSize") or []            # [n1,n2,n3,n4,n5,n6,special]
        if len(nums) < 7 or not draw_no:
            return None
        return {
            "期別": draw_no,
            "日期": raw_date,
            "第1球": int(nums[0]),
            "第2球": int(nums[1]),
            "第3球": int(nums[2]),
            "第4球": int(nums[3]),
            "第5球": int(nums[4]),
            "第6球": int(nums[5]),
            "特別號": int(nums[6]),
        }
    except Exception:
        return None


# ──────────────────────────────────────────────
# 2. 補抓歷史資料（多個月份）
# ──────────────────────────────────────────────
def fetch_history_months(months: int = 36) -> List[dict]:
    """
    從今日往前抓取 months 個月的開獎資料。
    months=36 約等於三年歷史資料。
    """
    today = date.today()
    records: List[dict] = []
    for i in range(months):
        # 計算目標年月（往前推 i 個月）
        total_months = today.month - 1 - i
        y = today.year + total_months // 12
        m = total_months % 12 + 1
        records.extend(fetch_month(y, m))
        time.sleep(0.3)
    return records


# ──────────────────────────────────────────────
# 3. 增量更新（只抓最新幾個月）
# ──────────────────────────────────────────────
def fetch_latest_draws(n_months: int = 3) -> List[dict]:
    """抓取最新 n_months 個月，用於日常增量更新。"""
    today = date.today()
    records: List[dict] = []
    for i in range(n_months):
        total_months = today.month - 1 - i
        y = today.year + total_months // 12
        m = total_months % 12 + 1
        records.extend(fetch_month(y, m))
        time.sleep(0.3)
    return records


# ──────────────────────────────────────────────
# 4. 寫入 CSV（通用）
# ──────────────────────────────────────────────
def _save_records(new_records: List[dict], csv_path: Path) -> int:
    """
    將新記錄合併進現有 CSV，去重排序後寫回。
    回傳實際新增筆數。
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    if csv_path.exists() and csv_path.stat().st_size > 0:
        existing_df = pd.read_csv(csv_path, dtype={"期別": str})
    else:
        existing_df = pd.DataFrame(columns=CSV_COLUMNS)

    existing_count = len(existing_df)
    new_df = pd.DataFrame(new_records, columns=CSV_COLUMNS)
    merged = pd.concat([existing_df, new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["期別"])
    merged = merged.sort_values("期別").reset_index(drop=True)
    merged.to_csv(csv_path, index=False, encoding="utf-8-sig")

    added = len(merged) - existing_count
    print(f"[scraper] 新增 {added} 筆，CSV 共 {len(merged)} 筆")
    return added


# ──────────────────────────────────────────────
# 5. 增量更新（對外介面，供 app.py 呼叫）
# ──────────────────────────────────────────────
def incremental_update(csv_path: Path = DATA_PATH) -> int:
    """
    增量更新：只抓最近 3 個月，補充新期號。
    供 Streamlit app 側邊欄「立即更新」按鈕使用。
    """
    records = fetch_latest_draws(n_months=3)
    if not records:
        print("[scraper] 無法取得新資料")
        return 0
    return _save_records(records, Path(csv_path))


# ──────────────────────────────────────────────
# 6. 補抓歷史（三年）
# ──────────────────────────────────────────────
def backfill(months: int = 36, csv_path: Path = DATA_PATH) -> int:
    """補抓過去 months 個月的全部歷史資料。"""
    print(f"[scraper] 開始補抓過去 {months} 個月歷史資料...")
    records = fetch_history_months(months)
    if not records:
        print("[scraper] 無法取得任何資料")
        return 0
    return _save_records(records, Path(csv_path))


# ──────────────────────────────────────────────
# 7. 載入歷史（供 engine.py / app.py 使用）
# ──────────────────────────────────────────────
def load_history(csv_path: Path = DATA_PATH) -> List[List[int]]:
    """
    從 CSV 載入大樂透歷史資料，回傳 List[List[int]]。
    每個子列表為 [第1球..第6球]（不含特別號，已排序）。
    """
    csv_path = Path(csv_path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        print("[scraper] CSV 不存在，回傳空歷史", file=sys.stderr)
        return []

    df = pd.read_csv(csv_path, dtype={"期別": str})
    num_cols = ["第1球", "第2球", "第3球", "第4球", "第5球", "第6球"]
    history = []
    for _, row in df.iterrows():
        try:
            nums = [int(row[c]) for c in num_cols]
            if all(1 <= n <= 49 for n in nums):
                history.append(sorted(nums))
        except (ValueError, KeyError):
            continue
    return history


# ──────────────────────────────────────────────
# 直接執行
# ──────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="大樂透資料更新工具")
    parser.add_argument(
        "--backfill", type=int, metavar="MONTHS",
        help="補抓過去 N 個月的歷史資料（預設 36 個月 = 三年）"
    )
    args = parser.parse_args()

    if args.backfill is not None:
        added = backfill(months=args.backfill)
    else:
        added = incremental_update()

    sys.exit(0 if added >= 0 else 1)
