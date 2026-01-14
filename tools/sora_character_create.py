from collections.abc import Generator
from typing import Any
import logging

import requests
from dify_plugin import Tool
from dify_plugin.config.logger_format import plugin_logger_handler
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class SoraCharacterCreateTool(Tool):
    def _create_retry_session(self) -> requests.Session:
        """创建带重试策略的 HTTP Session

        说明:
            - 用于应对网络抖动、连接重置、服务端临时 5xx 等问题
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

    def _normalize_param(self, value: Any) -> Any:
        """规范化工具参数值

        规则:
            - 当参数值为字符串 'variable'（前端默认引用变量占位）时，视为未传入并置为 None
        """
        if isinstance(value, str) and value == "variable":
            return None
        return value

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """通过任务创建 Sora 角色（真人角色可用）

        参数:
            tool_parameters:
                - apiKey: 鉴权用 API Key
                - task_id: 用于创建角色的视频任务 ID（接口字段 taskId）
                - timestamps: 角色片段时间范围（接口字段 timestamps，格式如 1,3，跨度不大于 3 秒）

        行为:
            - 向固定主机 https://api.modellink.online 的 /v1/videos 提交角色创建任务
            - 请求体为 multipart/form-data，固定 model=sora-2-character，prompt=创建角色
            - 成功时返回标准化 JSON 消息（包含任务 id、状态等）
        """
        host = "https://api.modellink.online"

        api_key = self._normalize_param(tool_parameters.get("apiKey"))
        task_id = self._normalize_param(tool_parameters.get("task_id"))
        timestamps = self._normalize_param(tool_parameters.get("timestamps"))

        if not api_key or not task_id or not timestamps:
            raise ValueError("apiKey、task_id、timestamps 为必填参数")

        logger.info(f"[Sora Character Create] 开始创建角色，task_id: {task_id}, timestamps: {timestamps}")

        request_data = {
            "model": "sora-2-character",
            "prompt": "创建角色",
            "taskId": task_id,
            "timestamps": timestamps,
        }

        api_url = f"{host}/v1/videos"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            files = {k: (None, str(v)) for k, v in request_data.items() if v is not None}
            session = self._create_retry_session()
            response = session.post(api_url, headers=headers, files=files, timeout=(10, 120))

            logger.info(f"[Sora Character Create] 响应状态: {response.status_code}")

            if not response.ok:
                logger.error(f"[Sora Character Create] 错误响应: {response.text}")
                response.raise_for_status()

            result = response.json()
            logger.info(f"[Sora Character Create] 请求成功，任务 ID: {result.get('id')}")

            response_result = {
                "success": True,
                "message": "角色创建任务已提交",
                "data": {
                    "id": result.get("id"),
                    "object": result.get("object"),
                    "model": result.get("model"),
                    "status": result.get("status"),
                    "progress": result.get("progress"),
                    "created_at": result.get("created_at"),
                },
            }

            yield self.create_json_message(response_result)

        except requests.exceptions.RequestException as e:
            logger.error(f"[Sora Character Create] 网络异常: {str(e)}")
            raise Exception(str(e))
        except Exception as e:
            logger.error(f"[Sora Character Create] 异常: {str(e)}")
            raise
