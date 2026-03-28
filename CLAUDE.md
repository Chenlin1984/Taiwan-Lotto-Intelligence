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
- 開發分支：系統分配的 `claude/...` 分支，**絕不直接推送到 main/master**
- Commit 格式：`類型: 簡短說明`（類型如 feat / fix / refactor / docs）
- Stop hook 自動檢查未 commit 或未 push 的變更

## 自動合併政策 (Auto-Merge Policy)
1. 所有修改建立在 `claude/...` 分支
2. 完成後發起 PR（使用 `mcp__github__create_pull_request`）
3. **立即執行合併**（使用 `mcp__github__merge_pull_request`，merge_method="merge"）
4. 僅在以下情況請求人工介入：衝突無法自動解決、測試明確失敗

## 開發自省 (Self-Audit)
每次撰寫或修改代碼後，**自動執行**以下 4 步驟：
1. **邏輯審查**：確認是否完全符合需求，有無邊界遺漏
2. **邊界測試**：考慮空值、極端值（如空 list、0、49、全同號）是否能正確處理
3. **效能評估**：大量資料下（如 C(49,6)）的時間複雜度是否可接受
4. **Debug 修正**：標註任何發現的邏輯錯誤並立即修正，不留待後續

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
- `FilterConfig` 控制 9 大篩選指標，由 UI 側邊欄傳入

## UI 強制同步
Streamlit 側邊欄必須保留以下強制同步按鈕，確保部署後邏輯更新能即時生效：
```python
if st.sidebar.button("♻️ 強制同步 GitHub 最新邏輯"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.success("已清除緩存，請重新整理網頁")
    st.rerun()
```

## 常見任務提醒
- 修改 UI：編輯 `app.py`
- 修改分析邏輯：編輯 `src/engine.py` 或 `src/utils.py`
- 新增工具函式後記得在 `app.py` 的 import 區段同步更新
- 新增篩選指標：修改 `FilterConfig`（engine.py）並同步更新側邊欄控制項與驗證報告
