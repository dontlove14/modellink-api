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

from video_toolkit import build_submit_message, normalize_params, parse_int_value, request_json, require_param


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class ViduImage2VideoTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """提交 Vidu 首帧图生视频任务。"""
        params = normalize_params(tool_parameters)
        api_key = require_param(params, "apiKey")
        model = require_param(params, "model")
        image = require_param(params, "image")

        payload: dict[str, Any] = {
            "model": model,
            "images": [image],
            "prompt": params.get("prompt"),
            "audio": params.get("audio"),
            "audio_type": params.get("audio_type"),
            "voice_id": params.get("voice_id"),
            "is_rec": params.get("is_rec"),
            "bgm": params.get("bgm"),
            "duration": parse_int_value(params.get("duration")),
            "seed": parse_int_value(params.get("seed")),
            "resolution": params.get("resolution"),
            "movement_amplitude": params.get("movement_amplitude"),
            "payload": params.get("payload"),
            "off_peak": params.get("off_peak"),
            "watermark": params.get("watermark"),
            "wm_position": parse_int_value(params.get("wm_position")),
            "wm_url": params.get("wm_url"),
            "meta_data": params.get("meta_data"),
            "callback_url": params.get("callback_url"),
        }

        logger.info("[Vidu Image2Video] submit task")
        result = request_json(
            method="POST",
            path="/vidu/ent/v2/img2video",
            api_key=api_key,
            auth_type="token",
            json_body=payload,
        )

        yield self.create_json_message(
            build_submit_message(
                "Vidu 首帧图生视频任务已提交",
                {
                    "task_id": result.get("task_id"),
                    "state": result.get("state"),
                    "model": result.get("model"),
                    "images": result.get("images"),
                    "prompt": result.get("prompt"),
                    "duration": result.get("duration"),
                    "resolution": result.get("resolution"),
                    "credits": result.get("credits"),
                    "created_at": result.get("created_at"),
                },
            )
        )
