#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模型使用監控模塊
Model Usage Monitor Module

監控和追蹤LLM模型的使用情況，包括：
- 使用次數和頻率
- Token消耗
- 成本計算
- 配額管理
- 效能指標
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import yaml


class ModelMonitor:
    """
    模型使用監控器

    負責追蹤所有LLM模型的使用情況，提供成本控制和配額管理
    """

    def __init__(self, config_path: str = "config/model_selection.yaml",
                 log_dir: str = "logs/model_usage"):
        """
        初始化監控器

        Args:
            config_path: 模型配置文件路徑
            log_dir: 日誌儲存目錄
        """
        self.config_path = Path(config_path)
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 載入配置
        self.config = self._load_config()

        # 當日使用記錄
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.usage_file = self.log_dir / f"usage_{self.today}.json"
        self.daily_usage = self._load_daily_usage()

        # 成本追蹤
        self.session_cost = 0.0
        self.session_start = datetime.now()

    def _load_config(self) -> Dict:
        """載入模型配置"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return {}

    def _load_daily_usage(self) -> Dict:
        """載入當日使用記錄"""
        if self.usage_file.exists():
            with open(self.usage_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        return {
            "date": self.today,
            "models": {},
            "total_cost": 0.0,
            "total_requests": 0,
            "total_tokens": 0,
            "errors": []
        }

    def _save_daily_usage(self):
        """保存當日使用記錄"""
        with open(self.usage_file, 'w', encoding='utf-8') as f:
            json.dump(self.daily_usage, f, indent=2, ensure_ascii=False)

    def track_usage(self,
                   model_name: str,
                   provider: str,
                   tokens_used: int,
                   response_time: float,
                   success: bool,
                   task_type: Optional[str] = None,
                   error_message: Optional[str] = None) -> Dict[str, Any]:
        """
        追蹤模型使用

        Args:
            model_name: 模型名稱
            provider: 提供者（google/anthropic/ollama）
            tokens_used: 使用的token數量
            response_time: 響應時間（秒）
            success: 是否成功
            task_type: 任務類型
            error_message: 錯誤信息（如果失敗）

        Returns:
            包含成本和配額信息的字典
        """
        # 初始化模型記錄
        model_key = f"{provider}_{model_name}"
        if model_key not in self.daily_usage["models"]:
            self.daily_usage["models"][model_key] = {
                "provider": provider,
                "model": model_name,
                "requests": 0,
                "successful": 0,
                "failed": 0,
                "tokens": 0,
                "cost": 0.0,
                "avg_response_time": 0.0,
                "task_types": {}
            }

        model_stats = self.daily_usage["models"][model_key]

        # 更新統計
        model_stats["requests"] += 1
        model_stats["tokens"] += tokens_used
        self.daily_usage["total_requests"] += 1
        self.daily_usage["total_tokens"] += tokens_used

        if success:
            model_stats["successful"] += 1
        else:
            model_stats["failed"] += 1
            if error_message:
                self.daily_usage["errors"].append({
                    "time": datetime.now().isoformat(),
                    "model": model_key,
                    "error": error_message
                })

        # 計算成本
        cost = self._calculate_cost(provider, model_name, tokens_used)
        model_stats["cost"] += cost
        self.daily_usage["total_cost"] += cost
        self.session_cost += cost

        # 更新響應時間
        if model_stats["requests"] > 1:
            model_stats["avg_response_time"] = (
                (model_stats["avg_response_time"] * (model_stats["requests"] - 1) + response_time) /
                model_stats["requests"]
            )
        else:
            model_stats["avg_response_time"] = response_time

        # 記錄任務類型
        if task_type:
            if task_type not in model_stats["task_types"]:
                model_stats["task_types"][task_type] = 0
            model_stats["task_types"][task_type] += 1

        # 保存記錄
        self._save_daily_usage()

        # 檢查配額和成本限制
        quota_status = self.check_quota_status(provider, model_name)
        cost_status = self.check_cost_status()

        return {
            "cost": cost,
            "session_cost": self.session_cost,
            "daily_cost": self.daily_usage["total_cost"],
            "quota_status": quota_status,
            "cost_status": cost_status
        }

    def _calculate_cost(self, provider: str, model_name: str, tokens: int) -> float:
        """
        計算使用成本

        Args:
            provider: 提供者
            model_name: 模型名稱
            tokens: token數量

        Returns:
            估算成本（美元）
        """
        # 從配置中查找模型信息
        models = self.config.get("models", {})

        for model_id, model_info in models.items():
            if model_info.get("provider") == provider and model_info.get("model_name") == model_name:
                # 免費模型
                if model_info.get("free_quota", False):
                    return 0.0

                # 付費模型
                if "cost_per_1k_tokens" in model_info:
                    # 假設輸入和輸出token各佔一半
                    input_cost = model_info["cost_per_1k_tokens"]["input"] * (tokens / 2000)
                    output_cost = model_info["cost_per_1k_tokens"]["output"] * (tokens / 2000)
                    return input_cost + output_cost

                # 使用預估成本
                if "estimated_cost_per_use" in model_info:
                    return model_info["estimated_cost_per_use"]

        # 默認成本（未知模型）
        return 0.0

    def check_quota_status(self, provider: str, model_name: str) -> Dict[str, Any]:
        """
        檢查配額狀態

        Args:
            provider: 提供者
            model_name: 模型名稱

        Returns:
            配額狀態信息
        """
        model_key = f"{provider}_{model_name}"

        # 檢查是否有配額限制
        models = self.config.get("models", {})
        for model_id, model_info in models.items():
            if model_info.get("provider") == provider and model_info.get("model_name") == model_name:
                if "daily_limit" in model_info:
                    daily_limit = model_info["daily_limit"]
                    used_today = self.daily_usage["models"].get(model_key, {}).get("requests", 0)
                    remaining = max(0, daily_limit - used_today)
                    percentage_used = (used_today / daily_limit * 100) if daily_limit > 0 else 0

                    return {
                        "has_quota": True,
                        "daily_limit": daily_limit,
                        "used_today": used_today,
                        "remaining": remaining,
                        "percentage_used": percentage_used,
                        "warning": percentage_used >= 80,
                        "exceeded": percentage_used >= 100
                    }

        return {
            "has_quota": False,
            "unlimited": True
        }

    def check_cost_status(self) -> Dict[str, Any]:
        """
        檢查成本狀態

        Returns:
            成本狀態信息
        """
        cost_control = self.config.get("cost_control", {})
        if not cost_control.get("enabled", False):
            return {"controlled": False}

        limits = cost_control.get("limits", {})

        # 會話成本檢查
        session_limit = limits.get("per_session", float('inf'))
        session_percentage = (self.session_cost / session_limit * 100) if session_limit > 0 else 0

        # 每日成本檢查
        daily_limit = limits.get("per_day", float('inf'))
        daily_cost = self.daily_usage["total_cost"]
        daily_percentage = (daily_cost / daily_limit * 100) if daily_limit > 0 else 0

        return {
            "controlled": True,
            "session": {
                "cost": self.session_cost,
                "limit": session_limit,
                "percentage": session_percentage,
                "warning": session_percentage >= 50,
                "exceeded": session_percentage >= 100
            },
            "daily": {
                "cost": daily_cost,
                "limit": daily_limit,
                "percentage": daily_percentage,
                "warning": daily_percentage >= 50,
                "exceeded": daily_percentage >= 100
            }
        }

    def get_usage_report(self, period: str = "today") -> Dict[str, Any]:
        """
        獲取使用報告

        Args:
            period: 報告期間（today/week/month）

        Returns:
            使用報告
        """
        if period == "today":
            return self.daily_usage

        # TODO: 實現週報和月報
        # 需要聚合多個日誌文件

        return self.daily_usage

    def suggest_model_switch(self, current_model: str,
                            current_provider: str,
                            task_type: Optional[str] = None) -> Optional[Dict[str, str]]:
        """
        建議模型切換

        基於當前使用情況和成本，建議是否切換到其他模型

        Args:
            current_model: 當前模型
            current_provider: 當前提供者
            task_type: 任務類型

        Returns:
            建議的模型信息，如果不需要切換則返回None
        """
        # 檢查當前模型的配額狀態
        quota_status = self.check_quota_status(current_provider, current_model)
        if quota_status.get("exceeded", False):
            # 配額已超，需要切換
            return self._find_alternative_model(current_model, current_provider, task_type, "quota_exceeded")

        # 檢查成本狀態
        cost_status = self.check_cost_status()
        if cost_status.get("controlled") and cost_status["session"].get("warning"):
            # 成本接近限制，建議切換到更便宜的模型
            return self._find_alternative_model(current_model, current_provider, task_type, "cost_warning")

        # 檢查錯誤率
        model_key = f"{current_provider}_{current_model}"
        model_stats = self.daily_usage["models"].get(model_key, {})
        if model_stats.get("requests", 0) > 5:
            success_rate = model_stats.get("successful", 0) / model_stats["requests"]
            if success_rate < 0.5:
                # 成功率太低，建議切換
                return self._find_alternative_model(current_model, current_provider, task_type, "low_success_rate")

        return None

    def _find_alternative_model(self, current_model: str,
                               current_provider: str,
                               task_type: Optional[str],
                               reason: str) -> Optional[Dict[str, str]]:
        """
        尋找替代模型

        Args:
            current_model: 當前模型
            current_provider: 當前提供者
            task_type: 任務類型
            reason: 切換原因

        Returns:
            替代模型信息
        """
        # 根據任務類型查找推薦模型
        if task_type:
            task_mapping = self.config.get("task_model_mapping", {}).get(task_type, {})
            preferred = task_mapping.get("preferred", [])
            fallback = task_mapping.get("fallback", [])
            avoid = task_mapping.get("avoid", [])

            # 嘗試找到可用的替代模型
            candidates = preferred + fallback

            for model_id in candidates:
                if model_id in avoid:
                    continue

                model_info = self.config.get("models", {}).get(model_id)
                if not model_info:
                    continue

                # 檢查是否是當前模型
                if (model_info.get("provider") == current_provider and
                    model_info.get("model_name") == current_model):
                    continue

                # 檢查配額
                quota_status = self.check_quota_status(
                    model_info["provider"],
                    model_info["model_name"]
                )

                if not quota_status.get("exceeded", False):
                    return {
                        "provider": model_info["provider"],
                        "model": model_info["model_name"],
                        "reason": reason,
                        "suggestion": f"切換到 {model_id} 以{self._get_reason_text(reason)}"
                    }

        return None

    def _get_reason_text(self, reason: str) -> str:
        """獲取切換原因的中文說明"""
        reasons = {
            "quota_exceeded": "避免超出配額",
            "cost_warning": "降低成本",
            "low_success_rate": "提高成功率",
            "timeout": "提高響應速度"
        }
        return reasons.get(reason, "優化效能")

    def reset_session(self):
        """重置會話統計"""
        self.session_cost = 0.0
        self.session_start = datetime.now()

    def get_model_performance(self, provider: str, model_name: str) -> Dict[str, Any]:
        """
        獲取模型效能指標

        Args:
            provider: 提供者
            model_name: 模型名稱

        Returns:
            效能指標
        """
        model_key = f"{provider}_{model_name}"
        model_stats = self.daily_usage["models"].get(model_key, {})

        if model_stats.get("requests", 0) == 0:
            return {
                "no_data": True
            }

        return {
            "requests": model_stats["requests"],
            "success_rate": model_stats["successful"] / model_stats["requests"] if model_stats["requests"] > 0 else 0,
            "avg_response_time": model_stats["avg_response_time"],
            "total_cost": model_stats["cost"],
            "tokens_used": model_stats["tokens"],
            "task_distribution": model_stats["task_types"]
        }