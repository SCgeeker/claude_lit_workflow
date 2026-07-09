"""
pytest 配置和共享夾具

claude_lit 由 uv 的 editable install 提供，測試不需要 sys.path 操作。
"""

from pathlib import Path

import pytest


@pytest.fixture
def test_data_dir():
    """返回測試數據目錄"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def temp_db(tmp_path):
    """創建臨時數據庫"""
    db_path = tmp_path / "test.db"
    return str(db_path)


@pytest.fixture
def sample_paper_data():
    """樣本論文數據"""
    return {
        "title": "Test Paper",
        "authors": ["Author One", "Author Two"],
        "year": 2024,
        "abstract": "This is a test paper abstract.",
        "keywords": ["test", "sample"],
    }
