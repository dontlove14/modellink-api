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

from video_toolkit import build_submit_message, normalize_params, request_json, require_param


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class GrokVideoEditTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """提交 Grok 视频编辑任务。"""
        params = normalize_params(tool_parameters)
        api_key = require_param(params, "apiKey")
        prompt = require_param(params, "prompt")
        video_url = require_param(params, "video_url")
        model = params.get("model") or "grok-imagine-video"

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "video": {"url": video_url},
        }

        logger.info("[Grok Video Edit] submit task")
        result = request_json(
            method="POST",
            path="/xai-video/v1/videos/edits",
            api_key=api_key,
            auth_type="bearer",
            json_body=payload,
        )

        yield self.create_json_message(
            build_submit_message(
                "Grok 视频编辑任务已提交",
                {"request_id": result.get("request_id"), "model": model, "prompt": prompt, "video_url": video_url},
            )
        )
