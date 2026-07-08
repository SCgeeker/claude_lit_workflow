#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
使用報告生成器
Usage Report Generator

生成LLM模型使用情況報告
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any


class UsageReporter:
    """
    使用報告生成器

    負責生成各種格式的使用報告
    """

    def __init__(self, log_dir: str = "logs/model_usage"):
        """
        初始化報告生成器

        Args:
            log_dir: 日誌目錄路徑
        """
        self.log_dir = Path(log_dir)

    def generate_daily_report(self, date: Optional[str] = None) -> str:
        """
        生成每日使用報告

        Args:
            date: 日期字串（YYYY-MM-DD），默認為今天

        Returns:
            Markdown格式的報告
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        usage_file = self.log_dir / f"usage_{date}.json"
        if not usage_file.exists():
            return f"# 使用報告 - {date}\n\n沒有找到當日使用記錄。"

        with open(usage_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        report = []
        report.append(f"# 📊 LLM使用報告 - {date}")
        report.append("")
        report.append("---")
        report.append("")

        # 總覽
        report.append("## 📈 總覽")
        report.append("")
        report.append(f"- **總請求數**: {data['total_requests']}")
        report.append(f"- **總Token數**: {data['total_tokens']:,}")
        report.append(f"- **總成本**: ${data['total_cost']:.4f}")
        report.append("")

        # 模型使用詳情
        report.append("## 🤖 模型使用詳情")
        report.append("")

        if data['models']:
            report.append("| 模型 | 提供者 | 請求數 | 成功率 | 平均響應時間 | Token數 | 成本 |")
            report.append("|------|--------|--------|--------|--------------|---------|------|")

            for model_key, stats in data['models'].items():
                success_rate = (stats['successful'] / stats['requests'] * 100) if stats['requests'] > 0 else 0
                report.append(
                    f"| {stats['model']} | {stats['provider']} | "
                    f"{stats['requests']} | {success_rate:.1f}% | "
                    f"{stats['avg_response_time']:.2f}s | "
                    f"{stats['tokens']:,} | ${stats['cost']:.4f} |"
                )
        else:
            report.append("*沒有模型使用記錄*")

        report.append("")

        # 任務類型分布
        report.append("## 📋 任務類型分布")
        report.append("")

        task_counts = {}
        for model_stats in data['models'].values():
            for task, count in model_stats.get('task_types', {}).items():
                task_counts[task] = task_counts.get(task, 0) + count

        if task_counts:
            total_tasks = sum(task_counts.values())
            report.append("| 任務類型 | 次數 | 佔比 |")
            report.append("|----------|------|------|")
            for task, count in sorted(task_counts.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_tasks * 100) if total_tasks > 0 else 0
                report.append(f"| {task or '未分類'} | {count} | {percentage:.1f}% |")
        else:
            report.append("*沒有任務類型記錄*")

        report.append("")

        # 錯誤記錄
        if data.get('errors'):
            report.append("## ⚠️ 錯誤記錄")
            report.append("")
            report.append(f"共發生 {len(data['errors'])} 個錯誤：")
            report.append("")
            for i, error in enumerate(data['errors'][:5], 1):  # 只顯示前5個
                time_str = error['time'].split('T')[1][:8]  # 只顯示時間
                report.append(f"{i}. **{time_str}** - {error['model']}: {error['error'][:100]}...")
            if len(data['errors']) > 5:
                report.append(f"... 還有 {len(data['errors']) - 5} 個錯誤")

        report.append("")
        report.append("---")
        report.append("")
        report.append(f"*報告生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(report)

    def generate_weekly_report(self, end_date: Optional[str] = None) -> str:
        """
        生成週報告

        Args:
            end_date: 結束日期（YYYY-MM-DD），默認為今天

        Returns:
            Markdown格式的報告
        """
        if end_date is None:
            end_date = datetime.now()
        else:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        start_date = end_date - timedelta(days=6)

        report = []
        report.append(f"# 📊 週使用報告")
        report.append(f"**期間**: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
        report.append("")
        report.append("---")
        report.append("")

        # 收集週數據
        weekly_data = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "daily_stats": [],
            "model_totals": {}
        }

        for i in range(7):
            date = start_date + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            usage_file = self.log_dir / f"usage_{date_str}.json"

            if usage_file.exists():
                with open(usage_file, 'r', encoding='utf-8') as f:
                    daily_data = json.load(f)

                weekly_data["total_requests"] += daily_data["total_requests"]
                weekly_data["total_tokens"] += daily_data["total_tokens"]
                weekly_data["total_cost"] += daily_data["total_cost"]

                weekly_data["daily_stats"].append({
                    "date": date_str,
                    "requests": daily_data["total_requests"],
                    "cost": daily_data["total_cost"]
                })

                # 聚合模型統計
                for model_key, stats in daily_data["models"].items():
                    if model_key not in weekly_data["model_totals"]:
                        weekly_data["model_totals"][model_key] = {
                            "provider": stats["provider"],
                            "model": stats["model"],
                            "requests": 0,
                            "tokens": 0,
                            "cost": 0.0
                        }
                    weekly_data["model_totals"][model_key]["requests"] += stats["requests"]
                    weekly_data["model_totals"][model_key]["tokens"] += stats["tokens"]
                    weekly_data["model_totals"][model_key]["cost"] += stats["cost"]

        # 生成報告
        report.append("## 📈 週總覽")
        report.append("")
        report.append(f"- **總請求數**: {weekly_data['total_requests']}")
        report.append(f"- **總Token數**: {weekly_data['total_tokens']:,}")
        report.append(f"- **總成本**: ${weekly_data['total_cost']:.2f}")
        report.append(f"- **日均請求**: {weekly_data['total_requests'] / 7:.1f}")
        report.append(f"- **日均成本**: ${weekly_data['total_cost'] / 7:.4f}")
        report.append("")

        # 每日趨勢
        report.append("## 📅 每日趨勢")
        report.append("")
        report.append("| 日期 | 請求數 | 成本 |")
        report.append("|------|--------|------|")

        for daily in weekly_data["daily_stats"]:
            report.append(f"| {daily['date']} | {daily['requests']} | ${daily['cost']:.4f} |")

        report.append("")

        # 模型排行
        report.append("## 🏆 模型使用排行")
        report.append("")

        if weekly_data["model_totals"]:
            sorted_models = sorted(
                weekly_data["model_totals"].items(),
                key=lambda x: x[1]["requests"],
                reverse=True
            )

            report.append("| 排名 | 模型 | 提供者 | 請求數 | 成本 |")
            report.append("|------|------|--------|--------|------|")

            for i, (model_key, stats) in enumerate(sorted_models[:5], 1):
                report.append(
                    f"| {i} | {stats['model']} | {stats['provider']} | "
                    f"{stats['requests']} | ${stats['cost']:.4f} |"
                )

        report.append("")

        # 成本分析
        report.append("## 💰 成本分析")
        report.append("")

        if weekly_data["total_cost"] > 0:
            report.append("### 成本分布")
            report.append("")
            for model_key, stats in sorted(
                weekly_data["model_totals"].items(),
                key=lambda x: x[1]["cost"],
                reverse=True
            ):
                if stats["cost"] > 0:
                    percentage = (stats["cost"] / weekly_data["total_cost"] * 100)
                    report.append(f"- **{stats['model']}**: ${stats['cost']:.4f} ({percentage:.1f}%)")

        report.append("")

        # 優化建議
        report.append("## 💡 優化建議")
        report.append("")

        if weekly_data["total_requests"] > 0:
            # 找出最常用的付費模型
            paid_models = [
                (k, v) for k, v in weekly_data["model_totals"].items()
                if v["cost"] > 0
            ]

            if paid_models:
                most_expensive = max(paid_models, key=lambda x: x[1]["cost"])
                report.append(
                    f"1. **成本最高模型**: {most_expensive[1]['model']} "
                    f"(${most_expensive[1]['cost']:.2f})，考慮使用免費替代方案"
                )

            # 計算平均請求成本
            avg_cost = weekly_data["total_cost"] / weekly_data["total_requests"]
            if avg_cost > 0.01:
                report.append(f"2. **平均請求成本較高**: ${avg_cost:.4f}，建議增加免費模型使用比例")

            # 檢查失敗率
            # （這裡需要額外的失敗統計，暫時省略）

        else:
            report.append("*本週無使用記錄*")

        report.append("")
        report.append("---")
        report.append("")
        report.append(f"*報告生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(report)

    def save_report(self, content: str, filename: str):
        """
        保存報告到文件

        Args:
            content: 報告內容
            filename: 文件名
        """
        report_dir = self.log_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)

        report_file = report_dir / filename
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"📝 報告已保存：{report_file}")


if __name__ == "__main__":
    # 測試報告生成
    reporter = UsageReporter()

    # 生成今日報告
    daily_report = reporter.generate_daily_report()
    print(daily_report)
    reporter.save_report(daily_report, f"daily_{datetime.now().strftime('%Y%m%d')}.md")

    # 生成週報告
    weekly_report = reporter.generate_weekly_report()
    print("\n" + "=" * 60 + "\n")
    print(weekly_report)
    reporter.save_report(weekly_report, f"weekly_{datetime.now().strftime('%Y%m%d')}.md")