from collections.abc import Generator
from typing import Any
import logging
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
import requests
from dify_plugin.config.logger_format import plugin_logger_handler

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)

class VeoVideoTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Veo Video Generation API 封装"""
        try:
            host = "https://api.modellink.online"
            apiKey = tool_parameters.get("apiKey")
            model = tool_parameters.get("model", "veo3.1")
            prompt = tool_parameters.get("prompt")
            seconds = tool_parameters.get("seconds", "8")
            input_reference = tool_parameters.get("input_reference")
            size = tool_parameters.get("size", "16x9")

            def process_param(value):
                if value == "variable":
                    return None
                return value

            apiKey = process_param(apiKey)
            model = process_param(model)
            prompt = process_param(prompt)
            seconds = process_param(seconds)
            input_reference = process_param(input_reference)
            size = process_param(size)

            logger.info(f"[Veo Video] 开始生成视频，模型: {model}")

            request_data = {
                "model": model,
                "prompt": prompt,
                "seconds": seconds,
            }
            if size:
                request_data["size"] = size

            def parse_input_refs(value) -> list[str]:
                if value is None:
                    return []
                if isinstance(value, list):
                    return [str(x).strip() for x in value if str(x).strip()]
                if isinstance(value, str):
                    s = value.strip()
                    if s.startswith("[") and s.endswith("]"):
                        import json
                        try:
                            arr = json.loads(s)
                            if isinstance(arr, list):
                                return [str(x).strip() for x in arr if str(x).strip()]
                        except Exception:
                            pass
                    return [x.strip() for x in s.split(",") if x.strip()]
                return []

            input_refs = parse_input_refs(input_reference)

            logger.info(f"[Veo Video] 请求数据: {request_data}, input_reference: {input_refs}")

            api_url = f"{host}/v1/videos"
            headers = {"Authorization": f"Bearer {apiKey}"}
            files = [(k, (None, v)) for k, v in request_data.items()]
            for url in input_refs:
                files.append(("input_reference", (None, url)))
            response = requests.post(api_url, headers=headers, files=files, timeout=60)

            logger.info(f"[Veo Video] 响应状态: {response.status_code}")

            if not response.ok:
                error_text = response.text
                logger.error(f"[Veo Video] 错误响应: {error_text}")
                raise Exception(f"API 请求失败: {response.status_code} - {error_text}")

            result = response.json()
            logger.info(f"[Veo Video] 请求成功，任务 ID: {result.get('id')}")

            response_result = {
                "success": True,
                "message": "视频生成任务已提交",
                "data": {
                    "task_id": result.get("id"),
                    "model": result.get("model"),
                    "status": result.get("status"),
                    "created": result.get("created"),
                    "expires_at": result.get("expires_at"),
                    "task_type": result.get("task_type"),
                },
            }

            yield self.create_json_message(response_result)

        except Exception as e:
            logger.error(f"[Veo Video] 异常: {str(e)}")
            yield self.create_json_message({
                "success": False,
                "message": str(e) or "视频生成失败",
                "error": str(e),
            })
