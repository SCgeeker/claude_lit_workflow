# -*- coding: utf-8 -*-
"""wheel 冒煙測試（spec: cli — 可安裝套件）

uv build → 臨時 venv 安裝 wheel → console scripts 可執行。
耗時較長，標記 slow；CI / archive 前必跑。
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent

pytestmark = pytest.mark.slow


def _run(cmd, **kw):
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600, **kw
    )


@pytest.fixture(scope="module")
def wheel_venv(tmp_path_factory):
    """建 wheel 並安裝到乾淨 venv，回傳 venv Scripts 目錄"""
    tmp = tmp_path_factory.mktemp("wheel_smoke")
    dist = tmp / "dist"

    build = _run(["uv", "build", "--wheel", "--out-dir", str(dist)], cwd=str(ROOT))
    assert build.returncode == 0, f"uv build 失敗：{build.stderr[-800:]}"
    wheels = list(dist.glob("*.whl"))
    assert wheels, "未產出 wheel"

    venv_dir = tmp / "venv"
    create = _run(["uv", "venv", str(venv_dir)])
    assert create.returncode == 0, create.stderr[-500:]

    py = venv_dir / "Scripts" / "python.exe"
    install = _run(["uv", "pip", "install", "--python", str(py), str(wheels[0])])
    assert install.returncode == 0, f"wheel 安裝失敗：{install.stderr[-800:]}"

    return venv_dir / "Scripts"


class TestWheelSmoke:
    def test_slides_list_options(self, wheel_venv, tmp_path):
        # 在無原始碼樹的目錄執行 → 資源必須來自套件內建
        r = _run([str(wheel_venv / "slides.exe"), "--list-options"], cwd=str(tmp_path))
        assert r.returncode == 0, r.stderr[-800:]
        assert "modern_academic" in r.stdout

    def test_mcp_server_help(self, wheel_venv, tmp_path):
        r = _run([str(wheel_venv / "mcp-server.exe"), "--help"], cwd=str(tmp_path))
        assert r.returncode == 0, r.stderr[-800:]
        assert "--transport" in r.stdout

    def test_zettel_help(self, wheel_venv, tmp_path):
        r = _run([str(wheel_venv / "zettel.exe"), "--help"], cwd=str(tmp_path))
        assert r.returncode == 0, r.stderr[-800:]

    def test_import_in_clean_env(self, wheel_venv, tmp_path):
        py = wheel_venv / "python.exe"
        r = _run(
            [str(py), "-c",
             "from claude_lit.api import SlideRequest, generate_slides; "
             "from claude_lit.resource_loader import resolve_resource; "
             "p = resolve_resource('templates/prompts/journal_club_template.jinja2'); "
             "assert p.exists(); print('OK')"],
            cwd=str(tmp_path),
        )
        assert r.returncode == 0, r.stderr[-800:]
        assert "OK" in r.stdout
