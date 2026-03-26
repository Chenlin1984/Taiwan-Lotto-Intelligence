"""
scraper.py — 台彩大樂透爬蟲
從台彩官網抓取歷史開獎資料，並增量更新 CSV。
直接執行此腳本即可更新資料：python src/scraper.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ── 路徑設定 ────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "lotto_history.csv"

CSV_COLUMNS = ["期別", "日期", "第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "特別號"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# 台彩大樂透查詢 API（JSON）
API_URL = "https://www.taiwanlottery.com/lotto/bigLotto/history.aspx"
JSON_API = "https://api.taiwanlottery.com/TLCAPIWeB/Lottery/Lotto649Result"


# ──────────────────────────────────────────────
# 1. 從台彩 API 抓取最新 N 頁資料
# ──────────────────────────────────────────────
def fetch_latest_draws(n_pages: int = 5) -> List[dict]:
    """
    從台彩 JSON API 抓取最新開獎記錄。
    每頁約 30 筆，n_pages=5 可取得約 150 筆。

    Returns
    -------
    List[dict]  每筆含 {期別, 日期, 第1球~第6球, 特別號}
    """
    records = []
    for page in range(1, n_pages + 1):
        try:
            resp = requests.get(
                JSON_API,
                params={"pageNum": page, "pageSize": 30},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            items = (
                data.get("content", {}).get("lotteryList", [])
                or data.get("lotteryList", [])
                or data.get("content", [])
            )

            for item in items:
                row = _parse_api_item(item)
                if row:
                    records.append(row)

            time.sleep(0.5)
        except Exception as e:
            print(f"[scraper] API 第 {page} 頁失敗: {e}", file=sys.stderr)
            break

    # 備用：若 API 失敗，嘗試 HTML 解析
    if not records:
        records = _fetch_html_fallback()

    return records


def _parse_api_item(item: dict) -> Optional[dict]:
    """解析台彩 API 單筆記錄。"""
    try:
        # 台彩 API 欄位名稱（可能隨官網更新而變動）
        draw_no = str(item.get("lotteryNo") or item.get("drawNo") or "")
        draw_date = str(item.get("openDate") or item.get("drawDate") or "")

        nums = (
            item.get("drawNo6") or item.get("numbers") or item.get("winningNums") or []
        )
        if isinstance(nums, str):
            nums = [int(x) for x in nums.split(",") if x.strip()]
        elif isinstance(nums, list):
            nums = [int(x) for x in nums]

        special = int(
            item.get("specialNo") or item.get("bonusNo") or item.get("spNo") or 0
        )

        if len(nums) < 6 or not draw_no:
            return None

        return {
            "期別": draw_no,
            "日期": draw_date,
            "第1球": nums[0],
            "第2球": nums[1],
            "第3球": nums[2],
            "第4球": nums[3],
            "第5球": nums[4],
            "第6球": nums[5],
            "特別號": special,
        }
    except Exception:
        return None


def _fetch_html_fallback() -> List[dict]:
    """備用 HTML 解析，從台彩網頁表格取得最近一頁資料。"""
    records = []
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 尋找包含開獎號碼的表格
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:  # 跳過表頭
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) >= 9:
                    try:
                        records.append({
                            "期別": cols[0],
                            "日期": cols[1],
                            "第1球": int(cols[2]),
                            "第2球": int(cols[3]),
                            "第3球": int(cols[4]),
                            "第4球": int(cols[5]),
                            "第5球": int(cols[6]),
                            "第6球": int(cols[7]),
                            "特別號": int(cols[8]) if cols[8].isdigit() else 0,
                        })
                    except (ValueError, IndexError):
                        continue
            if records:
                break
    except Exception as e:
        print(f"[scraper] HTML 備用解析失敗: {e}", file=sys.stderr)
    return records


# ──────────────────────────────────────────────
# 2. 增量更新 CSV
# ──────────────────────────────────────────────
def incremental_update(csv_path: Path = DATA_PATH) -> int:
    """
    增量更新歷史資料 CSV。
    1. 讀取現有 CSV，取得最後一期期別
    2. 從 API 抓取最新資料
    3. 僅寫入新於最後一期的記錄
    4. 回傳新增筆數

    Returns
    -------
    int  新增筆數（0 表示已是最新）
    """
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # 讀取現有資料
    if csv_path.exists() and csv_path.stat().st_size > 0:
        existing_df = pd.read_csv(csv_path, dtype={"期別": str})
        last_no = existing_df["期別"].iloc[-1] if len(existing_df) else ""
    else:
        existing_df = pd.DataFrame(columns=CSV_COLUMNS)
        last_no = ""

    print(f"[scraper] 現有資料: {len(existing_df)} 期，最後一期: {last_no}")

    # 抓取新資料（多抓幾頁以確保涵蓋最新）
    new_records = fetch_latest_draws(n_pages=10)
    if not new_records:
        print("[scraper] 無法取得新資料")
        return 0

    new_df = pd.DataFrame(new_records, columns=CSV_COLUMNS)

    # 過濾：僅保留期別 > 最後一期
    if last_no:
        new_df = new_df[new_df["期別"] > last_no]

    if new_df.empty:
        print("[scraper] 資料已是最新，無需更新")
        return 0

    # 合併並去重排序
    merged = pd.concat([existing_df, new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["期別"])
    merged = merged.sort_values("期別").reset_index(drop=True)

    merged.to_csv(csv_path, index=False, encoding="utf-8-sig")
    added = len(new_df)
    print(f"[scraper] 成功新增 {added} 期，總計 {len(merged)} 期")
    return added


# ──────────────────────────────────────────────
# 3. 載入歷史資料（供其他模組使用）
# ──────────────────────────────────────────────
def load_history(csv_path: Path = DATA_PATH) -> List[List[int]]:
    """
    從 CSV 載入大樂透歷史資料，回傳 List[List[int]]。
    每個子列表為 [第1球, 第2球, ..., 第6球]（不含特別號）。
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
# 直接執行時進行增量更新
# ──────────────────────────────────────────────
if __name__ == "__main__":
    added = incremental_update()
    if added == 0:
        sys.exit(0)
    print(f"[scraper] 完成，新增 {added} 筆")
