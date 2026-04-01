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


class Sd20VideoGenerateTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """提交 Seedance 2.0 视频生成任务。"""
        params = normalize_params(tool_parameters)
        api_key = require_param(params, "apiKey")
        model = params.get("model") or "doubao-seedance-2-0-260128"
        prompt = params.get("prompt")
        reference_images = parse_string_list(params.get("reference_images"))
        reference_videos = parse_string_list(params.get("reference_videos"))
        reference_audios = parse_string_list(params.get("reference_audios"))

        content: list[dict[str, Any]] = []
        if prompt:
            content.append({"type": "text", "text": prompt})
        content.extend(
            {"type": "image_url", "image_url": {"url": url}, "role": "reference_image"} for url in reference_images
        )
        content.extend(
            {"type": "video_url", "video_url": {"url": url}, "role": "reference_video"} for url in reference_videos
        )
        content.extend(
            {"type": "audio_url", "audio_url": {"url": url}, "role": "reference_audio"} for url in reference_audios
        )

        if not content:
            raise ValueError("prompt、reference_images、reference_videos、reference_audios 至少需要提供一个")

        payload: dict[str, Any] = {
            "model": model,
            "content": content,
            "generate_audio": params.get("generate_audio"),
            "ratio": params.get("ratio"),
            "duration": parse_int_value(params.get("duration")),
            "resolution": params.get("resolution"),
            "watermark": params.get("watermark"),
            "return_last_frame": params.get("return_last_frame"),
        }

        logger.info("[SD2.0 Video Generate] submit task")
        result = request_json(
            method="POST",
            path="/sd2/api/v1/doubao/create",
            api_key=api_key,
            auth_type="bearer",
            json_body=payload,
        )

        yield self.create_json_message(
            build_submit_message(
                "SD2.0 视频生成任务已提交",
                {
                    "id": result.get("id"),
                    "model": model,
                    "prompt": prompt,
                    "reference_images": reference_images,
                    "reference_videos": reference_videos,
                    "reference_audios": reference_audios,
                    "ratio": params.get("ratio"),
                    "duration": parse_int_value(params.get("duration")),
                    "resolution": params.get("resolution"),
                    "generate_audio": params.get("generate_audio"),
                    "return_last_frame": params.get("return_last_frame"),
                },
            )
        )
