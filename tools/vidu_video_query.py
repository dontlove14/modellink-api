import logging
import mimetypes
import os
import sys
from collections.abc import Generator
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from dify_plugin import File, Tool
from dify_plugin.config.logger_format import plugin_logger_handler
from dify_plugin.entities.tool import ToolInvokeMessage

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from video_toolkit import build_query_message, normalize_params, request_json, require_param


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class ViduVideoQueryTool(Tool):
    def _guess_file_name(self, url: str, content_type: str | None, fallback_name: str) -> str:
        """根据远程地址与响应类型推断上传到 Dify 时使用的文件名。"""
        path = urlparse(url).path
        base_name = os.path.basename(path)
        decoded_name = unquote(base_name).strip() if base_name else ""
        if decoded_name and "." in decoded_name:
            return decoded_name
        mime_type = (content_type or "video/mp4").split(";", 1)[0].strip() or "video/mp4"
        extension = mimetypes.guess_extension(mime_type) or ".mp4"
        return f"{fallback_name}{extension}"

    def _download_remote_file(self, url: str, fallback_name: str) -> tuple[bytes, str, str]:
        """下载远程文件并返回文件内容、MIME 类型与推断后的文件名。"""
        session = requests.Session()
        session.trust_env = False
        response = session.get(url, timeout=(10, 300))
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "video/mp4")
        mime_type = content_type.split(";", 1)[0].strip() or "video/mp4"
        file_name = self._guess_file_name(url, content_type, fallback_name)
        return response.content, mime_type, file_name

    def _upload_url_to_dify(self, url: str, fallback_name: str) -> dict[str, Any]:
        """将远程 URL 对应文件上传到 Dify，并返回可写回响应的文件信息。"""
        file_content, mime_type, file_name = self._download_remote_file(url, fallback_name)
        uploaded_file = File(self.session).upload(
            filename=file_name,
            content=file_content,
            mimetype=mime_type,
        )
        return {
            "url": uploaded_file.preview_url or url,
            "file": uploaded_file.to_app_parameter(),
            "file_id": uploaded_file.id,
            "file_name": uploaded_file.name,
            "mime_type": uploaded_file.mime_type,
            "size": uploaded_file.size,
        }

    def _replace_creation_urls(self, creations: Any) -> Any:
        """将 Vidu 返回的 creations[*].url 替换为 Dify 转存后的链接。"""
        if not isinstance(creations, list):
            return creations

        replaced_creations: list[Any] = []
        for index, creation in enumerate(creations, start=1):
            if not isinstance(creation, dict):
                replaced_creations.append(creation)
                continue

            creation_data = dict(creation)
            url = creation_data.get("url")
            if isinstance(url, str) and url.strip():
                logger.info(f"[Vidu Video Query] upload creation url to dify, index={index}")
                creation_data.update(self._upload_url_to_dify(url.strip(), f"vidu_video_{index}"))
            replaced_creations.append(creation_data)
        return replaced_creations

    def _replace_video_urls(self, video: Any) -> Any:
        """兼容处理 video.url 结构，替换为 Dify 转存后的链接。"""
        if not isinstance(video, dict):
            return video

        video_data = dict(video)
        url = video_data.get("url")
        if isinstance(url, str) and url.strip():
            logger.info("[Vidu Video Query] upload video.url to dify")
            video_data.update(self._upload_url_to_dify(url.strip(), "vidu_video"))
        return video_data

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """查询 Vidu 视频任务结果。"""
        params = normalize_params(tool_parameters)
        api_key = require_param(params, "apiKey")
        task_id = require_param(params, "id")

        logger.info("[Vidu Video Query] query task")
        result = request_json(
            method="GET",
            path=f"/vidu/ent/v2/tasks/{task_id}/creations",
            api_key=api_key,
            auth_type="token",
        )
        creations = self._replace_creation_urls(result.get("creations"))
        video = self._replace_video_urls(result.get("video"))

        yield self.create_json_message(
            build_query_message(
                "Vidu 视频任务查询成功",
                {
                    "id": result.get("id"),
                    "state": result.get("state"),
                    "err_code": result.get("err_code"),
                    "credits": result.get("credits"),
                    "payload": result.get("payload"),
                    "bgm": result.get("bgm"),
                    "off_peak": result.get("off_peak"),
                    "creations": creations,
                    "video": video,
                },
            )
        )
