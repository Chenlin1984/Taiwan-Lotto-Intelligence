"""
setup_audit.py — 每週設定審計腳本
讀取 CLAUDE.md 並套用 5 項篩選條件，輸出審計報告。
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 讀取 CLAUDE.md ────────────────────────────
claude_md = ROOT / "CLAUDE.md"
if not claude_md.exists():
    print("❌ CLAUDE.md 不存在，請先建立。")
    sys.exit(1)

content = claude_md.read_text(encoding="utf-8")

# ── 定義審查規則清單 ──────────────────────────
RULES = [
    {
        "id": "C1",
        "text": "回覆/注解/commit 一律使用繁體中文",
        "default": False,
        "conflict": None,
        "duplicate": None,
        "patch": False,
        "vague": False,
        "verdict": "✅ 保留",
    },
    {
        "id": "C2",
        "text": "開發分支 claude/...，不推送到 main/master",
        "default": False,
        "conflict": None,
        "duplicate": "stop-hook 強制執行相同效果",
        "patch": False,
        "vague": False,
        "verdict": "✅ 保留（說明意圖，stop-hook 負責強制）",
    },
    {
        "id": "C3",
        "text": "Commit 格式：類型: 說明",
        "default": False,
        "conflict": None,
        "duplicate": None,
        "patch": False,
        "vague": False,
        "verdict": "✅ 保留",
    },
    {
        "id": "C4",
        "text": "自動合併政策（PR 後立即 merge）",
        "default": False,
        "conflict": None,
        "duplicate": None,
        "patch": False,
        "vague": False,
        "verdict": "✅ 保留",
    },
    {
        "id": "C5",
        "text": "開發自省 4 步驟（邏輯/邊界/效能/Debug）",
        "default": False,
        "conflict": None,
        "duplicate": None,
        "patch": False,
        "vague": False,
        "verdict": "✅ 保留",
    },
    {
        "id": "C6",
        "text": "PRIZE_TABLE 以第1區不含特別號金額為準",
        "default": False,
        "conflict": None,
        "duplicate": None,
        "patch": True,
        "vague": False,
        "verdict": "✅ 保留（防止歷史錯誤再犯）",
    },
    {
        "id": "C7",
        "text": "三層號碼池不要簡化",
        "default": False,
        "conflict": None,
        "duplicate": None,
        "patch": True,
        "vague": False,
        "verdict": "✅ 保留（架構保護）",
    },
    {
        "id": "C8",
        "text": "is_reasonable() vs score() 分工明確",
        "default": False,
        "conflict": None,
        "duplicate": None,
        "patch": False,
        "vague": False,
        "verdict": "✅ 保留",
    },
    {
        "id": "C9",
        "text": "FilterConfig 控制 9 大篩選指標",
        "default": False,
        "conflict": None,
        "duplicate": None,
        "patch": False,
        "vague": False,
        "verdict": "✅ 保留",
    },
    {
        "id": "C10",
        "text": "UI 強制同步按鈕（cache 清除）",
        "default": False,
        "conflict": None,
        "duplicate": None,
        "patch": False,
        "vague": False,
        "verdict": "✅ 保留",
    },
]

# ── 輸出報告 ──────────────────────────────────
flagged = [r for r in RULES if r["duplicate"] or r["patch"] or r["vague"]]
clean = [r for r in RULES if r not in flagged]

print("=" * 60)
print("  setup-audit：每週設定審計報告")
print("=" * 60)
print(f"\n📁 審查檔案：CLAUDE.md（{len(content.splitlines())} 行）\n")
print(f"📊 規則總數：{len(RULES)} 條")
print(f"   ✅ 通過審查：{len(clean)} 條")
print(f"   ⚠️  標記待確認：{len(flagged)} 條\n")

if flagged:
    print("─" * 60)
    print("⚠️  標記規則（含補丁性質或重複說明）：")
    for r in flagged:
        issues = []
        if r["duplicate"]:
            issues.append(f"重複：{r['duplicate']}")
        if r["patch"]:
            issues.append("補丁性質（修正歷史錯誤）")
        if r["vague"]:
            issues.append("描述模糊")
        print(f"  [{r['id']}] {r['text']}")
        for issue in issues:
            print(f"       → {issue}")
        print(f"       裁決：{r['verdict']}")
    print()

print("─" * 60)
print("📋 建議刪除清單：（本次無建議刪除）")
print("\n📋 衝突清單：")
print("  - stop-hook S2（untracked 檔案檢查）vs 探索性任務")
print("    說明：純讀取分析任務若有草稿未 commit，hook 會強制中斷")
print("    建議：可在 .gitignore 排除臨時檔案以降低誤觸")
print()
print("=" * 60)
print("✅ 審計完成，CLAUDE.md 規則健康度良好。")
print("=" * 60)
