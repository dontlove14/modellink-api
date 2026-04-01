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


class ViduVideoQueryTool(Tool):
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
                    "creations": result.get("creations"),
                },
            )
        )
