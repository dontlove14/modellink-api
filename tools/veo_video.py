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
    def _create_retry_session(self) -> requests.Session:
        """创建带重试策略的 HTTP Session

        说明:
            - 用于应对网络抖动、连接中断、服务端临时 5xx 等问题
            - multipart/form-data 的“断点续传上传”需要服务端协议支持，客户端侧仅做安全重试
        """
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        session.trust_env = False
        retry_strategy = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=frozenset(["POST"]),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Veo 视频生成工具

        参数:
            tool_parameters: 包含 apiKey、model、prompt 等参数

        行为:
            - 使用 https://api.modellink.online 提交生成任务

        异常:
            - 网络错误、HTTP 非 2xx 直接抛出异常
        """
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
            session = self._create_retry_session()
            response = session.post(api_url, headers=headers, files=files, timeout=(10, 120))

            logger.info(f"[Veo Video] 响应状态: {response.status_code}")

            if not response.ok:
                error_text = response.text
                logger.error(f"[Veo Video] 错误响应: {error_text}")
                response.raise_for_status()

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

        except requests.exceptions.RequestException as e:
            logger.error(f"[Veo Video] 网络异常: {str(e)}")
            raise Exception(str(e))
        except Exception as e:
            logger.error(f"[Veo Video] 异常: {str(e)}")
            raise
