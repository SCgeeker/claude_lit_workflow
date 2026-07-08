#!/usr/bin/env python3
"""
批次處理器 Python API 使用範例
"""

from claude_lit.processors import BatchProcessor

# 創建批次處理器實例
processor = BatchProcessor(max_workers=3, error_handling='skip')

# 執行批次處理
result = processor.process_batch(
    pdf_paths="D:\\pdfs",
    domain="CogSci",
    add_to_kb=True,
    generate_zettel=True,
    zettel_config={
        'detail_level': 'detailed',
        'card_count': 20,
        'llm_provider': 'google'
    }
)

# 查看結果
print(f"成功: {result.success}/{result.total}")
print(f"失敗: {len(result.failures)}")
print(f"處理時間: {result.processing_time:.2f} 秒")

# 生成報告
print("\n" + result.to_report())
