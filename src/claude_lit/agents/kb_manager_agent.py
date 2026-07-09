#!/usr/bin/env python3
"""
Knowledge Base Manager Agent (MVP版本)
知識庫管理員Agent - 負責批次處理、質量檢查、Zettelkasten索引等任務
"""
import sys
import io
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml
from datetime import datetime

# 注意：庫模組不得在 import 時重新包裝 sys.stdout / sys.stderr
# （會關閉 pytest capture 與 MCP stdio 的底層串流）；編碼防護由 CLI 入口負責。

# 導入Skills
from claude_lit.processors import BatchProcessor
from claude_lit.checkers import QualityChecker
from claude_lit.knowledge_base import KnowledgeBaseManager


class KnowledgeBaseManagerAgent:
    """
    知識庫管理員Agent (MVP版本)

    核心功能：
    1. 批次導入PDF
    2. 質量審計
    3. 整合Zettelkasten
    4. 搜索知識
    5. 生成簡報
    6. 生成筆記

    特性：
    - 對話式交互（主動詢問參數）
    - Skill調度
    - 優雅錯誤處理
    - 進度報告
    """

    def __init__(self, config_path: str = None):
        """
        初始化Agent

        Args:
            config_path: Agent配置文件路徑（默認使用.claude/agents/knowledge-integrator/）
        """
        self.config_path = config_path or ".claude/agents/knowledge-integrator"
        self.config = self._load_config()
        self.workflows = self._load_workflows()

        # 初始化Skill實例
        self.skills = {
            'batch-processor': BatchProcessor(max_workers=3),
            'quality-checker': QualityChecker(),
            'kb-connector': KnowledgeBaseManager()
        }

        print(f"✅ Knowledge Base Manager Agent 已初始化")
        print(f"   版本: {self.config.get('agent', {}).get('version', '1.0.0-mvp')}")
        print(f"   支援工作流: {len(self.workflows)} 個\n")

    def _load_config(self) -> Dict:
        """載入Agent配置"""
        try:
            config_file = Path(self.config_path) / "agent.yaml"
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"⚠️  無法載入配置，使用默認值: {e}")
            return {}

    def _load_workflows(self) -> Dict:
        """載入工作流定義"""
        try:
            workflow_file = Path(self.config_path) / "workflows.yaml"
            with open(workflow_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data.get('workflows', {})
        except Exception as e:
            print(f"⚠️  無法載入工作流定義: {e}")
            return {}

    # ========== 公共介面方法 ==========

    def execute_workflow(self, workflow_name: str, params: Dict = None) -> Dict:
        """
        執行指定的工作流

        Args:
            workflow_name: 工作流名稱（batch_import/quality_audit/integrate_zettel/等）
            params: 工作流參數（可選，會自動詢問缺失的參數）

        Returns:
            執行結果字典
        """
        if workflow_name not in self.workflows:
            return {
                'success': False,
                'error': f"未知的工作流: {workflow_name}",
                'available_workflows': list(self.workflows.keys())
            }

        workflow = self.workflows[workflow_name]
        params = params or {}

        print(f"\n{'='*70}")
        print(f"🚀 執行工作流: {workflow.get('name', workflow_name)}")
        print(f"{'='*70}\n")

        try:
            # 步驟1：收集參數
            params = self._collect_parameters(workflow, params)

            # 步驟2：確認執行
            if not self._confirm_execution(workflow, params):
                return {'success': False, 'message': '用戶取消執行'}

            # 步驟3：執行工作流
            result = self._execute_workflow_steps(workflow, params)

            # 步驟4：生成報告
            self._generate_report(workflow_name, result)

            return result

        except Exception as e:
            print(f"\n❌ 執行失敗: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    # ========== 核心工作流方法 ==========

    def batch_import(self, folder_path: str, domain: str = "Research",
                    generate_zettel: bool = False, **kwargs) -> Dict:
        """
        批次導入PDF

        Args:
            folder_path: PDF資料夾路徑
            domain: 領域（CogSci/Linguistics/AI/Research）
            generate_zettel: 是否生成Zettelkasten筆記
            **kwargs: 其他參數

        Returns:
            處理結果
        """
        params = {
            'folder_path': folder_path,
            'domain': domain,
            'add_to_kb': kwargs.get('add_to_kb', True),
            'generate_zettel': generate_zettel,
            'max_workers': kwargs.get('max_workers', 3),
            'zettel_config': kwargs.get('zettel_config', {})
        }

        return self.execute_workflow('batch_import', params)

    def quality_audit(self, severity: str = "all", auto_fix: bool = False, **kwargs) -> Dict:
        """
        質量審計

        Args:
            severity: 嚴重程度（critical/high/all）
            auto_fix: 是否自動修復
            **kwargs: 其他參數

        Returns:
            檢查結果
        """
        params = {
            'severity': severity,
            'auto_fix': auto_fix,
            'detect_duplicates': kwargs.get('detect_duplicates', False),
            'report_format': kwargs.get('report_format', 'text')
        }

        return self.execute_workflow('quality_audit', params)

    def integrate_zettel(self, zettel_dir: str = "output/zettelkasten_notes",
                        domain: str = "all", auto_link: bool = True, **kwargs) -> Dict:
        """
        整合Zettelkasten

        Args:
            zettel_dir: Zettelkasten根目錄
            domain: 限定領域
            auto_link: 是否自動關聯論文
            **kwargs: 其他參數

        Returns:
            索引結果
        """
        params = {
            'zettel_dir': zettel_dir,
            'domain': domain,
            'auto_link': auto_link,
            'similarity_threshold': kwargs.get('similarity_threshold', 0.7)
        }

        return self.execute_workflow('integrate_zettel', params)

    # ========== 內部輔助方法 ==========

    def _collect_parameters(self, workflow: Dict, params: Dict) -> Dict:
        """收集工作流所需的參數"""
        workflow_params = workflow.get('parameters', {})
        required = workflow_params.get('required', [])
        optional = workflow_params.get('optional', [])

        # 檢查必要參數
        for param in required:
            param_name = param.get('name') if isinstance(param, dict) else param
            if param_name not in params:
                # MVP版本：使用默認值或拋出錯誤
                # 完整版應該主動詢問用戶
                if isinstance(param, dict) and 'default' in param:
                    params[param_name] = param['default']
                else:
                    raise ValueError(f"缺少必要參數: {param_name}")

        # 設置可選參數的默認值
        for param in optional:
            if isinstance(param, dict):
                param_name = param.get('name')
                if param_name not in params and 'default' in param:
                    params[param_name] = param['default']

        return params

    def _confirm_execution(self, workflow: Dict, params: Dict) -> bool:
        """
        確認執行（MVP版本自動確認）

        完整版應該顯示參數摘要並詢問用戶
        """
        # MVP版本：自動確認
        print(f"📋 配置摘要:")
        for key, value in params.items():
            print(f"   - {key}: {value}")
        print()

        return True  # 自動確認

    def _execute_workflow_steps(self, workflow: Dict, params: Dict) -> Dict:
        """執行工作流的各個步驟"""
        steps = workflow.get('steps', [])
        result = {'success': True, 'steps_completed': []}

        for step in steps:
            step_id = step.get('id')
            skill_name = step.get('skill')

            if skill_name:
                # 執行Skill
                step_result = self._execute_skill(skill_name, step, params)
                result['steps_completed'].append(step_id)

                if not step_result.get('success', True):
                    result['success'] = False
                    result['error'] = step_result.get('error')
                    break

                # 合併結果
                result.update(step_result)

        return result

    def _execute_skill(self, skill_name: str, step: Dict, params: Dict) -> Dict:
        """執行指定的Skill"""
        print(f"⚙️  執行: {skill_name}...")

        try:
            if skill_name == 'batch-processor':
                return self._run_batch_processor(params)

            elif skill_name == 'quality-checker':
                return self._run_quality_checker(params)

            elif skill_name == 'zettel-indexer' or (skill_name == 'kb-connector' and step.get('method') == 'auto_link_zettel_papers'):
                return self._run_zettel_operations(params)

            else:
                return {'success': False, 'error': f'未實作的Skill: {skill_name}'}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _run_batch_processor(self, params: Dict) -> Dict:
        """執行批次處理Skill"""
        processor = self.skills['batch-processor']

        result = processor.process_batch(
            pdf_paths=params.get('folder_path'),
            domain=params.get('domain', 'Research'),
            add_to_kb=params.get('add_to_kb', True),
            generate_zettel=params.get('generate_zettel', False),
            zettel_config=params.get('zettel_config', {}),
            error_handling='skip'
        )

        return {
            'success': result.success > 0,
            'total': result.total,
            'success_count': result.success,
            'failed': result.failed,
            'processing_time': result.processing_time,
            'report': result.to_report()
        }

    def _run_quality_checker(self, params: Dict) -> Dict:
        """執行質量檢查Skill"""
        checker = self.skills['quality-checker']

        # 檢查所有論文
        reports = checker.check_all_papers()

        # 生成摘要
        summary = checker.generate_summary_report(
            reports,
            detail_level='comprehensive' if params.get('severity') == 'all' else 'standard'
        )

        # 檢測重複（如果需要）
        duplicates = []
        if params.get('detect_duplicates', False):
            duplicates = checker.detect_duplicates(threshold=0.85)

        return {
            'success': True,
            'issues_found': len(reports),
            'summary': summary,
            'duplicates': len(duplicates),
            'reports': reports
        }

    def _run_zettel_operations(self, params: Dict) -> Dict:
        """執行Zettelkasten相關操作"""
        kb = self.skills['kb-connector']

        result = {}

        # 索引Zettelkasten
        if 'zettel_dir' in params:
            zettel_dir = Path(params['zettel_dir'])

            if zettel_dir.exists():
                # 掃描所有資料夾
                zettel_folders = sorted([d for d in zettel_dir.iterdir()
                                       if d.is_dir() and d.name.startswith('zettel_')])

                total_stats = {
                    'total_cards': 0,
                    'success': 0,
                    'failed': 0,
                    'skipped': 0
                }

                for folder in zettel_folders:
                    try:
                        stats = kb.index_zettelkasten(
                            str(folder),
                            domain=params.get('domain') if params.get('domain') != 'all' else None
                        )

                        total_stats['total_cards'] += stats['total']
                        total_stats['success'] += stats['success']
                        total_stats['failed'] += stats['failed']
                        total_stats['skipped'] += stats['skipped']

                    except Exception as e:
                        print(f"  ⚠️  跳過資料夾 {folder.name}: {e}")
                        continue

                result.update(total_stats)

        # 自動關聯論文
        if params.get('auto_link', False):
            link_stats = kb.auto_link_zettel_papers(
                similarity_threshold=params.get('similarity_threshold', 0.7)
            )
            result['linking'] = link_stats

        result['success'] = True
        return result

    def _generate_report(self, workflow_name: str, result: Dict):
        """生成執行報告"""
        print(f"\n{'='*70}")
        print(f"📊 執行報告: {workflow_name}")
        print(f"{'='*70}\n")

        if result.get('success'):
            print("✅ 執行成功！\n")

            # 顯示主要統計
            if 'total' in result:
                print(f"📈 統計:")
                print(f"   - 總數: {result.get('total', 0)}")
                print(f"   - 成功: {result.get('success_count', 0)}")
                print(f"   - 失敗: {result.get('failed', 0)}")

                if 'processing_time' in result:
                    print(f"   - 處理時間: {result['processing_time']}")

            if 'total_cards' in result:
                print(f"📝 卡片索引:")
                print(f"   - 總卡片數: {result['total_cards']}")
                print(f"   - 成功索引: {result['success']}")

                if 'linking' in result:
                    link_stats = result['linking']
                    print(f"\n🔗 論文關聯:")
                    print(f"   - 已關聯: {link_stats.get('linked', 0)}")
                    print(f"   - 未匹配: {link_stats.get('unmatched', 0)}")

            if 'issues_found' in result:
                print(f"⚠️  發現問題: {result['issues_found']}")
                if 'duplicates' in result:
                    print(f"   重複論文: {result['duplicates']}")

        else:
            print(f"❌ 執行失敗: {result.get('error', '未知錯誤')}")

        print(f"\n{'='*70}\n")


# ========== 便利函數 ==========

def create_agent() -> KnowledgeBaseManagerAgent:
    """創建Agent實例的便利函數"""
    return KnowledgeBaseManagerAgent()


# ========== 測試代碼 ==========

if __name__ == '__main__':
    # 簡單測試
    agent = create_agent()

    print("\n🧪 測試Agent基本功能...")
    print("\n可用的工作流:")
    for wf_name, wf_config in agent.workflows.items():
        print(f"  - {wf_name}: {wf_config.get('name', wf_name)}")

    print("\n✅ Agent初始化成功！")
    print("\n使用範例:")
    print("  agent.batch_import('D:\\\\pdfs', domain='CogSci')")
    print("  agent.quality_audit(severity='high')")
    print("  agent.integrate_zettel()")
