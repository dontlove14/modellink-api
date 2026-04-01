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

from video_toolkit import build_submit_message, normalize_params, parse_int_value, parse_string_list, request_json, require_param


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class Sd15Reference2VideoTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """提交 SD1.5 参考图生视频任务。"""
        params = normalize_params(tool_parameters)
        api_key = require_param(params, "apiKey")
        reference_images = parse_string_list(require_param(params, "reference_images"))
        model = params.get("model") or "doubao-seedance-1-5-pro-251215"

        content: list[dict[str, Any]] = [
            {"type": "image_url", "image_url": {"url": url}, "role": "reference_image"}
            for url in reference_images
        ]

        payload: dict[str, Any] = {
            "model": model,
            "content": content,
            "return_last_frame": params.get("return_last_frame"),
            "generate_audio": params.get("generate_audio"),
            "resolution": params.get("resolution"),
            "ratio": params.get("ratio"),
            "duration": parse_int_value(params.get("duration")),
            "watermark": params.get("watermark"),
        }

        logger.info("[SD1.5 Reference2Video] submit task")
        result = request_json(
            method="POST",
            path="/seedance/v3/contents/generations/tasks",
            api_key=api_key,
            auth_type="bearer",
            json_body=payload,
        )

        yield self.create_json_message(
            build_submit_message(
                "SD1.5 参考图生视频任务已提交",
                {
                    "id": result.get("id"),
                    "model": model,
                    "reference_images": reference_images,
                    "resolution": params.get("resolution"),
                    "ratio": params.get("ratio"),
                    "duration": parse_int_value(params.get("duration")),
                    "generate_audio": params.get("generate_audio"),
                    "return_last_frame": params.get("return_last_frame"),
                },
            )
        )
