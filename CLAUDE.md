# 台灣大樂透智能選號系統 — Claude 工作指引

## 專案背景
台灣大樂透（6/49）號碼分析與推薦系統。資料來源為台彩官方 API，以 Streamlit 建構網頁介面。

## 技術棧
- Python 3.11、Streamlit、pandas、numpy、scikit-learn
- 資料：`data/lotto_history.csv`（每週二、五自動更新）
- 核心邏輯：`src/engine.py`、`src/utils.py`、`src/scraper.py`
- 入口：`streamlit run app.py`

## 語言
所有回覆、注解、commit message 一律使用**繁體中文**。

## Git 規範
- 開發分支：系統分配的 `claude/...` 分支，不推送到 main
- Commit 格式：`類型: 簡短說明`（類型如 feat / fix / refactor）
- 每次任務結束前必須 commit + push（stop hook 會檢查）

## 樂透規則（大樂透）
- 第1區：1–49 選 6 個號碼，每注 NT$50
- 獎項（不含特別號，本系統未追蹤第2區特別號）：
  - 6 中：貳獎，浮動頭獎，估算 8,000,000
  - 5 中：肆獎 20,000
  - 4 中：陸獎 800
  - 3 中：玖獎 100
- 三個以上連號（如 12-13-14）系統自動排除
- 一組二連號允許且加分

## 核心設計決策（勿隨意更動）
- `compute_missing_periods`：從最新期往回掃，連續未出現期數即遺漏數
- `PRIZE_TABLE`：以第1區不含特別號的固定金額為準
- 三層號碼池（Pool1→2→3）負責號碼循環，不要簡化掉
- `is_reasonable()` 是硬性過濾，`score()` 是加分評估，兩者分工明確

## 常見任務提醒
- 修改 UI：編輯 `app.py`
- 修改分析邏輯：編輯 `src/engine.py` 或 `src/utils.py`
- 新增工具函式後記得在 `app.py` 的 import 區段同步更新
