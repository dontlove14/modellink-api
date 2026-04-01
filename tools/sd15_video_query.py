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


class Sd15VideoQueryTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """查询 Seedance 1.5 视频任务结果。"""
        params = normalize_params(tool_parameters)
        api_key = require_param(params, "apiKey")
        task_id = require_param(params, "id")

        logger.info("[SD1.5 Video Query] query task")
        result = request_json(
            method="GET",
            path=f"/seedance/v3/contents/generations/tasks/{task_id}",
            api_key=api_key,
            auth_type="bearer",
        )

        yield self.create_json_message(
            build_query_message(
                "SD1.5 视频任务查询成功",
                {
                    "id": result.get("id"),
                    "model": result.get("model"),
                    "status": result.get("status"),
                    "content": result.get("content"),
                    "usage": result.get("usage"),
                    "error": result.get("error"),
                    "created_at": result.get("created_at"),
                    "updated_at": result.get("updated_at"),
                    "resolution": result.get("resolution"),
                    "ratio": result.get("ratio"),
                    "duration": result.get("duration"),
                    "framespersecond": result.get("framespersecond"),
                    "execution_expires_after": result.get("execution_expires_after"),
                },
            )
        )
