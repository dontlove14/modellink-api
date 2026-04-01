from collections.abc import Generator
from typing import Any
import logging
import os
import sys

from dify_plugin import Tool
from dify_plugin.config.logger_format import plugin_logger_handler
from dify_plugin.entities.tool import ToolInvokeMessage

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from video_toolkit import build_query_message, normalize_params, request_json, require_param


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class Sd20VideoQueryTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """查询 Seedance 2.0 视频任务结果。"""
        params = normalize_params(tool_parameters)
        api_key = require_param(params, "apiKey")
        task_id = require_param(params, "id")

        logger.info("[SD2.0 Video Query] query task")
        result = request_json(
            method="POST",
            path="/sd2/api/v1/doubao/get_result",
            api_key=api_key,
            auth_type="bearer",
            json_body={"id": task_id},
        )

        yield self.create_json_message(
            build_query_message(
                "SD2.0 视频任务查询成功",
                {
                    "id": result.get("id"),
                    "model": result.get("model"),
                    "status": result.get("status"),
                    "error": result.get("error"),
                    "content": result.get("content"),
                    "usage": result.get("usage"),
                    "created_at": result.get("created_at"),
                    "updated_at": result.get("updated_at"),
                    "duration": result.get("duration"),
                    "ratio": result.get("ratio"),
                    "resolution": result.get("resolution"),
                    "generate_audio": result.get("generate_audio"),
                    "execution_expires_after": result.get("execution_expires_after"),
                },
            )
        )
