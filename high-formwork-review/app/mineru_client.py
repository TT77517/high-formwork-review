"""MinerU HTTP 客户端。

所有 MinerU 请求都必须通过 ``self.session`` 发送。
"""

from __future__ import annotations
from dotenv import load_dotenv
import os
import time
import zipfile
from pathlib import Path
from typing import Any

import requests


def _load_project_env() -> None:
    """加载项目根 .env，与启动目录无关（override=False 不覆盖已显式导出的变量）。"""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)


_TRUE_VALUES = {"true", "1", "yes", "on"}


class MinerUClient:
    """通过统一 Session 完成 MinerU PDF 解析。"""

    def __init__(self) -> None:
        self.session = requests.Session()
        proxy_setting = os.getenv("MINERU_USE_SYSTEM_PROXY", "false")
        self.session.trust_env = proxy_setting.strip().lower() in _TRUE_VALUES

    def parse_pdf(
        self,
        pdf_path: str | Path,
        output_dir: str | Path,
    ) -> Path:
        """上传 PDF，等待 MinerU 解析并返回解压后的 raw 目录。"""
        if not str(pdf_path).strip():
            raise ValueError("PDF 路径不能为空")

        source_path = Path(pdf_path).expanduser().resolve()
        target_dir = Path(output_dir).expanduser().resolve()

        if not source_path.is_file():
            raise FileNotFoundError(f"PDF 文件不存在：{source_path}")
        if source_path.stat().st_size == 0:
            raise ValueError(f"PDF 文件为空：{source_path}")
        _load_project_env()
        token = os.getenv("MINERU_API_TOKEN", "").strip()
        if not token:
            raise RuntimeError("缺少环境变量：MINERU_API_TOKEN")

        base_url = os.getenv(
            "MINERU_API_BASE_URL",
            "https://mineru.net",
        )
        batch_id, upload_url = self._request_upload_url(
            base_url,
            token,
            source_path,
        )
        self._upload_pdf(upload_url, source_path)
        result_body = self._poll_result(base_url, token, batch_id)
        return self._download_and_extract(result_body, target_dir)

    def _request_upload_url(
        self,
        base_url: str,
        token: str,
        pdf_path: Path,
    ) -> tuple[str, str]:
        try:
            response = self.session.post(
                f"{base_url.rstrip('/')}/api/v4/file-urls/batch",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "files": [
                        {
                            "name": pdf_path.name,
                            "data_id": f"manual-{int(time.time())}",
                            "is_ocr": True,
                        }
                    ],
                    "model_version": os.getenv("MINERU_MODEL_VERSION", "vlm"),
                    "enable_table": True,
                    "enable_formula": True,
                    "language": "ch",
                },
                timeout=60,
            )
            response.raise_for_status()
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError("创建 MinerU 解析任务失败") from exc

        if body.get("code") != 0:
            raise RuntimeError(
                f"创建 MinerU 解析任务失败："
                f"code={body.get('code')}, msg={body.get('msg')}"
            )

        try:
            return body["data"]["batch_id"], body["data"]["file_urls"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("MinerU 未返回有效的上传地址") from exc

    def _upload_pdf(
        self,
        upload_url: str,
        pdf_path: Path,
    ) -> None:
        try:
            with pdf_path.open("rb") as file_obj:
                response = self.session.put(
                    upload_url,
                    data=file_obj,
                    timeout=600,
                )
            response.raise_for_status()
        except (OSError, requests.RequestException) as exc:
            raise RuntimeError("PDF 上传失败") from exc

    def _poll_result(
        self,
        base_url: str,
        token: str,
        batch_id: str,
    ) -> dict[str, Any]:
        url = f"{base_url.rstrip('/')}/api/v4/extract-results/batch/{batch_id}"

        for _ in range(240):
            try:
                response = self.session.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=60,
                )
                response.raise_for_status()
                body = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise RuntimeError("查询 MinerU 任务状态失败") from exc

            results = body.get("data", {}).get("extract_result", [])
            if results:
                result = results[0]
                state = result.get("state")

                if state == "done":
                    return body

                if state == "failed":
                    raise RuntimeError(
                        f"MinerU 解析失败：{result.get('err_msg', '未知错误')}"
                    )

            time.sleep(5)

        raise TimeoutError("等待 MinerU 解析结果超时")

    def _download_and_extract(
        self,
        result_body: dict[str, Any],
        output_dir: Path,
    ) -> Path:
        try:
            result = result_body["data"]["extract_result"][0]
            zip_url = result["full_zip_url"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("MinerU 未返回结果 ZIP 下载地址") from exc

        output_dir.mkdir(parents=True, exist_ok=True)
        zip_path = output_dir / "mineru-result.zip"

        try:
            with self.session.get(zip_url, stream=True, timeout=600) as response:
                response.raise_for_status()
                with zip_path.open("wb") as file_obj:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            file_obj.write(chunk)
        except (OSError, requests.RequestException) as exc:
            raise RuntimeError("MinerU 结果 ZIP 下载失败") from exc

        extract_dir = output_dir / "raw"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path) as archive:
                self._validate_zip_paths(archive, extract_dir)
                archive.extractall(extract_dir)
        except (OSError, zipfile.BadZipFile) as exc:
            raise RuntimeError("MinerU 结果 ZIP 解压失败") from exc

        return extract_dir

    @staticmethod
    def _validate_zip_paths(
        archive: zipfile.ZipFile,
        extract_dir: Path,
    ) -> None:
        extract_root = extract_dir.resolve()
        for member in archive.infolist():
            member_path = (extract_root / member.filename).resolve()
            if member_path != extract_root and extract_root not in member_path.parents:
                raise RuntimeError("MinerU 结果 ZIP 包含不安全路径")
