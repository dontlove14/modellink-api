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


class GrokVideoGenerateTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """提交 Grok 视频生成任务。"""
        params = normalize_params(tool_parameters)
        api_key = require_param(params, "apiKey")
        prompt = require_param(params, "prompt")
        model = params.get("model") or "grok-imagine-video"
        duration = require_param(params, "duration")
        aspect_ratio = require_param(params, "aspect_ratio")
        resolution = require_param(params, "resolution")
        image_url = params.get("image_url")
        reference_images = parse_string_list(params.get("reference_images"))

        if image_url and reference_images:
            raise ValueError("image_url 和 reference_images 不能同时传入")

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "duration": parse_int_value(duration),
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        }
        if image_url:
            payload["image"] = {"url": image_url}
        if reference_images:
            payload["reference_images"] = [{"url": url} for url in reference_images]

        logger.info("[Grok Video Generate] submit task")
        result = request_json(
            method="POST",
            path="/xai-video/v1/videos/generations",
            api_key=api_key,
            auth_type="bearer",
            json_body=payload,
        )

        yield self.create_json_message(
            build_submit_message(
                "Grok 视频生成任务已提交",
                {
                    "request_id": result.get("request_id"),
                    "model": model,
                    "prompt": prompt,
                    "duration": parse_int_value(duration),
                    "aspect_ratio": aspect_ratio,
                    "resolution": resolution,
                    "image_url": image_url,
                    "reference_images": reference_images,
                },
            )
        )
