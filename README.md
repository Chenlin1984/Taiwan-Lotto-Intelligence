# 台灣大樂透智能選號系統 🎯

> 資料驅動 · 三層池管理 · 隨機森林 ML 預測 · GitHub Actions 自動更新

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://streamlit.io/cloud)

---

## 專案簡介

本專案整合統計分析、機器學習與自動化資料更新，提供科學化的大樂透選號參考。

**免責聲明：** 彩券本質上為機率事件，本系統僅供娛樂與學習參考，不構成投注建議。

---

## 目錄結構

```
Taiwan-Lotto-Intelligence/
├── .github/
│   └── workflows/
│       └── update_data.yml      # 每週二、五自動抓取新資料
├── data/
│   └── lotto_history.csv        # 歷史開獎資料（2000+ 期）
├── src/
│   ├── engine.py                # 核心分析引擎
│   ├── scraper.py               # 台彩爬蟲
│   └── utils.py                 # 工具函式與常數
├── app.py                       # Streamlit 互動介面
├── requirements.txt
└── README.md
```

---

## 核心演算法

### 1. 三層號碼池（Multi-Level Pool）

```
Pool 1（精選池）
  ↓ 用完後移入
Pool 2（循環池）
  ↓ 用完後移入
Pool 3（備用池）
  ↓ 仍不足時
全域安全補充（1-49 自動填充）
```

觸發條件：任一池剩餘號碼 ≤ 6 時自動遞補。

### 2. 連號評分制（Consecutive Scoring）

| 連號情況 | 處理方式 |
|---------|---------|
| 無連號 | 正常評分 |
| 1 組二連號（如 12, 13）| **+2 分加分** |
| 三連號以上（如 12, 13, 14）| **強制排除** |

### 3. 多因子評分（Max ~35 分）

| 指標 | 滿分 |
|------|------|
| 和值落在 Q25~Q75 | 3 |
| 奇偶均衡（3:3）| 3 |
| 大小均衡（≤25 佔 3 個）| 3 |
| 熱號命中數 | 4 |
| 質數數量（2~3 個）| 3 |
| 尾數多樣性 | 3 |
| 區段覆蓋（10 區段）| 5 |
| 夥伴號碼對數 | 3 |
| 連號加分 | 2 |
| 中遺漏號碼命中 | 3 |

### 4. ML 隨機森林預測

- **模型**：49 個獨立 `RandomForestClassifier`（每個號碼一個）
- **特徵**（共 147 維）：
  - 前期 one-hot 編碼（49 維）
  - 目前遺漏期數，正規化（49 維）
  - 近 30 期冷熱加權（49 維）
- **訓練**：近 200 期資料，80%/20% 分割

---

## 快速開始

### 本機執行

```bash
# 1. 建立虛擬環境（建議）
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. 安裝套件
pip install -r requirements.txt

# 3. 更新歷史資料
python src/scraper.py

# 4. 啟動 Streamlit
streamlit run app.py
```

瀏覽器開啟 `http://localhost:8501` 即可使用。

### 僅更新資料

```bash
python src/scraper.py
```

---

## 部署至 Streamlit Cloud

1. 將此專案 Fork 或 Push 至你的 GitHub
2. 登入 [Streamlit Cloud](https://streamlit.io/cloud)
3. 點選 **New app** → 選擇你的 Repo → 主程式選 `app.py`
4. 點選 **Deploy** 完成！

---

## GitHub Actions 自動更新設定

系統已設定每週二、五 22:00（台灣時間）自動執行爬蟲並 Commit 新資料。

**確認 Actions 有寫入權限：**

1. 進入 GitHub Repo → Settings → Actions → General
2. **Workflow permissions** 選擇 **Read and write permissions**
3. 儲存即可

---

## 技術棧

| 類別 | 套件 |
|------|------|
| 資料處理 | pandas, numpy |
| 機器學習 | scikit-learn |
| 網頁介面 | streamlit |
| 爬蟲 | requests, beautifulsoup4 |
| 視覺化 | matplotlib |
| 自動化 | GitHub Actions |
