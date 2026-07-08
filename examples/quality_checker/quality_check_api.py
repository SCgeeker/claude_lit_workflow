#!/usr/bin/env python3
"""
質量檢查器 Python API 使用範例
"""

from claude_lit.checkers import QualityChecker

checker = QualityChecker()

# 檢查單篇論文
report = checker.check_paper(paper_id=27, auto_fix=False)
print(f"評分: {report.overall_score}/100")
print(f"質量等級: {report.quality_level}")
print(f"問題數量: {len(report.issues)}")

# 檢查所有論文
reports = checker.check_all_papers()
summary = checker.generate_summary_report(reports, detail_level="comprehensive")
print("\n" + summary)

# 檢測重複
duplicates = checker.detect_duplicates(threshold=0.85)
print(f"\n檢測到 {len(duplicates)} 組重複論文:")
for id1, id2, similarity in duplicates:
    print(f"  論文 {id1} 與 {id2} 相似度: {similarity:.2%}")
