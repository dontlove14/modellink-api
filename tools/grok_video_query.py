from collections.abc import Generator
from typing import Any
import logging
import os
import sys

import json
import requests
from dify_plugin import Tool
from dify_plugin.config.logger_format import plugin_logger_handler
from dify_plugin.entities.tool import ToolInvokeMessage

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from video_toolkit import HOST, build_headers, build_query_message, extract_error_message, normalize_params, require_param


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class GrokVideoQueryTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """查询 Grok 视频任务结果。"""
        params = normalize_params(tool_parameters)
        api_key = require_param(params, "apiKey")
        request_id = require_param(params, "request_id")

        def coerce_json_object(value: Any) -> dict[str, Any] | None:
            """将响应内容尽可能解析为 JSON 对象（dict）。"""
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    return None
                if text.startswith("not ok match:"):
                    text = text.split("not ok match:", 1)[1].strip()
                try:
                    parsed = json.loads(text)
                except Exception:
                    return None
                if isinstance(parsed, dict):
                    return parsed
                if isinstance(parsed, str):
                    nested = parsed.strip()
                    if nested.startswith("{") and nested.endswith("}"):
                        try:
                            parsed2 = json.loads(nested)
                        except Exception:
                            return None
                        if isinstance(parsed2, dict):
                            return parsed2
                return None
            return None
        
        def extract_task_status(value: Any) -> dict[str, Any] | None:
            """尽可能从错误包裹层中提取任务状态 JSON 对象。"""
            obj = coerce_json_object(value)
            if isinstance(obj, dict) and obj.get("status") in {"pending", "done", "failed", "expired"}:
                return obj
            if isinstance(obj, dict):
                msg = obj.get("message")
                nested = coerce_json_object(msg) if isinstance(msg, (str, dict)) else None
                if isinstance(nested, dict) and nested.get("status") in {"pending", "done", "failed", "expired"}:
                    return nested
            if isinstance(value, str):
                nested = coerce_json_object(value)
                if isinstance(nested, dict) and nested.get("status") in {"pending", "done", "failed", "expired"}:
                    return nested
            return None

        logger.info("[Grok Video Query] query task")
        session = requests.Session()
        session.trust_env = False
        response = session.get(
            url=f"{HOST}/xai-video/v1/videos/{request_id}",
            headers=build_headers(api_key, auth_type="bearer"),
            timeout=(10, 120),
        )
        raw_text = ""
        try:
            raw_text = response.text or ""
        except Exception:
            raw_text = ""

        logger.info(
            f"[Grok Video Query] response status_code={response.status_code} ok={response.ok} "
            f"content_type={(response.headers.get('Content-Type') or '').split(';', 1)[0].strip()}"
        )
        if raw_text:
            logger.info(f"[Grok Video Query] response body preview: {raw_text[:2000]}")

        result: dict[str, Any] | None = None
        try:
            parsed = response.json()
            result = coerce_json_object(parsed)
        except Exception:
            result = None
        if result is None and raw_text:
            result = coerce_json_object(raw_text)

        if not response.ok:
            status_obj = extract_task_status(result) or extract_task_status(raw_text)
            if status_obj is not None:
                result = status_obj
                logger.warning(
                    f"[Grok Video Query] non-2xx response but contains task status, treat as ok. "
                    f"status_code={response.status_code}"
                )
            else:
                raise Exception(
                    f"API 请求失败: {extract_error_message(result) or extract_error_message(raw_text) or response.reason}"
                )

        if not isinstance(result, dict):
            yield self.create_json_message(
                build_query_message(
                    "Grok 视频任务查询成功",
                    {
                        "request_id": request_id,
                        "status": None,
                        "progress": None,
                        "model": None,
                        "video": None,
                        "usage": None,
                        "raw": raw_text,
                    },
                )
            )
            return

        yield self.create_json_message(
            build_query_message(
                "Grok 视频任务查询成功",
                {
                    "request_id": request_id,
                    "status": result.get("status"),
                    "progress": result.get("progress"),
                    "model": result.get("model"),
                    "video": result.get("video"),
                    "usage": result.get("usage"),
                },
            )
        )
