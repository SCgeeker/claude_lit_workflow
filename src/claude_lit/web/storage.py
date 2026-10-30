# -*- coding: utf-8 -*-
"""job 目錄、上傳檔、下載邊界、zip 與保留期清理

    {data_dir}/jobs/{job_id}/
        job.json      狀態、參數、進度事件、結果
        input/        上傳檔（以固定名稱儲存，不使用使用者檔名組路徑）
        overlay/      per-job 模板覆蓋檔（resource_loader overlay）
        output/       生成結果（結構與本機 CLI 的 output/ 相同）
"""

import io
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

# 允許上傳的副檔名 → 檔頭檢查（None 表示須為可解碼的 UTF-8 文字）
UPLOAD_TYPES: Dict[str, Optional[bytes]] = {
    ".pdf": b"%PDF",
    ".epub": b"PK\x03\x04",
    ".txt": None,
    ".md": None,
    ".markdown": None,
    ".srt": None,
    ".vtt": None,
}

# 使用者可覆蓋的資源（per-job overlay）；其餘路徑一律拒絕。
# 不開放 .jinja2：模板以未沙箱化的 jinja2.Template 渲染，上傳模板等同在伺服器執行任意程式碼
# （可讀出 LLM 金鑰）。media_profiles.yaml 以 yaml.safe_load 載入、只當資料注入模板，安全。
OVERRIDABLE_RESOURCES = (
    "templates/styles/media_profiles.yaml",
)
MAX_OVERRIDE_BYTES = 256 * 1024
TEXT_SUFFIXES = (".txt", ".md", ".markdown")

_JOB_ID = re.compile(r"^[0-9a-f]{32}$")


class UploadRejected(ValueError):
    """上傳不符規定；status 為建議的 HTTP 狀態碼"""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def check_upload(filename: str, data: bytes, max_bytes: int) -> str:
    """檢查大小、副檔名白名單與檔頭；回傳正規化後的副檔名。

    Raises:
        UploadRejected: 413（過大）/ 415（類型不符）
    """
    if len(data) > max_bytes:
        raise UploadRejected(f"檔案超過上限（{max_bytes // (1024 * 1024)} MB）", 413)
    suffix = Path(filename or "").suffix.lower()
    if suffix not in UPLOAD_TYPES:
        raise UploadRejected(
            f"不支援的檔案類型：{suffix or '（無副檔名）'}（支援：{', '.join(UPLOAD_TYPES)}）", 415
        )
    magic = UPLOAD_TYPES[suffix]
    if magic is not None:
        if not data.startswith(magic):
            raise UploadRejected(f"檔案內容與副檔名 {suffix} 不符", 415)
    else:
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise UploadRejected(f"{suffix} 檔須為 UTF-8 文字", 415)
    return suffix


def safe_stem(filename: str, fallback: str = "source") -> str:
    """使用者檔名 → 安全的檔名主幹（只用於輸出命名，不用於讀寫上傳檔）"""
    stem = Path(filename or "").stem
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(". ")
    return cleaned[:60] or fallback


class JobStorage:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir) / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        if not _JOB_ID.match(job_id or ""):
            raise FileNotFoundError(job_id)
        return self.root / job_id

    def create(self, job_id: str) -> Path:
        d = self.job_dir(job_id)
        for sub in ("input", "overlay", "output"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        return d

    def save_input(self, job_id: str, suffix: str, data: bytes) -> Path:
        path = self.job_dir(job_id) / "input" / f"source{suffix}"
        path.write_bytes(data)
        return path

    def save_override(self, job_id: str, relpath: str, data: bytes) -> Path:
        if relpath not in OVERRIDABLE_RESOURCES:
            raise UploadRejected(f"不可覆蓋的資源：{relpath}", 400)
        if len(data) > MAX_OVERRIDE_BYTES:
            raise UploadRejected(f"覆蓋檔超過 {MAX_OVERRIDE_BYTES // 1024} KB 上限", 413)
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise UploadRejected(f"{relpath} 須為 UTF-8 文字", 415)
        path = self.job_dir(job_id) / "overlay" / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def output_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "output"

    def list_outputs(self, job_id: str) -> List[str]:
        out = self.output_dir(job_id)
        if not out.is_dir():
            return []
        return sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())

    def resolve_output(self, job_id: str, relpath: str) -> Path:
        """只允許 job output/ 內的檔案；穿越（..、絕對路徑、symlink 跳出）一律 FileNotFoundError"""
        out = self.output_dir(job_id).resolve()
        candidate = (out / relpath).resolve()
        if not candidate.is_relative_to(out) or not candidate.is_file():
            raise FileNotFoundError(relpath)
        return candidate

    def zip_outputs(self, job_id: str) -> bytes:
        out = self.output_dir(job_id)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel in self.list_outputs(job_id):
                zf.write(out / rel, rel)
        return buffer.getvalue()

    def delete(self, job_id: str) -> None:
        shutil.rmtree(self.job_dir(job_id), ignore_errors=True)

    def job_ids(self) -> List[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and _JOB_ID.match(p.name))

    def cleanup_expired(self, retention_days: int, finished_at: Dict[str, float], now: Optional[float] = None) -> List[str]:
        """刪除完成時間早於保留期限的 job 目錄；回傳被刪除的 job_id"""
        now = time.time() if now is None else now
        cutoff = now - retention_days * 86400
        removed = []
        for job_id, finished in finished_at.items():
            if finished and finished < cutoff:
                self.delete(job_id)
                removed.append(job_id)
        return removed
